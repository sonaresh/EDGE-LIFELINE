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


@pytest.mark.security
def test_phase4_gate_is_conditional_and_preserves_mvsg_evidence() -> None:
    script = Path("scripts/run_phase4_gate.ps1").read_text(encoding="utf-8")
    assert "phase3-external-acceptance.json" in script
    assert "validate_phase4_oracle" in script
    assert "generate_phase4_vectors.py" in script
    assert "timeout-safety-junit.xml" in script
    assert "external_review_required = $true" in script
    assert "phase4_complete = $false" in script
    assert "phase5_authorized = $false" in script
    assert "PIPAPI_PYTHON_LOCATION" in script
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["mission"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Run Phase 4 gate")
    upload = next(step for step in steps if step.get("name") == "Upload Phase 4 evidence")
    assert "run_phase4_gate.ps1" in gate["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "evidence/phase4/generated/"


@pytest.mark.security
def test_phase5_gate_is_conditional_and_preserves_identity_time_policy_evidence() -> None:
    script = Path("scripts/run_phase5_gate.ps1").read_text(encoding="utf-8")
    assert "phase4-external-acceptance.json" in script
    assert "install-opa.ps1" in script
    assert "--fail-on-empty" in script
    assert "generate_phase5_fixtures" in script
    assert "phase5-negative-tests-junit.xml" in script
    assert "external_review_required = $true" in script
    assert "phase5_complete = $false" in script
    assert "phase6_authorized = $false" in script
    assert "PIPAPI_PYTHON_LOCATION" in script
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["identity-time-policy"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Run Phase 5 gate")
    upload = next(step for step in steps if step.get("name") == "Upload Phase 5 evidence")
    assert "run_phase5_gate.ps1" in gate["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "evidence/phase5/generated/"


@pytest.mark.security
def test_phase6_gate_is_conditional_and_preserves_causal_recovery_evidence() -> None:
    script = Path("scripts/run_phase6_gate.ps1").read_text(encoding="utf-8")
    assert "phase5-external-acceptance.json" in script
    assert "generate_phase6_vectors" in script
    assert "phase6-negative-tests-junit.xml" in script
    assert "external_review_required = $true" in script
    assert "phase6_complete = $false" in script
    assert "phase7_authorized = $false" in script
    assert "PIPAPI_PYTHON_LOCATION" in script
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["causal-recovery"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Run Phase 6 gate")
    upload = next(step for step in steps if step.get("name") == "Upload Phase 6 evidence")
    assert "run_phase6_gate.ps1" in gate["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "evidence/phase6/generated/"


@pytest.mark.security
def test_phase7_gate_is_conditional_and_preserves_orchestration_evidence() -> None:
    script = Path("scripts/run_phase7_gate.ps1").read_text(encoding="utf-8")
    assert "phase6-external-acceptance.json" in script
    assert "run_phase7_topology.ps1" in script
    assert "generate_phase7_vectors" in script
    assert "phase7-negative-tests-junit.xml" in script
    assert "external_review_required = $true" in script
    assert "phase7_complete = $false" in script
    assert "phase8_authorized = $false" in script
    assert "PIPAPI_PYTHON_LOCATION" in script
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["orchestration"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Run Phase 7 gate")
    upload = next(step for step in steps if step.get("name") == "Upload Phase 7 evidence")
    assert "run_phase7_gate.ps1" in gate["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "evidence/phase7/generated/"


@pytest.mark.security
def test_phase8_gate_is_conditional_and_preserves_experiment_evidence() -> None:
    script = Path("scripts/run_phase8_gate.ps1").read_text(encoding="utf-8")
    assert "phase7-external-acceptance.json" in script
    assert "run_phase8_experiments" in script
    assert "generate_phase8_vector" in script
    assert "phase8-negative-tests-junit.xml" in script
    assert "hypothesis_favorability_required_for_gate = $false" in script
    assert "external_review_required = $true" in script
    assert "phase8_complete = $false" in script
    assert "phase9_authorized = $false" in script
    assert "PIPAPI_PYTHON_LOCATION" in script
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["experiments"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Run Phase 8 gate")
    upload = next(step for step in steps if step.get("name") == "Upload Phase 8 evidence")
    assert "run_phase8_gate.ps1" in gate["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["name"] == "phase8-validation-evidence"
    assert upload["with"]["path"] == "evidence/phase8/generated/"


@pytest.mark.security
def test_opa_installer_is_version_pinned_and_checks_official_sha256() -> None:
    script = Path("scripts/install-opa.ps1").read_text(encoding="utf-8")
    assert "$Version = '1.19.1'" in script
    assert "https://openpolicyagent.org/downloads/v$Version/$Asset" in script
    assert '"$BaseUrl.sha256"' in script
    assert "Get-FileHash" in script
    assert "$ActualHash -ne $ExpectedHash" in script
