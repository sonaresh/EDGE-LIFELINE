from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from edge_lifeline.ledger.model import CausalEvent, EventClass, EventSigner, verify_event
from edge_lifeline.proof.codec import canonical_dumps
from tests.phase6_helpers import (
    DECISION_HASH,
    EDGE_A_PRIVATE,
    EPOCH,
    KEYS,
    LEASE_HASH,
    PERMITTED,
    REGISTERED,
    make_event,
    sign_event,
)


def test_event_round_trip_and_signature_verification() -> None:
    event = make_event()
    encoded = sign_event(event)
    verified = verify_event(
        encoded,
        keys=KEYS,
        expected_epoch=EPOCH,
        valid_lease_hashes=frozenset({LEASE_HASH}),
        valid_decision_hashes=frozenset({DECISION_HASH}),
        registered_classes=REGISTERED,
        permitted_classes=PERMITTED,
    )
    assert verified.event == event
    assert CausalEvent.from_payload(event.payload()) == event
    assert len(verified.event_hash) == 64


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"event_id": ""}, "identifiers"),
        ({"sequence": -1}, "sequence"),
        ({"causal_parent_hashes": ("x",)}, "causal parents"),
        ({"vector_clock": {"edge-a": 2}}, "vector clock"),
        ({"lease_hash": "x"}, "lease hash"),
        ({"event_class": EventClass.INVALID_OR_MALICIOUS}, "not an issuable"),
    ],
)
def test_invalid_event_fields_fail_closed(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        replace(make_event(), **changes)


def test_non_genesis_requires_previous_hash() -> None:
    with pytest.raises(ValueError, match="previous-event"):
        replace(make_event(), sequence=1, vector_clock={"edge-a": 2})


def test_previous_hash_must_be_a_parent() -> None:
    with pytest.raises(ValueError, match="causal parent"):
        replace(
            make_event(),
            sequence=1,
            previous_event_hash="a" * 64,
            vector_clock={"edge-a": 2},
        )


def test_s2_requires_compensation_and_s4_requires_effect() -> None:
    with pytest.raises(ValueError, match="compensation"):
        replace(
            make_event(),
            event_class=EventClass.COMPENSATABLE,
            event_kind="state-change",
        )
    with pytest.raises(ValueError, match="effect"):
        replace(
            make_event(),
            event_class=EventClass.IRREVERSIBLE_PHYSICAL,
            event_kind="physical-effect",
        )


def test_event_payload_rejects_unknown_field() -> None:
    value = make_event().to_obj()
    value["unexpected"] = True
    with pytest.raises(ValueError, match="missing or unknown"):
        CausalEvent.from_payload(canonical_dumps(value))


def test_signer_rejects_different_identity() -> None:
    signer = EventSigner("other", b"key", EDGE_A_PRIVATE)
    with pytest.raises(ValueError, match="signing identity"):
        signer.issue(make_event())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"expected_epoch": "other"}, "different isolation epoch"),
        ({"valid_lease_hashes": frozenset()}, "unverified authority lease"),
        ({"valid_decision_hashes": frozenset()}, "unverified decision certificate"),
        ({"registered_classes": {}}, "registered schema class"),
        ({"permitted_classes": frozenset()}, "does not permit"),
    ],
)
def test_verification_context_mismatch_fails_closed(
    overrides: dict[str, object], message: str
) -> None:
    event = make_event(event_class=EventClass.COMMUTATIVE, event_kind="counter")
    arguments: dict[str, object] = {
        "keys": KEYS,
        "expected_epoch": EPOCH,
        "valid_lease_hashes": frozenset({LEASE_HASH}),
        "valid_decision_hashes": frozenset({DECISION_HASH}),
        "registered_classes": REGISTERED,
        "permitted_classes": PERMITTED,
    }
    arguments.update(overrides)
    with pytest.raises(ValueError, match=message):
        verify_event(sign_event(event), **arguments)  # type: ignore[arg-type]
