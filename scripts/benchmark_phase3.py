"""Measure Phase 3 proof operations without imposing a performance pass threshold."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from edge_lifeline.formal.authority import Budgets
from edge_lifeline.proof.artifact import ArtifactType
from edge_lifeline.proof.codec import sha256_hex
from edge_lifeline.proof.issuer import AuthorityIssuer
from edge_lifeline.proof.verifier import EdgeProofVerifier, TrustedSigner
from scripts.generate_phase3_vectors import _context, _envelope, build_vector


def _summary(samples: list[int]) -> dict[str, float | int]:
    ordered = sorted(samples)
    p95_index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return {
        "count": len(samples),
        "min_ns": ordered[0],
        "median_ns": statistics.median(ordered),
        "mean_ns": statistics.fmean(ordered),
        "p95_ns": ordered[p95_index],
        "max_ns": ordered[-1],
        "population_stdev_ns": statistics.pstdev(ordered),
    }


def benchmark(iterations: int, warmup: int) -> dict[str, Any]:
    if iterations < 1 or warmup < 0:
        raise ValueError("iterations must be positive and warmup cannot be negative")
    vector = build_vector()
    artifacts = cast(dict[str, dict[str, str]], vector["artifacts"])
    root = bytes.fromhex(artifacts["root"]["encoded_hex"])
    child = bytes.fromhex(artifacts["child"]["encoded_hex"])
    decision = bytes.fromhex(artifacts["decision"]["encoded_hex"])
    keys = cast(dict[str, str], vector["public_keys_hex"])
    key_ids = cast(dict[str, str], vector["key_ids_hex"])
    verifier = EdgeProofVerifier(
        {
            bytes.fromhex(key_ids["cloud"]): TrustedSigner(
                "cloud-authority",
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(keys["cloud"])),
                frozenset({ArtifactType.AUTHORITY_LEASE}),
                root_authority=True,
            ),
            bytes.fromhex(key_ids["edge"]): TrustedSigner(
                "edge-a",
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(keys["edge"])),
                frozenset({ArtifactType.AUTHORITY_LEASE, ArtifactType.DECISION_CERTIFICATE}),
            ),
        }
    )
    evidence = {"sensor-attestation": b"synthetic-vector-evidence-v1"}
    decision_envelope = replace(
        _envelope(),
        budgets=Budgets(10, 20, 30, 40, 50, 1),
        delegation_depth_remaining=0,
        actions=frozenset({"monitor"}),
        resources=frozenset({"patient-index"}),
    )
    context = _context(decision_envelope, evidence)
    claims = verifier.decode_and_authenticate(decision).claims
    issuer = AuthorityIssuer(
        "edge-a",
        b"edge-vector-key",
        Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64))),
    )

    for _ in range(warmup):
        issuer.issue(claims)
        verifier.verify(decision, context=context, parent_chain=(child, root))

    issue_samples: list[int] = []
    verify_samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        encoded = issuer.issue(claims)
        issue_samples.append(time.perf_counter_ns() - started)
        started = time.perf_counter_ns()
        verifier.verify(encoded, context=context, parent_chain=(child, root))
        verify_samples.append(time.perf_counter_ns() - started)

    return {
        "schema_version": "phase3-proof-benchmark-v1",
        "synthetic_nonclinical": True,
        "engineering_validation_only": True,
        "no_acceptance_threshold": True,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "algorithm": "canonical-CBOR/COSE_Sign1/Ed25519",
        "iterations": iterations,
        "warmup_iterations": warmup,
        "proof_size_bytes": len(decision),
        "proof_sha256": sha256_hex(decision),
        "generation": _summary(issue_samples),
        "verification_full_chain": _summary(verify_samples),
        "raw_generation_ns": issue_samples,
        "raw_verification_full_chain_ns": verify_samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=1_000)
    parser.add_argument("--warmup", type=int, default=100)
    args = parser.parse_args()
    result = benchmark(args.iterations, args.warmup)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
