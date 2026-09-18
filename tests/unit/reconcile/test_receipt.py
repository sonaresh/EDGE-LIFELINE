from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from edge_lifeline.reconcile.model import (
    EventDisposition,
    LedgerCheckpoint,
    ReconciliationPlan,
    ReconciliationReceipt,
    Resolution,
)
from edge_lifeline.reconcile.receipt import RecoverySigner, verify_recovery_artifact

PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes(range(65, 97)))
SIGNER = RecoverySigner("cloud-reconciler", b"reconciler-key", PRIVATE)


def checkpoint() -> LedgerCheckpoint:
    return LedgerCheckpoint(
        checkpoint_id="checkpoint-1",
        witness_identity="cloud-reconciler",
        issued_at_ms=10_000,
        isolation_epoch="epoch-phase6",
        frontier=("a" * 64,),
        accepted_history_root="b" * 64,
        prior_checkpoint_hash=None,
    )


def receipt() -> ReconciliationReceipt:
    return ReconciliationReceipt(
        receipt_id="receipt-1",
        reconciler_identity="cloud-reconciler",
        issued_at_ms=10_001,
        plan_digest="c" * 64,
        checkpoint_hash="d" * 64,
        accepted_event_hashes=("a" * 64,),
        quarantined_event_hashes=("e" * 64,),
    )


@pytest.mark.parametrize("payload", [checkpoint(), receipt()])
def test_signed_recovery_artifact_round_trip(
    payload: LedgerCheckpoint | ReconciliationReceipt,
) -> None:
    encoded = SIGNER.issue(payload)
    verified = verify_recovery_artifact(
        encoded,
        public_key=PRIVATE.public_key(),
        expected_key_id=b"reconciler-key",
        payload_type=type(payload),
        expected_identity="cloud-reconciler",
    )
    assert verified.payload == payload
    assert len(verified.artifact_hash) == 64


def test_wrong_key_id_or_identity_is_rejected() -> None:
    encoded = SIGNER.issue(receipt())
    with pytest.raises(ValueError, match="key identifier"):
        verify_recovery_artifact(
            encoded,
            public_key=PRIVATE.public_key(),
            expected_key_id=b"wrong",
            payload_type=ReconciliationReceipt,
            expected_identity="cloud-reconciler",
        )
    with pytest.raises(ValueError, match="identity mismatch"):
        verify_recovery_artifact(
            encoded,
            public_key=PRIVATE.public_key(),
            expected_key_id=b"reconciler-key",
            payload_type=ReconciliationReceipt,
            expected_identity="other",
        )


def test_signer_rejects_claimed_identity() -> None:
    with pytest.raises(ValueError, match="does not match"):
        SIGNER.issue(replace(receipt(), reconciler_identity="other"))


@pytest.mark.parametrize(
    "changes",
    [
        {"authority_restored": True},
        {"fresh_connected_epoch_lease_required": False},
        {"effect_replay_count": 1},
    ],
)
def test_receipt_cannot_grant_authority_or_hide_replay(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(receipt(), **changes)


def test_plan_cannot_grant_authority_or_replay_effects() -> None:
    with pytest.raises(ValueError, match="restore authority"):
        ReconciliationPlan("episode", "epoch", (), (), authority_restored=True)
    with pytest.raises(ValueError, match="replay"):
        ReconciliationPlan("episode", "epoch", (), (), effect_replay_count=1)


def test_plan_and_receipt_reject_malformed_or_duplicate_event_hashes() -> None:
    with pytest.raises(ValueError, match="event hash"):
        Resolution("bad", EventDisposition.QUARANTINE, "reason")
    with pytest.raises(ValueError, match="event hashes"):
        replace(receipt(), accepted_event_hashes=("a" * 64, "a" * 64))
    left = Resolution("b" * 64, EventDisposition.QUARANTINE, "left")
    right = Resolution("a" * 64, EventDisposition.QUARANTINE, "right")
    with pytest.raises(ValueError, match="deterministic"):
        ReconciliationPlan("episode", "epoch", (), (left, right))


def test_checkpoint_rejects_invalid_hash_and_empty_frontier() -> None:
    with pytest.raises(ValueError, match="nonempty frontier"):
        replace(checkpoint(), frontier=())
    with pytest.raises(ValueError, match="SHA-256"):
        replace(checkpoint(), accepted_history_root="bad")
