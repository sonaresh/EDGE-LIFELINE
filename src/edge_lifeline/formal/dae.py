"""Deterministic degraded-autonomy envelope contraction.

All scores use integer per-mille units.  This avoids platform-dependent
floating-point decisions in authorization-critical model code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from types import MappingProxyType

from edge_lifeline.formal.authority import (
    ApprovalLevel,
    AuthorityEnvelope,
    Budgets,
    ImpactClass,
    ReconciliationClass,
    SecurityPosture,
)


class HazardDimension(StrEnum):
    ISOLATION = "isolation"
    CLOCK = "clock"
    DATA = "data"
    SENSOR = "sensor"
    ENERGY = "energy"
    RESOURCE = "resource"
    SECURITY = "security"
    IDENTITY = "identity"
    REVOCATION = "revocation"
    PHYSICAL = "physical"
    FINANCIAL = "financial"
    HUMAN = "human"


class ContractionBand(IntEnum):
    NORMAL_DELEGATED = 0
    GUARDED = 1
    ESSENTIAL_ONLY = 2
    PROTECTIVE = 3
    TERMINAL_SAFE = 4


class DecisionResult(StrEnum):
    CONTINUE_LOCALLY = "CONTINUE_LOCALLY"
    REDUCE_SERVICE = "REDUCE_SERVICE"
    PRIORITIZE_CRITICAL_WORKLOAD = "PRIORITIZE_CRITICAL_WORKLOAD"
    DENY_UNSAFE_ACTION = "DENY_UNSAFE_ACTION"
    USE_CACHED_IDENTITY = "USE_CACHED_IDENTITY"
    ENTER_READ_ONLY_MODE = "ENTER_READ_ONLY_MODE"
    REQUEST_HUMAN_OVERRIDE = "REQUEST_HUMAN_OVERRIDE"
    ISOLATE_FROM_CLOUD = "ISOLATE_FROM_CLOUD"
    RECONNECT_AND_RECONCILE = "RECONNECT_AND_RECONCILE"
    SAFE_SHUTDOWN = "SAFE_SHUTDOWN"


@dataclass(frozen=True, slots=True)
class HazardVector:
    values: Mapping[HazardDimension, int]

    def __post_init__(self) -> None:
        normalized = dict(self.values)
        missing = set(HazardDimension) - set(normalized)
        extra = set(normalized) - set(HazardDimension)
        if missing or extra:
            raise ValueError(
                f"hazard vector must be complete; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        if any(not 0 <= value <= 1000 for value in normalized.values()):
            raise ValueError("hazards must be integer per-mille values in [0, 1000]")
        object.__setattr__(self, "values", MappingProxyType(normalized))

    @classmethod
    def fail_safe(cls, observed: Mapping[HazardDimension, int]) -> HazardVector:
        """Build a complete vector, treating missing mandatory evidence as worst case."""

        return cls({dimension: observed.get(dimension, 1000) for dimension in HazardDimension})

    def maximum(self) -> int:
        return max(self.values.values())

    def no_better_than(self, other: HazardVector) -> bool:
        """True when every hazard is unchanged or worse than ``other``."""

        return all(self.values[item] >= other.values[item] for item in HazardDimension)


@dataclass(frozen=True, slots=True)
class ActionRule:
    weights: Mapping[HazardDimension, int]
    threshold: int

    def __post_init__(self) -> None:
        normalized = {
            dimension: int(self.weights.get(dimension, 0)) for dimension in HazardDimension
        }
        if any(not 0 <= value <= 1000 for value in normalized.values()):
            raise ValueError("action weights must be in [0, 1000]")
        if not 0 <= self.threshold <= 1000:
            raise ValueError("action threshold must be in [0, 1000]")
        object.__setattr__(self, "weights", MappingProxyType(normalized))

    def risk(self, hazards: HazardVector) -> int:
        return max(
            (self.weights[item] * hazards.values[item] + 999) // 1000 for item in HazardDimension
        )


@dataclass(frozen=True, slots=True)
class ContractionPolicy:
    action_rules: Mapping[str, ActionRule]
    guarded_at: int = 250
    essential_at: int = 500
    protective_at: int = 750
    terminal_at: int = 950
    budget_floor_per_mille: int = 100
    essential_actions: frozenset[str] = frozenset()
    read_only_actions: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        thresholds = (
            self.guarded_at,
            self.essential_at,
            self.protective_at,
            self.terminal_at,
        )
        if tuple(sorted(thresholds)) != thresholds or not all(
            0 <= value <= 1000 for value in thresholds
        ):
            raise ValueError("band thresholds must be ordered values in [0, 1000]")
        if not 0 <= self.budget_floor_per_mille <= 1000:
            raise ValueError("budget floor must be in [0, 1000]")
        object.__setattr__(self, "action_rules", MappingProxyType(dict(self.action_rules)))

    def band(self, hazards: HazardVector, *, enforcement_integrity: bool) -> ContractionBand:
        if not enforcement_integrity:
            return ContractionBand.TERMINAL_SAFE
        maximum = hazards.maximum()
        if maximum >= self.terminal_at:
            return ContractionBand.TERMINAL_SAFE
        if maximum >= self.protective_at:
            return ContractionBand.PROTECTIVE
        if maximum >= self.essential_at:
            return ContractionBand.ESSENTIAL_ONLY
        if maximum >= self.guarded_at:
            return ContractionBand.GUARDED
        return ContractionBand.NORMAL_DELEGATED


@dataclass(frozen=True, slots=True)
class DaeDecision:
    envelope: AuthorityEnvelope
    band: ContractionBand
    result: DecisionResult
    maximum_hazard: int
    budget_factor_per_mille: int
    action_risks: tuple[tuple[str, int], ...]
    denied_actions: tuple[str, ...]
    justification: tuple[str, ...]


def _budget_factor(hazards: HazardVector, policy: ContractionPolicy) -> int:
    return max(policy.budget_floor_per_mille, 1000 - hazards.maximum())


def _result_for(
    band: ContractionBand,
    hazards: HazardVector,
    allowed_actions: frozenset[str],
) -> DecisionResult:
    if band is ContractionBand.TERMINAL_SAFE:
        return DecisionResult.SAFE_SHUTDOWN
    if band is ContractionBand.PROTECTIVE:
        if hazards.values[HazardDimension.SECURITY] >= 750:
            return DecisionResult.ISOLATE_FROM_CLOUD
        return DecisionResult.ENTER_READ_ONLY_MODE
    if band is ContractionBand.ESSENTIAL_ONLY:
        return DecisionResult.PRIORITIZE_CRITICAL_WORKLOAD
    if band is ContractionBand.GUARDED:
        return DecisionResult.REDUCE_SERVICE
    if not allowed_actions:
        return DecisionResult.DENY_UNSAFE_ACTION
    return DecisionResult.CONTINUE_LOCALLY


def calculate_envelope(
    *,
    previous: AuthorityEnvelope,
    parent: AuthorityEnvelope,
    lease: AuthorityEnvelope,
    hazards: HazardVector,
    policy: ContractionPolicy,
    enforcement_integrity: bool = True,
) -> DaeDecision:
    """Calculate ``A(t) = A(t-) meet parent meet lease meet C(x)``.

    The final meet with ``previous`` is structural, so improving evidence cannot
    re-expand authority inside an isolation epoch.
    """

    base = AuthorityEnvelope.meet_all(previous, parent, lease)
    band = policy.band(hazards, enforcement_integrity=enforcement_integrity)
    risks: dict[str, int] = {}
    allowed: set[str] = set()
    denied: set[str] = set()
    for action in sorted(base.actions):
        rule = policy.action_rules.get(action)
        if rule is None:
            denied.add(action)
            continue
        risk = rule.risk(hazards)
        risks[action] = risk
        if risk <= rule.threshold:
            allowed.add(action)
        else:
            denied.add(action)

    if band is ContractionBand.ESSENTIAL_ONLY:
        denied.update(allowed - set(policy.essential_actions))
        allowed.intersection_update(policy.essential_actions)
    elif band is ContractionBand.PROTECTIVE:
        denied.update(allowed - set(policy.read_only_actions))
        allowed.intersection_update(policy.read_only_actions)
    elif band is ContractionBand.TERMINAL_SAFE:
        denied.update(allowed)
        allowed.clear()

    factor = _budget_factor(hazards, policy)
    if band is ContractionBand.TERMINAL_SAFE:
        factor = 0

    max_impact = base.max_impact
    max_financial = base.max_financial_exposure_cents
    min_approval = base.min_approval
    min_security = base.min_security_posture
    reconciliation = base.reconciliation_classes
    if band >= ContractionBand.ESSENTIAL_ONLY:
        max_impact = min(max_impact, ImpactClass.REVERSIBLE_DIGITAL)
        max_financial = min(max_financial, 1_000)
        min_approval = max(min_approval, ApprovalLevel.SINGLE_LOCAL)
        reconciliation &= {
            ReconciliationClass.COMMUTATIVE,
            ReconciliationClass.COMPENSATABLE,
        }
    if band >= ContractionBand.PROTECTIVE:
        max_impact = ImpactClass.READ_ONLY
        max_financial = 0
        min_approval = max(min_approval, ApprovalLevel.THRESHOLD_LOCAL)
        min_security = max(min_security, SecurityPosture.ATTESTED)
        reconciliation &= {ReconciliationClass.COMMUTATIVE}
    if band is ContractionBand.TERMINAL_SAFE:
        reconciliation = frozenset()

    contracted = AuthorityEnvelope(
        actions=frozenset(allowed),
        resources=base.resources,
        sites=base.sites,
        time_window=base.time_window,
        max_lease_horizon_ms=(base.max_lease_horizon_ms * factor) // 1000,
        max_data_age_ms=(base.max_data_age_ms * factor) // 1000,
        min_sensor_confidence_per_mille=max(
            base.min_sensor_confidence_per_mille,
            min(1000, hazards.values[HazardDimension.SENSOR]),
        ),
        budgets=base.budgets.scale_per_mille(factor),
        max_impact=max_impact,
        max_financial_exposure_cents=max_financial,
        min_approval=min_approval,
        min_security_posture=min_security,
        max_identity_cache_age_ms=(base.max_identity_cache_age_ms * factor) // 1000,
        max_revocation_staleness_ms=(base.max_revocation_staleness_ms * factor) // 1000,
        delegation_depth_remaining=base.delegation_depth_remaining,
        reconciliation_classes=frozenset(reconciliation),
        schema_version=base.schema_version,
        policy_hash=base.policy_hash,
        mvsg_hash=base.mvsg_hash,
        verifier_profile_hash=base.verifier_profile_hash,
        isolation_epoch=base.isolation_epoch,
        artifact_family=base.artifact_family,
    )
    if not contracted.is_no_more_authoritative_than(previous):
        raise AssertionError("DAE calculation widened the previous envelope")
    if not contracted.is_no_more_authoritative_than(parent):
        raise AssertionError("DAE calculation exceeded the parent envelope")

    justification = (
        f"band={band.name}",
        f"maximum_hazard={hazards.maximum()}",
        f"budget_factor_per_mille={factor}",
        f"allowed_actions={','.join(sorted(allowed))}",
        f"denied_actions={','.join(sorted(denied))}",
    )
    return DaeDecision(
        envelope=contracted,
        band=band,
        result=_result_for(band, hazards, contracted.actions),
        maximum_hazard=hazards.maximum(),
        budget_factor_per_mille=factor,
        action_risks=tuple(sorted(risks.items())),
        denied_actions=tuple(sorted(denied)),
        justification=justification,
    )


def zero_budgets() -> Budgets:
    return Budgets(0, 0, 0, 0, 0, 0)
