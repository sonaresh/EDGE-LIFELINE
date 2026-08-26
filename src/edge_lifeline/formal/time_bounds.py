"""Conservative trusted-time intervals for disconnected lease validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrustedTimeInterval:
    lower_ms: int
    upper_ms: int

    def __post_init__(self) -> None:
        if self.lower_ms > self.upper_ms:
            raise ValueError("trusted-time interval is inverted")

    @property
    def uncertainty_half_width_ms(self) -> int:
        return (self.upper_ms - self.lower_ms + 1) // 2


@dataclass(frozen=True, slots=True)
class TrustedTimeAnchor:
    utc_estimate_ms: int
    initial_error_ms: int
    monotonic_anchor_ms: int
    drift_parts_per_million: int
    restart_suspend_penalty_ms: int = 0
    retained_across_restart: bool = True

    def __post_init__(self) -> None:
        if (
            min(
                self.utc_estimate_ms,
                self.initial_error_ms,
                self.monotonic_anchor_ms,
                self.drift_parts_per_million,
                self.restart_suspend_penalty_ms,
            )
            < 0
        ):
            raise ValueError("trusted-time anchor values cannot be negative")
        if self.drift_parts_per_million > 1_000_000:
            raise ValueError("drift bound cannot exceed one second per second")

    def estimate(self, monotonic_now_ms: int, *, restarted: bool = False) -> TrustedTimeInterval:
        if monotonic_now_ms < self.monotonic_anchor_ms:
            raise ValueError("monotonic rollback detected")
        if restarted and not self.retained_across_restart:
            raise ValueError("restart lacks a retained authenticated time anchor")
        elapsed = monotonic_now_ms - self.monotonic_anchor_ms
        drift = (elapsed * self.drift_parts_per_million + 999_999) // 1_000_000
        penalty = self.restart_suspend_penalty_ms if restarted else 0
        return TrustedTimeInterval(
            lower_ms=self.utc_estimate_ms - self.initial_error_ms + elapsed - drift - penalty,
            upper_ms=self.utc_estimate_ms + self.initial_error_ms + elapsed + drift + penalty,
        )


@dataclass(frozen=True, slots=True)
class LeaseTimeBounds:
    not_before_ms: int
    activate_by_ms: int
    expires_at_ms: int
    clock_uncertainty_max_ms: int

    def __post_init__(self) -> None:
        if not (
            0 <= self.not_before_ms <= self.activate_by_ms < self.expires_at_ms
            and self.clock_uncertainty_max_ms >= 0
        ):
            raise ValueError("invalid lease time bounds")

    def validate(
        self,
        interval: TrustedTimeInterval,
        *,
        first_activation: bool,
    ) -> TimeValidation:
        failures: list[str] = []
        if interval.lower_ms < self.not_before_ms:
            failures.append("NOT_YET_VALID")
        if first_activation and interval.upper_ms > self.activate_by_ms:
            failures.append("ACTIVATION_DEADLINE_UNPROVABLE")
        if interval.upper_ms >= self.expires_at_ms:
            failures.append("EXPIRATION_UNPROVABLE")
        if interval.uncertainty_half_width_ms > self.clock_uncertainty_max_ms:
            failures.append("CLOCK_UNCERTAINTY_EXCEEDED")
        return TimeValidation(active=not failures, failures=tuple(failures), interval=interval)


@dataclass(frozen=True, slots=True)
class TimeValidation:
    active: bool
    failures: tuple[str, ...]
    interval: TrustedTimeInterval
