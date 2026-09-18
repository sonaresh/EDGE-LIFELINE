from __future__ import annotations

from collections.abc import Mapping

from edge_lifeline.ledger.dag import DAGImportResult, validate_event_dag
from edge_lifeline.ledger.model import VerifiedEvent, verify_event
from edge_lifeline.proof.codec import sha256_hex
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


def _validate(
    events: list[bytes], existing: Mapping[str, VerifiedEvent] | None = None
) -> DAGImportResult:
    return validate_event_dag(
        events,
        existing={} if existing is None else existing,
        keys=KEYS,
        expected_epoch=EPOCH,
        valid_lease_hashes=frozenset({LEASE_HASH}),
        valid_decision_hashes=frozenset({DECISION_HASH}),
        registered_classes=REGISTERED,
        permitted_classes=PERMITTED,
    )


def test_unordered_chain_is_topologically_accepted() -> None:
    root = sign_event(make_event())
    next_event = sign_event(child(root))
    result = _validate([next_event, root])
    assert [item.event.sequence for item in result.accepted] == [0, 1]
    assert result.frontier == (sha256_hex(next_event),)


def test_duplicate_is_idempotently_reported() -> None:
    encoded = sign_event(make_event())
    result = _validate([encoded, encoded])
    assert result.duplicates == (sha256_hex(encoded),)
    assert len(result.accepted) == 1


def test_missing_parent_is_quarantined() -> None:
    event = make_event(
        sequence=1,
        previous="a" * 64,
        vector_clock={"edge-a": 2},
    )
    result = _validate([sign_event(event)])
    assert next(iter(result.quarantined.values())) == ("CAUSAL_PARENT_MISSING",)


def test_invalid_vector_clock_is_quarantined() -> None:
    root = sign_event(make_event(vector_clock={"edge-a": 1, "edge-b": 2}))
    event = child(root)
    result = _validate([root, sign_event(event)])
    assert any("VECTOR_CLOCK" in reasons[0] for reasons in result.quarantined.values())


def test_forked_children_are_both_quarantined() -> None:
    root = sign_event(make_event())
    left = sign_event(child(root, event_id="left", idempotency_key="left"))
    right = sign_event(child(root, event_id="right", idempotency_key="right"))
    result = _validate([root, left, right])
    assert len(result.accepted) == 1
    assert set(result.quarantined) == {sha256_hex(left), sha256_hex(right)}


def test_descendant_of_quarantined_parent_is_quarantined() -> None:
    root = sign_event(make_event())
    bad = sign_event(child(root, event_id="bad", idempotency_key="bad"))
    bad_hash = sha256_hex(bad)
    sibling = sign_event(child(root, event_id="sibling", idempotency_key="sibling"))
    descendant = make_event(
        sequence=2,
        previous=bad_hash,
        vector_clock={"edge-a": 3},
        event_id="descendant",
        idempotency_key="descendant",
    )
    result = _validate([root, bad, sibling, sign_event(descendant)])
    assert "CAUSAL_PARENT_QUARANTINED" in result.quarantined[sha256_hex(sign_event(descendant))]


def test_cross_edge_parent_requires_vector_clock_dominance() -> None:
    a = sign_event(make_event(edge="edge-a"))
    b = make_event(
        edge="edge-b",
        parents=(sha256_hex(a),),
        vector_clock={"edge-b": 1},
    )
    result = _validate([a, sign_event(b)])
    assert any("VECTOR_CLOCK" in reasons[0] for reasons in result.quarantined.values())


def test_existing_event_supports_next_import() -> None:
    root_encoded = sign_event(make_event())
    root = verify_event(
        root_encoded,
        keys=KEYS,
        expected_epoch=EPOCH,
        valid_lease_hashes=frozenset({LEASE_HASH}),
        valid_decision_hashes=frozenset({DECISION_HASH}),
        registered_classes=REGISTERED,
        permitted_classes=PERMITTED,
    )
    next_encoded = sign_event(child(root_encoded))
    result = _validate([next_encoded], {root.event_hash: root})
    assert len(result.accepted) == 1


def test_invalid_signature_is_quarantined() -> None:
    encoded = bytearray(sign_event(make_event()))
    encoded[-1] ^= 1
    result = _validate([bytes(encoded)])
    assert next(iter(result.quarantined.values()))[0].startswith("INVALID_EVENT:")
