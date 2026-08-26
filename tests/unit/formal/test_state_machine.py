from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from edge_lifeline.formal.authority import AuthorityEnvelope
from edge_lifeline.formal.state_machine import (
    IsolationEvent,
    IsolationState,
    StateSnapshot,
    transition,
)


def test_reconnection_requires_receipt_and_fresh_epoch(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    envelope = envelope_factory()
    snapshot = StateSnapshot(IsolationState.CONNECTED, envelope)
    snapshot = transition(snapshot, IsolationEvent.CLOUD_LOST)
    assert snapshot.state is IsolationState.ISOLATED_BOUNDED
    snapshot = transition(snapshot, IsolationEvent.CONNECTIVITY_AUTHENTICATED)
    assert snapshot.state is IsolationState.RECONCILIATION_PENDING
    assert snapshot.envelope == envelope
    with pytest.raises(ValueError, match="accepted reconciliation"):
        transition(snapshot, IsolationEvent.FRESH_EPOCH_ADMITTED)
    snapshot = transition(snapshot, IsolationEvent.RECONCILIATION_ACCEPTED)
    with pytest.raises(ValueError, match="explicitly supplied"):
        transition(snapshot, IsolationEvent.FRESH_EPOCH_ADMITTED)
    with pytest.raises(ValueError, match="new isolation epoch"):
        transition(snapshot, IsolationEvent.FRESH_EPOCH_ADMITTED, fresh_envelope=envelope)
    fresh = replace(envelope, isolation_epoch="epoch-2")
    snapshot = transition(
        snapshot,
        IsolationEvent.FRESH_EPOCH_ADMITTED,
        fresh_envelope=fresh,
    )
    assert snapshot.state is IsolationState.CONNECTED
    assert snapshot.reconciliation_receipt
    assert snapshot.fresh_epoch_lease
    assert snapshot.envelope == fresh


def test_degradation_and_shutdown_are_one_way(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    snapshot = StateSnapshot(IsolationState.CONNECTED, envelope_factory())
    snapshot = transition(snapshot, IsolationEvent.CLOUD_LOST)
    snapshot = transition(snapshot, IsolationEvent.HAZARD_ESSENTIAL)
    assert snapshot.state is IsolationState.DEGRADED_ESSENTIAL
    snapshot = transition(snapshot, IsolationEvent.EVIDENCE_SEVERE)
    assert snapshot.state is IsolationState.PROTECTIVE_READ_ONLY
    snapshot = transition(snapshot, IsolationEvent.INTEGRITY_FAILED)
    assert snapshot.state is IsolationState.SAFE_SHUTDOWN
    with pytest.raises(ValueError, match="not permitted"):
        transition(snapshot, IsolationEvent.CONNECTIVITY_AUTHENTICATED)


def test_compromise_quarantines_and_requires_remediation(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    snapshot = transition(
        StateSnapshot(IsolationState.CONNECTED, envelope_factory()),
        IsolationEvent.COMPROMISE_DETECTED,
    )
    assert snapshot.state is IsolationState.QUARANTINED
    with pytest.raises(ValueError):
        transition(snapshot, IsolationEvent.CONNECTIVITY_AUTHENTICATED)
    remediated = transition(snapshot, IsolationEvent.REMEDIATION_ADMITTED)
    assert remediated.state is IsolationState.RECONCILIATION_PENDING
