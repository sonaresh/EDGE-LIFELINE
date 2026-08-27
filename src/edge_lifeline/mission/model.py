"""Immutable Phase 4 mission graph and plan schemas.

The model contains only declared synthetic systems-resilience priorities.  It does
not encode clinical decisions or infer mission importance from observed outcomes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from edge_lifeline.formal.authority import (
    ApprovalLevel,
    AuthorityEnvelope,
    Budgets,
    ImpactClass,
    SecurityPosture,
)
from edge_lifeline.proof.codec import canonical_dumps, envelope_to_obj, sha256_hex


def _frozen_map(value: Mapping[str, int], label: str) -> Mapping[str, int]:
    normalized = {str(key): int(item) for key, item in value.items()}
    if any(not key or item < 0 for key, item in normalized.items()):
        raise ValueError(f"{label} must contain nonempty keys and nonnegative integers")
    return MappingProxyType(normalized)


def _budget_obj(value: Budgets) -> dict[str, int]:
    return {
        "energy_mj": value.energy_mj,
        "cpu_ms": value.cpu_ms,
        "memory_mb_s": value.memory_mb_s,
        "storage_bytes": value.storage_bytes,
        "network_bytes": value.network_bytes,
        "action_count": value.action_count,
    }


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    capability_id: str
    required_units: int
    mandatory: bool
    deadline_ms: int
    optional_utility: int = 0

    def __post_init__(self) -> None:
        if not self.capability_id or self.required_units <= 0 or self.deadline_ms <= 0:
            raise ValueError("capability requirements need an ID, positive units, and deadline")
        if self.optional_utility < 0:
            raise ValueError("optional utility cannot be negative")
        if self.mandatory and self.optional_utility:
            raise ValueError("mandatory capability cannot carry optional utility")


@dataclass(frozen=True, slots=True)
class ServiceNode:
    service_id: str
    service_class: str
    capability_units: Mapping[str, int]
    allowed_sites: frozenset[str]
    demand: Budgets
    required_actions: frozenset[str]
    required_resources: frozenset[str]
    required_impact: ImpactClass
    required_approval: ApprovalLevel
    required_security_posture: SecurityPosture
    min_sensor_confidence_per_mille: int
    data_max_age_ms: Mapping[str, int]
    and_dependencies: frozenset[str] = frozenset()
    alternative_groups: tuple[frozenset[str], ...] = ()
    startup_after: frozenset[str] = frozenset()
    startup_time_ms: int = 1
    response_latency_ms: int = 1
    authority_exposure_units: int = 0
    optional_utility: int = 0

    def __post_init__(self) -> None:
        if not self.service_id or not self.service_class or not self.allowed_sites:
            raise ValueError("service ID, class, and allowed sites are required")
        if not self.required_actions or not self.required_resources:
            raise ValueError("services require explicit authority actions and resources")
        if not 0 <= self.min_sensor_confidence_per_mille <= 1000:
            raise ValueError("sensor confidence must be in [0, 1000]")
        if (
            min(
                self.startup_time_ms,
                self.response_latency_ms,
                self.authority_exposure_units,
                self.optional_utility,
            )
            < 0
        ):
            raise ValueError("service timing, exposure, and utility cannot be negative")
        object.__setattr__(
            self,
            "capability_units",
            _frozen_map(self.capability_units, "capability units"),
        )
        object.__setattr__(
            self,
            "data_max_age_ms",
            _frozen_map(self.data_max_age_ms, "data freshness requirements"),
        )
        if any(not group for group in self.alternative_groups):
            raise ValueError("alternative dependency groups cannot be empty")
        referenced = self.and_dependencies | self.startup_after
        if self.service_id in referenced or any(
            self.service_id in group for group in self.alternative_groups
        ):
            raise ValueError("service cannot depend on itself")

    def to_obj(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "service_class": self.service_class,
            "capability_units": dict(sorted(self.capability_units.items())),
            "allowed_sites": sorted(self.allowed_sites),
            "demand": _budget_obj(self.demand),
            "required_actions": sorted(self.required_actions),
            "required_resources": sorted(self.required_resources),
            "required_impact": int(self.required_impact),
            "required_approval": int(self.required_approval),
            "required_security_posture": int(self.required_security_posture),
            "min_sensor_confidence_per_mille": self.min_sensor_confidence_per_mille,
            "data_max_age_ms": dict(sorted(self.data_max_age_ms.items())),
            "and_dependencies": sorted(self.and_dependencies),
            "alternative_groups": [sorted(group) for group in self.alternative_groups],
            "startup_after": sorted(self.startup_after),
            "startup_time_ms": self.startup_time_ms,
            "response_latency_ms": self.response_latency_ms,
            "authority_exposure_units": self.authority_exposure_units,
            "optional_utility": self.optional_utility,
        }


@dataclass(frozen=True, slots=True)
class RedundancyRequirement:
    requirement_id: str
    members: frozenset[str]
    minimum_selected: int
    distinct_sites: bool = False

    def __post_init__(self) -> None:
        if (
            not self.requirement_id
            or self.minimum_selected <= 0
            or self.minimum_selected > len(self.members)
        ):
            raise ValueError("invalid redundancy requirement")


@dataclass(frozen=True, slots=True)
class LatencyConstraint:
    constraint_id: str
    service_ids: tuple[str, ...]
    maximum_latency_ms: int

    def __post_init__(self) -> None:
        if (
            not self.constraint_id
            or not self.service_ids
            or len(set(self.service_ids)) != len(self.service_ids)
            or self.maximum_latency_ms <= 0
        ):
            raise ValueError("invalid latency constraint")


@dataclass(frozen=True, slots=True)
class SiteCapacity:
    site_id: str
    capacity: Budgets

    def __post_init__(self) -> None:
        if not self.site_id:
            raise ValueError("site ID is required")


@dataclass(frozen=True, slots=True)
class MissionGraph:
    graph_id: str
    graph_version: str
    services: tuple[ServiceNode, ...]
    capabilities: tuple[CapabilityRequirement, ...]
    exclusions: tuple[tuple[str, str], ...] = ()
    redundancy: tuple[RedundancyRequirement, ...] = ()
    latency_constraints: tuple[LatencyConstraint, ...] = ()
    schema_version: str = "edge-lifeline-mvsg-v1"

    def __post_init__(self) -> None:
        if not self.graph_id or not self.graph_version or not self.services:
            raise ValueError("graph ID, version, and services are required")
        service_ids = [item.service_id for item in self.services]
        capability_ids = [item.capability_id for item in self.capabilities]
        if len(service_ids) != len(set(service_ids)):
            raise ValueError("service IDs must be unique")
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("capability IDs must be unique")
        known = set(service_ids)
        for service in self.services:
            references = service.and_dependencies | service.startup_after
            references |= frozenset().union(*service.alternative_groups)
            if not references <= known:
                raise ValueError(f"unknown dependency for service {service.service_id}")
            if not set(service.capability_units) <= set(capability_ids):
                raise ValueError(f"unknown capability on service {service.service_id}")
        for first, second in self.exclusions:
            if first == second or first not in known or second not in known:
                raise ValueError("exclusions must reference two distinct known services")
        for requirement in self.redundancy:
            if not requirement.members <= known:
                raise ValueError("redundancy requirement references an unknown service")
        redundancy_ids = [item.requirement_id for item in self.redundancy]
        if len(redundancy_ids) != len(set(redundancy_ids)):
            raise ValueError("redundancy requirement IDs must be unique")
        for constraint in self.latency_constraints:
            if not set(constraint.service_ids) <= known:
                raise ValueError("latency constraint references an unknown service")
        latency_ids = [item.constraint_id for item in self.latency_constraints]
        if len(latency_ids) != len(set(latency_ids)):
            raise ValueError("latency constraint IDs must be unique")
        normalized_exclusions = [tuple(sorted(item)) for item in self.exclusions]
        if len(normalized_exclusions) != len(set(normalized_exclusions)):
            raise ValueError("exclusions must be unique")
        self._validate_acyclic()

    @property
    def service_map(self) -> Mapping[str, ServiceNode]:
        return MappingProxyType({item.service_id: item for item in self.services})

    @property
    def capability_map(self) -> Mapping[str, CapabilityRequirement]:
        return MappingProxyType({item.capability_id: item for item in self.capabilities})

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "graph_id": self.graph_id,
            "graph_version": self.graph_version,
            "services": [
                item.to_obj() for item in sorted(self.services, key=lambda x: x.service_id)
            ],
            "capabilities": [
                {
                    "capability_id": item.capability_id,
                    "required_units": item.required_units,
                    "mandatory": item.mandatory,
                    "deadline_ms": item.deadline_ms,
                    "optional_utility": item.optional_utility,
                }
                for item in sorted(self.capabilities, key=lambda x: x.capability_id)
            ],
            "exclusions": [
                list(item) for item in sorted(tuple(sorted(x)) for x in self.exclusions)
            ],
            "redundancy": [
                {
                    "requirement_id": item.requirement_id,
                    "members": sorted(item.members),
                    "minimum_selected": item.minimum_selected,
                    "distinct_sites": item.distinct_sites,
                }
                for item in sorted(self.redundancy, key=lambda x: x.requirement_id)
            ],
            "latency_constraints": [
                {
                    "constraint_id": item.constraint_id,
                    "service_ids": list(item.service_ids),
                    "maximum_latency_ms": item.maximum_latency_ms,
                }
                for item in sorted(self.latency_constraints, key=lambda x: x.constraint_id)
            ],
        }

    def graph_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))

    def _validate_acyclic(self) -> None:
        dependencies = {
            item.service_id: set(item.and_dependencies | item.startup_after)
            | set().union(*item.alternative_groups)
            for item in self.services
        }
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(service_id: str) -> None:
            if service_id in permanent:
                return
            if service_id in temporary:
                raise ValueError("service dependency graph must be acyclic")
            temporary.add(service_id)
            for dependency in dependencies[service_id]:
                visit(dependency)
            temporary.remove(service_id)
            permanent.add(service_id)

        for service_id in dependencies:
            visit(service_id)


@dataclass(frozen=True, slots=True)
class MissionContext:
    authority: AuthorityEnvelope
    site_capacities: tuple[SiteCapacity, ...]
    available_sites: frozenset[str]
    unavailable_services: frozenset[str]
    data_age_ms: Mapping[str, int]
    sensor_confidence_per_mille: int
    approval_level: ApprovalLevel
    security_posture: SecurityPosture
    starvation_ms: Mapping[str, int]
    context_id: str

    def __post_init__(self) -> None:
        if not self.context_id or not self.site_capacities:
            raise ValueError("context ID and site capacities are required")
        site_ids = [item.site_id for item in self.site_capacities]
        if len(site_ids) != len(set(site_ids)):
            raise ValueError("site capacities must be unique")
        if not self.available_sites <= set(site_ids):
            raise ValueError("available sites must have declared capacity")
        if not 0 <= self.sensor_confidence_per_mille <= 1000:
            raise ValueError("sensor confidence must be in [0, 1000]")
        object.__setattr__(self, "data_age_ms", _frozen_map(self.data_age_ms, "data ages"))
        object.__setattr__(
            self,
            "starvation_ms",
            _frozen_map(self.starvation_ms, "starvation durations"),
        )

    @property
    def capacity_map(self) -> Mapping[str, Budgets]:
        return MappingProxyType({item.site_id: item.capacity for item in self.site_capacities})

    def to_obj(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "authority": envelope_to_obj(self.authority),
            "site_capacities": {
                item.site_id: _budget_obj(item.capacity)
                for item in sorted(self.site_capacities, key=lambda x: x.site_id)
            },
            "available_sites": sorted(self.available_sites),
            "unavailable_services": sorted(self.unavailable_services),
            "data_age_ms": dict(sorted(self.data_age_ms.items())),
            "sensor_confidence_per_mille": self.sensor_confidence_per_mille,
            "approval_level": int(self.approval_level),
            "security_posture": int(self.security_posture),
            "starvation_ms": dict(sorted(self.starvation_ms.items())),
        }

    def context_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))


@dataclass(frozen=True, slots=True)
class MissionPlan:
    graph_hash: str
    context_hash: str
    placements: tuple[tuple[str, str], ...]
    startup_order: tuple[str, ...]
    objective: tuple[int, int, int]
    solver_status: str
    optimized_stages: int
    schema_version: str = "edge-lifeline-mvsg-plan-v1"

    @property
    def selected_services(self) -> frozenset[str]:
        return frozenset(service for service, _site in self.placements)

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "graph_hash": self.graph_hash,
            "context_hash": self.context_hash,
            "placements": [list(item) for item in sorted(self.placements)],
            "startup_order": list(self.startup_order),
            "objective": list(self.objective),
            "solver_status": self.solver_status,
            "optimized_stages": self.optimized_stages,
        }

    def plan_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))
