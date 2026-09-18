"""Generate the compact deterministic Phase 8 experiment digest vector."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from scripts.run_phase8_experiments import execute


def vector(root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="edge-lifeline-phase8-") as directory:
        manifest = execute(root, Path(directory))
    return {
        "schema_version": "edge-lifeline-phase8-digest-vector-v1",
        "protocol_sha256": manifest["protocol_sha256"],
        "oracle_sha256": manifest["oracle_sha256"],
        "raw_results_sha256": manifest["raw_results_sha256"],
        "analysis_sha256": manifest["analysis_sha256"],
        "run_count": manifest["run_count"],
        "trace_count": manifest["trace_count"],
        "method_count": manifest["method_count"],
        "scenario_count": manifest["scenario_count"],
        "seed_count": manifest["seed_count"],
        "excluded_runs": manifest["excluded_runs"],
    }


def encoded_vector(root: Path) -> bytes:
    return (json.dumps(vector(root), indent=2, sort_keys=True) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded_vector(args.root.resolve()))


if __name__ == "__main__":
    main()
