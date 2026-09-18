from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from edge_lifeline.ledger import CausalLedger, validate_event_dag
from edge_lifeline.ledger.model import EventClass
from edge_lifeline.proof.codec import canonical_dumps, sha256_hex
from edge_lifeline.reconcile import ReconciliationEngine, RecoverySigner
from edge_lifeline.reconcile.model import LedgerCheckpoint, ReconciliationReceipt
from tests.phase6_helpers import (
    DECISION_HASH,
    EPOCH,
    KEYS,
    LEASE_HASH,
    PERMITTED,
    REGISTERED,
    make_event,
    sign_event,
)


def test_reconnect_validates_plans_persists_and_requires_fresh_lease(tmp_path: Path) -> None:
    observation = sign_event(make_event(edge="edge-a", conflict_key="telemetry:ward-a"))
    physical = sign_event(
        make_event(
            edge="edge-b",
            event_class=EventClass.IRREVERSIBLE_PHYSICAL,
            event_kind="physical-effect",
            conflict_key="actuator:door-1",
            effect_id="door-command-1",
        )
    )
    dag = validate_event_dag(
        [physical, observation],
        existing={},
        keys=KEYS,
        expected_epoch=EPOCH,
        valid_lease_hashes=frozenset({LEASE_HASH}),
        valid_decision_hashes=frozenset({DECISION_HASH}),
        registered_classes=REGISTERED,
        permitted_classes=PERMITTED,
    )
    assert not dag.quarantined
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    plan = ReconciliationEngine().plan(
        episode_id="recovery-1",
        isolation_epoch=EPOCH,
        dag=dag,
        existing={},
    )
    ledger.append_verified(dag.accepted)
    history_root = sha256_hex(canonical_dumps(list(ledger.event_hashes())))
    checkpoint = LedgerCheckpoint(
        checkpoint_id="checkpoint-1",
        witness_identity="cloud-reconciler",
        issued_at_ms=20_000,
        isolation_epoch=EPOCH,
        frontier=dag.frontier,
        accepted_history_root=history_root,
        prior_checkpoint_hash=None,
    )
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(65, 97)))
    signer = RecoverySigner("cloud-reconciler", b"reconciler", key)
    checkpoint_encoded = signer.issue(checkpoint)
    checkpoint_hash = sha256_hex(checkpoint_encoded)
    receipt = ReconciliationReceipt(
        receipt_id="receipt-1",
        reconciler_identity="cloud-reconciler",
        issued_at_ms=20_001,
        plan_digest=plan.digest,
        checkpoint_hash=checkpoint_hash,
        accepted_event_hashes=ledger.event_hashes(),
        quarantined_event_hashes=(),
    )
    receipt_encoded = signer.issue(receipt)
    ledger.persist_checkpoint(checkpoint_hash, checkpoint_encoded)
    ledger.persist_receipt(sha256_hex(receipt_encoded), receipt_encoded)
    assert ledger.irreversible_effect_ids() == frozenset({"door-command-1"})
    assert plan.effect_replay_count == 0
    assert plan.authority_restored is False
    assert receipt.fresh_connected_epoch_lease_required is True


def test_invalid_event_subtree_never_mutates_authoritative_ledger(tmp_path: Path) -> None:
    invalid = bytearray(sign_event(make_event()))
    invalid[-1] ^= 1
    dag = validate_event_dag(
        [bytes(invalid)],
        existing={},
        keys=KEYS,
        expected_epoch=EPOCH,
        valid_lease_hashes=frozenset({LEASE_HASH}),
        valid_decision_hashes=frozenset({DECISION_HASH}),
        registered_classes=REGISTERED,
        permitted_classes=PERMITTED,
    )
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    ledger.record_quarantine(dict(dag.quarantined))
    ledger.append_verified(dag.accepted)
    assert ledger.event_hashes() == ()
