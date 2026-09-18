"""Host-specific Phase 8 H4 proof/admission engineering benchmark."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from typing import Any, cast

from scripts.benchmark_phase3 import benchmark


def _p99(samples: list[int]) -> int:
    return sorted(samples)[max(0, (99 * len(samples) + 99) // 100 - 1)]


def measure(iterations: int, warmup: int) -> dict[str, Any]:
    result = benchmark(iterations, warmup)
    generation = cast(list[int], result["raw_generation_ns"])
    verification = cast(list[int], result["raw_verification_full_chain_ns"])
    admission = [left + right for left, right in zip(generation, verification, strict=True)]
    verification_p99_ms = _p99(verification) / 1_000_000
    admission_p99_ms = _p99(admission) / 1_000_000
    return {
        "schema_version": "edge-lifeline-phase8-performance-v1",
        "synthetic_nonclinical": True,
        "host_specific_engineering_measurement": True,
        "not_a_clinical_deadline": True,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "iterations": iterations,
        "warmup_iterations": warmup,
        "proof_size_bytes": result["proof_size_bytes"],
        "proof_sha256": result["proof_sha256"],
        "verification_p99_ms": verification_p99_ms,
        "consequential_admission_proxy_p99_ms": admission_p99_ms,
        "targets_ms": {"verification_p99": 10.0, "admission_proxy_p99": 50.0},
        "targets_met": verification_p99_ms <= 10.0 and admission_p99_ms <= 50.0,
        "measurement_boundary": (
            "Local COSE/Ed25519 generation plus full-chain verification; excludes network, "
            "sensor, and physical-effect latency."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=1_000)
    parser.add_argument("--warmup", type=int, default=100)
    args = parser.parse_args()
    if args.iterations < 100 or args.warmup < 0:
        raise ValueError("benchmark requires at least 100 iterations and nonnegative warmup")
    payload = measure(args.iterations, args.warmup)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
