"""Engineering-only Phase 4 CP-SAT and independent-validator benchmark."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path
from typing import Any

from edge_lifeline.mission.fixtures import context_for, synthetic_hospital_graph
from edge_lifeline.mission.optimizer import MissionOptimizer
from edge_lifeline.mission.validator import PlanValidator


def _summary(samples: list[int]) -> dict[str, float | int]:
    ordered = sorted(samples)
    p95_index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return {
        "count": len(samples),
        "min_ns": ordered[0],
        "median_ns": statistics.median(ordered),
        "mean_ns": statistics.fmean(ordered),
        "p95_ns": ordered[p95_index],
        "max_ns": ordered[-1],
        "population_stdev_ns": statistics.pstdev(ordered),
    }


def benchmark(iterations: int, warmup: int) -> dict[str, Any]:
    if iterations < 1 or warmup < 0:
        raise ValueError("iterations must be positive and warmup cannot be negative")
    graph = synthetic_hospital_graph()
    context = context_for(graph)
    optimizer = MissionOptimizer()
    validator = PlanValidator()
    accepted = optimizer.optimize(graph, context)
    if accepted.plan is None or accepted.certificate is None or not accepted.certificate.valid:
        raise RuntimeError("benchmark fixture is not feasible")
    for _ in range(warmup):
        optimizer.optimize(graph, context)
        validator.validate(graph, context, accepted.plan)
    solve_samples: list[int] = []
    validation_samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = optimizer.optimize(graph, context)
        solve_samples.append(time.perf_counter_ns() - started)
        if result.plan is None:
            raise RuntimeError("optimizer returned no benchmark plan")
        started = time.perf_counter_ns()
        certificate = validator.validate(graph, context, result.plan)
        validation_samples.append(time.perf_counter_ns() - started)
        if not certificate.valid:
            raise RuntimeError("independent validator rejected benchmark plan")
    return {
        "schema_version": "phase4-mvsg-benchmark-v1",
        "synthetic_nonclinical": True,
        "engineering_validation_only": True,
        "no_acceptance_threshold": True,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "solver": "OR-Tools CP-SAT",
        "validator": "phase4-validator-v1",
        "iterations": iterations,
        "warmup_iterations": warmup,
        "graph_hash": graph.graph_hash(),
        "context_hash": context.context_hash(),
        "plan_hash": accepted.plan.plan_hash(),
        "selected_service_count": len(accepted.plan.selected_services),
        "objective": list(accepted.plan.objective),
        "optimization": _summary(solve_samples),
        "independent_validation": _summary(validation_samples),
        "raw_optimization_ns": solve_samples,
        "raw_independent_validation_ns": validation_samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--warmup", type=int, default=25)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(benchmark(args.iterations, args.warmup), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
