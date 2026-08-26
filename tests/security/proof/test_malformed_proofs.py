from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import cbor2
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from edge_lifeline.proof.artifact import ArtifactType, ProofClaims
from edge_lifeline.proof.codec import CanonicalCborError, canonical_dumps, strict_loads
from edge_lifeline.proof.cose import CoseVerificationError, parse_sign1, sign1
from edge_lifeline.proof.issuer import AuthorityIssuer
from edge_lifeline.proof.verifier import ProofVerificationError


def _decision() -> tuple[bytes, Ed25519PrivateKey, bytes]:
    vector = json.loads(Path("tests/vectors/phase3/proof-chain-v1.json").read_bytes())
    artifacts = vector["artifacts"]
    key_ids = vector["key_ids_hex"]
    assert isinstance(artifacts, dict) and isinstance(key_ids, dict)
    decision = bytes.fromhex(artifacts["decision"]["encoded_hex"])
    return (
        decision,
        Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64))),
        bytes.fromhex(key_ids["edge"]),
    )


def _resign_payload(change: dict[str, Any]) -> bytes:
    decision, private_key, key_id = _decision()
    payload = strict_loads(parse_sign1(decision).payload)
    assert isinstance(payload, dict)
    payload.update(change)
    return sign1(canonical_dumps(payload), key_id=key_id, private_key=private_key)


@pytest.mark.security
@pytest.mark.parametrize(
    ("encoded", "message"),
    [
        (b"\xff", "malformed CBOR"),
        (canonical_dumps([]), "not tagged"),
        (canonical_dumps(cbor2.CBORTag(17, [])), "not tagged"),
        (canonical_dumps(cbor2.CBORTag(18, [b"", {}, b""])), "four elements"),
        (
            canonical_dumps(cbor2.CBORTag(18, [{}, {}, b"payload", b"0" * 64])),
            "byte strings",
        ),
        (
            canonical_dumps(cbor2.CBORTag(18, [canonical_dumps({1: -8, 4: b"k"}), {}, b"p", b""])),
            "64 bytes",
        ),
        (
            canonical_dumps(cbor2.CBORTag(18, [b"\xff", {}, b"p", b"0" * 64])),
            "protected header",
        ),
        (
            canonical_dumps(cbor2.CBORTag(18, [canonical_dumps({1: -8}), {}, b"p", b"0" * 64])),
            "only alg and kid",
        ),
        (
            canonical_dumps(
                cbor2.CBORTag(
                    18,
                    [canonical_dumps({1: -7, 4: b"k"}), {}, b"p", b"0" * 64],
                )
            ),
            "must be EdDSA",
        ),
        (
            canonical_dumps(
                cbor2.CBORTag(
                    18,
                    [canonical_dumps({1: -8, 4: b""}), {}, b"p", b"0" * 64],
                )
            ),
            "key identifier",
        ),
    ],
)
def test_strict_cose_profile_rejects_malformed_structures(encoded: bytes, message: str) -> None:
    with pytest.raises(CoseVerificationError, match=message):
        parse_sign1(encoded)


@pytest.mark.security
def test_signer_rejects_invalid_key_identifiers() -> None:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    for key_id in (b"", b"x" * 65):
        with pytest.raises(ValueError, match="key identifier"):
            sign1(b"payload", key_id=key_id, private_key=private_key)


@pytest.mark.security
def test_strict_cbor_rejects_malformed_and_duplicate_set_encodings() -> None:
    with pytest.raises(CanonicalCborError, match="malformed"):
        strict_loads(b"\xff")
    decision, _, _ = _decision()
    payload = strict_loads(parse_sign1(decision).payload)
    assert isinstance(payload, dict)
    envelope = payload["authority_envelope"]
    envelope["actions"] = ["monitor", "monitor"]
    with pytest.raises(ValueError, match="invalid authority envelope"):
        ProofClaims.from_payload(canonical_dumps(payload))


@pytest.mark.security
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"artifact_family": "unknown"}, "unsupported proof artifact family"),
        ({"evidence_hashes": []}, "evidence or justification"),
        ({"justification_trace": {}}, "evidence or justification"),
        ({"permitted_actions": ["widened"]}, "redundant proof field"),
    ],
)
def test_validly_signed_malformed_claim_payloads_fail_closed(
    change: dict[str, Any], message: str
) -> None:
    encoded = _resign_payload(change)
    decision, private_key, key_id = _decision()
    parsed = parse_sign1(decision)
    issuer = AuthorityIssuer("edge-a", key_id, private_key)
    assert issuer.authority_reference(encoded)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from edge_lifeline.proof.verifier import EdgeProofVerifier, TrustedSigner

    verifier = EdgeProofVerifier(
        {
            key_id: TrustedSigner(
                "edge-a",
                Ed25519PublicKey.from_public_bytes(private_key.public_key().public_bytes_raw()),
                frozenset(ArtifactType),
            )
        }
    )
    assert parsed.payload
    with pytest.raises(ProofVerificationError, match=message):
        verifier.decode_and_authenticate(encoded)


@pytest.mark.security
def test_claim_constructor_rejects_semantically_invalid_values() -> None:
    decision, _, _ = _decision()
    claims = ProofClaims.from_payload(parse_sign1(decision).payload)
    invalid: list[tuple[dict[str, Any], str]] = [
        ({"artifact_id": ""}, "identifiers"),
        ({"issued_at_ms": -1}, "time bounds"),
        ({"activation_not_before_ms": claims.activation_not_before_ms + 1}, "activation"),
        ({"expiration_ms": claims.expiration_ms - 1}, "expiration"),
        (
            {"envelope": replace(claims.envelope, max_lease_horizon_ms=1)},
            "maximum lease horizon",
        ),
        ({"justification_trace": ()}, "justification"),
        ({"decision": "UNLIMITED_AUTONOMY"}, "unsupported consequential"),
        ({"evidence_hashes": {}}, "evidence hashes"),
        ({"previous_event_hash": "not-a-hash"}, "previous event hash"),
        ({"parent_authority_ref": None}, "parent-authority"),
    ]
    for change, message in invalid:
        with pytest.raises(ValueError, match=message):
            replace(claims, **change)
