"""Signed reconciliation receipts and witnessed ledger checkpoints."""

from __future__ import annotations

from dataclasses import dataclass

from edge_lifeline.proof.codec import sha256_hex
from edge_lifeline.proof.cose import (
    SigningPrivateKey,
    SigningPublicKey,
    parse_sign1,
    sign1,
    verify_sign1,
)
from edge_lifeline.reconcile.model import LedgerCheckpoint, ReconciliationReceipt

RecoveryPayload = ReconciliationReceipt | LedgerCheckpoint


@dataclass(frozen=True, slots=True)
class SignedRecoveryArtifact:
    payload: RecoveryPayload
    encoded: bytes
    artifact_hash: str
    key_id: bytes


@dataclass(frozen=True, slots=True)
class RecoverySigner:
    identity: str
    key_id: bytes
    private_key: SigningPrivateKey

    def issue(self, payload: RecoveryPayload) -> bytes:
        claimed_identity = (
            payload.reconciler_identity
            if isinstance(payload, ReconciliationReceipt)
            else payload.witness_identity
        )
        if claimed_identity != self.identity:
            raise ValueError("recovery artifact identity does not match signer")
        return sign1(payload.payload(), key_id=self.key_id, private_key=self.private_key)


def verify_recovery_artifact(
    encoded: bytes,
    *,
    public_key: SigningPublicKey,
    expected_key_id: bytes,
    payload_type: type[ReconciliationReceipt] | type[LedgerCheckpoint],
    expected_identity: str,
) -> SignedRecoveryArtifact:
    parsed = parse_sign1(encoded)
    if parsed.key_id != expected_key_id:
        raise ValueError("unexpected recovery-artifact key identifier")
    verified = verify_sign1(encoded, public_key)
    payload = payload_type.from_payload(verified.payload)
    claimed_identity = (
        payload.reconciler_identity
        if isinstance(payload, ReconciliationReceipt)
        else payload.witness_identity
    )
    if claimed_identity != expected_identity:
        raise ValueError("recovery-artifact signer identity mismatch")
    return SignedRecoveryArtifact(payload, encoded, sha256_hex(encoded), parsed.key_id)
