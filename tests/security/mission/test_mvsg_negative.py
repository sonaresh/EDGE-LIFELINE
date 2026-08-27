from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from edge_lifeline.formal.authority import Budgets, ImpactClass
from edge_lifeline.mission.fixtures import context_for, small_oracle_graph, synthetic_hospital_graph
from edge_lifeline.mission.model import MissionContext, MissionGraph, MissionPlan, SiteCapacity
from edge_lifeline.mission.optimizer import MissionOptimizer
from edge_lifeline.mission.validator import PlanValidator, objective_for, startup_order_for

pytestmark = pytest.mark.security


def _accepted() -> tuple[MissionGraph, MissionContext, MissionPlan]:
    graph = small_oracle_graph()
    context = context_for(graph)
    result = MissionOptimizer().optimize(graph, context)
    assert result.plan is not None
    return graph, context, result.plan


@pytest.mark.parametrize(
    ("mutation", "failure"),
    [
        (lambda plan: replace(plan, graph_hash="0" * 64), "GRAPH_HASH_MISMATCH"),
        (lambda plan: replace(plan, context_hash="0" * 64), "CONTEXT_HASH_MISMATCH"),
        (lambda plan: replace(plan, objective=(0, 0, 0)), "OBJECTIVE_MISMATCH"),
        (
            lambda plan: replace(plan, startup_order=tuple(reversed(plan.startup_order))),
            "STARTUP_ORDER_VIOLATION",
        ),
        (
            lambda plan: replace(
                plan,
                placements=(*plan.placements, plan.placements[0]),
            ),
            "DUPLICATE_PLACEMENT",
        ),
        (lambda plan: replace(plan, placements=(("unknown", "edge-a"),)), "UNKNOWN_SERVICE"),
    ],
)
def test_validator_rejects_mutated_plan(
    mutation: Callable[[MissionPlan], MissionPlan],
    failure: str,
) -> None:
    graph, context, plan = _accepted()
    changed = mutation(plan)
    certificate = PlanValidator().validate(graph, context, changed)
    assert not certificate.valid
    assert any(item.startswith(failure) for item in certificate.failures)


def test_validator_rejects_missing_and_or_dependencies() -> None:
    graph, context, accepted = _accepted()
    selected = frozenset({"mission", "base"})
    plan = replace(
        accepted,
        placements=(("base", "edge-a"), ("mission", "edge-a")),
        startup_order=startup_order_for(graph, selected),
        objective=objective_for(graph, context, selected),
    )
    certificate = PlanValidator().validate(graph, context, plan)
    assert not certificate.valid
    assert "OR_DEPENDENCY_MISSING:mission:0" in certificate.failures


def test_validator_rejects_both_mutually_exclusive_alternatives() -> None:
    graph, context, accepted = _accepted()
    selected = frozenset({"base", "fast", "slow", "mission"})
    plan = replace(
        accepted,
        placements=tuple((item, "edge-a") for item in sorted(selected)),
        startup_order=startup_order_for(graph, selected),
        objective=objective_for(graph, context, selected),
    )
    certificate = PlanValidator().validate(graph, context, plan)
    assert "MUTUAL_EXCLUSION_VIOLATION:fast:slow" in certificate.failures


def test_validator_rejects_authority_graph_hash_mismatch() -> None:
    graph, context, plan = _accepted()
    changed = replace(context, authority=replace(context.authority, mvsg_hash="f" * 64))
    certificate = PlanValidator().validate(
        graph, changed, replace(plan, context_hash=changed.context_hash())
    )
    assert "AUTHORITY_MVSG_HASH_MISMATCH" in certificate.failures


def test_optimizer_rejects_stale_mandatory_data() -> None:
    graph = synthetic_hospital_graph()
    context = context_for(graph)
    changed = replace(context, data_age_ms={**context.data_age_ms, "safety-snapshot": 60_001})
    result = MissionOptimizer().optimize(graph, changed)
    assert result.decision == "SAFE_SHUTDOWN"


def test_optimizer_rejects_insufficient_sensor_confidence() -> None:
    graph = synthetic_hospital_graph()
    context = replace(context_for(graph), sensor_confidence_per_mille=799)
    result = MissionOptimizer().optimize(graph, context)
    assert result.decision == "SAFE_SHUTDOWN"


def test_validator_rejects_site_capacity_oversubscription() -> None:
    graph, context, plan = _accepted()
    tiny = Budgets(0, 0, 0, 0, 0, 0)
    changed = replace(
        context,
        site_capacities=(SiteCapacity("edge-a", tiny), SiteCapacity("edge-b", tiny)),
    )
    rebound = replace(plan, context_hash=changed.context_hash())
    certificate = PlanValidator().validate(graph, changed, rebound)
    assert any(item.startswith("SITE_CAPACITY_EXCEEDED") for item in certificate.failures)


def test_optimizer_rejects_authority_impact_contraction() -> None:
    graph = small_oracle_graph()
    services = tuple(
        replace(item, required_impact=ImpactClass.REVERSIBLE_PHYSICAL)
        if item.service_id == "mission"
        else item
        for item in graph.services
    )
    graph = replace(graph, services=services)
    result = MissionOptimizer().optimize(graph, context_for(graph))
    assert result.decision == "SAFE_SHUTDOWN"


def test_validator_rejects_redundancy_collocated_on_one_site() -> None:
    graph = synthetic_hospital_graph()
    context = context_for(graph)
    result = MissionOptimizer().optimize(graph, context)
    assert result.plan is not None
    placements = tuple(
        (service, "edge-a" if service == "essential-monitor-b" else site)
        for service, site in result.plan.placements
    )
    changed = replace(result.plan, placements=placements)
    certificate = PlanValidator().validate(graph, context, changed)
    assert any(
        item.startswith(("LOCALITY_VIOLATION", "REDUNDANCY_SITE_INSUFFICIENT"))
        for item in certificate.failures
    )


def test_validator_rejects_any_selected_service_that_misses_its_deadline() -> None:
    graph = small_oracle_graph()
    services = tuple(
        replace(
            item,
            capability_units={"mission": 1},
            startup_time_ms=200,
        )
        if item.service_id == "slow"
        else item
        for item in graph.services
    )
    graph = replace(graph, services=services, exclusions=())
    context = context_for(graph)
    selected = frozenset({"base", "fast", "slow", "mission"})
    plan = MissionPlan(
        graph_hash=graph.graph_hash(),
        context_hash=context.context_hash(),
        placements=tuple((item, "edge-a") for item in sorted(selected)),
        startup_order=startup_order_for(graph, selected),
        objective=objective_for(graph, context, selected),
        solver_status="SECURITY_TEST",
        optimized_stages=0,
    )
    certificate = PlanValidator().validate(graph, context, plan)
    assert "SERVICE_DEADLINE_MISSED:slow:mission" in certificate.failures
