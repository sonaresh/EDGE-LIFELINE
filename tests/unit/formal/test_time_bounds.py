from __future__ import annotations

import pytest

from edge_lifeline.formal.time_bounds import LeaseTimeBounds, TrustedTimeAnchor


def test_interval_applies_drift_and_uncertainty_conservatively() -> None:
    anchor = TrustedTimeAnchor(
        utc_estimate_ms=1_000_000,
        initial_error_ms=100,
        monotonic_anchor_ms=5_000,
        drift_parts_per_million=1_000,
        restart_suspend_penalty_ms=50,
    )
    interval = anchor.estimate(15_000)
    assert interval.lower_ms == 1_009_890
    assert interval.upper_ms == 1_010_110
    assert interval.uncertainty_half_width_ms == 110


def test_validity_uses_lower_for_activation_and_upper_for_expiration() -> None:
    bounds = LeaseTimeBounds(900, 1_200, 2_000, 150)
    anchor = TrustedTimeAnchor(1_000, 100, 0, 0)
    report = bounds.validate(anchor.estimate(0), first_activation=True)
    assert report.active
    assert not report.failures


@pytest.mark.parametrize(
    ("interval_now", "expected"),
    [
        (0, "NOT_YET_VALID"),
        (1_101, "ACTIVATION_DEADLINE_UNPROVABLE"),
        (1_900, "EXPIRATION_UNPROVABLE"),
    ],
)
def test_unprovable_time_bounds_deny(interval_now: int, expected: str) -> None:
    bounds = LeaseTimeBounds(900, 1_200, 2_000, 200)
    anchor = TrustedTimeAnchor(0, 100, 0, 0)
    report = bounds.validate(anchor.estimate(interval_now), first_activation=True)
    assert not report.active
    assert expected in report.failures


def test_excess_uncertainty_denies() -> None:
    bounds = LeaseTimeBounds(0, 5_000, 10_000, 10)
    report = bounds.validate(TrustedTimeAnchor(1_000, 20, 0, 0).estimate(0), first_activation=False)
    assert report.failures == ("CLOCK_UNCERTAINTY_EXCEEDED",)


def test_monotonic_rollback_and_unretained_restart_deny() -> None:
    anchor = TrustedTimeAnchor(1_000, 1, 100, 100, retained_across_restart=False)
    with pytest.raises(ValueError, match="rollback"):
        anchor.estimate(99)
    with pytest.raises(ValueError, match="retained"):
        anchor.estimate(101, restarted=True)


def test_restart_penalty_expands_interval() -> None:
    anchor = TrustedTimeAnchor(1_000, 10, 0, 0, restart_suspend_penalty_ms=100)
    normal = anchor.estimate(100)
    restarted = anchor.estimate(100, restarted=True)
    assert restarted.lower_ms == normal.lower_ms - 100
    assert restarted.upper_ms == normal.upper_ms + 100


def test_invalid_bounds_are_rejected() -> None:
    with pytest.raises(ValueError):
        LeaseTimeBounds(10, 9, 20, 1)
    with pytest.raises(ValueError):
        TrustedTimeAnchor(1, 0, 0, 1_000_001)
