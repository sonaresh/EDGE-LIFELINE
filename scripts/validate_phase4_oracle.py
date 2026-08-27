"""Produce Phase 4 CP-SAT versus brute-force oracle conformance evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from edge_lifeline.mission.fixtures import context_for, small_oracle_graph
from edge_lifeline.mission.optimizer import MissionOptimizer
from edge_lifeline.mission.oracle import brute_force_optimum


def validate_cases(case_count: int) -> dict[str, Any]:
    if case_count < 1:
        raise ValueError("case count must be positive")
    cases: list[dict[str, Any]] = []
    for index in range(case_count):
        graph = small_oracle_graph()
        fast_cost = index % 11
        slow_cost = fast_cost + 1 + ((index * 7) % 19)
        services = tuple(
            replace(
                item,
                authority_exposure_units=(
                    fast_cost
                    if item.service_id == "fast"
                    else slow_cost
                    if item.service_id == "slow"
                    else item.authority_exposure_units
                ),
            )
            for item in graph.services
        )
        graph = replace(graph, services=services, graph_version=f"oracle-{index}")
        context = context_for(graph)
        solver = MissionOptimizer().optimize(graph, context, random_seed=index)
        oracle = brute_force_optimum(graph, context)
        passed = (
            solver.plan is not None
            and solver.certificate is not None
            and solver.certificate.valid
            and oracle is not None
            and solver.plan.objective == oracle.objective
        )
        cases.append(
            {
                "case": index,
                "graph_hash": graph.graph_hash(),
                "fast_exposure": fast_cost,
                "slow_exposure": slow_cost,
                "solver_objective": None if solver.plan is None else list(solver.plan.objective),
                "oracle_objective": None if oracle is None else list(oracle.objective),
                "passed": passed,
            }
        )
    return {
        "schema_version": "phase4-oracle-conformance-v1",
        "synthetic_nonclinical": True,
        "independent_oracle": "brute-force subset and placement enumeration",
        "case_count": case_count,
        "passed_count": sum(bool(item["passed"]) for item in cases),
        "all_passed": all(bool(item["passed"]) for item in cases),
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=30)
    args = parser.parse_args()
    report = validate_cases(args.cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not report["all_passed"]:
        raise SystemExit("CP-SAT and brute-force oracle objectives differ")


if __name__ == "__main__":
    main()
