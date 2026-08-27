"""Generate deterministic Phase 5 identity, time, and policy fixtures."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from edge_lifeline.formal.time_bounds import TrustedTimeInterval
from edge_lifeline.identity import (
    AssuranceLevel,
    CachedIdentityPolicy,
    IdentityAssertion,
    RevocationSnapshot,
    evaluate_cached_identity,
)
from edge_lifeline.policy import PolicyBundle
from edge_lifeline.time import (
    AuthenticatedTimeAnchor,
    TimeObservation,
    estimate_bounded_time,
)

OPA_VERSION = "1.19.1"
POLICY_VERSION = "phase5-policy-v1"


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _identity_fixture() -> dict[str, Any]:
    assertion = IdentityAssertion(
        subject_id="pseudonym:ward-a:operator-7",
        roles=frozenset({"operator"}),
        assurance=AssuranceLevel.CACHED_MULTIFACTOR,
        issued_at_ms=1_000,
        expires_at_ms=10_000,
        issuer="hospital-idp",
        source_artifact_hash="a" * 64,
        revocation_snapshot_id="snapshot-17",
    )
    snapshot = RevocationSnapshot(
        snapshot_id="snapshot-17",
        issuer="hospital-idp",
        generated_at_ms=1_500,
        next_update_ms=8_000,
        revoked_subject_hashes=frozenset(),
        source_artifact_hash="b" * 64,
    )
    policy = CachedIdentityPolicy(
        max_cache_age_ms=6_000,
        max_revocation_staleness_ms=5_500,
        minimum_assurance=AssuranceLevel.CACHED_MULTIFACTOR,
        permitted_roles=frozenset({"operator"}),
    )
    valid = evaluate_cached_identity(
        assertion,
        snapshot,
        TrustedTimeInterval(2_000, 2_100),
        policy,
        required_role="operator",
    )
    stale = evaluate_cached_identity(
        assertion,
        snapshot,
        TrustedTimeInterval(7_000, 7_001),
        policy,
        required_role="operator",
    )
    revoked = evaluate_cached_identity(
        assertion,
        replace(snapshot, revoked_subject_hashes=frozenset({assertion.subject_hash})),
        TrustedTimeInterval(2_000, 2_100),
        policy,
        required_role="operator",
    )
    return {
        "schema_version": "edge-lifeline-phase5-identity-fixtures-v1",
        "claim_boundary": (
            "Revocation state is the last authenticated snapshot, not current state."
        ),
        "assertion": assertion.to_obj(),
        "snapshot": snapshot.to_obj(),
        "cases": {
            "valid_cached_identity": valid.to_obj(),
            "stale_identity_and_revocation": stale.to_obj(),
            "revoked_in_snapshot": revoked.to_obj(),
        },
    }


def _time_fixture() -> dict[str, Any]:
    anchor = AuthenticatedTimeAnchor(
        anchor_id="anchor-1",
        source_artifact_hash="c" * 64,
        utc_estimate_ms=1_000_000,
        initial_error_ms=25,
        boot_id="boot-a",
        boottime_anchor_ms=10_000,
        drift_parts_per_million=100,
        maximum_anchor_age_ms=60_000,
        restart_suspend_penalty_ms=500,
    )
    cases = {
        "normal": estimate_bounded_time(anchor, TimeObservation("boot-a", 20_000)).to_obj(),
        "rollback": estimate_bounded_time(anchor, TimeObservation("boot-a", 9_999)).to_obj(),
        "restart_without_retained_anchor": estimate_bounded_time(
            anchor, TimeObservation("boot-b", 1)
        ).to_obj(),
        "stale_anchor": estimate_bounded_time(anchor, TimeObservation("boot-a", 70_000)).to_obj(),
    }
    return {
        "schema_version": "edge-lifeline-phase5-time-traces-v1",
        "wall_clock_authority": False,
        "anchor": anchor.to_obj(),
        "cases": cases,
    }


def _policy_fixture(repo_root: Path) -> dict[str, Any]:
    source = (repo_root / "policy/rego/edge_lifeline.rego").read_bytes()
    bundle = PolicyBundle(
        sources={"policy/edge_lifeline.rego": source},
        data_documents={},
        entrypoints=("edge_lifeline/phase5/result",),
        policy_version=POLICY_VERSION,
        opa_version=OPA_VERSION,
    )
    return bundle.diagnostic_manifest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    _write(args.output_directory / "identity-fixtures-v1.json", _identity_fixture())
    _write(args.output_directory / "time-traces-v1.json", _time_fixture())
    _write(
        args.output_directory / "policy-manifest-v1.json",
        _policy_fixture(args.repo_root.resolve()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
