"""Cloud or edge authority artifact issuer."""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from edge_lifeline.proof.artifact import ProofClaims
from edge_lifeline.proof.codec import sha256_hex
from edge_lifeline.proof.cose import sign1


@dataclass(frozen=True, slots=True)
class AuthorityIssuer:
    identity: str
    key_id: bytes
    private_key: Ed25519PrivateKey

    def issue(self, claims: ProofClaims) -> bytes:
        if claims.issuer != self.identity:
            raise ValueError("claim issuer does not match signing identity")
        return sign1(claims.payload(), key_id=self.key_id, private_key=self.private_key)

    @staticmethod
    def authority_reference(encoded_artifact: bytes) -> str:
        return sha256_hex(encoded_artifact)
