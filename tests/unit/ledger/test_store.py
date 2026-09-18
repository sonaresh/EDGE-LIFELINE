from __future__ import annotations

from pathlib import Path

import pytest

from edge_lifeline.ledger.model import EventClass, VerifiedEvent, verify_event
from edge_lifeline.ledger.store import CausalLedger, LedgerError
from tests.phase6_helpers import (
    DECISION_HASH,
    EPOCH,
    KEYS,
    LEASE_HASH,
    PERMITTED,
    REGISTERED,
    child,
    make_event,
    sign_event,
)


def _verified(encoded: bytes) -> VerifiedEvent:
    return verify_event(
        encoded,
        keys=KEYS,
        expected_epoch=EPOCH,
        valid_lease_hashes=frozenset({LEASE_HASH}),
        valid_decision_hashes=frozenset({DECISION_HASH}),
        registered_classes=REGISTERED,
        permitted_classes=PERMITTED,
    )


def test_append_only_chain_persists_across_restart(tmp_path: Path) -> None:
    root_encoded = sign_event(make_event())
    child_encoded = sign_event(child(root_encoded))
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    ledger.append_verified((_verified(root_encoded), _verified(child_encoded)))
    assert len(CausalLedger(tmp_path / "ledger.sqlite").event_hashes()) == 2


def test_event_replay_is_rejected(tmp_path: Path) -> None:
    event = _verified(sign_event(make_event()))
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    ledger.append_verified((event,))
    with pytest.raises(LedgerError, match="replay"):
        ledger.append_verified((event,))


def test_sequence_fork_is_rejected_atomically(tmp_path: Path) -> None:
    root_encoded = sign_event(make_event())
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    ledger.append_verified((_verified(root_encoded),))
    left = _verified(sign_event(child(root_encoded, event_id="left", idempotency_key="left")))
    right = _verified(sign_event(child(root_encoded, event_id="right", idempotency_key="right")))
    ledger.append_verified((left,))
    with pytest.raises(LedgerError, match="fork"):
        ledger.append_verified((right,))
    assert len(ledger.event_hashes()) == 2


def test_irreversible_effect_is_recorded_once_never_dispatched(tmp_path: Path) -> None:
    event = _verified(
        sign_event(
            make_event(
                event_class=EventClass.IRREVERSIBLE_PHYSICAL,
                event_kind="physical-effect",
                effect_id="physical-1",
            )
        )
    )
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    ledger.append_verified((event,))
    assert ledger.irreversible_effect_ids() == frozenset({"physical-1"})


def test_missing_previous_event_rolls_back_transaction(tmp_path: Path) -> None:
    event = make_event(sequence=1, previous="a" * 64, vector_clock={"edge-a": 2})
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    with pytest.raises(LedgerError, match="not durably present"):
        ledger.append_verified((_verified(sign_event(event)),))
    assert ledger.event_hashes() == ()


def test_child_before_parent_is_rejected_atomically(tmp_path: Path) -> None:
    root_encoded = sign_event(make_event())
    child_encoded = sign_event(child(root_encoded))
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    with pytest.raises(LedgerError, match="causal order"):
        ledger.append_verified((_verified(child_encoded), _verified(root_encoded)))
    assert ledger.event_hashes() == ()


def test_quarantine_and_signed_artifacts_are_append_only(tmp_path: Path) -> None:
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    ledger.record_quarantine({"a" * 64: ("BAD_SIGNATURE",)})
    ledger.persist_receipt("b" * 64, b"receipt")
    ledger.persist_checkpoint("c" * 64, b"checkpoint")
    with pytest.raises(LedgerError, match="replay"):
        ledger.persist_receipt("b" * 64, b"other")


def test_unsupported_signed_artifact_table_is_rejected(tmp_path: Path) -> None:
    ledger = CausalLedger(tmp_path / "ledger.sqlite")
    with pytest.raises(LedgerError, match="unsupported"):
        ledger._persist_signed("bad", "bad", "a" * 64, b"value")
