"""Typed authority lattice used by the Phase 2 executable model.

The order is intentionally structural.  A scalar risk score is never used to
decide whether one authority envelope is bounded by another.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import IntEnum, StrEnum


class ImpactClass(IntEnum):
    READ_ONLY = 0
    REVERSIBLE_DIGITAL = 1
    REVERSIBLE_PHYSICAL = 2
    IRREVERSIBLE_PHYSICAL = 3


class ApprovalLevel(IntEnum):
    NONE = 0
    SINGLE_LOCAL = 1
    THRESHOLD_LOCAL = 2
    MANDATORY_REMOTE = 3


class SecurityPosture(IntEnum):
    BASIC = 0
    HARDENED = 1
    ATTESTED = 2
    QUARANTINE_ELIGIBLE = 3


class ReconciliationClass(StrEnum):
    COMMUTATIVE = "S1_COMMUTATIVE"
    COMPENSATABLE = "S2_COMPENSATABLE"
    REVIEW_REQUIRED = "S3_REVIEW_REQUIRED"
    IRREVERSIBLE_PHYSICAL = "S4_IRREVERSIBLE_PHYSICAL"
    INVALID_OR_MALICIOUS = "S5_INVALID_OR_MALICIOUS"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    not_before_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        if self.not_before_ms < 0 or self.expires_at_ms <= self.not_before_ms:
            raise ValueError("time window must be non-empty and non-negative")

    def is_subset_of(self, other: TimeWindow) -> bool:
        return (
            self.not_before_ms >= other.not_before_ms and self.expires_at_ms <= other.expires_at_ms
        )

    def meet(self, other: TimeWindow) -> TimeWindow:
        lower = max(self.not_before_ms, other.not_before_ms)
        upper = min(self.expires_at_ms, other.expires_at_ms)
        if lower >= upper:
            raise ValueError("authority time windows have an empty intersection")
        return TimeWindow(lower, upper)


@dataclass(frozen=True, slots=True)
class Budgets:
    energy_mj: int
    cpu_ms: int
    memory_mb_s: int
    storage_bytes: int
    network_bytes: int
    action_count: int

    def __post_init__(self) -> None:
        if any(getattr(self, item.name) < 0 for item in fields(self)):
            raise ValueError("budget dimensions cannot be negative")

    def is_no_more_than(self, other: Budgets) -> bool:
        return all(getattr(self, item.name) <= getattr(other, item.name) for item in fields(self))

    def meet(self, other: Budgets) -> Budgets:
        return Budgets(
            **{
                item.name: min(getattr(self, item.name), getattr(other, item.name))
                for item in fields(self)
            }
        )

    def scale_per_mille(self, factor: int) -> Budgets:
        if not 0 <= factor <= 1000:
            raise ValueError("budget scale factor must be in [0, 1000]")
        return Budgets(
            **{item.name: (getattr(self, item.name) * factor) // 1000 for item in fields(self)}
        )

    def add(self, other: Budgets) -> Budgets:
        return Budgets(
            **{
                item.name: getattr(self, item.name) + getattr(other, item.name)
                for item in fields(self)
            }
        )


@dataclass(frozen=True, slots=True)
class AuthorityEnvelope:
    actions: frozenset[str]
    resources: frozenset[str]
    sites: frozenset[str]
    time_window: TimeWindow
    max_lease_horizon_ms: int
    max_data_age_ms: int
    min_sensor_confidence_per_mille: int
    budgets: Budgets
    max_impact: ImpactClass
    max_financial_exposure_cents: int
    min_approval: ApprovalLevel
    min_security_posture: SecurityPosture
    max_identity_cache_age_ms: int
    max_revocation_staleness_ms: int
    delegation_depth_remaining: int
    reconciliation_classes: frozenset[ReconciliationClass]
    schema_version: str
    policy_hash: str
    mvsg_hash: str
    verifier_profile_hash: str
    isolation_epoch: str
    artifact_family: str = "edge-lifeline-authority-v1"

    def __post_init__(self) -> None:
        maxima = (
            self.max_lease_horizon_ms,
            self.max_data_age_ms,
            self.max_financial_exposure_cents,
            self.max_identity_cache_age_ms,
            self.max_revocation_staleness_ms,
            self.delegation_depth_remaining,
        )
        if any(value < 0 for value in maxima):
            raise ValueError("authority maxima cannot be negative")
        if not 0 <= self.min_sensor_confidence_per_mille <= 1000:
            raise ValueError("sensor-confidence requirement must be in [0, 1000]")
        exact = (
            self.schema_version,
            self.policy_hash,
            self.mvsg_hash,
            self.verifier_profile_hash,
            self.isolation_epoch,
            self.artifact_family,
        )
        if any(not value for value in exact):
            raise ValueError("equality-constrained authority fields cannot be empty")

    def is_no_more_authoritative_than(self, other: AuthorityEnvelope) -> bool:
        return (
            self.actions <= other.actions
            and self.resources <= other.resources
            and self.sites <= other.sites
            and self.time_window.is_subset_of(other.time_window)
            and self.max_lease_horizon_ms <= other.max_lease_horizon_ms
            and self.max_data_age_ms <= other.max_data_age_ms
            and self.min_sensor_confidence_per_mille >= other.min_sensor_confidence_per_mille
            and self.budgets.is_no_more_than(other.budgets)
            and self.max_impact <= other.max_impact
            and self.max_financial_exposure_cents <= other.max_financial_exposure_cents
            and self.min_approval >= other.min_approval
            and self.min_security_posture >= other.min_security_posture
            and self.max_identity_cache_age_ms <= other.max_identity_cache_age_ms
            and self.max_revocation_staleness_ms <= other.max_revocation_staleness_ms
            and self.delegation_depth_remaining <= other.delegation_depth_remaining
            and self.reconciliation_classes <= other.reconciliation_classes
            and self._exact_identity() == other._exact_identity()
        )

    def _exact_identity(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.schema_version,
            self.policy_hash,
            self.mvsg_hash,
            self.verifier_profile_hash,
            self.isolation_epoch,
            self.artifact_family,
        )

    def meet(self, other: AuthorityEnvelope) -> AuthorityEnvelope:
        if self._exact_identity() != other._exact_identity():
            raise ValueError("equality-constrained authority dimensions differ")
        return AuthorityEnvelope(
            actions=self.actions & other.actions,
            resources=self.resources & other.resources,
            sites=self.sites & other.sites,
            time_window=self.time_window.meet(other.time_window),
            max_lease_horizon_ms=min(self.max_lease_horizon_ms, other.max_lease_horizon_ms),
            max_data_age_ms=min(self.max_data_age_ms, other.max_data_age_ms),
            min_sensor_confidence_per_mille=max(
                self.min_sensor_confidence_per_mille,
                other.min_sensor_confidence_per_mille,
            ),
            budgets=self.budgets.meet(other.budgets),
            max_impact=min(self.max_impact, other.max_impact),
            max_financial_exposure_cents=min(
                self.max_financial_exposure_cents,
                other.max_financial_exposure_cents,
            ),
            min_approval=max(self.min_approval, other.min_approval),
            min_security_posture=max(self.min_security_posture, other.min_security_posture),
            max_identity_cache_age_ms=min(
                self.max_identity_cache_age_ms, other.max_identity_cache_age_ms
            ),
            max_revocation_staleness_ms=min(
                self.max_revocation_staleness_ms,
                other.max_revocation_staleness_ms,
            ),
            delegation_depth_remaining=min(
                self.delegation_depth_remaining,
                other.delegation_depth_remaining,
            ),
            reconciliation_classes=self.reconciliation_classes & other.reconciliation_classes,
            schema_version=self.schema_version,
            policy_hash=self.policy_hash,
            mvsg_hash=self.mvsg_hash,
            verifier_profile_hash=self.verifier_profile_hash,
            isolation_epoch=self.isolation_epoch,
            artifact_family=self.artifact_family,
        )

    @classmethod
    def meet_all(
        cls,
        first: AuthorityEnvelope,
        *others: AuthorityEnvelope,
    ) -> AuthorityEnvelope:
        result = first
        for other in others:
            result = result.meet(other)
        return result
