"""Preregistered deterministic Phase 8 statistical summaries."""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from edge_lifeline.experiments.model import Method, RunResult

Metric = Callable[[RunResult], float]

PRIMARY_COMPARISONS: tuple[tuple[str, Method, str, str, tuple[str, ...]], ...] = (
    (
        "H1",
        Method.B0_FAIL_CLOSED,
        "critical_availability",
        "greater",
        ("E2", "E3", "E4", "E5", "E12", "E15"),
    ),
    (
        "H2",
        Method.B1_UNRESTRICTED,
        "unsafe_actions_executed",
        "less",
        ("E7", "E8", "E13", "E15", "E16", "E17", "E18", "E19", "E20"),
    ),
    (
        "H3",
        Method.B0_FAIL_CLOSED,
        "false_denials",
        "less",
        ("E2", "E3", "E4", "E5", "E12", "E15"),
    ),
    (
        "H5",
        Method.B6_STATIC_PRIORITY,
        "utility_per_resource",
        "greater",
        ("E10",),
    ),
    (
        "H6",
        Method.B5_LAST_WRITER_WINS,
        "incorrect_conflict_resolutions",
        "less",
        ("E11", "E14", "E20"),
    ),
    (
        "H7",
        Method.B3_FIXED_LEASE,
        "invariant_violations",
        "less",
        ("E12", "E16"),
    ),
    (
        "H8",
        Method.B1_UNRESTRICTED,
        "unsafe_actions_executed",
        "less",
        ("E8", "E13", "E15"),
    ),
    (
        "H9",
        Method.B2_STATIC_POLICY,
        "invariant_violations",
        "less",
        ("E13", "E17", "E19", "E20"),
    ),
)


def primary_comparison_spec() -> list[dict[str, Any]]:
    """Return the machine-checkable analysis registry used by the frozen protocol."""
    return [
        {
            "hypothesis": hypothesis,
            "baseline": baseline.value,
            "metric": metric,
            "direction": direction,
            "scenarios": list(scenarios),
            **(
                {"safety_guard": "mean invariant violations must not increase"}
                if hypothesis == "H3"
                else {}
            ),
        }
        for hypothesis, baseline, metric, direction, scenarios in PRIMARY_COMPARISONS
    ]


def _value(result: RunResult, metric: str) -> float:
    value = getattr(result, metric)
    if isinstance(value, bool):
        return float(value)
    return float(value)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _bootstrap_ci(differences: list[float], label: str) -> tuple[float, float]:
    rng_seed = int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")
    rng = random.Random(rng_seed)  # noqa: S311
    means = [statistics.fmean(rng.choice(differences) for _ in differences) for _ in range(2_000)]
    return _percentile(means, 0.025), _percentile(means, 0.975)


def _sign_flip_pvalue(differences: list[float], label: str) -> float:
    observed = abs(statistics.fmean(differences))
    rng_seed = int.from_bytes(hashlib.sha256((label + ":permutation").encode()).digest()[:8], "big")
    rng = random.Random(rng_seed)  # noqa: S311
    extreme = 0
    iterations = 10_000
    for _ in range(iterations):
        permuted = abs(
            statistics.fmean(item if rng.randrange(2) else -item for item in differences)
        )
        extreme += int(permuted >= observed)
    return (extreme + 1) / (iterations + 1)


def _holm(rows: list[dict[str, Any]]) -> None:
    ranked = sorted(enumerate(rows), key=lambda item: float(item[1]["p_value"]))
    adjusted = [1.0] * len(rows)
    running = 0.0
    count = len(rows)
    for rank, (original_index, row) in enumerate(ranked):
        candidate = min(1.0, (count - rank) * float(row["p_value"]))
        running = max(running, candidate)
        adjusted[original_index] = running
    for row, value in zip(rows, adjusted, strict=True):
        row["holm_adjusted_p_value"] = value


def analyze_results(results: Iterable[RunResult]) -> dict[str, Any]:
    rows = tuple(results)
    by_key = {(item.method, item.scenario_id, item.seed): item for item in rows}
    comparisons: list[dict[str, Any]] = []
    for hypothesis, baseline, metric, direction, scenarios in PRIMARY_COMPARISONS:
        differences: list[float] = []
        safety_guard_differences: list[float] = []
        for (method, scenario, seed), treatment in by_key.items():
            if method is not Method.EDGE_LIFELINE:
                continue
            if scenario not in scenarios:
                continue
            comparator = by_key[(baseline, scenario, seed)]
            raw = _value(treatment, metric) - _value(comparator, metric)
            differences.append(raw if direction == "greater" else -raw)
            safety_guard_differences.append(
                float(treatment.invariant_violations - comparator.invariant_violations)
            )
        label = f"{hypothesis}:{baseline.value}:{metric}"
        ci_low, ci_high = _bootstrap_ci(differences, label)
        comparisons.append(
            {
                "hypothesis": hypothesis,
                "treatment": Method.EDGE_LIFELINE.value,
                "baseline": baseline.value,
                "metric": metric,
                "scenarios": list(scenarios),
                "favorable_direction": direction,
                "paired_blocks": len(differences),
                "mean_favorable_difference": statistics.fmean(differences),
                "median_favorable_difference": statistics.median(differences),
                "bootstrap_95_ci": [ci_low, ci_high],
                "p_value": _sign_flip_pvalue(differences, label),
                "test": "paired sign-flip permutation",
                "result_interpretation": "estimate only; gate does not require a favorable outcome",
                "mean_invariant_violation_difference": statistics.fmean(safety_guard_differences),
                "safety_guard_non_increasing": statistics.fmean(safety_guard_differences) <= 0.0,
            }
        )
    _holm(comparisons)
    grouped: dict[str, list[RunResult]] = defaultdict(list)
    for result in rows:
        grouped[result.method.value].append(result)
    summaries = {}
    for method_name, items in sorted(grouped.items()):
        summaries[method_name] = {
            "runs": len(items),
            "mission_outcome_rate": statistics.fmean(float(x.mission_outcome) for x in items),
            "median_critical_availability": statistics.median(
                x.critical_availability for x in items
            ),
            "unsafe_actions_executed": sum(x.unsafe_actions_executed for x in items),
            "false_denials": sum(x.false_denials for x in items),
            "invariant_violations": sum(x.invariant_violations for x in items),
            "incorrect_conflict_resolutions": sum(x.incorrect_conflict_resolutions for x in items),
            "prohibited_effect_replays": sum(x.prohibited_effect_replays for x in items),
            "median_utility_per_resource": statistics.median(x.utility_per_resource for x in items),
        }
    return {
        "schema_version": "edge-lifeline-phase8-analysis-v1",
        "synthetic_nonclinical": True,
        "analysis_frozen_before_final_run": True,
        "run_count": len(rows),
        "method_summaries": summaries,
        "primary_comparisons": comparisons,
        "multiplicity_control": "Holm",
        "inference_boundary": (
            "Accelerated synthetic simulation; no clinical or production efficacy claim."
        ),
    }
