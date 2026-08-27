"""Phase 5 fail-safe composition for cached identity, bounded time, and OPA policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from edge_lifeline.identity import (
    CachedIdentityDecision,
    CachedIdentityPolicy,
    IdentityAssertion,
    RevocationSnapshot,
    evaluate_cached_identity,
)
from edge_lifeline.policy import OpaPolicyClient, PolicyDecision
from edge_lifeline.proof.codec import canonical_dumps, sha256_hex
from edge_lifeline.time import (
    AuthenticatedTimeAnchor,
    BoundedTimeEstimate,
    TimeObservation,
    estimate_bounded_time,
)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class Phase5AdmissionDecision:
    allow: bool
    decision: str
    failures: tuple[str, ...]
    time: BoundedTimeEstimate
    identity: CachedIdentityDecision | None
    policy: PolicyDecision | None
    schema_version: str = "edge-lifeline-phase5-admission-v1"

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "allow": self.allow,
            "decision": self.decision,
            "failures": list(self.failures),
            "time": self.time.to_obj(),
            "identity": None if self.identity is None else self.identity.to_obj(),
            "policy": (
                None
                if self.policy is None
                else {
                    "allow": self.policy.allow,
                    "decision": self.policy.decision,
                    "obligations": _plain(self.policy.obligations),
                    "policy_hash": self.policy.policy_hash,
                    "policy_version": self.policy.policy_version,
                    "failures": list(self.policy.failures),
                }
            ),
        }

    def decision_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.to_obj()))


def evaluate_phase5_admission(
    *,
    assertion: IdentityAssertion,
    snapshot: RevocationSnapshot,
    identity_policy: CachedIdentityPolicy,
    required_role: str,
    time_anchor: AuthenticatedTimeAnchor,
    observation: TimeObservation,
    previous_observation: TimeObservation | None,
    policy_client: OpaPolicyClient,
    action: str,
    resource: str,
    authority_actions: frozenset[str],
    authority_resources: frozenset[str],
) -> Phase5AdmissionDecision:
    """Require every Phase 5 predicate before returning an actionable decision."""

    time = estimate_bounded_time(
        time_anchor, observation, previous_observation=previous_observation
    )
    if not time.active or time.interval is None:
        return Phase5AdmissionDecision(False, "DENY_UNSAFE_ACTION", time.failures, time, None, None)
    identity = evaluate_cached_identity(
        assertion,
        snapshot,
        time.interval,
        identity_policy,
        required_role=required_role,
    )
    if not identity.eligible:
        return Phase5AdmissionDecision(
            False, "DENY_UNSAFE_ACTION", identity.failures, time, identity, None
        )
    policy = policy_client.evaluate(
        {
            "identity": {"eligible": identity.eligible, "decision_hash": identity.decision_hash()},
            "time": {"active": time.active, "estimate_hash": time.estimate_hash()},
            "action": action,
            "resource": resource,
            "authority": {
                "actions": sorted(authority_actions),
                "resources": sorted(authority_resources),
            },
        }
    )
    return Phase5AdmissionDecision(
        policy.allow,
        policy.decision if policy.allow else "DENY_UNSAFE_ACTION",
        policy.failures,
        time,
        identity,
        policy,
    )
