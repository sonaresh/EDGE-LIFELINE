"""Phase 3 proof-carrying authority artifacts and verification."""

from edge_lifeline.proof.artifact import ArtifactType, ProofClaims
from edge_lifeline.proof.cose import CoseSign1, sign1, verify_sign1
from edge_lifeline.proof.issuer import AuthorityIssuer
from edge_lifeline.proof.verifier import (
    AuthenticatedProof,
    EdgeProofVerifier,
    VerificationContext,
    VerifiedProof,
)

__all__ = [
    "ArtifactType",
    "AuthenticatedProof",
    "AuthorityIssuer",
    "CoseSign1",
    "EdgeProofVerifier",
    "ProofClaims",
    "VerificationContext",
    "VerifiedProof",
    "sign1",
    "verify_sign1",
]
