"""Independent, solver-free validation for Phase 4 MVSG plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from edge_lifeline.formal.authority import Budgets
from edge_lifeline.mission.model import MissionContext, MissionGraph, MissionPlan, ServiceNode
from edge_lifeline.proof.codec import canonical_dumps, sha256_hex

VALIDATOR_VERSION = "phase4-validator-v1"
_BUDGET_FIELDS = (
    "energy_mj",
    "cpu_ms",
    "memory_mb_s",
    "storage_bytes",
    "network_bytes",
    "action_count",
)


def service_cost(service: ServiceNode) -> int:
    """Integer-scaled declared resource and authority-exposure cost."""

    demand = service.demand
    return (
        demand.energy_mj
        + demand.cpu_ms
        + demand.memory_mb_s
        + demand.storage_bytes // 1024
        + demand.network_bytes // 1024
        + demand.action_count * 100
        + service.authority_exposure_units
    )


def _zero_budget() -> dict[str, int]:
    return {name: 0 for name in _BUDGET_FIELDS}


def _add_budget(total: dict[str, int], demand: Budgets) -> None:
    for name in _BUDGET_FIELDS:
        total[name] += int(getattr(demand, name))


def _within(total: dict[str, int], limit: Budgets) -> bool:
    return all(total[name] <= getattr(limit, name) for name in _BUDGET_FIELDS)


def objective_for(
    graph: MissionGraph,
    context: MissionContext,
    selected: frozenset[str],
) -> tuple[int, int, int]:
    services = graph.service_map
    coverage = {
        capability.capability_id: sum(
            services[item].capability_units.get(capability.capability_id, 0) for item in selected
        )
        for capability in graph.capabilities
    }
    fairness_penalty = sum(
        min(context.starvation_ms.get(capability.capability_id, 0), 1_000_000) // 1000
        for capability in graph.capabilities
        if coverage[capability.capability_id] < capability.required_units
    )
    weighted_cost = sum(service_cost(services[item]) for item in selected) + fairness_penalty
    optional_utility = sum(services[item].optional_utility for item in selected)
    optional_utility += sum(
        capability.optional_utility
        for capability in graph.capabilities
        if not capability.mandatory
        and coverage[capability.capability_id] >= capability.required_units
    )
    return len(selected), weighted_cost, -optional_utility


def startup_order_for(graph: MissionGraph, selected: frozenset[str]) -> tuple[str, ...]:
    """Return a deterministic topological order for a selected service set."""

    service_map = graph.service_map
    remaining = set(selected)
    order: list[str] = []
    while remaining:
        ready = []
        for service_id in remaining:
            service = service_map[service_id]
            dependencies = (service.and_dependencies | service.startup_after) & selected
            dependencies |= frozenset().union(
                *(group & selected for group in service.alternative_groups)
            )
            if dependencies <= set(order):
                ready.append(service_id)
        if not ready:
            raise ValueError("selected service relation is cyclic or lacks a startup dependency")
        chosen = min(ready)
        order.append(chosen)
        remaining.remove(chosen)
    return tuple(order)


@dataclass(frozen=True, slots=True)
class ValidationCertificate:
    valid: bool
    graph_hash: str
    context_hash: str
    plan_hash: str
    validator_version: str
    checks: tuple[str, ...]
    failures: tuple[str, ...]
    recomputed_objective: tuple[int, int, int] | None
    schema_version: str = "edge-lifeline-mvsg-validation-v1"

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "valid": self.valid,
            "graph_hash": self.graph_hash,
            "context_hash": self.context_hash,
            "plan_hash": self.plan_hash,
            "validator_version": self.validator_version,
            "checks": list(self.checks),
            "failures": list(self.failures),
            "recomputed_objective": (
                None if self.recomputed_objective is None else list(self.recomputed_objective)
            ),
        }

    def certificate_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))


class PlanValidator:
    """Validate a solver incumbent without importing or trusting OR-Tools."""

    def validate(
        self,
        graph: MissionGraph,
        context: MissionContext,
        plan: MissionPlan,
    ) -> ValidationCertificate:
        failures: list[str] = []
        checks: list[str] = []
        expected_graph_hash = graph.graph_hash()
        expected_context_hash = context.context_hash()
        if plan.graph_hash != expected_graph_hash:
            failures.append("GRAPH_HASH_MISMATCH")
        else:
            checks.append("GRAPH_HASH_BOUND")
        if plan.context_hash != expected_context_hash:
            failures.append("CONTEXT_HASH_MISMATCH")
        else:
            checks.append("CONTEXT_HASH_BOUND")
        if context.authority.mvsg_hash != expected_graph_hash:
            failures.append("AUTHORITY_MVSG_HASH_MISMATCH")
        else:
            checks.append("AUTHORITY_MVSG_BOUND")

        service_map = graph.service_map
        placements: dict[str, str] = {}
        for service_id, site_id in plan.placements:
            if service_id in placements:
                failures.append(f"DUPLICATE_PLACEMENT:{service_id}")
            placements[service_id] = site_id
        selected = frozenset(placements)
        unknown = selected - set(service_map)
        if unknown:
            failures.extend(f"UNKNOWN_SERVICE:{item}" for item in sorted(unknown))
        if set(plan.startup_order) != set(selected) or len(plan.startup_order) != len(selected):
            failures.append("STARTUP_ORDER_NOT_EXACT")

        if not unknown:
            self._validate_services(graph, context, placements, failures, checks)
            self._validate_graph_constraints(graph, placements, failures, checks)
            ready_times = self._validate_startup(graph, placements, plan, failures, checks)
            self._validate_deadlines(graph, selected, ready_times, failures, checks)

        objective = None if unknown else objective_for(graph, context, selected)
        if objective is not None and plan.objective != objective:
            failures.append("OBJECTIVE_MISMATCH")
        elif objective is not None:
            checks.append("OBJECTIVE_RECOMPUTED")
        return ValidationCertificate(
            valid=not failures,
            graph_hash=expected_graph_hash,
            context_hash=expected_context_hash,
            plan_hash=plan.plan_hash(),
            validator_version=VALIDATOR_VERSION,
            checks=tuple(sorted(set(checks))),
            failures=tuple(sorted(set(failures))),
            recomputed_objective=objective,
        )

    def _validate_services(
        self,
        graph: MissionGraph,
        context: MissionContext,
        placements: dict[str, str],
        failures: list[str],
        checks: list[str],
    ) -> None:
        authority = context.authority
        total = _zero_budget()
        by_site = {site.site_id: _zero_budget() for site in context.site_capacities}
        for service_id, site_id in placements.items():
            service = graph.service_map[service_id]
            if service_id in context.unavailable_services:
                failures.append(f"SERVICE_UNAVAILABLE:{service_id}")
            if (
                site_id not in service.allowed_sites
                or site_id not in context.available_sites
                or site_id not in authority.sites
            ):
                failures.append(f"LOCALITY_VIOLATION:{service_id}:{site_id}")
            if not service.required_actions <= authority.actions:
                failures.append(f"ACTION_AUTHORITY_MISSING:{service_id}")
            if not service.required_resources <= authority.resources:
                failures.append(f"RESOURCE_AUTHORITY_MISSING:{service_id}")
            if service.required_impact > authority.max_impact:
                failures.append(f"IMPACT_AUTHORITY_EXCEEDED:{service_id}")
            if context.approval_level < max(service.required_approval, authority.min_approval):
                failures.append(f"APPROVAL_INSUFFICIENT:{service_id}")
            if context.security_posture < max(
                service.required_security_posture,
                authority.min_security_posture,
            ):
                failures.append(f"SECURITY_POSTURE_INSUFFICIENT:{service_id}")
            if context.sensor_confidence_per_mille < max(
                service.min_sensor_confidence_per_mille,
                authority.min_sensor_confidence_per_mille,
            ):
                failures.append(f"SENSOR_CONFIDENCE_INSUFFICIENT:{service_id}")
            for data_id, max_age in service.data_max_age_ms.items():
                observed = context.data_age_ms.get(data_id)
                if observed is None:
                    failures.append(f"DATA_EVIDENCE_MISSING:{service_id}:{data_id}")
                elif observed > min(max_age, authority.max_data_age_ms):
                    failures.append(f"DATA_STALE:{service_id}:{data_id}")
            _add_budget(total, service.demand)
            if site_id in by_site:
                _add_budget(by_site[site_id], service.demand)
        if not _within(total, authority.budgets):
            failures.append("AGGREGATE_AUTHORITY_BUDGET_EXCEEDED")
        for site_id, demand in by_site.items():
            if not _within(demand, context.capacity_map[site_id]):
                failures.append(f"SITE_CAPACITY_EXCEEDED:{site_id}")
        if not any(
            item.startswith(
                (
                    "SERVICE_",
                    "LOCALITY_",
                    "ACTION_",
                    "RESOURCE_",
                    "IMPACT_",
                    "APPROVAL_",
                    "SECURITY_",
                    "SENSOR_",
                    "DATA_",
                    "AGGREGATE_",
                    "SITE_",
                )
            )
            for item in failures
        ):
            checks.extend(("SERVICE_ELIGIBILITY", "AUTHORITY_BUDGET", "SITE_CAPACITY"))

    def _validate_graph_constraints(
        self,
        graph: MissionGraph,
        placements: dict[str, str],
        failures: list[str],
        checks: list[str],
    ) -> None:
        selected = frozenset(placements)
        coverage = {item.capability_id: 0 for item in graph.capabilities}
        for service_id in selected:
            service = graph.service_map[service_id]
            if not service.and_dependencies <= selected:
                failures.append(f"AND_DEPENDENCY_MISSING:{service_id}")
            for index, group in enumerate(service.alternative_groups):
                if not group & selected:
                    failures.append(f"OR_DEPENDENCY_MISSING:{service_id}:{index}")
            for capability_id, units in service.capability_units.items():
                coverage[capability_id] += units
        for capability in graph.capabilities:
            if (
                capability.mandatory
                and coverage[capability.capability_id] < capability.required_units
            ):
                failures.append(f"MANDATORY_CAPABILITY_MISSING:{capability.capability_id}")
        for first, second in graph.exclusions:
            if first in selected and second in selected:
                failures.append(f"MUTUAL_EXCLUSION_VIOLATION:{first}:{second}")
        for requirement in graph.redundancy:
            chosen = requirement.members & selected
            if len(chosen) < requirement.minimum_selected:
                failures.append(f"REDUNDANCY_COUNT_INSUFFICIENT:{requirement.requirement_id}")
            if requirement.distinct_sites:
                sites = {placements[item] for item in chosen}
                if len(sites) < requirement.minimum_selected:
                    failures.append(f"REDUNDANCY_SITE_INSUFFICIENT:{requirement.requirement_id}")
        if not any(
            item.startswith(("AND_", "OR_", "MANDATORY_", "MUTUAL_", "REDUNDANCY_"))
            for item in failures
        ):
            checks.extend(("DEPENDENCY_CLOSURE", "MISSION_COVERAGE", "EXCLUSION", "REDUNDANCY"))

    def _validate_startup(
        self,
        graph: MissionGraph,
        placements: dict[str, str],
        plan: MissionPlan,
        failures: list[str],
        checks: list[str],
    ) -> dict[str, int]:
        selected = frozenset(placements)
        position = {item: index for index, item in enumerate(plan.startup_order)}
        ready: dict[str, int] = {}
        for service_id in plan.startup_order:
            if service_id not in selected:
                continue
            service = graph.service_map[service_id]
            hard_dependencies = service.and_dependencies | service.startup_after
            for dependency in hard_dependencies:
                if (
                    dependency in selected
                    and position.get(dependency, len(selected)) >= position[service_id]
                ):
                    failures.append(f"STARTUP_ORDER_VIOLATION:{service_id}:{dependency}")
            selected_alt: list[str] = []
            for group in service.alternative_groups:
                candidates = sorted(
                    group & selected, key=lambda item: position.get(item, len(selected))
                )
                if candidates:
                    selected_alt.extend(candidates)
                    for candidate in candidates:
                        if position.get(candidate, len(selected)) >= position[service_id]:
                            failures.append(f"STARTUP_ORDER_VIOLATION:{service_id}:{candidate}")
            dependencies = [item for item in hard_dependencies if item in ready]
            dependencies.extend(item for item in selected_alt if item in ready)
            ready[service_id] = (
                max((ready[item] for item in dependencies), default=0) + service.startup_time_ms
            )
        if not any(item.startswith("STARTUP_") for item in failures):
            checks.append("STARTUP_ORDER")
        return ready

    def _validate_deadlines(
        self,
        graph: MissionGraph,
        selected: frozenset[str],
        ready: dict[str, int],
        failures: list[str],
        checks: list[str],
    ) -> None:
        for capability in graph.capabilities:
            completions = [
                (item, ready[item] + graph.service_map[item].response_latency_ms)
                for item in selected
                if graph.service_map[item].capability_units.get(capability.capability_id, 0) > 0
                and item in ready
            ]
            if capability.mandatory and (
                not completions
                or min(completion for _item, completion in completions) > capability.deadline_ms
            ):
                failures.append(f"CAPABILITY_DEADLINE_MISSED:{capability.capability_id}")
            for service_id, completion in completions:
                if completion > capability.deadline_ms:
                    failures.append(
                        f"SERVICE_DEADLINE_MISSED:{service_id}:{capability.capability_id}"
                    )
        for constraint in graph.latency_constraints:
            if set(constraint.service_ids) <= selected:
                latency = sum(
                    graph.service_map[item].response_latency_ms for item in constraint.service_ids
                )
                if latency > constraint.maximum_latency_ms:
                    failures.append(f"PATH_LATENCY_EXCEEDED:{constraint.constraint_id}")
        if not any(
            item.startswith(("CAPABILITY_DEADLINE_", "SERVICE_DEADLINE_", "PATH_LATENCY_"))
            for item in failures
        ):
            checks.append("DEADLINES")
