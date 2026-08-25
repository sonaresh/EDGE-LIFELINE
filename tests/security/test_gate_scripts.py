from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.mark.security
def test_compose_startup_is_inside_cleanup_guard() -> None:
    script = Path("scripts/verify.ps1").read_text(encoding="utf-8")
    try_position = script.index("try {", script.index("docker compose config"))
    startup_position = script.index("docker compose up")
    finally_position = script.index("finally {", startup_position)
    cleanup_position = script.index("docker compose down", finally_position)
    assert try_position < startup_position < finally_position < cleanup_position


@pytest.mark.security
def test_gate_remains_conditional_and_generates_complete_manifests() -> None:
    script = Path("scripts/run_phase_gate.ps1").read_text(encoding="utf-8")
    assert "source-manifest --root $RepoRoot" in script
    assert "source-manifest --root $EvidenceDir" in script
    assert "external_review_required = $true" in script
    assert "phase_2_authorized = $false" in script
    assert "decision = if ($GatePassed) { 'CONDITIONAL_PASS' }" in script


@pytest.mark.security
def test_prerequisite_script_checks_command_presence_and_exit_failures() -> None:
    script = Path("scripts/verify-prerequisites.ps1").read_text(encoding="utf-8")
    assert "$PSNativeCommandUseErrorActionPreference = $true" in script
    assert "Get-Command $Check.Command" in script
    assert "Status = 'UNAVAILABLE'" in script


@pytest.mark.security
def test_ci_runs_the_canonical_gate_and_always_preserves_evidence() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["validate"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Run Phase 1 gate")
    upload = next(step for step in steps if step.get("name") == "Upload validation evidence")
    assert "run_phase_gate.ps1" in gate["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "evidence/phase1/generated/"
