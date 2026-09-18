from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.mark.security
def test_workload_manifest_uses_restricted_security_context() -> None:
    documents = list(
        yaml.safe_load_all(Path("infra/k3d/base/workload.yaml").read_text(encoding="utf-8"))
    )
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert pod["serviceAccountName"] == "edge-lifeline"
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["imagePullPolicy"] == "Never"
    assert container["resources"]["limits"]


@pytest.mark.security
def test_network_policy_defaults_to_deny() -> None:
    documents = list(
        yaml.safe_load_all(Path("infra/k3d/base/network-policy.yaml").read_text(encoding="utf-8"))
    )
    deny = next(item for item in documents if item["metadata"]["name"] == "default-deny")
    assert set(deny["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    assert deny["spec"]["podSelector"] == {}


@pytest.mark.security
def test_phase7_does_not_provision_cloud_resources() -> None:
    paths = [Path("infra/k3d"), Path("scripts/run_phase7_gate.ps1")]
    text = "\n".join(
        file.read_text(encoding="utf-8")
        for path in paths
        for file in ([path] if path.is_file() else path.rglob("*"))
        if file.is_file()
    ).lower()
    for forbidden in ("aws cloudformation", "terraform apply", "eksctl create", "az aks"):
        assert forbidden not in text


@pytest.mark.security
def test_fault_plan_is_fixed_and_cleanup_is_mandatory() -> None:
    plan = yaml.safe_load(Path("infra/k3d/fault-plan.yaml").read_text(encoding="utf-8"))
    assert [case["id"] for case in plan["cases"]] == ["F7-POD-RESTART", "F7-EDGE-RESTART"]
    script = Path("scripts/run_phase7_topology.ps1").read_text(encoding="utf-8")
    assert "finally {" in script
    assert "$K3dPath cluster delete" in script
    assert (
        script.index("try {") < script.index("$K3dPath cluster create") < script.index("finally {")
    )
