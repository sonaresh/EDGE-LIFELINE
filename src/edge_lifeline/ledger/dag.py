"""Fail-safe validation and deterministic ordering for imported event DAGs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from edge_lifeline.ledger.model import (
    EventClass,
    EventKey,
    VerifiedEvent,
    verify_event,
)
from edge_lifeline.proof.codec import sha256_hex


@dataclass(frozen=True, slots=True)
class DAGImportResult:
    accepted: tuple[VerifiedEvent, ...]
    duplicates: tuple[str, ...]
    quarantined: Mapping[str, tuple[str, ...]]
    frontier: tuple[str, ...]


def _clock_follows(event: VerifiedEvent, parents: Sequence[VerifiedEvent]) -> bool:
    clock = event.event.vector_clock
    for parent in parents:
        for edge, counter in parent.event.vector_clock.items():
            if clock.get(edge, 0) < counter:
                return False
    previous = next(
        (parent for parent in parents if parent.event_hash == event.event.previous_event_hash),
        None,
    )
    if previous is None:
        return event.event.sequence == 0
    return (
        previous.event.edge_identity == event.event.edge_identity
        and previous.event.isolation_epoch == event.event.isolation_epoch
        and previous.event.sequence + 1 == event.event.sequence
        and clock[event.event.edge_identity]
        == previous.event.vector_clock[event.event.edge_identity] + 1
    )


def validate_event_dag(
    encoded_events: Sequence[bytes],
    *,
    existing: Mapping[str, VerifiedEvent],
    keys: Mapping[bytes, EventKey],
    expected_epoch: str,
    valid_lease_hashes: frozenset[str],
    valid_decision_hashes: frozenset[str],
    registered_classes: Mapping[str, EventClass],
    permitted_classes: frozenset[EventClass],
) -> DAGImportResult:
    candidates: dict[str, VerifiedEvent] = {}
    quarantined: dict[str, list[str]] = defaultdict(list)
    duplicates: set[str] = set()
    for encoded in encoded_events:
        event_hash = sha256_hex(encoded)
        if event_hash in existing or event_hash in candidates:
            duplicates.add(event_hash)
            continue
        try:
            candidates[event_hash] = verify_event(
                encoded,
                keys=keys,
                expected_epoch=expected_epoch,
                valid_lease_hashes=valid_lease_hashes,
                valid_decision_hashes=valid_decision_hashes,
                registered_classes=registered_classes,
                permitted_classes=permitted_classes,
            )
        except (TypeError, ValueError) as error:
            quarantined[event_hash].append(f"INVALID_EVENT:{error}")

    all_events = {**existing, **candidates}
    successors: dict[tuple[str, str, str | None], list[str]] = defaultdict(list)
    for event_hash, verified in all_events.items():
        event = verified.event
        successors[(event.edge_identity, event.isolation_epoch, event.previous_event_hash)].append(
            event_hash
        )
    for event_hash, verified in candidates.items():
        siblings = successors[
            (
                verified.event.edge_identity,
                verified.event.isolation_epoch,
                verified.event.previous_event_hash,
            )
        ]
        if len(siblings) > 1:
            quarantined[event_hash].append("EDGE_HISTORY_FORK")

    unresolved = set(candidates) - set(quarantined)
    accepted: list[VerifiedEvent] = []
    resolved = dict(existing)
    while unresolved:
        progressed = False
        for event_hash in sorted(unresolved):
            event = candidates[event_hash].event
            invalid_parent = next(
                (parent for parent in event.causal_parent_hashes if parent in quarantined),
                None,
            )
            if invalid_parent is not None:
                quarantined[event_hash].append("CAUSAL_PARENT_QUARANTINED")
                unresolved.remove(event_hash)
                progressed = True
                break
            missing = [parent for parent in event.causal_parent_hashes if parent not in all_events]
            if missing:
                quarantined[event_hash].append("CAUSAL_PARENT_MISSING")
                unresolved.remove(event_hash)
                progressed = True
                break
            if any(parent not in resolved for parent in event.causal_parent_hashes):
                continue
            parents = [resolved[parent] for parent in event.causal_parent_hashes]
            if not _clock_follows(candidates[event_hash], parents):
                quarantined[event_hash].append("VECTOR_CLOCK_OR_SEQUENCE_INVALID")
            else:
                accepted.append(candidates[event_hash])
                resolved[event_hash] = candidates[event_hash]
            unresolved.remove(event_hash)
            progressed = True
            break
        if not progressed:
            for event_hash in sorted(unresolved):
                quarantined[event_hash].append("CAUSAL_CYCLE_OR_UNRESOLVED_GAP")
            unresolved.clear()

    parented = {
        parent
        for verified in resolved.values()
        for parent in verified.event.causal_parent_hashes
        if parent in resolved
    }
    frontier = tuple(sorted(set(resolved) - parented))
    return DAGImportResult(
        tuple(accepted),
        tuple(sorted(duplicates)),
        {key: tuple(value) for key, value in sorted(quarantined.items())},
        frontier,
    )
