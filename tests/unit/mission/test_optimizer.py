from __future__ import annotations

from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from edge_lifeline.mission.fixtures import (
    context_for,
    small_oracle_graph,
    synthetic_hospital_graph,
)
from edge_lifeline.mission.optimizer import MissionOptimizer
from edge_lifeline.mission.oracle import brute_force_optimum
from edge_lifeline.mission.validator import PlanValidator, ValidationCertificate


class _RejectingValidator(PlanValidator):
    def validate(self, graph, context, plan) -> ValidationCertificate:  # type: ignore[no-untyped-def]
        certificate = super().validate(graph, context, plan)
        return replace(certificate, valid=False, failures=("INJECTED_REJECTION",))


def test_cp_sat_matches_brute_force_oracle() -> None:
    graph = small_oracle_graph()
    context = context_for(graph)
    result = MissionOptimizer().optimize(graph, context)
    oracle = brute_force_optimum(graph, context)
    assert result.decision == "SELECT_MVSG"
    assert result.certificate is not None and result.certificate.valid
    assert result.plan is not None and oracle is not None
    assert result.plan.objective == oracle.objective
    assert "fast" in result.plan.selected_services
    assert "slow" not in result.plan.selected_services


def test_hospital_graph_selects_minimum_valid_service_graph() -> None:
    graph = synthetic_hospital_graph()
    context = context_for(graph)
    result = MissionOptimizer().optimize(graph, context)
    assert result.decision == "SELECT_MVSG"
    assert result.reason == "LEXICOGRAPHIC_OPTIMUM_VALIDATED"
    assert result.plan is not None
    assert result.certificate is not None and result.certificate.valid
    assert {
        "essential-monitor-a",
        "essential-monitor-b",
        "local-network",
        "medication-allergy-cache",
        "clinical-event-recorder",
    } <= result.plan.selected_services
    assert "external-route" not in result.plan.selected_services
    assert "audit-dashboard" not in result.plan.selected_services
    assert result.plan.optimized_stages == 3


def test_zero_timeout_fails_safe_without_prior_plan() -> None:
    graph = small_oracle_graph()
    result = MissionOptimizer().optimize(graph, context_for(graph), timeout_seconds=0)
    assert result.decision == "SAFE_SHUTDOWN"
    assert result.plan is None
    assert result.reason == "SOLVER_TIMEOUT_WITHOUT_INCUMBENT"


def test_timeout_can_retain_only_a_revalidated_previous_plan() -> None:
    graph = small_oracle_graph()
    context = context_for(graph)
    accepted = MissionOptimizer().optimize(graph, context)
    assert accepted.plan is not None
    retained = MissionOptimizer().optimize(
        graph,
        context,
        timeout_seconds=0,
        previous_plan=accepted.plan,
    )
    assert retained.decision == "RETAIN_LAST_VALID_MVSG"
    assert retained.certificate is not None and retained.certificate.valid


def test_invalid_previous_plan_is_not_used_as_timeout_fallback() -> None:
    graph = small_oracle_graph()
    context = context_for(graph)
    accepted = MissionOptimizer().optimize(graph, context)
    assert accepted.plan is not None
    broken = replace(accepted.plan, placements=(("mission", "edge-a"),))
    result = MissionOptimizer().optimize(
        graph,
        context,
        timeout_seconds=0,
        previous_plan=broken,
    )
    assert result.decision == "SAFE_SHUTDOWN"


def test_resource_infeasibility_fails_safe() -> None:
    graph = synthetic_hospital_graph()
    result = MissionOptimizer().optimize(graph, context_for(graph, energy_mj=1))
    assert result.decision == "SAFE_SHUTDOWN"
    assert result.reason == "MISSION_GRAPH_INFEASIBLE"


def test_independent_validator_rejection_fails_safe() -> None:
    graph = small_oracle_graph()
    result = MissionOptimizer(_RejectingValidator()).optimize(graph, context_for(graph))
    assert result.decision == "SAFE_SHUTDOWN"
    assert result.plan is None
    assert result.reason == "SOLVER_INCUMBENT_REJECTED_BY_INDEPENDENT_VALIDATOR"


@given(fast_exposure=st.integers(min_value=0, max_value=50), slow_delta=st.integers(1, 50))
@settings(max_examples=30, deadline=None)
def test_cp_sat_and_oracle_agree_across_declared_costs(
    fast_exposure: int,
    slow_delta: int,
) -> None:
    graph = small_oracle_graph()
    services = tuple(
        replace(
            item,
            authority_exposure_units=(
                fast_exposure
                if item.service_id == "fast"
                else fast_exposure + slow_delta
                if item.service_id == "slow"
                else item.authority_exposure_units
            ),
        )
        for item in graph.services
    )
    graph = replace(graph, services=services)
    context = context_for(graph)
    result = MissionOptimizer().optimize(graph, context)
    oracle = brute_force_optimum(graph, context)
    assert result.plan is not None and oracle is not None
    assert result.plan.objective == oracle.objective
