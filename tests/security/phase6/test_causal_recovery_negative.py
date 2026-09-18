from __future__ import annotations

import pytest

from edge_lifeline.ledger.dag import DAGImportResult, validate_event_dag
from edge_lifeline.ledger.model import EventClass
from edge_lifeline.proof.codec import canonical_dumps, strict_loads
from edge_lifeline.proof.cose import sign1
from edge_lifeline.reconcile.engine import ReconciliationEngine
from edge_lifeline.reconcile.model import EventDisposition
from tests.phase6_helpers import (
    DECISION_HASH,
    EDGE_A_PRIVATE,
    EPOCH,
    KEYS,
    LEASE_HASH,
    PERMITTED,
    REGISTERED,
    child,
    make_event,
    sign_event,
)


def _validate(events: list[bytes]) -> DAGImportResult:
    return validate_event_dag(
        events,
        existing={},
        keys=KEYS,
        expected_epoch=EPOCH,
        valid_lease_hashes=frozenset({LEASE_HASH}),
        valid_decision_hashes=frozenset({DECISION_HASH}),
        registered_classes=REGISTERED,
        permitted_classes=PERMITTED,
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("isolation_epoch", "connected-epoch", "different isolation epoch"),
        ("lease_hash", "9" * 64, "unverified authority lease"),
        ("decision_certificate_hash", "8" * 64, "unverified decision certificate"),
        ("event_class", EventClass.COMMUTATIVE.value, "registered schema class"),
    ],
)
def test_authorized_key_cannot_import_false_claims(field: str, value: object, reason: str) -> None:
    payload = make_event().to_obj()
    payload[field] = value
    encoded = sign1(
        canonical_dumps(payload),
        key_id=b"edge-a-key",
        private_key=EDGE_A_PRIVATE,
    )
    result = _validate([encoded])
    assert reason in next(iter(result.quarantined.values()))[0]


def test_unknown_signer_and_signature_mutation_are_quarantined() -> None:
    event = make_event()
    unknown = sign1(event.payload(), key_id=b"unknown", private_key=EDGE_A_PRIVATE)
    mutated = bytearray(sign_event(event))
    mutated[-1] ^= 0x80
    assert len(_validate([unknown]).quarantined) == 1
    assert len(_validate([bytes(mutated)]).quarantined) == 1


def test_gap_fork_and_parent_quarantine_do_not_partially_import() -> None:
    root = sign_event(make_event())
    left = sign_event(child(root, event_id="left", idempotency_key="left"))
    right = sign_event(child(root, event_id="right", idempotency_key="right"))
    result = _validate([right, root, left])
    assert len(result.accepted) == 1
    assert len(result.quarantined) == 2


def test_irreversible_effect_disposition_contains_no_dispatch_path() -> None:
    encoded = sign_event(
        make_event(
            event_class=EventClass.IRREVERSIBLE_PHYSICAL,
            event_kind="physical-effect",
            effect_id="effect-1",
        )
    )
    dag = _validate([encoded])
    plan = ReconciliationEngine().plan(
        episode_id="episode",
        isolation_epoch=EPOCH,
        dag=dag,
        existing={},
        recorded_effect_ids=frozenset({"effect-1"}),
    )
    assert plan.resolutions[0].disposition is EventDisposition.DEDUPLICATE_EFFECT_NO_REPLAY
    assert plan.effect_replay_count == 0
    assert b"DISPATCH" not in plan.payload()


def test_noncanonical_event_payload_is_quarantined() -> None:
    payload = make_event().payload()
    value = strict_loads(payload)
    noncanonical = canonical_dumps(value) + b"\x00"
    encoded = sign1(noncanonical, key_id=b"edge-a-key", private_key=EDGE_A_PRIVATE)
    assert len(_validate([encoded]).quarantined) == 1


def test_claiming_s5_is_rejected_even_with_valid_signature() -> None:
    payload = make_event().to_obj()
    payload["event_class"] = EventClass.INVALID_OR_MALICIOUS.value
    payload["event_kind"] = "malicious"
    encoded = sign1(
        canonical_dumps(payload),
        key_id=b"edge-a-key",
        private_key=EDGE_A_PRIVATE,
    )
    result = validate_event_dag(
        [encoded],
        existing={},
        keys=KEYS,
        expected_epoch=EPOCH,
        valid_lease_hashes=frozenset({LEASE_HASH}),
        valid_decision_hashes=frozenset({DECISION_HASH}),
        registered_classes={**REGISTERED, "malicious": EventClass.INVALID_OR_MALICIOUS},
        permitted_classes=PERMITTED | {EventClass.INVALID_OR_MALICIOUS},
    )
    assert len(result.quarantined) == 1
