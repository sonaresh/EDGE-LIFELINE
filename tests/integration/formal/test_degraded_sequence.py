from __future__ import annotations

from collections.abc import Callable

from edge_lifeline.formal.authority import AuthorityEnvelope
from edge_lifeline.formal.dae import (
    ActionRule,
    ContractionBand,
    ContractionPolicy,
    HazardDimension,
    HazardVector,
    calculate_envelope,
)
from edge_lifeline.formal.invariants import assert_monotonic_trace
from edge_lifeline.formal.state_machine import (
    IsolationEvent,
    IsolationState,
    StateSnapshot,
    transition,
)


def test_end_to_end_isolation_contraction_and_reconnect(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    root = envelope_factory()
    rules = {
        action: ActionRule({dimension: 1000 for dimension in HazardDimension}, 1000)
        for action in root.actions
    }
    policy = ContractionPolicy(
        action_rules=rules,
        essential_actions=frozenset({"monitor", "record", "communicate"}),
        read_only_actions=frozenset({"monitor", "record"}),
    )
    state = transition(StateSnapshot(IsolationState.CONNECTED, root), IsolationEvent.CLOUD_LOST)
    trace = [root]
    for severity, expected_band in (
        (300, ContractionBand.GUARDED),
        (550, ContractionBand.ESSENTIAL_ONLY),
        (800, ContractionBand.PROTECTIVE),
    ):
        decision = calculate_envelope(
            previous=trace[-1],
            parent=root,
            lease=root,
            hazards=HazardVector({dimension: severity for dimension in HazardDimension}),
            policy=policy,
        )
        assert decision.band is expected_band
        trace.append(decision.envelope)
    assert_monotonic_trace(trace)
    state = StateSnapshot(state.state, trace[-1])
    state = transition(state, IsolationEvent.CONNECTIVITY_AUTHENTICATED)
    assert state.state is IsolationState.RECONCILIATION_PENDING
    assert state.envelope == trace[-1]
