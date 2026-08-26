from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import cbor2
import pytest
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
from edge_lifeline.proof.codec import canonical_dumps, sha256_hex, strict_loads
from edge_lifeline.proof.cose import COSE_SIGN1_TAG, CoseVerificationError, parse_sign1
from edge_lifeline.proof.issuer import AuthorityIssuer
from edge_lifeline.proof.store import DurableProofStore, ProofStoreError
from edge_lifeline.proof.verifier import (
    EdgeProofVerifier,
    ProofVerificationError,
    TrustedSigner,
    VerificationContext,
    VerifiedProof,
)


def _keys() -> tuple[Ed25519PrivateKey, Ed25519PrivateKey]:
    return (
        Ed25519PrivateKey.from_private_bytes(bytes(range(32))),
        Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64))),
    )


def _context(envelope: AuthorityEnvelope, evidence: dict[str, bytes]) -> VerificationContext:
    return VerificationContext(
        edge_identity="edge-a",
        isolation_epoch=envelope.isolation_epoch,
        trusted_time=TrustedTimeInterval(2_000, 2_100),
        action="monitor",
        resource="patient-index",
        policy_version="policy-v1",
        policy_hash=envelope.policy_hash,
        mvsg_hash=envelope.mvsg_hash,
        verifier_profile_hash=envelope.verifier_profile_hash,
        data_age_ms=500,
        identity_cache_age_ms=500,
        revocation_staleness_ms=500,
        sensor_confidence_per_mille=900,
        approval_level=envelope.min_approval,
        security_posture=envelope.min_security_posture,
        requested_impact=ImpactClass.READ_ONLY,
        requested_financial_exposure_cents=0,
        expected_previous_event_hash="0" * 64,
        evidence=evidence,
        context_attributes={"site": "edge-a", "mode": "ISOLATED_BOUNDED"},
    )


def _claims(
    *,
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
        clock_uncertainty_allowance_ms=1_000,
        policy_version="policy-v1",
        envelope=envelope,
        evidence_hashes={key: sha256_hex(value) for key, value in context.evidence.items()},
        decision=(
            "CONTINUE_LOCALLY"
            if artifact_type is ArtifactType.DECISION_CERTIFICATE
            else "AUTHORIZE_EMERGENCY_CAPABILITY"
            if artifact_type is ArtifactType.EMERGENCY_CAPABILITY
            else "AUTHORIZE_ENVELOPE"
        ),
        justification_trace=("signature-required", "parent-bounded", "context-bound"),
        nonce=nonce,
        replay_domain=f"{envelope.isolation_epoch}:monitor",
        previous_event_hash="0" * 64,
        context_hash=context.binding_hash(),
    )


def _chain(
    envelope_factory: Callable[..., AuthorityEnvelope],
    **root_changes: Any,
) -> tuple[
    EdgeProofVerifier,
    VerificationContext,
    bytes,
    bytes,
    bytes,
]:
    cloud_key, edge_key = _keys()
    evidence = {"sensor": b"authenticated-synthetic-sensor-evidence"}
    root_envelope = envelope_factory(
        policy_hash="a" * 64,
        mvsg_hash="b" * 64,
        verifier_profile_hash="c" * 64,
        **root_changes,
    )
    context = _context(root_envelope, evidence)
    cloud = AuthorityIssuer("cloud-authority", b"cloud-key-1", cloud_key)
    edge = AuthorityIssuer("edge-a", b"edge-key-1", edge_key)
    root = cloud.issue(
        _claims(
            artifact_type=ArtifactType.AUTHORITY_LEASE,
            artifact_id="root-artifact",
            lease_id="lease-root",
            issuer="cloud-authority",
            envelope=root_envelope,
            context=context,
            parent=None,
            nonce="root-nonce",
        )
    )
    child_envelope = replace(
        root_envelope,
        actions=frozenset({"monitor", "record"}),
        budgets=Budgets(8_000, 16_000, 24_000, 32_000, 40_000, 80),
        delegation_depth_remaining=1,
    )
    child_context = _context(child_envelope, evidence)
    child = edge.issue(
        _claims(
            artifact_type=ArtifactType.AUTHORITY_LEASE,
            artifact_id="child-artifact",
            lease_id="lease-child",
            issuer="edge-a",
            envelope=child_envelope,
            context=child_context,
            parent=root,
            nonce="child-nonce",
        )
    )
    decision_envelope = replace(
        child_envelope,
        actions=frozenset({"monitor"}),
        resources=frozenset({"patient-index"}),
        budgets=Budgets(100, 200, 300, 400, 500, 1),
        delegation_depth_remaining=0,
    )
    decision_context = _context(decision_envelope, evidence)
    decision = edge.issue(
        _claims(
            artifact_type=ArtifactType.DECISION_CERTIFICATE,
            artifact_id="decision-artifact",
            lease_id="lease-child",
            issuer="edge-a",
            envelope=decision_envelope,
            context=decision_context,
            parent=child,
            nonce="decision-nonce",
        )
    )
    verifier = EdgeProofVerifier(
        {
            b"cloud-key-1": TrustedSigner(
                "cloud-authority",
                cloud_key.public_key(),
                frozenset({ArtifactType.AUTHORITY_LEASE}),
                root_authority=True,
            ),
            b"edge-key-1": TrustedSigner(
                "edge-a",
                edge_key.public_key(),
                frozenset(
                    {
                        ArtifactType.AUTHORITY_LEASE,
                        ArtifactType.DECISION_CERTIFICATE,
                        ArtifactType.EMERGENCY_CAPABILITY,
                    }
                ),
            ),
        }
    )
    return verifier, decision_context, root, child, decision


