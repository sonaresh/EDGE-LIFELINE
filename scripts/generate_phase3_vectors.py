"""Generate deterministic, synthetic-only Phase 3 interoperability vectors."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from edge_lifeline.formal.authority import (
    ApprovalLevel,
    AuthorityEnvelope,
    Budgets,
    ImpactClass,
    ReconciliationClass,
    SecurityPosture,
    TimeWindow,
)
from edge_lifeline.formal.time_bounds import TrustedTimeInterval
from edge_lifeline.proof.artifact import ArtifactType, ProofClaims
from edge_lifeline.proof.codec import sha256_hex
from edge_lifeline.proof.issuer import AuthorityIssuer
from edge_lifeline.proof.verifier import VerificationContext


def _envelope() -> AuthorityEnvelope:
    return AuthorityEnvelope(
        actions=frozenset({"monitor", "record"}),
        resources=frozenset({"patient-index", "event-ledger"}),
        sites=frozenset({"edge-a"}),
        time_window=TimeWindow(1_000, 61_000),
        max_lease_horizon_ms=60_000,
        max_data_age_ms=10_000,
        min_sensor_confidence_per_mille=800,
        budgets=Budgets(5_000, 10_000, 20_000, 30_000, 40_000, 20),
        max_impact=ImpactClass.REVERSIBLE_DIGITAL,
        max_financial_exposure_cents=10_000,
        min_approval=ApprovalLevel.SINGLE_LOCAL,
        min_security_posture=SecurityPosture.HARDENED,
        max_identity_cache_age_ms=3_600_000,
        max_revocation_staleness_ms=600_000,
        delegation_depth_remaining=2,
        reconciliation_classes=frozenset(
            {ReconciliationClass.COMMUTATIVE, ReconciliationClass.COMPENSATABLE}
        ),
        schema_version="authority-v1",
        policy_hash="a" * 64,
        mvsg_hash="b" * 64,
        verifier_profile_hash="c" * 64,
        isolation_epoch="epoch-vector-1",
    )


def _context(envelope: AuthorityEnvelope, evidence: dict[str, bytes]) -> VerificationContext:
    return VerificationContext(
        edge_identity="edge-a",
        isolation_epoch="epoch-vector-1",
        trusted_time=TrustedTimeInterval(2_000, 2_020),
        action="monitor",
        resource="patient-index",
        policy_version="policy-v1",
        policy_hash=envelope.policy_hash,
        mvsg_hash=envelope.mvsg_hash,
        verifier_profile_hash=envelope.verifier_profile_hash,
        data_age_ms=100,
        identity_cache_age_ms=200,
        revocation_staleness_ms=300,
        sensor_confidence_per_mille=950,
        approval_level=ApprovalLevel.THRESHOLD_LOCAL,
        security_posture=SecurityPosture.ATTESTED,
        requested_impact=ImpactClass.READ_ONLY,
        requested_financial_exposure_cents=0,
        expected_previous_event_hash="0" * 64,
        evidence={**evidence},
        context_attributes={"mode": "ISOLATED_BOUNDED", "site": "edge-a"},
    )


def _claims(
    artifact_type: ArtifactType,
    artifact_id: str,
    lease_id: str,
    issuer: str,
    envelope: AuthorityEnvelope,
    context: VerificationContext,
    parent: bytes | None,
    nonce: str,
) -> ProofClaims:
    return ProofClaims(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        lease_id=lease_id,
        parent_authority_ref=None if parent is None else sha256_hex(parent),
        issuer=issuer,
        edge_identity="edge-a",
        issued_at_ms=900,
        activation_not_before_ms=envelope.time_window.not_before_ms,
        expiration_ms=envelope.time_window.expires_at_ms,
        clock_uncertainty_allowance_ms=100,
        policy_version="policy-v1",
        envelope=envelope,
        evidence_hashes={key: sha256_hex(value) for key, value in context.evidence.items()},
        decision=(
            "CONTINUE_LOCALLY"
            if artifact_type is ArtifactType.DECISION_CERTIFICATE
            else "AUTHORIZE_ENVELOPE"
        ),
        justification_trace=("vector", "signature", "parent-bound", "context-bound"),
        nonce=nonce,
        replay_domain="epoch-vector-1:monitor",
        previous_event_hash="0" * 64,
        context_hash=context.binding_hash(),
    )


def build_vector() -> dict[str, object]:
    cloud_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    edge_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64)))
    evidence = {"sensor-attestation": b"synthetic-vector-evidence-v1"}
    root_envelope = _envelope()
    root_context = _context(root_envelope, evidence)
    root = AuthorityIssuer("cloud-authority", b"cloud-vector-key", cloud_key).issue(
        _claims(
            ArtifactType.AUTHORITY_LEASE,
            "vector-root",
            "vector-root-lease",
            "cloud-authority",
            root_envelope,
            root_context,
            None,
            "vector-root-nonce",
        )
    )
    child_envelope = replace(
        root_envelope,
        budgets=Budgets(4_000, 8_000, 16_000, 24_000, 32_000, 10),
        delegation_depth_remaining=1,
    )
    child_context = _context(child_envelope, evidence)
    edge_issuer = AuthorityIssuer("edge-a", b"edge-vector-key", edge_key)
    child = edge_issuer.issue(
        _claims(
            ArtifactType.AUTHORITY_LEASE,
            "vector-child",
            "vector-child-lease",
            "edge-a",
            child_envelope,
            child_context,
            root,
            "vector-child-nonce",
        )
    )
    decision_envelope = replace(
        child_envelope,
        actions=frozenset({"monitor"}),
        resources=frozenset({"patient-index"}),
        budgets=Budgets(10, 20, 30, 40, 50, 1),
        delegation_depth_remaining=0,
    )
    decision_context = _context(decision_envelope, evidence)
    decision = edge_issuer.issue(
        _claims(
            ArtifactType.DECISION_CERTIFICATE,
            "vector-decision",
            "vector-child-lease",
            "edge-a",
            decision_envelope,
            decision_context,
            child,
            "vector-decision-nonce",
        )
    )

    def public_hex(key: Ed25519PrivateKey) -> str:
        return (
            key.public_key()
            .public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
            .hex()
        )

    return {
        "schema_version": "edge-lifeline-phase3-vector-v1",
        "synthetic_nonclinical": True,
        "encoding": "tagged canonical CBOR COSE_Sign1; EdDSA (-8); Ed25519",
        "key_ids_hex": {
            "cloud": b"cloud-vector-key".hex(),
            "edge": b"edge-vector-key".hex(),
        },
        "public_keys_hex": {"cloud": public_hex(cloud_key), "edge": public_hex(edge_key)},
        "artifacts": {
            "root": {"sha256": sha256_hex(root), "encoded_hex": root.hex()},
            "child": {"sha256": sha256_hex(child), "encoded_hex": child.hex()},
            "decision": {"sha256": sha256_hex(decision), "encoded_hex": decision.hex()},
        },
        "expected_decision": "CONTINUE_LOCALLY",
        "expected_context_hash": decision_context.binding_hash(),
        "evidence_hex": {key: value.hex() for key, value in evidence.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_vector(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
