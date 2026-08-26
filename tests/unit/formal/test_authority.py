from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

import pytest

from edge_lifeline.formal.authority import (
    ApprovalLevel,
    AuthorityEnvelope,
    Budgets,
    ImpactClass,
    SecurityPosture,
    TimeWindow,
)


def test_structural_child_is_bounded(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    parent = envelope_factory()
    child = envelope_factory(
        actions=frozenset({"monitor", "record"}),
        resources=frozenset({"device-stream", "event-ledger"}),
        time_window=TimeWindow(2_000, 90_000),
        max_lease_horizon_ms=80_000,
        max_data_age_ms=30_000,
        min_sensor_confidence_per_mille=850,
        budgets=parent.budgets.scale_per_mille(500),
        max_impact=ImpactClass.REVERSIBLE_DIGITAL,
        max_financial_exposure_cents=1_000,
        min_approval=ApprovalLevel.SINGLE_LOCAL,
        min_security_posture=SecurityPosture.HARDENED,
        max_identity_cache_age_ms=10_000,
        max_revocation_staleness_ms=5_000,
        delegation_depth_remaining=1,
    )
    assert child.is_no_more_authoritative_than(parent)
    assert not parent.is_no_more_authoritative_than(child)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actions", frozenset({"monitor", "record", "communicate", "actuate", "admin"})),
        ("max_financial_exposure_cents", 50_001),
        ("min_approval", ApprovalLevel.NONE),
        ("delegation_depth_remaining", 3),
        ("min_sensor_confidence_per_mille", 699),
    ],
)
def test_each_widened_dimension_is_rejected(
    envelope_factory: Callable[..., AuthorityEnvelope], field: str, value: object
) -> None:
    parent = envelope_factory(min_approval=ApprovalLevel.SINGLE_LOCAL)
    child = replace(parent, **cast(Any, {field: value}))
    assert not child.is_no_more_authoritative_than(parent)


def test_meet_takes_intersections_and_stricter_bounds(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    left = envelope_factory(actions=frozenset({"monitor", "record"}))
    right = envelope_factory(
        actions=frozenset({"record", "communicate"}),
        max_data_age_ms=20_000,
        min_approval=ApprovalLevel.THRESHOLD_LOCAL,
    )
    result = left.meet(right)
    assert result.actions == {"record"}
    assert result.max_data_age_ms == 20_000
    assert result.min_approval is ApprovalLevel.THRESHOLD_LOCAL
    assert result.is_no_more_authoritative_than(left)
    assert result.is_no_more_authoritative_than(right)


def test_meet_rejects_cross_epoch_or_policy_migration(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    with pytest.raises(ValueError, match="equality-constrained"):
        envelope_factory().meet(envelope_factory(isolation_epoch="epoch-2"))
    with pytest.raises(ValueError, match="equality-constrained"):
        envelope_factory().meet(envelope_factory(policy_hash="different"))


def test_budget_arithmetic_is_componentwise() -> None:
    first = Budgets(10, 20, 30, 40, 50, 6)
    second = Budgets(1, 2, 3, 4, 5, 6)
    assert first.meet(second) == second
    assert second.scale_per_mille(500) == Budgets(0, 1, 1, 2, 2, 3)
    assert second.add(second) == Budgets(2, 4, 6, 8, 10, 12)
    assert second.is_no_more_than(first)


@pytest.mark.parametrize(
    "constructor",
    [
        lambda: TimeWindow(10, 10),
        lambda: Budgets(-1, 0, 0, 0, 0, 0),
    ],
)
def test_invalid_authority_values_fail_closed(constructor: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        constructor()


def test_disjoint_time_meet_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty intersection"):
        TimeWindow(1, 2).meet(TimeWindow(2, 3))
