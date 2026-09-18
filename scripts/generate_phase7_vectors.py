"""Generate deterministic Phase 7 orchestration decision vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from edge_lifeline.orchestration import (
    ClusterObservation,
    ClusterRole,
    Connectivity,
    LeaseState,
    decide_runtime_mode,
)


def vector() -> dict[str, Any]:
    cases = (
        ClusterObservation(
            cluster_id="edge-a",
            role=ClusterRole.EDGE,
            connectivity=Connectivity.ISOLATED,
            lease_state=LeaseState.VALID,
            workload_ready=True,
            policy_ready=True,
            proof_verifier_ready=True,
        ),
        ClusterObservation(
            cluster_id="edge-b",
            role=ClusterRole.EDGE,
            connectivity=Connectivity.CONNECTED,
            lease_state=LeaseState.EXPIRED,
            workload_ready=True,
            policy_ready=True,
            proof_verifier_ready=True,
        ),
        ClusterObservation(
            cluster_id="edge-c",
            role=ClusterRole.EDGE,
            connectivity=Connectivity.CONNECTED,
            lease_state=LeaseState.VALID,
            workload_ready=True,
            policy_ready=True,
            proof_verifier_ready=True,
            recovery_complete=True,
            fresh_connected_epoch_lease=False,
        ),
    )
    return {
        "schema_version": "edge-lifeline-phase7-runtime-vector-v1",
        "decisions": [decide_runtime_mode(case).model_dump(mode="json") for case in cases],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "runtime-vector-v1.json").write_text(
        json.dumps(vector(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
