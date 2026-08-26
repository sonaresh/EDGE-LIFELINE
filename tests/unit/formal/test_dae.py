from __future__ import annotations

from collections.abc import Callable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from edge_lifeline.formal.authority import AuthorityEnvelope, ImpactClass
from edge_lifeline.formal.dae import (
    ActionRule,
    ContractionBand,
    ContractionPolicy,
    DecisionResult,
    HazardDimension,
    HazardVector,
    calculate_envelope,
)


def _hazards(value: int = 0, **overrides: int) -> HazardVector:
    values = {dimension: value for dimension in HazardDimension}
    values.update({HazardDimension(name): item for name, item in overrides.items()})
    return HazardVector(values)


def _policy() -> ContractionPolicy:
    zero = {dimension: 0 for dimension in HazardDimension}
    return ContractionPolicy(
        action_rules={
            "monitor": ActionRule({**zero, HazardDimension.ENERGY: 500}, 900),
            "record": ActionRule({**zero, HazardDimension.RESOURCE: 700}, 900),
            "communicate": ActionRule({**zero, HazardDimension.SECURITY: 800}, 700),
            "actuate": ActionRule(
                {
                    **zero,
                    HazardDimension.SENSOR: 1000,
                    HazardDimension.PHYSICAL: 1000,
                    HazardDimension.SECURITY: 1000,
                },
                400,
            ),
        },
        essential_actions=frozenset({"monitor", "record", "communicate"}),
        read_only_actions=frozenset({"monitor", "record"}),
    )


@pytest.mark.parametrize(
    ("hazard", "band", "result"),
    [
        (0, ContractionBand.NORMAL_DELEGATED, DecisionResult.CONTINUE_LOCALLY),
        (250, ContractionBand.GUARDED, DecisionResult.REDUCE_SERVICE),
        (500, ContractionBand.ESSENTIAL_ONLY, DecisionResult.PRIORITIZE_CRITICAL_WORKLOAD),
        (750, ContractionBand.PROTECTIVE, DecisionResult.ISOLATE_FROM_CLOUD),
        (950, ContractionBand.TERMINAL_SAFE, DecisionResult.SAFE_SHUTDOWN),
    ],
)
def test_contraction_bands_are_explicit(
    envelope_factory: Callable[..., AuthorityEnvelope],
    hazard: int,
    band: ContractionBand,
    result: DecisionResult,
) -> None:
    envelope = envelope_factory()
    decision = calculate_envelope(
        previous=envelope,
        parent=envelope,
        lease=envelope,
        hazards=_hazards(hazard),
        policy=_policy(),
    )
    assert decision.band is band
    assert decision.result is result
    assert decision.envelope.is_no_more_authoritative_than(envelope)


def test_security_hazard_selects_cloud_isolation(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    envelope = envelope_factory()
    decision = calculate_envelope(
        previous=envelope,
        parent=envelope,
        lease=envelope,
        hazards=_hazards(security=800),
        policy=_policy(),
    )
    assert decision.result is DecisionResult.ISOLATE_FROM_CLOUD
    assert decision.envelope.max_impact is ImpactClass.READ_ONLY
    assert decision.envelope.max_financial_exposure_cents == 0


def test_nonsecurity_protective_hazard_selects_read_only(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    envelope = envelope_factory()
    decision = calculate_envelope(
        previous=envelope,
        parent=envelope,
        lease=envelope,
        hazards=_hazards(data=800),
        policy=_policy(),
    )
    assert decision.result is DecisionResult.ENTER_READ_ONLY_MODE


def test_missing_hazard_evidence_is_worst_case(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    incomplete = HazardVector.fail_safe({HazardDimension.ISOLATION: 10})
    assert incomplete.values[HazardDimension.CLOCK] == 1000
    envelope = envelope_factory()
    decision = calculate_envelope(
        previous=envelope,
        parent=envelope,
        lease=envelope,
        hazards=incomplete,
        policy=_policy(),
    )
    assert decision.result is DecisionResult.SAFE_SHUTDOWN
    assert not decision.envelope.actions


def test_unknown_action_has_no_implicit_allow(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    envelope = envelope_factory(actions=frozenset({"monitor", "unclassified"}))
    decision = calculate_envelope(
        previous=envelope,
        parent=envelope,
        lease=envelope,
        hazards=_hazards(),
        policy=_policy(),
    )
    assert decision.envelope.actions == {"monitor"}
    assert decision.denied_actions == ("unclassified",)


def test_enforcement_integrity_failure_is_terminal(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    envelope = envelope_factory()
    decision = calculate_envelope(
        previous=envelope,
        parent=envelope,
        lease=envelope,
        hazards=_hazards(),
        policy=_policy(),
        enforcement_integrity=False,
    )
    assert decision.band is ContractionBand.TERMINAL_SAFE
    assert decision.budget_factor_per_mille == 0


@given(
    initial=st.integers(min_value=0, max_value=1000),
    increase=st.integers(min_value=0, max_value=1000),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_worsening_hazard_cannot_expand_authority(
    envelope_factory: Callable[..., AuthorityEnvelope], initial: int, increase: int
) -> None:
    worse = min(1000, initial + increase)
    root = envelope_factory()
    first = calculate_envelope(
        previous=root,
        parent=root,
        lease=root,
        hazards=_hazards(initial),
        policy=_policy(),
    )
    second = calculate_envelope(
        previous=first.envelope,
        parent=root,
        lease=root,
        hazards=_hazards(worse),
        policy=_policy(),
    )
    assert second.envelope.is_no_more_authoritative_than(first.envelope)


def test_improving_evidence_does_not_restore_same_epoch_authority(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    root = envelope_factory()
    degraded = calculate_envelope(
        previous=root,
        parent=root,
        lease=root,
        hazards=_hazards(700),
        policy=_policy(),
    )
    recovered_signal = calculate_envelope(
        previous=degraded.envelope,
        parent=root,
        lease=root,
        hazards=_hazards(0),
        policy=_policy(),
    )
    assert recovered_signal.envelope.is_no_more_authoritative_than(degraded.envelope)
    assert recovered_signal.envelope.actions == degraded.envelope.actions


def test_incomplete_direct_vector_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be complete"):
        HazardVector({HazardDimension.ISOLATION: 0})


def test_policy_threshold_order_is_validated() -> None:
    with pytest.raises(ValueError, match="ordered"):
        ContractionPolicy({}, guarded_at=500, essential_at=200)
