"""Typed Phase 8 experiment records."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Method(StrEnum):
    B0_FAIL_CLOSED = "B0"
    B1_UNRESTRICTED = "B1"
    B2_STATIC_POLICY = "B2"
    B3_FIXED_LEASE = "B3"
    B4_REPLICATION_ONLY = "B4"
    B5_LAST_WRITER_WINS = "B5"
    B6_STATIC_PRIORITY = "B6"
    EDGE_LIFELINE = "EL"


class ScenarioSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(pattern=r"^E(?:[1-9]|1[0-9]|20)$")
    name: str = Field(min_length=3)
    injection: str = Field(min_length=3)
    primary_oracle: str = Field(min_length=3)
    axes: tuple[str, ...]
    severity_per_mille: int = Field(ge=0, le=1000)
    detection_only: bool = False


class SyntheticEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    critical: bool
    consequential: bool
    authorized: bool
    intrinsically_safe: bool
    policy_signal_permits: bool
    identity_fresh: bool
    time_valid: bool
    proof_valid: bool
    lease_valid: bool
    bounded_identity_valid: bool
    bounded_time_valid: bool
    contracted_policy_valid: bool
    evidence_supports_action: bool
    replayed: bool
    child_expansion: bool
    conflict: bool
    physical_effect: bool
    confidence_per_mille: int = Field(ge=0, le=1000)
    energy_cost: int = Field(ge=1)
    compute_cost: int = Field(ge=1)
    utility: int = Field(ge=1)


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allow: bool
    quarantined: bool = False
    replayed_effect: bool = False
    reason: str


class RunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    method: Method
    scenario_id: str
    seed: int
    trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    oracle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    events: int = Field(gt=0)
    critical_events: int = Field(ge=0)
    permitted_events: int = Field(ge=0)
    allowed_events: int = Field(ge=0)
    unsafe_actions_executed: int = Field(ge=0)
    unsafe_actions_prevented: int = Field(ge=0)
    false_denials: int = Field(ge=0)
    invariant_violations: int = Field(ge=0)
    incorrect_conflict_resolutions: int = Field(ge=0)
    prohibited_effect_replays: int = Field(ge=0)
    quarantines: int = Field(ge=0)
    critical_availability: float = Field(ge=0.0, le=1.0)
    mission_outcome: bool
    mission_utility: int = Field(ge=0)
    energy_consumed_model_units: int = Field(ge=0)
    compute_consumed_model_units: int = Field(ge=0)
    utility_per_resource: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_counts(self) -> RunResult:
        if max(self.permitted_events, self.allowed_events, self.critical_events) > self.events:
            raise ValueError("event counts cannot exceed total events")
        if self.unsafe_actions_prevented + self.unsafe_actions_executed > self.events:
            raise ValueError("unsafe action accounting exceeds total events")
        return self
