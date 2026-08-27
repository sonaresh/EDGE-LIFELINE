"""Fail-safe cached identity and revocation-snapshot checks.

The evaluator never claims that a disconnected revocation snapshot is current.  It only
decides whether a previously authenticated, pseudonymous assertion remains inside the
explicit cache, assurance, role, and revocation-staleness bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from edge_lifeline.formal.time_bounds import TrustedTimeInterval
from edge_lifeline.proof.codec import canonical_dumps, sha256_hex


def _sha256(value: str, label: str) -> str:
    if len(value) != 64 or any(item not in "0123456789abcdef" for item in value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")
    return value


class AssuranceLevel(IntEnum):
    UNVERIFIED = 0
    CACHED_SINGLE_FACTOR = 1
    CACHED_MULTIFACTOR = 2
    HARDWARE_BOUND = 3


@dataclass(frozen=True, slots=True)
class IdentityAssertion:
    subject_id: str
    roles: frozenset[str]
    assurance: AssuranceLevel
    issued_at_ms: int
    expires_at_ms: int
    issuer: str
    source_artifact_hash: str
    revocation_snapshot_id: str
    schema_version: str = "edge-lifeline-identity-assertion-v1"

    def __post_init__(self) -> None:
        if (
            not self.subject_id
            or not self.roles
            or not self.issuer
            or not self.revocation_snapshot_id
            or self.issued_at_ms < 0
            or self.expires_at_ms <= self.issued_at_ms
        ):
            raise ValueError("invalid cached identity assertion")
        if not isinstance(self.roles, frozenset) or any(not role for role in self.roles):
            raise ValueError("identity roles must be nonempty")
        if not isinstance(self.assurance, AssuranceLevel):
            raise ValueError("identity assurance must be an AssuranceLevel")
        _sha256(self.source_artifact_hash, "identity source artifact hash")

    @property
    def subject_hash(self) -> str:
        return sha256_hex(self.subject_id.encode("utf-8"))

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
            "roles": sorted(self.roles),
            "assurance": int(self.assurance),
            "issued_at_ms": self.issued_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "issuer": self.issuer,
            "source_artifact_hash": self.source_artifact_hash,
            "revocation_snapshot_id": self.revocation_snapshot_id,
        }

    def assertion_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))


@dataclass(frozen=True, slots=True)
class RevocationSnapshot:
    snapshot_id: str
    issuer: str
    generated_at_ms: int
    next_update_ms: int
    revoked_subject_hashes: frozenset[str]
    source_artifact_hash: str
    schema_version: str = "edge-lifeline-revocation-snapshot-v1"

    def __post_init__(self) -> None:
        if (
            not self.snapshot_id
            or not self.issuer
            or self.generated_at_ms < 0
            or self.next_update_ms <= self.generated_at_ms
        ):
            raise ValueError("invalid revocation snapshot")
        _sha256(self.source_artifact_hash, "revocation source artifact hash")
        if not isinstance(self.revoked_subject_hashes, frozenset):
            raise ValueError("revoked subject hashes must be an immutable set")
        for item in self.revoked_subject_hashes:
            _sha256(item, "revoked subject hash")

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "issuer": self.issuer,
            "generated_at_ms": self.generated_at_ms,
            "next_update_ms": self.next_update_ms,
            "revoked_subject_hashes": sorted(self.revoked_subject_hashes),
            "source_artifact_hash": self.source_artifact_hash,
        }

    def snapshot_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))


@dataclass(frozen=True, slots=True)
class CachedIdentityPolicy:
    max_cache_age_ms: int
    max_revocation_staleness_ms: int
    minimum_assurance: AssuranceLevel
    permitted_roles: frozenset[str]

    def __post_init__(self) -> None:
        if min(self.max_cache_age_ms, self.max_revocation_staleness_ms) < 0:
            raise ValueError("identity freshness limits cannot be negative")
        if (
            not isinstance(self.permitted_roles, frozenset)
            or not self.permitted_roles
            or any(not item for item in self.permitted_roles)
        ):
            raise ValueError("identity policy needs permitted roles")
        if not isinstance(self.minimum_assurance, AssuranceLevel):
            raise ValueError("minimum assurance must be an AssuranceLevel")


@dataclass(frozen=True, slots=True)
class CachedIdentityDecision:
    eligible: bool
    decision: str
    failures: tuple[str, ...]
    subject_hash: str
    assertion_hash: str
    revocation_snapshot_hash: str
    cache_age_ms: int
    revocation_age_ms: int
    schema_version: str = "edge-lifeline-cached-identity-decision-v1"

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "eligible": self.eligible,
            "decision": self.decision,
            "failures": list(self.failures),
            "subject_hash": self.subject_hash,
            "assertion_hash": self.assertion_hash,
            "revocation_snapshot_hash": self.revocation_snapshot_hash,
            "cache_age_ms": self.cache_age_ms,
            "revocation_age_ms": self.revocation_age_ms,
        }

    def decision_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))


def evaluate_cached_identity(
    assertion: IdentityAssertion,
    snapshot: RevocationSnapshot,
    interval: TrustedTimeInterval,
    policy: CachedIdentityPolicy,
    *,
    required_role: str,
) -> CachedIdentityDecision:
    """Evaluate an already authenticated assertion using conservative interval bounds."""

    failures: list[str] = []
    cache_age = max(0, interval.upper_ms - assertion.issued_at_ms)
    revocation_age = max(0, interval.upper_ms - snapshot.generated_at_ms)
    if assertion.revocation_snapshot_id != snapshot.snapshot_id:
        failures.append("REVOCATION_SNAPSHOT_BINDING_MISMATCH")
    if assertion.issuer != snapshot.issuer:
        failures.append("IDENTITY_ISSUER_MISMATCH")
    if interval.lower_ms < assertion.issued_at_ms:
        failures.append("IDENTITY_NOT_YET_VALID")
    if interval.upper_ms >= assertion.expires_at_ms:
        failures.append("IDENTITY_EXPIRED_OR_UNPROVABLE")
    if interval.lower_ms < snapshot.generated_at_ms:
        failures.append("REVOCATION_SNAPSHOT_FROM_FUTURE")
    if interval.upper_ms >= snapshot.next_update_ms:
        failures.append("REVOCATION_NEXT_UPDATE_EXCEEDED")
    if cache_age > policy.max_cache_age_ms:
        failures.append("IDENTITY_CACHE_STALE")
    if revocation_age > policy.max_revocation_staleness_ms:
        failures.append("REVOCATION_STATE_STALE")
    if assertion.assurance < policy.minimum_assurance:
        failures.append("IDENTITY_ASSURANCE_INSUFFICIENT")
    if required_role not in assertion.roles or required_role not in policy.permitted_roles:
        failures.append("IDENTITY_ROLE_NOT_PERMITTED")
    if assertion.subject_hash in snapshot.revoked_subject_hashes:
        failures.append("IDENTITY_REVOKED_IN_LAST_AUTHENTICATED_SNAPSHOT")
    failures = sorted(set(failures))
    return CachedIdentityDecision(
        eligible=not failures,
        decision="USE_CACHED_IDENTITY" if not failures else "DENY_UNSAFE_ACTION",
        failures=tuple(failures),
        subject_hash=assertion.subject_hash,
        assertion_hash=assertion.assertion_hash(),
        revocation_snapshot_hash=snapshot.snapshot_hash(),
        cache_age_ms=cache_age,
        revocation_age_ms=revocation_age,
    )
