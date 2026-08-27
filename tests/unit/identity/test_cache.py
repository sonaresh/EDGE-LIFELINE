from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from edge_lifeline.formal.time_bounds import TrustedTimeInterval
from edge_lifeline.identity import (
    AssuranceLevel,
    CachedIdentityDecision,
    CachedIdentityPolicy,
    IdentityAssertion,
    RevocationSnapshot,
    evaluate_cached_identity,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def assertion() -> IdentityAssertion:
    return IdentityAssertion(
        subject_id="pseudonym:ward-a:operator-7",
        roles=frozenset({"operator"}),
        assurance=AssuranceLevel.CACHED_MULTIFACTOR,
        issued_at_ms=1_000,
        expires_at_ms=10_000,
        issuer="hospital-idp",
        source_artifact_hash=HASH_A,
        revocation_snapshot_id="snapshot-17",
    )


def snapshot() -> RevocationSnapshot:
    return RevocationSnapshot(
        snapshot_id="snapshot-17",
        issuer="hospital-idp",
        generated_at_ms=1_500,
        next_update_ms=8_000,
        revoked_subject_hashes=frozenset(),
        source_artifact_hash=HASH_B,
    )


def policy() -> CachedIdentityPolicy:
    return CachedIdentityPolicy(
        max_cache_age_ms=6_000,
        max_revocation_staleness_ms=5_500,
        minimum_assurance=AssuranceLevel.CACHED_MULTIFACTOR,
        permitted_roles=frozenset({"operator"}),
    )


def evaluate(
    identity: IdentityAssertion | None = None,
    revocations: RevocationSnapshot | None = None,
    interval: TrustedTimeInterval | None = None,
    rules: CachedIdentityPolicy | None = None,
    role: str = "operator",
) -> CachedIdentityDecision:
    return evaluate_cached_identity(
        identity or assertion(),
        revocations or snapshot(),
        interval or TrustedTimeInterval(2_000, 2_100),
        rules or policy(),
        required_role=role,
    )


def test_valid_cached_identity_is_deterministic() -> None:
    first = evaluate()
    second = evaluate()
    assert first.eligible
    assert first.decision == "USE_CACHED_IDENTITY"
    assert first.decision_hash() == second.decision_hash()


@pytest.mark.parametrize(
    ("identity", "revocations", "interval", "rules", "role", "failure"),
    [
        (
            replace(assertion(), revocation_snapshot_id="other"),
            None,
            None,
            None,
            None,
            "REVOCATION_SNAPSHOT_BINDING_MISMATCH",
        ),
        (replace(assertion(), issuer="other"), None, None, None, None, "IDENTITY_ISSUER_MISMATCH"),
        (None, None, TrustedTimeInterval(900, 950), None, None, "IDENTITY_NOT_YET_VALID"),
        (
            None,
            None,
            TrustedTimeInterval(9_900, 10_000),
            None,
            None,
            "IDENTITY_EXPIRED_OR_UNPROVABLE",
        ),
        (
            None,
            None,
            TrustedTimeInterval(1_400, 1_450),
            None,
            None,
            "REVOCATION_SNAPSHOT_FROM_FUTURE",
        ),
        (
            None,
            None,
            TrustedTimeInterval(7_900, 8_000),
            None,
            None,
            "REVOCATION_NEXT_UPDATE_EXCEEDED",
        ),
        (None, None, TrustedTimeInterval(7_000, 7_001), None, None, "IDENTITY_CACHE_STALE"),
        (
            None,
            None,
            TrustedTimeInterval(7_000, 7_001),
            replace(policy(), max_cache_age_ms=10_000),
            None,
            "REVOCATION_STATE_STALE",
        ),
        (
            replace(assertion(), assurance=AssuranceLevel.CACHED_SINGLE_FACTOR),
            None,
            None,
            None,
            None,
            "IDENTITY_ASSURANCE_INSUFFICIENT",
        ),
        (None, None, None, None, "clinician", "IDENTITY_ROLE_NOT_PERMITTED"),
    ],
)
def test_cached_identity_fails_safe(
    identity: IdentityAssertion | None,
    revocations: RevocationSnapshot | None,
    interval: TrustedTimeInterval | None,
    rules: CachedIdentityPolicy | None,
    role: str | None,
    failure: str,
) -> None:
    result = evaluate(
        identity,
        revocations,
        interval or TrustedTimeInterval(2_000, 2_100),
        rules,
        role or "operator",
    )
    assert not result.eligible
    assert result.decision == "DENY_UNSAFE_ACTION"
    assert failure in result.failures


def test_last_authenticated_snapshot_revocation_denies() -> None:
    revoked = replace(snapshot(), revoked_subject_hashes=frozenset({assertion().subject_hash}))
    assert evaluate(revocations=revoked).failures == (
        "IDENTITY_REVOKED_IN_LAST_AUTHENTICATED_SNAPSHOT",
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(assertion(), source_artifact_hash="A" * 64),
        lambda: replace(snapshot(), next_update_ms=1_500),
        lambda: replace(policy(), max_cache_age_ms=-1),
    ],
)
def test_invalid_identity_inputs_are_rejected(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        factory()
