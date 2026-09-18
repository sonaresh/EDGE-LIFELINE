from __future__ import annotations

import hashlib

from edge_lifeline.experiments.analysis import analyze_results
from edge_lifeline.experiments.catalog import METHODS, SCENARIO_BY_ID, SCENARIOS
from edge_lifeline.experiments.harness import (
    decide,
    generate_trace,
    run_cell,
    run_experiment,
    trace_bytes,
)
from edge_lifeline.experiments.model import Method

PROTOCOL_SHA = "a" * 64


def test_catalog_has_all_declared_methods_and_scenarios() -> None:
    assert [item.value for item in METHODS] == ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "EL"]
    assert [item.scenario_id for item in SCENARIOS] == [f"E{index}" for index in range(1, 21)]
    assert SCENARIO_BY_ID["E9"].detection_only is True


def test_trace_is_deterministic_and_seed_specific() -> None:
    scenario = SCENARIO_BY_ID["E15"]
    first = trace_bytes(generate_trace(scenario, 1000))
    assert first == trace_bytes(generate_trace(scenario, 1000))
    assert first != trace_bytes(generate_trace(scenario, 1001))
    assert (
        hashlib.sha256(first).hexdigest()
        == run_cell(Method.EDGE_LIFELINE, scenario, 1000, PROTOCOL_SHA).trace_sha256
    )


def test_each_method_receives_the_same_paired_trace() -> None:
    results = run_experiment([1000], PROTOCOL_SHA)
    assert len(results) == 160
    for scenario in SCENARIOS:
        hashes = {item.trace_sha256 for item in results if item.scenario_id == scenario.scenario_id}
        assert len(hashes) == 1


def test_edge_lifeline_rejects_invalid_evidence_and_replay() -> None:
    scenario = SCENARIO_BY_ID["E17"]
    event = generate_trace(scenario, 1000)[0].model_copy(
        update={"evidence_supports_action": True, "replayed": True}
    )
    decision = decide(Method.EDGE_LIFELINE, scenario, event)
    assert decision.allow is False
    assert decision.replayed_effect is False


def test_resource_scheduler_is_more_efficient_than_static_priority() -> None:
    scenario = SCENARIO_BY_ID["E10"]
    treatment = run_cell(Method.EDGE_LIFELINE, scenario, 1000, PROTOCOL_SHA)
    baseline = run_cell(Method.B6_STATIC_PRIORITY, scenario, 1000, PROTOCOL_SHA)
    assert treatment.utility_per_resource > baseline.utility_per_resource


def test_analysis_uses_preregistered_paired_blocks_and_holm() -> None:
    analysis = analyze_results(run_experiment([1000, 1001], PROTOCOL_SHA))
    comparisons = analysis["primary_comparisons"]
    assert len(comparisons) == 8
    assert [item["hypothesis"] for item in comparisons] == [
        "H1",
        "H2",
        "H3",
        "H5",
        "H6",
        "H7",
        "H8",
        "H9",
    ]
    assert next(item for item in comparisons if item["hypothesis"] == "H1")["paired_blocks"] == 12
    assert all(0.0 <= item["holm_adjusted_p_value"] <= 1.0 for item in comparisons)
    assert all("gate does not require" in item["result_interpretation"] for item in comparisons)
