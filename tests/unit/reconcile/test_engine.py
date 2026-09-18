from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from edge_lifeline.ledger.dag import DAGImportResult
from edge_lifeline.ledger.model import EventClass, VerifiedEvent, verify_event
from edge_lifeline.reconcile.engine import ReconciliationEngine
from edge_lifeline.reconcile.model import EventDisposition, ReconciliationPlan
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


def _verified(**kwargs: Any) -> VerifiedEvent:
    encoded = sign_event(make_event(**kwargs))
    return verify_event(
        encoded,
        keys=KEYS,
        expected_epoch=EPOCH,
        valid_lease_hashes=frozenset({LEASE_HASH}),
        valid_decision_hashes=frozenset({DECISION_HASH}),
        registered_classes=REGISTERED,
        permitted_classes=PERMITTED,
    )


def _plan(
    event: VerifiedEvent,
    *,
    existing: Mapping[str, VerifiedEvent] | None = None,
    effects: frozenset[str] = frozenset(),
) -> ReconciliationPlan:
    return ReconciliationEngine().plan(
        episode_id="episode-1",
        isolation_epoch=EPOCH,
        dag=DAGImportResult((event,), (), {}, (event.event_hash,)),
        existing={} if existing is None else existing,
        recorded_effect_ids=effects,
    )


def test_s0_and_s1_use_only_registered_merge_rules() -> None:
    observation = _verified()
    counter = _verified(
        edge="edge-b",
        event_class=EventClass.COMMUTATIVE,
        event_kind="counter",
    )
    assert _plan(observation).resolutions[0].disposition is EventDisposition.MERGE_OBSERVATION
    assert _plan(counter).resolutions[0].disposition is EventDisposition.MERGE_COMMUTATIVE


def test_concurrent_s2_emits_compensation_without_rewrite() -> None:
    existing = _verified(
        event_class=EventClass.COMPENSATABLE,
        event_kind="state-change",
        conflict_key="state:1",
    )
    incoming = _verified(
        edge="edge-b",
        event_class=EventClass.COMPENSATABLE,
        event_kind="state-change",
        conflict_key="state:1",
    )
    resolution = _plan(incoming, existing={existing.event_hash: existing}).resolutions[0]
    assert resolution.disposition is EventDisposition.EMIT_COMPENSATION
    assert resolution.compensation_kind == "append-inverse"
    assert resolution.related_event_hashes == (existing.event_hash,)


def test_concurrent_s3_requires_human_review() -> None:
    existing = _verified(
        event_class=EventClass.REVIEW_REQUIRED,
        event_kind="authoritative-record",
    )
    incoming = _verified(
        edge="edge-b",
        event_class=EventClass.REVIEW_REQUIRED,
        event_kind="authoritative-record",
    )
    resolution = _plan(incoming, existing={existing.event_hash: existing}).resolutions[0]
    assert resolution.disposition is EventDisposition.REQUIRE_HUMAN_REVIEW


def test_s2_without_conflict_accepts_state() -> None:
    event = _verified(event_class=EventClass.COMPENSATABLE, event_kind="state-change")
    assert _plan(event).resolutions[0].disposition is EventDisposition.ACCEPT_STATE


def test_s4_never_replays_new_or_previously_recorded_effect() -> None:
    event = _verified(
        event_class=EventClass.IRREVERSIBLE_PHYSICAL,
        event_kind="physical-effect",
        effect_id="effect-1",
    )
    fresh = _plan(event).resolutions[0]
    duplicate = _plan(event, effects=frozenset({"effect-1"})).resolutions[0]
    assert fresh.disposition is EventDisposition.PRESERVE_EFFECT_NO_REPLAY
    assert duplicate.disposition is EventDisposition.DEDUPLICATE_EFFECT_NO_REPLAY
    assert _plan(event).effect_replay_count == 0


def test_quarantine_is_preserved_in_plan() -> None:
    plan = ReconciliationEngine().plan(
        episode_id="episode-1",
        isolation_epoch=EPOCH,
        dag=DAGImportResult((), (), {"f" * 64: ("BAD_PROOF",)}, ()),
        existing={},
    )
    assert plan.resolutions[0].disposition is EventDisposition.QUARANTINE
    assert plan.authority_restored is False
    assert plan.fresh_connected_epoch_lease_required is True


def test_plan_is_deterministic_for_identical_inputs() -> None:
    event = _verified()
    first = _plan(event)
    second = _plan(event)
    assert first.payload() == second.payload()
    assert first.digest == second.digest
