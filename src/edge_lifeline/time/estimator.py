"""Boot-aware authenticated time interval construction.

Wall-clock readings are retained only as diagnostics.  They cannot reactivate authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from edge_lifeline.formal.time_bounds import TrustedTimeInterval
from edge_lifeline.proof.codec import canonical_dumps, sha256_hex


def _sha256(value: str, label: str) -> str:
    if len(value) != 64 or any(item not in "0123456789abcdef" for item in value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")
    return value


@dataclass(frozen=True, slots=True)
class AuthenticatedTimeAnchor:
    anchor_id: str
    source_artifact_hash: str
    utc_estimate_ms: int
    initial_error_ms: int
    boot_id: str
    boottime_anchor_ms: int
    drift_parts_per_million: int
    maximum_anchor_age_ms: int
    restart_suspend_penalty_ms: int
    hardware_retained_across_restart: bool = False
    schema_version: str = "edge-lifeline-time-anchor-v1"

    def __post_init__(self) -> None:
        if not self.anchor_id or not self.boot_id:
            raise ValueError("time anchor ID and boot ID are required")
        if (
            min(
                self.utc_estimate_ms,
                self.initial_error_ms,
                self.boottime_anchor_ms,
                self.drift_parts_per_million,
                self.maximum_anchor_age_ms,
                self.restart_suspend_penalty_ms,
            )
            < 0
        ):
            raise ValueError("time anchor values cannot be negative")
        if self.drift_parts_per_million > 1_000_000:
            raise ValueError("drift bound cannot exceed one second per second")
        _sha256(self.source_artifact_hash, "time anchor source hash")

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "anchor_id": self.anchor_id,
            "source_artifact_hash": self.source_artifact_hash,
            "utc_estimate_ms": self.utc_estimate_ms,
            "initial_error_ms": self.initial_error_ms,
            "boot_id": self.boot_id,
            "boottime_anchor_ms": self.boottime_anchor_ms,
            "drift_parts_per_million": self.drift_parts_per_million,
            "maximum_anchor_age_ms": self.maximum_anchor_age_ms,
            "restart_suspend_penalty_ms": self.restart_suspend_penalty_ms,
            "hardware_retained_across_restart": self.hardware_retained_across_restart,
        }

    def anchor_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))


@dataclass(frozen=True, slots=True)
class TimeObservation:
    boot_id: str
    boottime_ms: int
    wall_clock_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.boot_id or self.boottime_ms < 0:
            raise ValueError("invalid time observation")
        if self.wall_clock_ms is not None and self.wall_clock_ms < 0:
            raise ValueError("wall clock cannot be negative")


@dataclass(frozen=True, slots=True)
class BoundedTimeEstimate:
    active: bool
    mode: str
    failures: tuple[str, ...]
    interval: TrustedTimeInterval | None
    anchor_hash: str
    wall_clock_diagnostic_ms: int | None
    schema_version: str = "edge-lifeline-bounded-time-estimate-v1"

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "active": self.active,
            "mode": self.mode,
            "failures": list(self.failures),
            "interval": (
                None
                if self.interval is None
                else {"lower_ms": self.interval.lower_ms, "upper_ms": self.interval.upper_ms}
            ),
            "anchor_hash": self.anchor_hash,
            "wall_clock_diagnostic_ms": self.wall_clock_diagnostic_ms,
        }

    def estimate_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))


def estimate_bounded_time(
    anchor: AuthenticatedTimeAnchor,
    observation: TimeObservation,
    *,
    previous_observation: TimeObservation | None = None,
) -> BoundedTimeEstimate:
    """Construct a conservative interval or enter protective read-only mode."""

    failures: list[str] = []
    restarted = observation.boot_id != anchor.boot_id
    if restarted and not anchor.hardware_retained_across_restart:
        failures.append("RESTART_REQUIRES_REANCHOR")
    if not restarted and observation.boottime_ms < anchor.boottime_anchor_ms:
        failures.append("BOOTTIME_ROLLBACK")
    if previous_observation is not None:
        if previous_observation.boot_id == observation.boot_id:
            if observation.boottime_ms < previous_observation.boottime_ms:
                failures.append("BOOTTIME_DISCONTINUITY")
        elif not anchor.hardware_retained_across_restart:
            failures.append("BOOT_ID_CHANGED_WITHOUT_RETAINED_ANCHOR")
    if failures:
        return BoundedTimeEstimate(
            False,
            "PROTECTIVE_READ_ONLY",
            tuple(sorted(set(failures))),
            None,
            anchor.anchor_hash(),
            observation.wall_clock_ms,
        )

    elapsed = (
        observation.boottime_ms
        if restarted
        else observation.boottime_ms - anchor.boottime_anchor_ms
    )
    drift = (elapsed * anchor.drift_parts_per_million + 999_999) // 1_000_000
    penalty = anchor.restart_suspend_penalty_ms if restarted else 0
    interval = TrustedTimeInterval(
        anchor.utc_estimate_ms - anchor.initial_error_ms + elapsed - drift - penalty,
        anchor.utc_estimate_ms + anchor.initial_error_ms + elapsed + drift + penalty,
    )
    if interval.upper_ms - anchor.utc_estimate_ms > anchor.maximum_anchor_age_ms:
        return BoundedTimeEstimate(
            False,
            "PROTECTIVE_READ_ONLY",
            ("AUTHENTICATED_ANCHOR_STALE",),
            interval,
            anchor.anchor_hash(),
            observation.wall_clock_ms,
        )
    return BoundedTimeEstimate(
        True,
        "AUTHENTICATED_BOUNDED_TIME",
        (),
        interval,
        anchor.anchor_hash(),
        observation.wall_clock_ms,
    )
