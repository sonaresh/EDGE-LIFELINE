"""Execute the frozen Phase 8 paired-factorial synthetic experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from edge_lifeline.experiments import SCENARIOS, analyze_results, run_experiment
from edge_lifeline.experiments.analysis import primary_comparison_spec
from edge_lifeline.experiments.harness import generate_trace, trace_bytes
from edge_lifeline.experiments.oracle import canonical_oracle


def _canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def execute(root: Path, output: Path) -> dict[str, Any]:
    protocol_path = root / "experiments/phase8/protocol.json"
    oracle_path = root / "experiments/phase8/oracle.json"
    protocol_bytes = protocol_path.read_bytes()
    if oracle_path.read_bytes() != canonical_oracle():
        raise ValueError("frozen Phase 8 oracle differs from its independent generator")
    protocol = json.loads(protocol_bytes)
    if protocol["stage"] != "final" or not protocol["analysis_frozen_before_final_run"]:
        raise ValueError("final analysis protocol is not frozen")
    if protocol["primary_comparisons"] != primary_comparison_spec():
        raise ValueError("frozen protocol and executable analysis registry differ")
    seeds = tuple(int(item) for item in protocol["seeds"])
    if len(seeds) < 10 or len(seeds) != len(set(seeds)):
        raise ValueError("final protocol requires at least ten independent unique seeds")
    protocol_sha = _sha256(protocol_bytes)
    results = run_experiment(seeds, protocol_sha)
    expected = len(protocol["methods"]) * len(protocol["scenarios"]) * len(seeds)
    if len(results) != expected:
        raise RuntimeError("factorial experiment is incomplete")
    output.mkdir(parents=True, exist_ok=True)
    rows = [item.model_dump(mode="json") for item in results]
    raw_path = output / "raw-results.csv"
    with raw_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    analysis = analyze_results(results)
    (output / "analysis.json").write_bytes(_canonical_json(analysis))
    traces = {
        f"{scenario.scenario_id}:{seed}": _sha256(trace_bytes(generate_trace(scenario, seed)))
        for scenario in SCENARIOS
        for seed in seeds
    }
    manifest = {
        "schema_version": "edge-lifeline-phase8-run-manifest-v1",
        "protocol_sha256": protocol_sha,
        "oracle_sha256": _sha256(canonical_oracle()),
        "raw_results_sha256": _sha256(raw_path.read_bytes()),
        "analysis_sha256": _sha256((output / "analysis.json").read_bytes()),
        "trace_count": len(traces),
        "trace_sha256": traces,
        "run_count": len(results),
        "method_count": len(protocol["methods"]),
        "scenario_count": len(protocol["scenarios"]),
        "seed_count": len(seeds),
        "accepted_runs": len(results),
        "excluded_runs": 0,
        "failed_infrastructure_runs": 0,
    }
    (output / "run-manifest.json").write_bytes(_canonical_json(manifest))
    (output / "protocol.json").write_bytes(protocol_bytes)
    (output / "oracle.json").write_bytes(canonical_oracle())
    exclusions = {
        "schema_version": "edge-lifeline-phase8-exclusions-v1",
        "outcome_based_exclusions": 0,
        "infrastructure_failures": [],
        "excluded_runs": [],
    }
    (output / "exclusions.json").write_bytes(_canonical_json(exclusions))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = execute(args.root.resolve(), args.output.resolve())
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
