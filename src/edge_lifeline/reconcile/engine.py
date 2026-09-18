"""Safety-class reconciliation with no effect replay or implicit authority grant."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from edge_lifeline.ledger.dag import DAGImportResult
from edge_lifeline.ledger.model import EventClass, VerifiedEvent
from edge_lifeline.reconcile.model import (
    EventDisposition,
    ReconciliationPlan,
    Resolution,
)


def _concurrent(left: VerifiedEvent, right: VerifiedEvent) -> bool:
    left_clock = left.event.vector_clock
    right_clock = right.event.vector_clock
    dimensions = set(left_clock) | set(right_clock)
    left_before = all(left_clock.get(key, 0) <= right_clock.get(key, 0) for key in dimensions)
    right_before = all(right_clock.get(key, 0) <= left_clock.get(key, 0) for key in dimensions)
    return not left_before and not right_before


class ReconciliationEngine:
    def plan(
        self,
        *,
        episode_id: str,
        isolation_epoch: str,
        dag: DAGImportResult,
        existing: Mapping[str, VerifiedEvent],
        recorded_effect_ids: frozenset[str] = frozenset(),
    ) -> ReconciliationPlan:
        by_conflict: dict[str, list[VerifiedEvent]] = defaultdict(list)
        for verified in existing.values():
            by_conflict[verified.event.conflict_key].append(verified)
        resolutions: list[Resolution] = []
        effects = set(recorded_effect_ids)
        for event_hash, reasons in sorted(dag.quarantined.items()):
            resolutions.append(
                Resolution(
                    event_hash,
                    EventDisposition.QUARANTINE,
                    ";".join(reasons),
                )
            )
        for verified in dag.accepted:
            event = verified.event
            conflicts = tuple(
                sorted(
                    other.event_hash
                    for other in by_conflict[event.conflict_key]
                    if _concurrent(verified, other)
                )
            )
            if event.event_class is EventClass.OBSERVATIONAL:
                disposition = EventDisposition.MERGE_OBSERVATION
                reason = "observational provenance-preserving reducer"
            elif event.event_class is EventClass.COMMUTATIVE:
                disposition = EventDisposition.MERGE_COMMUTATIVE
                reason = "registered commutative reducer"
            elif event.event_class is EventClass.COMPENSATABLE and conflicts:
                disposition = EventDisposition.EMIT_COMPENSATION
                reason = "concurrent compensatable conflict; append inverse event"
            elif event.event_class is EventClass.REVIEW_REQUIRED and conflicts:
                disposition = EventDisposition.REQUIRE_HUMAN_REVIEW
                reason = "concurrent authoritative conflict requires review"
            elif event.event_class is EventClass.IRREVERSIBLE_PHYSICAL:
                if event.effect_id in effects:
                    disposition = EventDisposition.DEDUPLICATE_EFFECT_NO_REPLAY
                    reason = "effect already recorded; reconciliation cannot dispatch it"
                else:
                    disposition = EventDisposition.PRESERVE_EFFECT_NO_REPLAY
                    reason = "record irreversible effect exactly once without dispatch"
                    if event.effect_id is not None:
                        effects.add(event.effect_id)
            else:
                disposition = EventDisposition.ACCEPT_STATE
                reason = "causally valid state event without concurrent conflict"
            resolutions.append(
                Resolution(
                    verified.event_hash,
                    disposition,
                    reason,
                    conflicts,
                    event.compensation_kind
                    if disposition is EventDisposition.EMIT_COMPENSATION
                    else None,
                )
            )
            by_conflict[event.conflict_key].append(verified)
        resolutions.sort(key=lambda item: item.event_hash)
        return ReconciliationPlan(
            episode_id=episode_id,
            isolation_epoch=isolation_epoch,
            input_frontier=dag.frontier,
            resolutions=tuple(resolutions),
        )
