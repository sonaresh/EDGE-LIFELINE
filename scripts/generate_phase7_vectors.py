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
    """Build the deterministic Phase 7 runtime decision vector."""
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


def encoded_vector() -> bytes:
    """Return canonical UTF-8 vector bytes with LF line endings."""
    content = json.dumps(
        vector(),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"{content}\n".encode()


def write_vector(output_directory: Path) -> Path:
    """Write the deterministic vector and return its output path."""
    output_directory.mkdir(parents=True, exist_ok=True)

    output_path = output_directory / "runtime-vector-v1.json"
    output_path.write_bytes(encoded_vector())

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic Phase 7 orchestration vectors."
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="Directory where the Phase 7 runtime vector will be written.",
    )
    args = parser.parse_args()

    write_vector(args.output_directory)


if __name__ == "__main__":
    main()
