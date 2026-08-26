"""Minimal strict COSE_Sign1 profile using Ed25519/EdDSA."""

from __future__ import annotations

from dataclasses import dataclass

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from edge_lifeline.proof.codec import CanonicalCborError, canonical_dumps, strict_loads

COSE_SIGN1_TAG = 18
HEADER_ALGORITHM = 1
HEADER_KEY_ID = 4
EDDSA = -8


class CoseVerificationError(ValueError):
    """Raised when a COSE artifact violates the strict verifier profile."""


@dataclass(frozen=True, slots=True)
class CoseSign1:
    key_id: bytes
    payload: bytes
    signature: bytes
    protected: bytes
    encoded: bytes


def _signature_structure(protected: bytes, payload: bytes) -> bytes:
    return canonical_dumps(["Signature1", protected, b"", payload])


def sign1(payload: bytes, *, key_id: bytes, private_key: Ed25519PrivateKey) -> bytes:
    if not key_id or len(key_id) > 64:
        raise ValueError("COSE key identifier must contain 1..64 bytes")
    protected = canonical_dumps({HEADER_ALGORITHM: EDDSA, HEADER_KEY_ID: key_id})
    signature = private_key.sign(_signature_structure(protected, payload))
    return canonical_dumps(cbor2.CBORTag(COSE_SIGN1_TAG, [protected, {}, payload, signature]))


def parse_sign1(encoded: bytes) -> CoseSign1:
    try:
        tagged = strict_loads(encoded)
    except CanonicalCborError as error:
        raise CoseVerificationError(str(error)) from error
    if not isinstance(tagged, cbor2.CBORTag) or tagged.tag != COSE_SIGN1_TAG:
        raise CoseVerificationError("artifact is not tagged COSE_Sign1")
    if not isinstance(tagged.value, list) or len(tagged.value) != 4:
        raise CoseVerificationError("COSE_Sign1 must contain four elements")
    protected, unprotected, payload, signature = tagged.value
    if not isinstance(protected, bytes) or not isinstance(payload, bytes):
        raise CoseVerificationError("protected header and payload must be byte strings")
    if unprotected != {}:
        raise CoseVerificationError("unprotected headers are forbidden by this profile")
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise CoseVerificationError("Ed25519 signature must be 64 bytes")
    try:
        headers = strict_loads(protected)
    except CanonicalCborError as error:
        raise CoseVerificationError("protected header is not canonical") from error
    if not isinstance(headers, dict) or set(headers) != {HEADER_ALGORITHM, HEADER_KEY_ID}:
        raise CoseVerificationError("protected headers must contain only alg and kid")
    if headers[HEADER_ALGORITHM] != EDDSA:
        raise CoseVerificationError("COSE algorithm must be EdDSA")
    key_id = headers[HEADER_KEY_ID]
    if not isinstance(key_id, bytes) or not key_id or len(key_id) > 64:
        raise CoseVerificationError("invalid COSE key identifier")
    return CoseSign1(key_id, payload, signature, protected, encoded)


def verify_sign1(encoded: bytes, public_key: Ed25519PublicKey) -> CoseSign1:
    artifact = parse_sign1(encoded)
    try:
        public_key.verify(
            artifact.signature,
            _signature_structure(artifact.protected, artifact.payload),
        )
    except InvalidSignature as error:
        raise CoseVerificationError("invalid Ed25519 signature") from error
    return artifact
