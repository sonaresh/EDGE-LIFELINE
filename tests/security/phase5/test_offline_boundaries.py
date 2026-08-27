from __future__ import annotations

from dataclasses import replace

import pytest

from edge_lifeline.formal.time_bounds import TrustedTimeInterval
from edge_lifeline.identity import (
    AssuranceLevel,
    CachedIdentityPolicy,
    IdentityAssertion,
    RevocationSnapshot,
    evaluate_cached_identity,
)
from edge_lifeline.time import AuthenticatedTimeAnchor, TimeObservation, estimate_bounded_time

pytestmark = pytest.mark.security


def test_e4_identity_outage_bounds_exposure_instead_of_claiming_current_revocation() -> None:
    assertion = IdentityAssertion(
        subject_id="pseudonym:operator-7",
        roles=frozenset({"operator"}),
        assurance=AssuranceLevel.CACHED_MULTIFACTOR,
        issued_at_ms=1_000,
        expires_at_ms=20_000,
        issuer="idp",
        source_artifact_hash="a" * 64,
        revocation_snapshot_id="snapshot-1",
    )
    snapshot = RevocationSnapshot(
        snapshot_id="snapshot-1",
        issuer="idp",
        generated_at_ms=1_500,
        next_update_ms=20_000,
        revoked_subject_hashes=frozenset(),
        source_artifact_hash="b" * 64,
    )
    policy = CachedIdentityPolicy(
        max_cache_age_ms=3_000,
        max_revocation_staleness_ms=2_000,
        minimum_assurance=AssuranceLevel.CACHED_MULTIFACTOR,
        permitted_roles=frozenset({"operator"}),
    )
    inside = evaluate_cached_identity(
        assertion,
        snapshot,
        TrustedTimeInterval(3_400, 3_500),
        policy,
        required_role="operator",
    )
    outside = evaluate_cached_identity(
        assertion,
        snapshot,
        TrustedTimeInterval(3_500, 3_501),
        policy,
        required_role="operator",
    )
    assert inside.eligible
    assert not outside.eligible
    assert "REVOCATION_STATE_STALE" in outside.failures


def test_reboot_without_hardware_anchor_cannot_be_reactivated_by_wall_clock() -> None:
    anchor = AuthenticatedTimeAnchor(
        anchor_id="anchor",
        source_artifact_hash="c" * 64,
        utc_estimate_ms=1_000_000,
        initial_error_ms=10,
        boot_id="boot-a",
        boottime_anchor_ms=100,
        drift_parts_per_million=100,
        maximum_anchor_age_ms=10_000,
        restart_suspend_penalty_ms=1_000,
    )
    result = estimate_bounded_time(
        anchor,
        TimeObservation("boot-b", 1, wall_clock_ms=anchor.utc_estimate_ms + 1),
    )
    assert not result.active
    assert result.mode == "PROTECTIVE_READ_ONLY"
    assert "RESTART_REQUIRES_REANCHOR" in result.failures


def test_hardware_retention_must_be_explicit() -> None:
    base = AuthenticatedTimeAnchor(
        anchor_id="anchor",
        source_artifact_hash="c" * 64,
        utc_estimate_ms=1_000_000,
        initial_error_ms=10,
        boot_id="boot-a",
        boottime_anchor_ms=100,
        drift_parts_per_million=0,
        maximum_anchor_age_ms=10_000,
        restart_suspend_penalty_ms=1_000,
    )
    retained = estimate_bounded_time(
        replace(base, hardware_retained_across_restart=True),
        TimeObservation("boot-b", 1),
    )
    assert retained.active
    assert retained.interval is not None
    assert retained.interval.uncertainty_half_width_ms == 1_010
