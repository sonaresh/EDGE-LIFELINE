"""Normative Phase 3 proof-claim schema carried inside COSE_Sign1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from edge_lifeline.formal.authority import AuthorityEnvelope
from edge_lifeline.proof.codec import (
    canonical_dumps,
    envelope_from_obj,
    envelope_to_obj,
    strict_loads,
)


class ArtifactType(StrEnum):
    AUTHORITY_LEASE = "AUTHORITY_LEASE"
    DECISION_CERTIFICATE = "DECISION_CERTIFICATE"
    EMERGENCY_CAPABILITY = "EMERGENCY_CAPABILITY"


DECISION_RESULTS = frozenset(
    {
        "CONTINUE_LOCALLY",
        "REDUCE_SERVICE",
        "PRIORITIZE_CRITICAL_WORKLOAD",
        "DENY_UNSAFE_ACTION",
        "USE_CACHED_IDENTITY",
        "ENTER_READ_ONLY_MODE",
        "REQUEST_HUMAN_OVERRIDE",
        "ISOLATE_FROM_CLOUD",
        "RECONNECT_AND_RECONCILE",
        "SAFE_SHUTDOWN",
    }
)


@dataclass(frozen=True, slots=True)
class ProofClaims:
    artifact_type: ArtifactType
    artifact_id: str
    lease_id: str
    parent_authority_ref: str | None
    issuer: str
    edge_identity: str
    issued_at_ms: int
    activation_not_before_ms: int
    expiration_ms: int
    clock_uncertainty_allowance_ms: int
    policy_version: str
    envelope: AuthorityEnvelope
    evidence_hashes: Mapping[str, str]
    decision: str
    justification_trace: tuple[str, ...]
    nonce: str
    replay_domain: str
    previous_event_hash: str
    context_hash: str

    def __post_init__(self) -> None:
        identifiers = (
            self.artifact_id,
            self.lease_id,
            self.issuer,
            self.edge_identity,
            self.policy_version,
            self.decision,
            self.nonce,
            self.replay_domain,
        )
        if any(not item or len(item) > 256 for item in identifiers):
            raise ValueError("proof identifiers must contain 1..256 characters")
        if not (
            0 <= self.issued_at_ms <= self.activation_not_before_ms < self.expiration_ms
            and self.clock_uncertainty_allowance_ms >= 0
        ):
            raise ValueError("invalid proof time bounds")
        if self.activation_not_before_ms != self.envelope.time_window.not_before_ms:
            raise ValueError("activation bound differs from authority envelope")
        if self.expiration_ms != self.envelope.time_window.expires_at_ms:
            raise ValueError("expiration bound differs from authority envelope")
        if self.expiration_ms - self.activation_not_before_ms > self.envelope.max_lease_horizon_ms:
            raise ValueError("proof validity exceeds maximum lease horizon")
        if not self.justification_trace or any(not item for item in self.justification_trace):
            raise ValueError("justification trace must be nonempty")
        if (
            self.artifact_type is ArtifactType.DECISION_CERTIFICATE
            and self.decision not in DECISION_RESULTS
        ):
            raise ValueError("unsupported consequential decision result")
        if (
            self.artifact_type is ArtifactType.AUTHORITY_LEASE
            and self.decision != "AUTHORIZE_ENVELOPE"
        ):
            raise ValueError("authority lease must use AUTHORIZE_ENVELOPE")
        if (
            self.artifact_type is ArtifactType.EMERGENCY_CAPABILITY
            and self.decision != "AUTHORIZE_EMERGENCY_CAPABILITY"
        ):
            raise ValueError("emergency capability must use AUTHORIZE_EMERGENCY_CAPABILITY")
        normalized = dict(self.evidence_hashes)
        if not normalized or any(
            not key or not _is_sha256(value) for key, value in normalized.items()
        ):
            raise ValueError("evidence hashes must be a nonempty SHA-256 map")
        object.__setattr__(self, "evidence_hashes", MappingProxyType(normalized))
        for value, label in (
            (self.previous_event_hash, "previous event hash"),
            (self.context_hash, "context hash"),
            (self.envelope.policy_hash, "policy hash"),
            (self.envelope.mvsg_hash, "MVSG hash"),
        ):
            if not _is_sha256(value):
                raise ValueError(f"{label} must be lowercase SHA-256 hex")
        if self.artifact_type is ArtifactType.AUTHORITY_LEASE and self.parent_authority_ref is None:
            return
        if self.parent_authority_ref is None or not _is_sha256(self.parent_authority_ref):
            raise ValueError("non-root artifacts require a parent-authority SHA-256 reference")

    def to_obj(self) -> dict[str, Any]:
        envelope = envelope_to_obj(self.envelope)
        return {
            "artifact_family": "edge-lifeline-proof-v1",
            "artifact_type": self.artifact_type.value,
            "artifact_id": self.artifact_id,
            "lease_id": self.lease_id,
            "parent_authority_ref": self.parent_authority_ref,
            "issuer": self.issuer,
            "edge_identity": self.edge_identity,
            "permitted_actions": sorted(self.envelope.actions),
            "permitted_resources": sorted(self.envelope.resources),
            "isolation_epoch": self.envelope.isolation_epoch,
            "issued_at_ms": self.issued_at_ms,
            "activation_not_before_ms": self.activation_not_before_ms,
            "expiration_ms": self.expiration_ms,
            "clock_uncertainty_allowance_ms": self.clock_uncertainty_allowance_ms,
            "data_freshness_requirements": {
                "max_data_age_ms": self.envelope.max_data_age_ms,
                "max_identity_cache_age_ms": self.envelope.max_identity_cache_age_ms,
                "max_revocation_staleness_ms": self.envelope.max_revocation_staleness_ms,
            },
            "energy_and_resource_budgets": envelope["budgets"],
            "safety_and_physical_impact_limit": envelope["max_impact"],
            "financial_exposure_limit_cents": self.envelope.max_financial_exposure_cents,
            "required_approval_level": envelope["min_approval"],
            "security_posture_requirement": envelope["min_security_posture"],
            "policy_version": self.policy_version,
            "policy_hash": self.envelope.policy_hash,
            "mvsg_hash": self.envelope.mvsg_hash,
            "evidence_hashes": dict(sorted(self.evidence_hashes.items())),
            "decision": self.decision,
            "justification_trace": list(self.justification_trace),
            "nonce": self.nonce,
            "replay_domain": self.replay_domain,
            "previous_event_hash": self.previous_event_hash,
            "context_hash": self.context_hash,
            "authority_envelope": envelope,
        }

    def payload(self) -> bytes:
        return canonical_dumps(self.to_obj())

    @classmethod
    def from_payload(cls, payload: bytes) -> ProofClaims:
        value = strict_loads(payload)
        if not isinstance(value, dict) or set(value) != _REQUIRED_KEYS:
            raise ValueError("proof payload has missing or unknown fields")
        if value["artifact_family"] != "edge-lifeline-proof-v1":
            raise ValueError("unsupported proof artifact family")
        envelope = envelope_from_obj(value["authority_envelope"])
        _validate_redundant_fields(value, envelope)
        evidence = value["evidence_hashes"]
        trace = value["justification_trace"]
        if not isinstance(evidence, dict) or not isinstance(trace, list):
            raise ValueError("invalid evidence or justification encoding")
        return cls(
            artifact_type=ArtifactType(value["artifact_type"]),
            artifact_id=str(value["artifact_id"]),
            lease_id=str(value["lease_id"]),
            parent_authority_ref=value["parent_authority_ref"],
            issuer=str(value["issuer"]),
            edge_identity=str(value["edge_identity"]),
            issued_at_ms=int(value["issued_at_ms"]),
            activation_not_before_ms=int(value["activation_not_before_ms"]),
            expiration_ms=int(value["expiration_ms"]),
            clock_uncertainty_allowance_ms=int(value["clock_uncertainty_allowance_ms"]),
            policy_version=str(value["policy_version"]),
            envelope=envelope,
            evidence_hashes={str(key): str(item) for key, item in evidence.items()},
            decision=str(value["decision"]),
            justification_trace=tuple(str(item) for item in trace),
            nonce=str(value["nonce"]),
            replay_domain=str(value["replay_domain"]),
            previous_event_hash=str(value["previous_event_hash"]),
            context_hash=str(value["context_hash"]),
        )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(item in "0123456789abcdef" for item in value)
    )


def _validate_redundant_fields(value: dict[Any, Any], envelope: AuthorityEnvelope) -> None:
    expected = {
        "permitted_actions": sorted(envelope.actions),
        "permitted_resources": sorted(envelope.resources),
        "isolation_epoch": envelope.isolation_epoch,
        "activation_not_before_ms": envelope.time_window.not_before_ms,
        "expiration_ms": envelope.time_window.expires_at_ms,
        "data_freshness_requirements": {
            "max_data_age_ms": envelope.max_data_age_ms,
            "max_identity_cache_age_ms": envelope.max_identity_cache_age_ms,
            "max_revocation_staleness_ms": envelope.max_revocation_staleness_ms,
        },
        "energy_and_resource_budgets": envelope_to_obj(envelope)["budgets"],
        "safety_and_physical_impact_limit": int(envelope.max_impact),
        "financial_exposure_limit_cents": envelope.max_financial_exposure_cents,
        "required_approval_level": int(envelope.min_approval),
        "security_posture_requirement": int(envelope.min_security_posture),
        "policy_hash": envelope.policy_hash,
        "mvsg_hash": envelope.mvsg_hash,
    }
    for key, expected_value in expected.items():
        if value[key] != expected_value:
            raise ValueError(f"redundant proof field differs from authority envelope: {key}")


_REQUIRED_KEYS = {
    "artifact_family",
    "artifact_type",
    "artifact_id",
    "lease_id",
    "parent_authority_ref",
    "issuer",
    "edge_identity",
    "permitted_actions",
    "permitted_resources",
    "isolation_epoch",
    "issued_at_ms",
    "activation_not_before_ms",
    "expiration_ms",
    "clock_uncertainty_allowance_ms",
    "data_freshness_requirements",
    "energy_and_resource_budgets",
    "safety_and_physical_impact_limit",
    "financial_exposure_limit_cents",
    "required_approval_level",
    "security_posture_requirement",
    "policy_version",
    "policy_hash",
    "mvsg_hash",
    "evidence_hashes",
    "decision",
    "justification_trace",
    "nonce",
    "replay_domain",
    "previous_event_hash",
    "context_hash",
    "authority_envelope",
}
