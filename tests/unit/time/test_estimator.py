from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from edge_lifeline.time import (
    AuthenticatedTimeAnchor,
    TimeObservation,
    estimate_bounded_time,
)


def anchor() -> AuthenticatedTimeAnchor:
    return AuthenticatedTimeAnchor(
        anchor_id="anchor-1",
        source_artifact_hash="a" * 64,
        utc_estimate_ms=1_000_000,
        initial_error_ms=25,
        boot_id="boot-a",
        boottime_anchor_ms=10_000,
        drift_parts_per_million=100,
        maximum_anchor_age_ms=60_000,
        restart_suspend_penalty_ms=500,
    )


def test_authenticated_interval_uses_boottime_and_drift() -> None:
    result = estimate_bounded_time(anchor(), TimeObservation("boot-a", 20_000, 9_999_999))
    assert result.active
    assert result.mode == "AUTHENTICATED_BOUNDED_TIME"
    assert result.interval is not None
    assert (result.interval.lower_ms, result.interval.upper_ms) == (1_009_974, 1_010_026)


def test_wall_clock_cannot_reactivate_or_change_authority_time() -> None:
    first = estimate_bounded_time(anchor(), TimeObservation("boot-a", 20_000, 1))
    second = estimate_bounded_time(anchor(), TimeObservation("boot-a", 20_000, 99_999_999))
    assert first.interval == second.interval
    assert first.estimate_hash() != second.estimate_hash()  # diagnostic remains auditable


@pytest.mark.parametrize(
    ("observation", "previous", "failure"),
    [
        (TimeObservation("boot-b", 10), None, "RESTART_REQUIRES_REANCHOR"),
        (TimeObservation("boot-a", 9_999), None, "BOOTTIME_ROLLBACK"),
        (
            TimeObservation("boot-a", 15_000),
            TimeObservation("boot-a", 16_000),
            "BOOTTIME_DISCONTINUITY",
        ),
        (
            TimeObservation("boot-b", 10),
            TimeObservation("boot-a", 20_000),
            "BOOT_ID_CHANGED_WITHOUT_RETAINED_ANCHOR",
        ),
    ],
)
def test_rollback_discontinuity_and_unretained_restart_fail_safe(
    observation: TimeObservation,
    previous: TimeObservation | None,
    failure: str,
) -> None:
    result = estimate_bounded_time(anchor(), observation, previous_observation=previous)
    assert not result.active
    assert result.mode == "PROTECTIVE_READ_ONLY"
    assert result.interval is None
    assert failure in result.failures


def test_hardware_retained_restart_adds_penalty() -> None:
    result = estimate_bounded_time(
        replace(anchor(), hardware_retained_across_restart=True),
        TimeObservation("boot-b", 1_000),
    )
    assert result.active
    assert result.interval is not None
    assert result.interval.lower_ms == 1_000_474
    assert result.interval.upper_ms == 1_001_526


def test_stale_anchor_enters_protective_read_only_with_diagnostic_interval() -> None:
    result = estimate_bounded_time(anchor(), TimeObservation("boot-a", 70_000))
    assert not result.active
    assert result.interval is not None
    assert result.failures == ("AUTHENTICATED_ANCHOR_STALE",)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(anchor(), drift_parts_per_million=1_000_001),
        lambda: replace(anchor(), source_artifact_hash="bad"),
        lambda: TimeObservation("", 0),
        lambda: TimeObservation("boot-a", -1),
    ],
)
def test_invalid_time_inputs_are_rejected(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        factory()
