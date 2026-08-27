"""Brute-force reference oracle for small Phase 4 mission graphs."""

from __future__ import annotations

from itertools import combinations, product

from edge_lifeline.mission.model import MissionContext, MissionGraph, MissionPlan
from edge_lifeline.mission.validator import PlanValidator, objective_for, startup_order_for


def brute_force_optimum(
    graph: MissionGraph,
    context: MissionContext,
    *,
    maximum_services: int = 16,
) -> MissionPlan | None:
    """Enumerate subsets and placements without importing optimizer internals."""

    if len(graph.services) > maximum_services:
        raise ValueError("brute-force oracle is restricted to small graphs")
    validator = PlanValidator()
    service_ids = tuple(sorted(item.service_id for item in graph.services))
    best: MissionPlan | None = None
    for count in range(len(service_ids) + 1):
        for selected_tuple in combinations(service_ids, count):
            selected = frozenset(selected_tuple)
            site_options = [
                sorted(
                    graph.service_map[item].allowed_sites
                    & context.available_sites
                    & context.authority.sites
                )
                for item in selected_tuple
            ]
            if any(not options for options in site_options):
                continue
            for sites in product(*site_options):
                placements = tuple(zip(selected_tuple, sites, strict=True))
                try:
                    startup_order = startup_order_for(graph, selected)
                except ValueError:
                    continue
                plan = MissionPlan(
                    graph_hash=graph.graph_hash(),
                    context_hash=context.context_hash(),
                    placements=placements,
                    startup_order=startup_order,
                    objective=objective_for(graph, context, selected),
                    solver_status="BRUTE_FORCE_ORACLE",
                    optimized_stages=3,
                )
                if not validator.validate(graph, context, plan).valid:
                    continue
                if best is None or plan.objective < best.objective:
                    best = plan
        if best is not None:
            # Service count is the first lexicographic objective.
            break
    return best
