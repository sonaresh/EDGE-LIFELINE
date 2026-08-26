"""Explicit isolation-state transitions with no reconnect authority grant."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from edge_lifeline.formal.authority import AuthorityEnvelope


class IsolationState(StrEnum):
    CONNECTED = "CONNECTED"
    ISOLATED_BOUNDED = "ISOLATED_BOUNDED"
    DEGRADED_ESSENTIAL = "DEGRADED_ESSENTIAL"
    PROTECTIVE_READ_ONLY = "PROTECTIVE_READ_ONLY"
    RECONCILIATION_PENDING = "RECONCILIATION_PENDING"
    QUARANTINED = "QUARANTINED"
    SAFE_SHUTDOWN = "SAFE_SHUTDOWN"


class IsolationEvent(StrEnum):
    CLOUD_LOST = "CLOUD_LOST"
    HAZARD_ESSENTIAL = "HAZARD_ESSENTIAL"
    EVIDENCE_SEVERE = "EVIDENCE_SEVERE"
    INTEGRITY_FAILED = "INTEGRITY_FAILED"
    CONNECTIVITY_AUTHENTICATED = "CONNECTIVITY_AUTHENTICATED"
    COMPROMISE_DETECTED = "COMPROMISE_DETECTED"
    REMEDIATION_ADMITTED = "REMEDIATION_ADMITTED"
    RECONCILIATION_ACCEPTED = "RECONCILIATION_ACCEPTED"
    FRESH_EPOCH_ADMITTED = "FRESH_EPOCH_ADMITTED"


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    state: IsolationState
    envelope: AuthorityEnvelope
    reconciliation_receipt: bool = False
    fresh_epoch_lease: bool = False


def transition(
    snapshot: StateSnapshot,
    event: IsolationEvent,
    *,
    fresh_envelope: AuthorityEnvelope | None = None,
) -> StateSnapshot:
    state = snapshot.state
    next_state: IsolationState
    if event is IsolationEvent.COMPROMISE_DETECTED and state is not IsolationState.SAFE_SHUTDOWN:
        next_state = IsolationState.QUARANTINED
    elif state is IsolationState.CONNECTED and event is IsolationEvent.CLOUD_LOST:
        next_state = IsolationState.ISOLATED_BOUNDED
    elif state is IsolationState.ISOLATED_BOUNDED and event is IsolationEvent.HAZARD_ESSENTIAL:
        next_state = IsolationState.DEGRADED_ESSENTIAL
    elif state is IsolationState.DEGRADED_ESSENTIAL and event is IsolationEvent.EVIDENCE_SEVERE:
        next_state = IsolationState.PROTECTIVE_READ_ONLY
    elif (
        state
        in {
            IsolationState.ISOLATED_BOUNDED,
            IsolationState.DEGRADED_ESSENTIAL,
            IsolationState.PROTECTIVE_READ_ONLY,
        }
        and event is IsolationEvent.INTEGRITY_FAILED
    ):
        next_state = IsolationState.SAFE_SHUTDOWN
    elif (
        state
        in {
            IsolationState.ISOLATED_BOUNDED,
            IsolationState.DEGRADED_ESSENTIAL,
            IsolationState.PROTECTIVE_READ_ONLY,
        }
        and event is IsolationEvent.CONNECTIVITY_AUTHENTICATED
    ):
        next_state = IsolationState.RECONCILIATION_PENDING
    elif state is IsolationState.QUARANTINED and event is IsolationEvent.REMEDIATION_ADMITTED:
        next_state = IsolationState.RECONCILIATION_PENDING
    elif (
        state is IsolationState.RECONCILIATION_PENDING
        and event is IsolationEvent.RECONCILIATION_ACCEPTED
    ):
        return StateSnapshot(
            state=state,
            envelope=snapshot.envelope,
            reconciliation_receipt=True,
            fresh_epoch_lease=snapshot.fresh_epoch_lease,
        )
    elif (
        state is IsolationState.RECONCILIATION_PENDING
        and event is IsolationEvent.FRESH_EPOCH_ADMITTED
    ):
        if not snapshot.reconciliation_receipt:
            raise ValueError("fresh epoch requires an accepted reconciliation receipt")
        if fresh_envelope is None:
            raise ValueError("fresh epoch requires an explicitly supplied authority envelope")
        if fresh_envelope.isolation_epoch == snapshot.envelope.isolation_epoch:
            raise ValueError("fresh authority must name a new isolation epoch")
        return StateSnapshot(
            state=IsolationState.CONNECTED,
            envelope=fresh_envelope,
            reconciliation_receipt=True,
            fresh_epoch_lease=True,
        )
    else:
        raise ValueError(f"transition {state} + {event} is not permitted")
    return StateSnapshot(
        state=next_state,
        envelope=snapshot.envelope,
        reconciliation_receipt=snapshot.reconciliation_receipt,
        fresh_epoch_lease=snapshot.fresh_epoch_lease,
    )
