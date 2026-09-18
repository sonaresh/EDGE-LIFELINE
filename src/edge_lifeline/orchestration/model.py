"""Typed orchestration observations; Kubernetes state is evidence, never authority."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClusterRole(StrEnum):
    CLOUD = "cloud"
    EDGE = "edge"


class Connectivity(StrEnum):
    CONNECTED = "connected"
    ISOLATED = "isolated"
    UNKNOWN = "unknown"


class LeaseState(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    MISSING = "missing"


class RuntimeMode(StrEnum):
    CONNECTED = "connected"
    DEGRADED = "degraded"
    PROTECTIVE = "protective"
    QUARANTINED = "quarantined"


class ClusterObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: str = Field(pattern=r"^(cloud|edge-[abc])$")
    role: ClusterRole
    connectivity: Connectivity
    lease_state: LeaseState
    workload_ready: bool
    policy_ready: bool
    proof_verifier_ready: bool
    recovery_complete: bool = False
    fresh_connected_epoch_lease: bool = False

    @model_validator(mode="after")
    def role_matches_identity(self) -> ClusterObservation:
        expected = ClusterRole.CLOUD if self.cluster_id == "cloud" else ClusterRole.EDGE
        if self.role is not expected:
            raise ValueError("cluster role does not match the registered cluster identity")
        return self


class Topology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^edge-lifeline-topology-v1$")
    clusters: tuple[ClusterObservation, ...]


class RuntimeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: str
    mode: RuntimeMode
    authority_restored: bool = False
    effect_dispatch_allowed: bool
    reason: str
