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
    assert "PowerShell 7.4 or newer is required" in script
    assert "Java 17 or newer is required" in script


@pytest.mark.security
def test_ci_runs_the_canonical_gate_and_always_preserves_evidence() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["validate"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Run Phase 1 gate")
    upload = next(step for step in steps if step.get("name") == "Upload validation evidence")
    assert "run_phase_gate.ps1" in gate["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "evidence/phase1/generated/"
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            action = step.get("uses")
            if action:
                assert "@" in action
                assert len(action.rsplit("@", maxsplit=1)[1].split()[0]) == 40


@pytest.mark.security
def test_phase2_gate_remains_conditional_and_phase3_locked() -> None:
    script = Path("scripts/run_phase2_gate.ps1").read_text(encoding="utf-8")
    assert "external_review_required = $true" in script
    assert "phase2_complete = $false" in script
    assert "phase3_authorized = $false" in script
    assert "$RuntimePassed -and $TlcPassed -and $EvidencePassed" in script
    assert "'CONDITIONAL_PASS'" in script
    assert "runtime-invariant-map.json" in script


@pytest.mark.security
def test_tla_tool_is_versioned_and_hash_pinned() -> None:
    installer = Path("scripts/install-tla-tools.ps1").read_text(encoding="utf-8")
    runner = Path("scripts/run-tlc.ps1").read_text(encoding="utf-8")
    expected = "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"
    assert "releases/download/v1.7.4/tla2tools.jar" in installer
    assert expected in installer
    assert expected in runner
    for invariant in (
        "I2_ParentBounded",
        "I4_ConservativeTime",
        "I5_AntiReplay",
        "I6_ProofBeforeEffect",
        "I9_NoReconnectGrant",
        "I10_NoAutomaticEffectReplay",
    ):
        assert invariant in runner


@pytest.mark.security
def test_phase3_gate_is_conditional_and_preserves_proof_evidence() -> None:
    script = Path("scripts/run_phase3_gate.ps1").read_text(encoding="utf-8")
    assert "phase2-external-acceptance.json" in script
    assert "generate_phase3_vectors.py" in script
    assert "proof-benchmark.json" in script
    assert "-m security" in script
    assert "external_review_required = $true" in script
    assert "phase3_complete = $false" in script
    assert "phase4_authorized = $false" in script
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["proof"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Run Phase 3 gate")
    upload = next(step for step in steps if step.get("name") == "Upload Phase 3 evidence")
    assert "run_phase3_gate.ps1" in gate["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "evidence/phase3/generated/"
