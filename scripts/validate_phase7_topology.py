"""Validate Phase 7 topology and Kubernetes safety controls without a cluster."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def validate(root: Path) -> dict[str, object]:
    topology = yaml.safe_load((root / "infra/k3d/topology.yaml").read_text(encoding="utf-8"))
    clusters = topology["clusters"]
    require(topology["schema_version"] == "edge-lifeline-topology-v1", "invalid schema")
    require(topology["k3d_version"] == "v5.9.0", "k3d must be pinned")
    require(
        topology["k3s_image"] == "rancher/k3s:v1.37.0-k3s1",
        "K3s image must be pinned",
    )
    require(
        [(item["id"], item["role"]) for item in clusters]
        == [("cloud", "cloud"), ("edge-a", "edge"), ("edge-b", "edge"), ("edge-c", "edge")],
        "topology must be one cloud and three registered edges",
    )

    documents: list[dict[str, Any]] = [
        item
        for item in yaml.safe_load_all(
            (root / "infra/k3d/base/workload.yaml").read_text(encoding="utf-8")
        )
        if item
    ]
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    require(pod["automountServiceAccountToken"] is False, "service token must not mount")
    require(pod["securityContext"]["runAsNonRoot"] is True, "pod must run non-root")
    require(container["securityContext"]["readOnlyRootFilesystem"] is True, "rootfs read-only")
    require(
        container["securityContext"]["capabilities"]["drop"] == ["ALL"],
        "all Linux capabilities must be dropped",
    )

    policies = [
        item
        for item in yaml.safe_load_all(
            (root / "infra/k3d/base/network-policy.yaml").read_text(encoding="utf-8")
        )
        if item
    ]
    require(any(item["metadata"]["name"] == "default-deny" for item in policies), "deny policy")
    faults = yaml.safe_load((root / "infra/k3d/fault-plan.yaml").read_text(encoding="utf-8"))
    require(faults["seed"] == 7001, "fault seed must be frozen")
    return {
        "schema_version": "edge-lifeline-phase7-topology-validation-v1",
        "valid": True,
        "clusters": clusters,
        "k3d_version": topology["k3d_version"],
        "k3s_image": topology["k3s_image"],
        "fault_ids": [item["id"] for item in faults["cases"]],
        "security_controls": [
            "restricted-pod-security",
            "non-root",
            "read-only-rootfs",
            "drop-all-capabilities",
            "no-service-account-token",
            "default-deny-network-policy",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
