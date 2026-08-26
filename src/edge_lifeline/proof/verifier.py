"""Strict edge verifier for proof-carrying authority and decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from edge_lifeline.formal.authority import ApprovalLevel, ImpactClass, SecurityPosture
from edge_lifeline.formal.time_bounds import TrustedTimeInterval
from edge_lifeline.proof.artifact import ArtifactType, ProofClaims
from edge_lifeline.proof.codec import canonical_dumps, sha256_hex
from edge_lifeline.proof.cose import CoseVerificationError, parse_sign1, verify_sign1


class ProofVerificationError(ValueError):
    """A fail-safe proof verification rejection."""


@dataclass(frozen=True, slots=True)
class TrustedSigner:
    issuer: str
    public_key: Ed25519PublicKey
    artifact_types: frozenset[ArtifactType]
    root_authority: bool = False


@dataclass(frozen=True, slots=True)
class VerificationContext:
    edge_identity: str
    isolation_epoch: str
    trusted_time: TrustedTimeInterval
    action: str
    resource: str
    policy_version: str
    policy_hash: str
    mvsg_hash: str
    verifier_profile_hash: str
    data_age_ms: int
    identity_cache_age_ms: int
    revocation_staleness_ms: int
    sensor_confidence_per_mille: int
    approval_level: ApprovalLevel
    security_posture: SecurityPosture
    requested_impact: ImpactClass
    requested_financial_exposure_cents: int
    expected_previous_event_hash: str
    evidence: Mapping[str, bytes]
    context_attributes: Mapping[str, str]

    def __post_init__(self) -> None:
        if (
            min(
                self.data_age_ms,
                self.identity_cache_age_ms,
                self.revocation_staleness_ms,
                self.sensor_confidence_per_mille,
                self.requested_financial_exposure_cents,
            )
            < 0
        ):
            raise ValueError("verification context measurements cannot be negative")
        if self.sensor_confidence_per_mille > 1000:
            raise ValueError("sensor confidence must be in [0, 1000]")
        if len(self.expected_previous_event_hash) != 64 or any(
            item not in "0123456789abcdef" for item in self.expected_previous_event_hash
        ):
            raise ValueError("expected previous event hash must be lowercase SHA-256 hex")
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))
        object.__setattr__(
            self,
            "context_attributes",
            MappingProxyType(dict(self.context_attributes)),
        )

    def binding_hash(self) -> str:
        return sha256_hex(
            canonical_dumps(
                {
                    "edge_identity": self.edge_identity,
                    "isolation_epoch": self.isolation_epoch,
                    "action": self.action,
                    "resource": self.resource,
                    "policy_version": self.policy_version,
                    "policy_hash": self.policy_hash,
                    "mvsg_hash": self.mvsg_hash,
                    "verifier_profile_hash": self.verifier_profile_hash,
                    "data_age_ms": self.data_age_ms,
                    "identity_cache_age_ms": self.identity_cache_age_ms,
                    "revocation_staleness_ms": self.revocation_staleness_ms,
                    "sensor_confidence_per_mille": self.sensor_confidence_per_mille,
                    "approval_level": int(self.approval_level),
                    "security_posture": int(self.security_posture),
                    "requested_impact": int(self.requested_impact),
                    "requested_financial_exposure_cents": self.requested_financial_exposure_cents,
                    "previous_event_hash": self.expected_previous_event_hash,
                    "context_attributes": dict(sorted(self.context_attributes.items())),
                }
            )
        )


@dataclass(frozen=True, slots=True)
class AuthenticatedProof:
    encoded: bytes
    artifact_hash: str
    key_id: bytes
    claims: ProofClaims


@dataclass(frozen=True, slots=True)
class VerifiedProof(AuthenticatedProof):
    verified_context_hash: str


class EdgeProofVerifier:
    def __init__(self, signers: Mapping[bytes, TrustedSigner]) -> None:
        self._signers = MappingProxyType(dict(signers))

    def decode_and_authenticate(self, encoded: bytes) -> AuthenticatedProof:
        try:
            parsed = parse_sign1(encoded)
        except CoseVerificationError as error:
            raise ProofVerificationError(str(error)) from error
        signer = self._signers.get(parsed.key_id)
        if signer is None:
            raise ProofVerificationError("unknown signing key")
        try:
            authenticated = verify_sign1(encoded, signer.public_key)
            claims = ProofClaims.from_payload(authenticated.payload)
        except (CoseVerificationError, ValueError) as error:
            raise ProofVerificationError(str(error)) from error
        if claims.issuer != signer.issuer:
            raise ProofVerificationError("issuer identity does not match trusted key")
        if claims.artifact_type not in signer.artifact_types:
            raise ProofVerificationError("signing key is not authorized for artifact type")
        return AuthenticatedProof(encoded, sha256_hex(encoded), parsed.key_id, claims)

    def verify(
        self,
        encoded: bytes,
        *,
        context: VerificationContext,
        parent_chain: tuple[bytes, ...],
    ) -> VerifiedProof:
        verified = self.decode_and_authenticate(encoded)
        claims = verified.claims
        self._verify_chain(verified, parent_chain)
        self._verify_context(claims, context)
        return VerifiedProof(
            verified.encoded,
            verified.artifact_hash,
            verified.key_id,
            verified.claims,
            context.binding_hash(),
        )

    def _verify_chain(
        self,
        verified: AuthenticatedProof,
        parent_chain: tuple[bytes, ...],
    ) -> None:
        claims = verified.claims
        if claims.parent_authority_ref is None:
            if parent_chain:
                raise ProofVerificationError("root artifact cannot carry a parent chain")
            if claims.artifact_type is not ArtifactType.AUTHORITY_LEASE:
                raise ProofVerificationError("only an authority lease can be a root artifact")
            if not self._signers[verified.key_id].root_authority:
                raise ProofVerificationError("signing key is not a trusted root authority")
            return
        if not parent_chain:
            raise ProofVerificationError("parent authority artifact is missing")
        child = claims
        expected_reference = child.parent_authority_ref
        for index, encoded_parent in enumerate(parent_chain):
            if sha256_hex(encoded_parent) != expected_reference:
                raise ProofVerificationError("parent authority reference hash mismatch")
            verified_parent = self.decode_and_authenticate(encoded_parent)
            parent = verified_parent.claims
            if parent.artifact_type not in {
                ArtifactType.AUTHORITY_LEASE,
                ArtifactType.EMERGENCY_CAPABILITY,
            }:
                raise ProofVerificationError("decision certificate cannot be an authority parent")
            if not child.envelope.is_no_more_authoritative_than(parent.envelope):
                raise ProofVerificationError("artifact authority exceeds an ancestor")
            if child.clock_uncertainty_allowance_ms > parent.clock_uncertainty_allowance_ms:
                raise ProofVerificationError("clock uncertainty allowance widened")
            if child.policy_version != parent.policy_version:
                raise ProofVerificationError("policy version changed within authority chain")
            if child.artifact_type is ArtifactType.DECISION_CERTIFICATE:
                if (
                    child.envelope.delegation_depth_remaining
                    > parent.envelope.delegation_depth_remaining
                ):
                    raise ProofVerificationError("decision increased delegation depth")
            elif (
                child.envelope.delegation_depth_remaining
                >= parent.envelope.delegation_depth_remaining
            ):
                raise ProofVerificationError("delegated authority depth did not contract")
            if child.edge_identity != parent.edge_identity:
                raise ProofVerificationError("authority chain edge identity changed")
            expected_reference = parent.parent_authority_ref
            child = parent
            if expected_reference is None:
                if index != len(parent_chain) - 1:
                    raise ProofVerificationError(
                        "authority chain contains artifacts above its root"
                    )
                if not self._signers[verified_parent.key_id].root_authority:
                    raise ProofVerificationError(
                        "authority chain terminates at an untrusted root signer"
                    )
                return
        raise ProofVerificationError("authority chain did not terminate at a trusted root")

    def _verify_context(self, claims: ProofClaims, context: VerificationContext) -> None:
        envelope = claims.envelope
        failures: list[str] = []
        if claims.edge_identity != context.edge_identity:
            failures.append("EDGE_IDENTITY_MISMATCH")
        if envelope.isolation_epoch != context.isolation_epoch:
            failures.append("ISOLATION_EPOCH_MISMATCH")
        if context.trusted_time.lower_ms < claims.activation_not_before_ms:
            failures.append("NOT_YET_VALID")
        if context.trusted_time.upper_ms >= claims.expiration_ms:
            failures.append("EXPIRED_OR_EXPIRATION_UNPROVABLE")
        if context.trusted_time.uncertainty_half_width_ms > claims.clock_uncertainty_allowance_ms:
            failures.append("CLOCK_UNCERTAINTY_EXCEEDED")
        if context.action not in envelope.actions:
            failures.append("ACTION_NOT_PERMITTED")
        if context.resource not in envelope.resources:
            failures.append("RESOURCE_NOT_PERMITTED")
        if (
            context.policy_version != claims.policy_version
            or context.policy_hash != envelope.policy_hash
        ):
            failures.append("POLICY_MISMATCH")
        if context.mvsg_hash != envelope.mvsg_hash:
            failures.append("MVSG_MISMATCH")
        if context.verifier_profile_hash != envelope.verifier_profile_hash:
            failures.append("VERIFIER_PROFILE_MISMATCH")
        if context.data_age_ms > envelope.max_data_age_ms:
            failures.append("DATA_STALE")
        if context.identity_cache_age_ms > envelope.max_identity_cache_age_ms:
            failures.append("IDENTITY_CACHE_STALE")
        if context.revocation_staleness_ms > envelope.max_revocation_staleness_ms:
            failures.append("REVOCATION_STATE_STALE")
        if context.sensor_confidence_per_mille < envelope.min_sensor_confidence_per_mille:
            failures.append("SENSOR_CONFIDENCE_INSUFFICIENT")
        if context.approval_level < envelope.min_approval:
            failures.append("APPROVAL_INSUFFICIENT")
        if context.security_posture < envelope.min_security_posture:
            failures.append("SECURITY_POSTURE_INSUFFICIENT")
        if context.requested_impact > envelope.max_impact:
            failures.append("PHYSICAL_IMPACT_LIMIT_EXCEEDED")
        if context.requested_financial_exposure_cents > envelope.max_financial_exposure_cents:
            failures.append("FINANCIAL_EXPOSURE_LIMIT_EXCEEDED")
        if claims.previous_event_hash != context.expected_previous_event_hash:
            failures.append("PREVIOUS_EVENT_HASH_MISMATCH")
        if context.binding_hash() != claims.context_hash:
            failures.append("CONTEXT_HASH_MISMATCH")
        if set(context.evidence) != set(claims.evidence_hashes):
            failures.append("EVIDENCE_SET_MISMATCH")
        else:
            for evidence_id, content in context.evidence.items():
                if sha256_hex(content) != claims.evidence_hashes[evidence_id]:
                    failures.append(f"EVIDENCE_HASH_MISMATCH:{evidence_id}")
        if failures:
            raise ProofVerificationError(";".join(failures))
