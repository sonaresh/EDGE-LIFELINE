"""Deterministic CP-SAT Mission-Viable Service Graph optimizer."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ortools.sat.python import cp_model

from edge_lifeline.mission.model import MissionContext, MissionGraph, MissionPlan, ServiceNode
from edge_lifeline.mission.validator import (
    PlanValidator,
    ValidationCertificate,
    objective_for,
    service_cost,
    startup_order_for,
)

_BUDGET_FIELDS = (
    "energy_mj",
    "cpu_ms",
    "memory_mb_s",
    "storage_bytes",
    "network_bytes",
    "action_count",
)


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    decision: str
    plan: MissionPlan | None
    certificate: ValidationCertificate | None
    reason: str
    solver_wall_time_ms: int
    schema_version: str = "edge-lifeline-mvsg-result-v1"


@dataclass(slots=True)
class _Variables:
    selected: dict[str, cp_model.IntVar]
    placed: dict[tuple[str, str], cp_model.IntVar]
    capability_met: dict[str, cp_model.IntVar]
    ready_ms: dict[str, cp_model.IntVar]
    count: cp_model.LinearExpr
    weighted_cost: cp_model.LinearExpr
    optional_utility: cp_model.LinearExpr


class MissionOptimizer:
    def __init__(self, validator: PlanValidator | None = None) -> None:
        self._validator = validator or PlanValidator()

    def optimize(
        self,
        graph: MissionGraph,
        context: MissionContext,
        *,
        timeout_seconds: float = 5.0,
        random_seed: int = 0,
        previous_plan: MissionPlan | None = None,
    ) -> OptimizationResult:
        started = time.monotonic()
        if timeout_seconds <= 0:
            return self._fallback(
                graph,
                context,
                previous_plan,
                "SOLVER_TIMEOUT_WITHOUT_INCUMBENT",
                started,
            )
        model = cp_model.CpModel()
        variables = self._build_model(model, graph, context)
        last_valid: tuple[MissionPlan, ValidationCertificate] | None = None
        stages: tuple[tuple[str, cp_model.LinearExpr, bool], ...] = (
            ("MIN_SERVICE_COUNT", variables.count, False),
            ("MIN_WEIGHTED_EXPOSURE", variables.weighted_cost, False),
            ("MAX_OPTIONAL_UTILITY", variables.optional_utility, True),
        )
        for stage_number, (stage_name, expression, maximize) in enumerate(stages, start=1):
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                break
            if maximize:
                model.maximize(expression)
            else:
                model.minimize(expression)
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = remaining
            solver.parameters.num_search_workers = 1
            solver.parameters.random_seed = random_seed
            solver.parameters.log_search_progress = False
            status = solver.solve(model)
            if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
                if status == cp_model.INFEASIBLE and last_valid is None:
                    return self._fallback(
                        graph,
                        context,
                        previous_plan,
                        "MISSION_GRAPH_INFEASIBLE",
                        started,
                    )
                break
            plan = self._plan_from_solution(
                graph,
                context,
                solver,
                variables,
                f"{stage_name}:{solver.status_name(status)}",
                stage_number if status == cp_model.OPTIMAL else stage_number - 1,
            )
            certificate = self._validator.validate(graph, context, plan)
            if not certificate.valid:
                return self._fallback(
                    graph,
                    context,
                    previous_plan,
                    "SOLVER_INCUMBENT_REJECTED_BY_INDEPENDENT_VALIDATOR",
                    started,
                )
            last_valid = plan, certificate
            if status != cp_model.OPTIMAL:
                break
            optimum = round(solver.value(expression))
            model.add(expression == optimum)
        if last_valid is None:
            return self._fallback(
                graph,
                context,
                previous_plan,
                "SOLVER_TIMEOUT_WITHOUT_VALID_INCUMBENT",
                started,
            )
        plan, certificate = last_valid
        fully_optimized = plan.optimized_stages == len(stages)
        return OptimizationResult(
            decision="SELECT_MVSG" if fully_optimized else "SELECT_VALIDATED_INCUMBENT",
            plan=plan,
            certificate=certificate,
            reason=(
                "LEXICOGRAPHIC_OPTIMUM_VALIDATED"
                if fully_optimized
                else "TIME_LIMIT_REACHED_VALIDATED_INCUMBENT"
            ),
            solver_wall_time_ms=int((time.monotonic() - started) * 1000),
        )

    def _build_model(
        self,
        model: cp_model.CpModel,
        graph: MissionGraph,
        context: MissionContext,
    ) -> _Variables:
        selected = {
            item.service_id: model.new_bool_var(f"selected__{item.service_id}")
            for item in graph.services
        }
        placed: dict[tuple[str, str], cp_model.IntVar] = {}
        for service in graph.services:
            candidates = sorted(
                service.allowed_sites & context.available_sites & context.authority.sites
            )
            for site_id in candidates:
                placed[(service.service_id, site_id)] = model.new_bool_var(
                    f"placed__{service.service_id}__{site_id}"
                )
            model.add(
                sum(placed[(service.service_id, site)] for site in candidates)
                == selected[service.service_id]
            )
            if not self._eligible(service, context):
                model.add(selected[service.service_id] == 0)

        for service in graph.services:
            own = selected[service.service_id]
            for dependency in service.and_dependencies | service.startup_after:
                model.add(own <= selected[dependency])
            for group in service.alternative_groups:
                model.add(own <= sum(selected[item] for item in group))
        for first, second in graph.exclusions:
            model.add(selected[first] + selected[second] <= 1)
        for requirement in graph.redundancy:
            model.add(
                sum(selected[item] for item in requirement.members) >= requirement.minimum_selected
            )
            if requirement.distinct_sites:
                site_used = []
                for site_id in sorted(context.available_sites):
                    member_vars = [
                        placed[(member, site_id)]
                        for member in requirement.members
                        if (member, site_id) in placed
                    ]
                    if not member_vars:
                        continue
                    used = model.new_bool_var(
                        f"redundancy__{requirement.requirement_id}__{site_id}"
                    )
                    model.add(sum(member_vars) >= used)
                    model.add(sum(member_vars) <= len(member_vars) * used)
                    site_used.append(used)
                model.add(sum(site_used) >= requirement.minimum_selected)

        capability_met: dict[str, cp_model.IntVar] = {}
        for capability in graph.capabilities:
            coverage = sum(
                item.capability_units.get(capability.capability_id, 0) * selected[item.service_id]
                for item in graph.services
            )
            maximum = sum(
                item.capability_units.get(capability.capability_id, 0) for item in graph.services
            )
            met = model.new_bool_var(f"capability__{capability.capability_id}")
            capability_met[capability.capability_id] = met
            model.add(coverage >= capability.required_units * met)
            model.add(coverage <= (capability.required_units - 1) + maximum * met)
            if capability.mandatory:
                model.add(met == 1)

        for site_id, capacity in context.capacity_map.items():
            for field in _BUDGET_FIELDS:
                model.add(
                    sum(
                        getattr(service.demand, field) * placed[(service.service_id, site_id)]
                        for service in graph.services
                        if (service.service_id, site_id) in placed
                    )
                    <= getattr(capacity, field)
                )
        for field in _BUDGET_FIELDS:
            model.add(
                sum(
                    getattr(service.demand, field) * selected[service.service_id]
                    for service in graph.services
                )
                <= getattr(context.authority.budgets, field)
            )

        horizon = sum(item.startup_time_ms for item in graph.services) + 1
        ready_ms = {
            item.service_id: model.new_int_var(0, horizon, f"ready__{item.service_id}")
            for item in graph.services
        }
        for service in graph.services:
            own = selected[service.service_id]
            ready = ready_ms[service.service_id]
            model.add(ready == 0).only_enforce_if(own.Not())
            model.add(ready >= service.startup_time_ms).only_enforce_if(own)
            for dependency in service.and_dependencies | service.startup_after:
                model.add(ready >= ready_ms[dependency] + service.startup_time_ms).only_enforce_if(
                    own
                )
            for group in service.alternative_groups:
                for dependency in group:
                    model.add(
                        ready >= ready_ms[dependency] + service.startup_time_ms
                    ).only_enforce_if([own, selected[dependency]])
            for capability_id, units in service.capability_units.items():
                if units:
                    deadline = graph.capability_map[capability_id].deadline_ms
                    model.add(ready + service.response_latency_ms <= deadline).only_enforce_if(own)
        for constraint in graph.latency_constraints:
            active = [selected[item] for item in constraint.service_ids]
            model.add(
                sum(graph.service_map[item].response_latency_ms for item in constraint.service_ids)
                <= constraint.maximum_latency_ms
            ).only_enforce_if(active)

        count = cp_model.LinearExpr.sum(list(selected.values()))
        fairness_terms = [
            (min(context.starvation_ms.get(item.capability_id, 0), 1_000_000) // 1000)
            * (1 - capability_met[item.capability_id])
            for item in graph.capabilities
        ]
        weighted_cost = cp_model.LinearExpr.sum(
            [service_cost(item) * selected[item.service_id] for item in graph.services]
            + fairness_terms
        )
        optional_utility = cp_model.LinearExpr.sum(
            [item.optional_utility * selected[item.service_id] for item in graph.services]
            + [
                item.optional_utility * capability_met[item.capability_id]
                for item in graph.capabilities
                if not item.mandatory
            ]
        )
        return _Variables(
            selected,
            placed,
            capability_met,
            ready_ms,
            count,
            weighted_cost,
            optional_utility,
        )

    @staticmethod
    def _eligible(service: ServiceNode, context: MissionContext) -> bool:
        authority = context.authority
        if service.service_id in context.unavailable_services:
            return False
        if not service.required_actions <= authority.actions:
            return False
        if not service.required_resources <= authority.resources:
            return False
        if service.required_impact > authority.max_impact:
            return False
        if context.approval_level < max(service.required_approval, authority.min_approval):
            return False
        if context.security_posture < max(
            service.required_security_posture,
            authority.min_security_posture,
        ):
            return False
        if context.sensor_confidence_per_mille < max(
            service.min_sensor_confidence_per_mille,
            authority.min_sensor_confidence_per_mille,
        ):
            return False
        return all(
            data_id in context.data_age_ms
            and context.data_age_ms[data_id] <= min(max_age, authority.max_data_age_ms)
            for data_id, max_age in service.data_max_age_ms.items()
        )

    @staticmethod
    def _plan_from_solution(
        graph: MissionGraph,
        context: MissionContext,
        solver: cp_model.CpSolver,
        variables: _Variables,
        status: str,
        optimized_stages: int,
    ) -> MissionPlan:
        placements = tuple(
            sorted(
                key for key, variable in variables.placed.items() if solver.boolean_value(variable)
            )
        )
        selected = frozenset(service_id for service_id, _site_id in placements)
        return MissionPlan(
            graph_hash=graph.graph_hash(),
            context_hash=context.context_hash(),
            placements=placements,
            startup_order=startup_order_for(graph, selected),
            objective=objective_for(graph, context, selected),
            solver_status=status,
            optimized_stages=optimized_stages,
        )

    def _fallback(
        self,
        graph: MissionGraph,
        context: MissionContext,
        previous_plan: MissionPlan | None,
        reason: str,
        started: float,
    ) -> OptimizationResult:
        if previous_plan is not None and previous_plan.graph_hash == graph.graph_hash():
            selected = previous_plan.selected_services
            rebound = MissionPlan(
                graph_hash=graph.graph_hash(),
                context_hash=context.context_hash(),
                placements=previous_plan.placements,
                startup_order=startup_order_for(graph, selected),
                objective=objective_for(graph, context, selected),
                solver_status="REVALIDATED_PREVIOUS_PLAN",
                optimized_stages=0,
            )
            certificate = self._validator.validate(graph, context, rebound)
            if certificate.valid:
                return OptimizationResult(
                    decision="RETAIN_LAST_VALID_MVSG",
                    plan=rebound,
                    certificate=certificate,
                    reason=reason,
                    solver_wall_time_ms=int((time.monotonic() - started) * 1000),
                )
        return OptimizationResult(
            decision="SAFE_SHUTDOWN",
            plan=None,
            certificate=None,
            reason=reason,
            solver_wall_time_ms=int((time.monotonic() - started) * 1000),
        )