@pytest.mark.security
def test_canonical_cose_sign1_is_deterministic_and_verifiable(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    verified = verifier.verify(decision, context=context, parent_chain=(child, root))
    assert verified.claims.artifact_type is ArtifactType.DECISION_CERTIFICATE
    assert verified.artifact_hash == sha256_hex(decision)
    tagged = strict_loads(decision)
    assert isinstance(tagged, cbor2.CBORTag) and tagged.tag == COSE_SIGN1_TAG
    assert canonical_dumps(tagged) == decision
    assert _chain(envelope_factory)[4] == decision


@pytest.mark.security
def test_modified_forged_and_noncanonical_artifacts_are_rejected(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    modified = decision[:-1] + bytes([decision[-1] ^ 1])
    with pytest.raises(ProofVerificationError, match="signature"):
        verifier.verify(modified, context=context, parent_chain=(child, root))
    with pytest.raises(ProofVerificationError, match=r"canonical|trailing"):
        verifier.verify(decision + b"\x00", context=context, parent_chain=(child, root))
    parsed = parse_sign1(decision)
    unknown_header = canonical_dumps({1: -8, 4: b"unknown-key"})
    forged = canonical_dumps(
        cbor2.CBORTag(18, [unknown_header, {}, parsed.payload, parsed.signature])
    )
    with pytest.raises(ProofVerificationError, match="unknown signing key"):
        verifier.verify(forged, context=context, parent_chain=(child, root))


@pytest.mark.security
def test_parent_hash_and_chain_termination_are_mandatory(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    with pytest.raises(ProofVerificationError, match="missing"):
        verifier.verify(decision, context=context, parent_chain=())
    with pytest.raises(ProofVerificationError, match="reference hash"):
        verifier.verify(decision, context=context, parent_chain=(root,))
    with pytest.raises(ProofVerificationError, match="terminate"):
        verifier.verify(decision, context=context, parent_chain=(child,))


@pytest.mark.security
def test_edge_signing_key_cannot_self_assert_root_authority(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    verifier, context, _, child, _ = _chain(envelope_factory)
    child_claims = verifier.decode_and_authenticate(child).claims
    forged_root_claims = replace(
        child_claims,
        artifact_id="edge-self-asserted-root",
        parent_authority_ref=None,
        nonce="edge-root-nonce",
    )
    forged_root = AuthorityIssuer("edge-a", b"edge-key-1", _keys()[1]).issue(forged_root_claims)
    child_context = _context(child_claims.envelope, dict(context.evidence))
    with pytest.raises(ProofVerificationError, match="trusted root authority"):
        verifier.verify(forged_root, context=child_context, parent_chain=())


@pytest.mark.security
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"clock_uncertainty_allowance_ms": 1_001}, "clock uncertainty allowance widened"),
        ({"policy_version": "policy-v2"}, "policy version changed"),
    ],
)
def test_claim_dimensions_outside_envelope_cannot_widen(
    envelope_factory: Callable[..., AuthorityEnvelope],
    change: dict[str, Any],
    message: str,
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    claims = verifier.decode_and_authenticate(decision).claims
    changed = replace(claims, artifact_id="claim-widening", nonce="claim-widening", **change)
    encoded = AuthorityIssuer("edge-a", b"edge-key-1", _keys()[1]).issue(changed)
    changed_context = replace(
        context,
        policy_version=changed.policy_version,
    )
    with pytest.raises(ProofVerificationError, match=message):
        verifier.verify(encoded, context=changed_context, parent_chain=(child, root))


@pytest.mark.security
def test_validly_signed_widened_child_is_rejected(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    verifier, context, root, child, _ = _chain(envelope_factory)
    edge_key = _keys()[1]
    child_claims = verifier.decode_and_authenticate(child).claims
    widened = replace(
        child_claims.envelope,
        actions=child_claims.envelope.actions | {"actuate"},
        delegation_depth_remaining=0,
    )
    widened_context = _context(widened, dict(context.evidence))
    artifact = AuthorityIssuer("edge-a", b"edge-key-1", edge_key).issue(
        _claims(
            artifact_type=ArtifactType.DECISION_CERTIFICATE,
            artifact_id="widened",
            lease_id="lease-child",
            issuer="edge-a",
            envelope=widened,
            context=widened_context,
            parent=child,
            nonce="widened-nonce",
        )
    )
    with pytest.raises(ProofVerificationError, match="exceeds an ancestor"):
        verifier.verify(artifact, context=widened_context, parent_chain=(child, root))


@pytest.mark.security
@pytest.mark.parametrize(
    ("root_changes", "widen"),
    [
        ({}, lambda value: replace(value, actions=value.actions | {"unsafe"})),
        ({}, lambda value: replace(value, resources=value.resources | {"cloud-admin"})),
        ({}, lambda value: replace(value, sites=value.sites | {"edge-b"})),
        (
            {},
            lambda value: replace(value, time_window=TimeWindow(1_001, 101_001)),
        ),
        ({}, lambda value: replace(value, max_lease_horizon_ms=100_001)),
        ({}, lambda value: replace(value, max_data_age_ms=60_001)),
        ({}, lambda value: replace(value, min_sensor_confidence_per_mille=699)),
        (
            {},
            lambda value: replace(
                value,
                budgets=replace(value.budgets, energy_mj=10_001),
            ),
        ),
        ({}, lambda value: replace(value, max_impact=ImpactClass.IRREVERSIBLE_PHYSICAL)),
        ({}, lambda value: replace(value, max_financial_exposure_cents=50_001)),
        (
            {"min_approval": ApprovalLevel.SINGLE_LOCAL},
            lambda value: replace(value, min_approval=ApprovalLevel.NONE),
        ),
        (
            {"min_security_posture": SecurityPosture.HARDENED},
            lambda value: replace(value, min_security_posture=SecurityPosture.BASIC),
        ),
        ({}, lambda value: replace(value, max_identity_cache_age_ms=86_400_001)),
        ({}, lambda value: replace(value, max_revocation_staleness_ms=3_600_001)),
        ({}, lambda value: replace(value, delegation_depth_remaining=2)),
        (
            {"reconciliation_classes": frozenset({ReconciliationClass.COMMUTATIVE})},
            lambda value: replace(
                value,
                reconciliation_classes=value.reconciliation_classes
                | {ReconciliationClass.INVALID_OR_MALICIOUS},
            ),
        ),
        ({}, lambda value: replace(value, policy_hash="d" * 64)),
        ({}, lambda value: replace(value, mvsg_hash="d" * 64)),
        ({}, lambda value: replace(value, verifier_profile_hash="d" * 64)),
        ({}, lambda value: replace(value, isolation_epoch="epoch-2")),
    ],
    ids=[
        "actions",
        "resources",
        "sites",
        "time-window",
        "lease-horizon",
        "data-age",
        "sensor-confidence",
        "budgets",
        "physical-impact",
        "financial-exposure",
        "approval",
        "security-posture",
        "identity-cache",
        "revocation-freshness",
        "delegation-depth",
        "reconciliation-class",
        "policy-hash",
        "mvsg-hash",
        "verifier-profile",
        "isolation-epoch",
    ],
)
def test_validly_signed_widening_is_rejected_for_every_authority_dimension(
    envelope_factory: Callable[..., AuthorityEnvelope],
    root_changes: dict[str, Any],
    widen: Callable[[AuthorityEnvelope], AuthorityEnvelope],
) -> None:
    verifier, context, root, child, _ = _chain(envelope_factory, **root_changes)
    child_claims = verifier.decode_and_authenticate(child).claims
    widened = widen(child_claims.envelope)
    widened_context = _context(widened, dict(context.evidence))
    artifact = AuthorityIssuer("edge-a", b"edge-key-1", _keys()[1]).issue(
        _claims(
            artifact_type=ArtifactType.DECISION_CERTIFICATE,
            artifact_id="dimension-widening",
            lease_id="lease-child",
            issuer="edge-a",
            envelope=widened,
            context=widened_context,
            parent=child,
            nonce="dimension-widening-nonce",
        )
    )
    with pytest.raises(
        ProofVerificationError,
        match=r"exceeds an ancestor|delegation depth|delegated authority depth",
    ):
        verifier.verify(artifact, context=widened_context, parent_chain=(child, root))


@pytest.mark.security
@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"trusted_time": TrustedTimeInterval(100_999, 101_000)}, "EXPIRED"),
        ({"data_age_ms": 100_000}, "DATA_STALE"),
        ({"identity_cache_age_ms": 100_000_000}, "IDENTITY_CACHE_STALE"),
        ({"revocation_staleness_ms": 9_000_000}, "REVOCATION_STATE_STALE"),
        ({"sensor_confidence_per_mille": 1}, "SENSOR_CONFIDENCE"),
        ({"isolation_epoch": "epoch-replayed"}, "ISOLATION_EPOCH_MISMATCH"),
    ],
)
def test_expired_stale_or_epoch_invalid_context_is_rejected(
    envelope_factory: Callable[..., AuthorityEnvelope],
    change: dict[str, Any],
    expected: str,
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    invalid = replace(context, **change)
    with pytest.raises(ProofVerificationError, match=expected):
        verifier.verify(decision, context=invalid, parent_chain=(child, root))


@pytest.mark.security
@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"edge_identity": "edge-b"}, "EDGE_IDENTITY_MISMATCH"),
        ({"trusted_time": TrustedTimeInterval(900, 999)}, "NOT_YET_VALID"),
        (
            {"trusted_time": TrustedTimeInterval(1_000, 4_001)},
            "CLOCK_UNCERTAINTY_EXCEEDED",
        ),
        ({"action": "actuate"}, "ACTION_NOT_PERMITTED"),
        ({"resource": "event-ledger"}, "RESOURCE_NOT_PERMITTED"),
        ({"policy_version": "policy-v2"}, "POLICY_MISMATCH"),
        ({"policy_hash": "f" * 64}, "POLICY_MISMATCH"),
        ({"mvsg_hash": "f" * 64}, "MVSG_MISMATCH"),
        ({"verifier_profile_hash": "f" * 64}, "VERIFIER_PROFILE_MISMATCH"),
        (
            {"requested_impact": ImpactClass.IRREVERSIBLE_PHYSICAL},
            "PHYSICAL_IMPACT_LIMIT_EXCEEDED",
        ),
        (
            {"requested_financial_exposure_cents": 50_001},
            "FINANCIAL_EXPOSURE_LIMIT_EXCEEDED",
        ),
        ({"evidence": {}}, "EVIDENCE_SET_MISMATCH"),
    ],
)
def test_every_bound_runtime_context_dimension_fails_safe(
    envelope_factory: Callable[..., AuthorityEnvelope],
    change: dict[str, Any],
    expected: str,
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    with pytest.raises(ProofVerificationError, match=expected):
        verifier.verify(
            decision,
            context=replace(context, **change),
            parent_chain=(child, root),
        )


@pytest.mark.security
def test_approval_and_security_requirements_fail_safe(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    verifier, context, root, child, decision = _chain(
        envelope_factory,
        min_approval=ApprovalLevel.THRESHOLD_LOCAL,
        min_security_posture=SecurityPosture.ATTESTED,
    )
    invalid = replace(
        context,
        approval_level=ApprovalLevel.SINGLE_LOCAL,
        security_posture=SecurityPosture.HARDENED,
    )
    with pytest.raises(
        ProofVerificationError,
        match=r"APPROVAL_INSUFFICIENT.*SECURITY_POSTURE_INSUFFICIENT",
    ):
        verifier.verify(decision, context=invalid, parent_chain=(child, root))


@pytest.mark.security
def test_evidence_bytes_and_context_binding_are_required(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    altered = replace(context, evidence={"sensor": b"corrupted"})
    with pytest.raises(ProofVerificationError, match="EVIDENCE_HASH_MISMATCH"):
        verifier.verify(decision, context=altered, parent_chain=(child, root))
    changed_context = replace(context, context_attributes={"site": "edge-b"})
    with pytest.raises(ProofVerificationError, match="CONTEXT_HASH_MISMATCH"):
        verifier.verify(decision, context=changed_context, parent_chain=(child, root))
    wrong_previous = replace(context, expected_previous_event_hash="f" * 64)
    with pytest.raises(ProofVerificationError, match="PREVIOUS_EVENT_HASH_MISMATCH"):
        verifier.verify(decision, context=wrong_previous, parent_chain=(child, root))


def _activate_child(
    store: DurableProofStore,
    verifier: EdgeProofVerifier,
    context: VerificationContext,
    root: bytes,
    child: bytes,
) -> None:
    child_envelope = verifier.decode_and_authenticate(child).claims.envelope
    child_context = _context(child_envelope, dict(context.evidence))
    store.activate_lease(verifier.verify(child, context=child_context, parent_chain=(root,)))


@pytest.mark.security
def test_durable_replay_budget_and_proof_before_effect(
    envelope_factory: Callable[..., AuthorityEnvelope], tmp_path: Path
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    verified = verifier.verify(decision, context=context, parent_chain=(child, root))
    store = DurableProofStore(tmp_path / "proofs.sqlite3")
    _activate_child(store, verifier, context, root, child)
    receipt = store.commit_decision(
        verified,
        cost=Budgets(100, 200, 300, 400, 500, 1),
        effect_id="effect-1",
        context=context,
    )
    assert receipt.status == "COMMITTED"
    assert store.nonce_consumed("epoch-1:monitor", "decision-nonce")
    assert (
        store.authorize_dispatch(
            artifact_hash=verified.artifact_hash,
            effect_id="effect-1",
        ).status
        == "DISPATCHED"
    )
    with pytest.raises(ProofStoreError, match=r"replay|duplicate"):
        store.commit_decision(
            verified,
            cost=Budgets(0, 0, 0, 0, 0, 0),
            effect_id="effect-2",
            context=context,
        )
    with pytest.raises(ProofStoreError, match="uniquely committed"):
        store.authorize_dispatch(artifact_hash="f" * 64, effect_id="not-registered")


@pytest.mark.security
def test_failed_atomic_transaction_consumes_nothing(
    envelope_factory: Callable[..., AuthorityEnvelope], tmp_path: Path
) -> None:
    import sqlite3

    verifier, context, root, child, decision = _chain(envelope_factory)
    verified = verifier.verify(decision, context=context, parent_chain=(child, root))
    database = tmp_path / "proofs.sqlite3"
    store = DurableProofStore(database)
    _activate_child(store, verifier, context, root, child)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER fail_certificate BEFORE INSERT ON certificates "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
    with pytest.raises(ProofStoreError, match="atomic proof transaction failed"):
        store.commit_decision(
            verified,
            cost=Budgets(100, 200, 300, 400, 500, 1),
            effect_id="effect-1",
            context=context,
        )
    assert not store.nonce_consumed("epoch-1:monitor", "decision-nonce")
    assert store.budget_usage("lease-child") == Budgets(0, 0, 0, 0, 0, 0)


@pytest.mark.security
def test_decision_requires_activated_parent_and_fresh_atomic_admission(
    envelope_factory: Callable[..., AuthorityEnvelope], tmp_path: Path
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    verified = verifier.verify(decision, context=context, parent_chain=(child, root))
    store = DurableProofStore(tmp_path / "proofs.sqlite3")
    with pytest.raises(ProofStoreError, match="not activated"):
        store.commit_decision(
            verified,
            cost=Budgets(100, 200, 300, 400, 500, 1),
            effect_id="effect-before-activation",
            context=context,
        )
    _activate_child(store, verifier, context, root, child)
    with pytest.raises(ProofStoreError, match="validity is unprovable"):
        store.commit_decision(
            verified,
            cost=Budgets(100, 200, 300, 400, 500, 1),
            effect_id="effect-after-expiration",
            context=replace(
                context,
                trusted_time=TrustedTimeInterval(100_999, 101_000),
            ),
        )
    assert not store.nonce_consumed("epoch-1:monitor", "decision-nonce")


@pytest.mark.security
def test_effect_cost_cannot_exceed_decision_certificate_budget(
    envelope_factory: Callable[..., AuthorityEnvelope], tmp_path: Path
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    verified = verifier.verify(decision, context=context, parent_chain=(child, root))
    store = DurableProofStore(tmp_path / "proofs.sqlite3")
    _activate_child(store, verifier, context, root, child)
    with pytest.raises(ProofStoreError, match="decision certificate budget"):
        store.commit_decision(
            verified,
            cost=Budgets(101, 0, 0, 0, 0, 0),
            effect_id="overstated-effect",
            context=context,
        )
    assert not store.nonce_consumed("epoch-1:monitor", "decision-nonce")


@pytest.mark.security
def test_concurrent_decisions_cannot_oversubscribe_activated_lease(
    envelope_factory: Callable[..., AuthorityEnvelope], tmp_path: Path
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    original = verifier.decode_and_authenticate(decision).claims
    large_budget = Budgets(5_000, 0, 0, 0, 0, 1)
    decision_envelope = replace(original.envelope, budgets=large_budget)
    issuer = AuthorityIssuer("edge-a", b"edge-key-1", _keys()[1])

    def signed(index: int) -> VerifiedProof:
        encoded = issuer.issue(
            replace(
                original,
                artifact_id=f"concurrent-{index}",
                nonce=f"concurrent-{index}",
                envelope=decision_envelope,
            )
        )
        return verifier.verify(encoded, context=context, parent_chain=(child, root))

    proofs = (signed(1), signed(2))
    database = tmp_path / "proofs.sqlite3"
    store = DurableProofStore(database)
    _activate_child(store, verifier, context, root, child)

    def admit(index: int) -> str:
        try:
            DurableProofStore(database).commit_decision(
                proofs[index],
                cost=large_budget,
                effect_id=f"effect-{index}",
                context=context,
            )
        except ProofStoreError as error:
            return str(error)
        return "COMMITTED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(admit, range(2)))
    assert sorted(results) == ["COMMITTED", "authority budget exceeded"]
    assert store.budget_usage("lease-child").energy_mj == 5_000


@pytest.mark.security
def test_financial_exposure_is_context_bound_and_cumulatively_limited(
    envelope_factory: Callable[..., AuthorityEnvelope], tmp_path: Path
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    original = verifier.decode_and_authenticate(decision).claims
    exposure_context = replace(context, requested_financial_exposure_cents=30_000)
    issuer = AuthorityIssuer("edge-a", b"edge-key-1", _keys()[1])

    def signed(index: int) -> VerifiedProof:
        encoded = issuer.issue(
            replace(
                original,
                artifact_id=f"financial-{index}",
                nonce=f"financial-{index}",
                context_hash=exposure_context.binding_hash(),
            )
        )
        return verifier.verify(encoded, context=exposure_context, parent_chain=(child, root))

    first, second = signed(1), signed(2)
    store = DurableProofStore(tmp_path / "proofs.sqlite3")
    _activate_child(store, verifier, context, root, child)
    store.commit_decision(
        first,
        cost=Budgets(0, 0, 0, 0, 0, 0),
        effect_id="financial-effect-1",
        context=exposure_context,
    )
    with pytest.raises(ProofStoreError, match="financial exposure exceeded"):
        store.commit_decision(
            second,
            cost=Budgets(0, 0, 0, 0, 0, 0),
            effect_id="financial-effect-2",
            context=exposure_context,
        )
    assert store.financial_exposure("lease-child") == 30_000
    assert not store.nonce_consumed("epoch-1:monitor", "financial-2")


@pytest.mark.security
def test_store_rejects_a_context_other_than_the_verified_context(
    envelope_factory: Callable[..., AuthorityEnvelope], tmp_path: Path
) -> None:
    verifier, context, root, child, decision = _chain(envelope_factory)
    verified = verifier.verify(decision, context=context, parent_chain=(child, root))
    store = DurableProofStore(tmp_path / "proofs.sqlite3")
    _activate_child(store, verifier, context, root, child)
    with pytest.raises(ProofStoreError, match="not bound"):
        store.commit_decision(
            verified,
            cost=Budgets(0, 0, 0, 0, 0, 0),
            effect_id="mismatched-context",
            context=replace(context, policy_version="policy-v2"),
        )


@pytest.mark.security
def test_authority_activation_is_one_shot(
    envelope_factory: Callable[..., AuthorityEnvelope], tmp_path: Path
) -> None:
    verifier, context, root, _, _ = _chain(envelope_factory)
    verified_root = verifier.verify(root, context=context, parent_chain=())
    store = DurableProofStore(tmp_path / "proofs.sqlite3")
    store.activate_lease(verified_root)
    with pytest.raises(ProofStoreError, match="replay"):
        store.activate_lease(verified_root)


@pytest.mark.security
def test_emergency_capability_is_bounded_explicit_and_usable_without_redelegation(
    envelope_factory: Callable[..., AuthorityEnvelope], tmp_path: Path
) -> None:
    verifier, context, root, child, _ = _chain(envelope_factory)
    edge = AuthorityIssuer("edge-a", b"edge-key-1", _keys()[1])
    child_claims = verifier.decode_and_authenticate(child).claims
    emergency_envelope = replace(
        child_claims.envelope,
        actions=frozenset({"monitor"}),
        resources=frozenset({"patient-index"}),
        budgets=Budgets(50, 100, 150, 200, 250, 1),
        max_impact=ImpactClass.READ_ONLY,
        max_financial_exposure_cents=0,
        min_approval=ApprovalLevel.THRESHOLD_LOCAL,
        min_security_posture=SecurityPosture.ATTESTED,
        delegation_depth_remaining=0,
    )
    emergency_context = _context(emergency_envelope, dict(context.evidence))
    emergency = edge.issue(
        _claims(
            artifact_type=ArtifactType.EMERGENCY_CAPABILITY,
            artifact_id="emergency-capability",
            lease_id="emergency-lease",
            issuer="edge-a",
            envelope=emergency_envelope,
            context=emergency_context,
            parent=child,
            nonce="emergency-nonce",
        )
    )
    verified_emergency = verifier.verify(
        emergency,
        context=emergency_context,
        parent_chain=(child, root),
    )
    decision_envelope = replace(
        emergency_envelope,
        budgets=Budgets(10, 20, 30, 40, 50, 1),
    )
    decision_context = _context(decision_envelope, dict(context.evidence))
    decision = edge.issue(
        _claims(
            artifact_type=ArtifactType.DECISION_CERTIFICATE,
            artifact_id="emergency-decision",
            lease_id="emergency-lease",
            issuer="edge-a",
            envelope=decision_envelope,
            context=decision_context,
            parent=emergency,
            nonce="emergency-decision-nonce",
        )
    )
    verified_decision = verifier.verify(
        decision,
        context=decision_context,
        parent_chain=(emergency, child, root),
    )
    store = DurableProofStore(tmp_path / "proofs.sqlite3")
    store.activate_lease(verified_emergency)
    receipt = store.commit_decision(
        verified_decision,
        cost=Budgets(10, 20, 30, 40, 50, 1),
        effect_id="emergency-read-only-effect",
        context=decision_context,
    )
    assert receipt.status == "COMMITTED"

    redelegated = edge.issue(
        _claims(
            artifact_type=ArtifactType.AUTHORITY_LEASE,
            artifact_id="forbidden-emergency-redelegation",
            lease_id="forbidden-child",
            issuer="edge-a",
            envelope=emergency_envelope,
            context=emergency_context,
            parent=emergency,
            nonce="forbidden-redelegation-nonce",
        )
    )
    with pytest.raises(ProofVerificationError, match="delegated authority depth"):
        verifier.verify(
            redelegated,
            context=emergency_context,
            parent_chain=(emergency, child, root),
        )


@pytest.mark.security
def test_cose_parser_rejects_unprotected_headers(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    _, _, _, _, decision = _chain(envelope_factory)
    parsed = parse_sign1(decision)
    invalid = canonical_dumps(
        cbor2.CBORTag(18, [parsed.protected, {5: b"mutable"}, parsed.payload, parsed.signature])
    )
    with pytest.raises(CoseVerificationError, match="unprotected"):
        parse_sign1(invalid)
