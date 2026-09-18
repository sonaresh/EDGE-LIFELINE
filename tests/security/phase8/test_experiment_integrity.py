from __future__ import annotations

import json
from pathlib import Path

import pytest

from edge_lifeline.experiments.analysis import primary_comparison_spec
from edge_lifeline.experiments.harness import run_experiment
from edge_lifeline.experiments.oracle import canonical_oracle
from scripts.run_phase8_experiments import execute


@pytest.mark.security
def test_protocol_is_final_paired_and_matches_executable_registry() -> None:
    protocol = json.loads(Path("experiments/phase8/protocol.json").read_bytes())
    assert protocol["stage"] == "final"
    assert protocol["analysis_frozen_before_final_run"] is True
    assert len(protocol["seeds"]) == 10
    assert protocol["paired_block"] == "scenario-and-seed"
    assert protocol["primary_comparisons"] == primary_comparison_spec()
    assert "does not require hypotheses to be favorable" in protocol["acceptance_policy"]


@pytest.mark.security
def test_oracle_is_frozen_and_independent() -> None:
    assert Path("experiments/phase8/oracle.json").read_bytes() == canonical_oracle()


@pytest.mark.security
def test_complete_experiment_reproduces_exactly(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = execute(Path.cwd(), first)
    second_manifest = execute(Path.cwd(), second)
    assert first_manifest == second_manifest
    assert first_manifest["run_count"] == 1600
    assert first_manifest["trace_count"] == 200
    assert first_manifest["excluded_runs"] == 0
    for name in ("raw-results.csv", "analysis.json", "run-manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


@pytest.mark.security
def test_detection_only_tcb_profile_is_not_presented_as_prevention() -> None:
    protocol = Path("experiments/phase8/protocol.json").read_text(encoding="utf-8")
    limitations = Path("docs/phase8/limitations.md").read_text(encoding="utf-8")
    assert "E9" not in next(
        item["scenarios"]
        for item in json.loads(protocol)["primary_comparisons"]
        if item["hypothesis"] == "H8"
    )
    assert "full-TCB compromise" in limitations


@pytest.mark.security
def test_treatment_unsafe_executions_are_confined_to_declared_detection_profile() -> None:
    treatment = [item for item in run_experiment([1000], "a" * 64) if item.method.value == "EL"]
    assert all(item.unsafe_actions_executed == 0 for item in treatment if item.scenario_id != "E9")
    assert next(item for item in treatment if item.scenario_id == "E9").unsafe_actions_executed > 0
