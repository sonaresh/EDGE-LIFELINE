"""Durable atomic replay, budget, certificate, and effect registration store."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from edge_lifeline.formal.authority import Budgets, ImpactClass
from edge_lifeline.proof.artifact import ArtifactType
from edge_lifeline.proof.verifier import VerificationContext, VerifiedProof


class ProofStoreError(ValueError):
    """A durable admission transaction was rejected."""


@dataclass(frozen=True, slots=True)
class CommitReceipt:
    artifact_hash: str
    lease_id: str
    nonce: str
    effect_id: str
    status: str


_BUDGET_FIELDS = (
    "energy_mj",
    "cpu_ms",
    "memory_mb_s",
    "storage_bytes",
    "network_bytes",
    "action_count",
)


class DurableProofStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS activated_leases (
                    artifact_hash TEXT PRIMARY KEY,
                    lease_id TEXT NOT NULL,
                    replay_domain TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    energy_mj INTEGER NOT NULL,
                    cpu_ms INTEGER NOT NULL,
                    memory_mb_s INTEGER NOT NULL,
                    storage_bytes INTEGER NOT NULL,
                    network_bytes INTEGER NOT NULL,
                    action_count INTEGER NOT NULL,
                    activation_not_before_ms INTEGER NOT NULL,
                    expiration_ms INTEGER NOT NULL,
                    max_impact INTEGER NOT NULL,
                    max_financial_exposure_cents INTEGER NOT NULL,
                    UNIQUE(replay_domain, nonce)
                );
                CREATE TABLE IF NOT EXISTS consumed_nonces (
                    replay_domain TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    artifact_hash TEXT NOT NULL,
                    PRIMARY KEY(replay_domain, nonce)
                );
                CREATE TABLE IF NOT EXISTS budget_usage (
                    lease_id TEXT PRIMARY KEY,
                    energy_mj INTEGER NOT NULL,
                    cpu_ms INTEGER NOT NULL,
                    memory_mb_s INTEGER NOT NULL,
                    storage_bytes INTEGER NOT NULL,
                    network_bytes INTEGER NOT NULL,
                    action_count INTEGER NOT NULL,
                    financial_exposure_cents INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS certificates (
                    artifact_hash TEXT PRIMARY KEY,
                    artifact BLOB NOT NULL,
                    lease_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('COMMITTED', 'DISPATCHED'))
                );
                CREATE TABLE IF NOT EXISTS effects (
                    effect_id TEXT PRIMARY KEY,
                    artifact_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status IN ('PENDING', 'DISPATCHED')),
                    FOREIGN KEY(artifact_hash) REFERENCES certificates(artifact_hash)
                );
                """
            )

    def activate_lease(self, proof: VerifiedProof) -> None:
        claims = proof.claims
        if proof.verified_context_hash != claims.context_hash:
            raise ProofStoreError("lease lacks full context verification")
        if claims.artifact_type not in {
            ArtifactType.AUTHORITY_LEASE,
            ArtifactType.EMERGENCY_CAPABILITY,
        }:
            raise ProofStoreError("only authority artifacts can be activated")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO activated_leases VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        proof.artifact_hash,
                        claims.lease_id,
                        claims.replay_domain,
                        claims.nonce,
                        *[getattr(claims.envelope.budgets, field) for field in _BUDGET_FIELDS],
                        claims.activation_not_before_ms,
                        claims.expiration_ms,
                        int(claims.envelope.max_impact),
                        claims.envelope.max_financial_exposure_cents,
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as error:
            raise ProofStoreError("authority lease replay detected") from error

    def commit_decision(
        self,
        proof: VerifiedProof,
        *,
        cost: Budgets,
        effect_id: str,
        context: VerificationContext,
    ) -> CommitReceipt:
        claims = proof.claims
        if proof.verified_context_hash != claims.context_hash:
            raise ProofStoreError("decision lacks full context verification")
        if claims.artifact_type is not ArtifactType.DECISION_CERTIFICATE:
            raise ProofStoreError("only decision certificates can authorize an effect")
        if not effect_id:
            raise ProofStoreError("effect identifier cannot be empty")
        if context.binding_hash() != claims.context_hash:
            raise ProofStoreError("commit context is not bound by the decision certificate")
        if not cost.is_no_more_than(claims.envelope.budgets):
            raise ProofStoreError("effect cost exceeds decision certificate budget")
        if context.requested_impact > claims.envelope.max_impact:
            raise ProofStoreError("effect exceeds decision physical-impact limit")
        if (
            context.requested_financial_exposure_cents
            > claims.envelope.max_financial_exposure_cents
        ):
            raise ProofStoreError("effect exceeds decision financial-exposure limit")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                active = connection.execute(
                    "SELECT lease_id, energy_mj, cpu_ms, memory_mb_s, storage_bytes, "
                    "network_bytes, action_count, activation_not_before_ms, expiration_ms, "
                    "max_impact, max_financial_exposure_cents "
                    "FROM activated_leases "
                    "WHERE artifact_hash = ?",
                    (claims.parent_authority_ref,),
                ).fetchone()
                if active is None or str(active[0]) != claims.lease_id:
                    raise ProofStoreError("decision parent lease is not activated")
                lease_budget = Budgets(*map(int, active[1:7]))
                if (
                    context.trusted_time.lower_ms < int(active[7])
                    or context.trusted_time.upper_ms >= int(active[8])
                    or context.trusted_time.lower_ms < claims.activation_not_before_ms
                    or context.trusted_time.upper_ms >= claims.expiration_ms
                ):
                    raise ProofStoreError("authority expired or validity is unprovable at commit")
                if context.requested_impact > ImpactClass(int(active[9])):
                    raise ProofStoreError("effect exceeds activated lease physical-impact limit")
                connection.execute(
                    "INSERT INTO consumed_nonces VALUES (?, ?, ?)",
                    (claims.replay_domain, claims.nonce, proof.artifact_hash),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO budget_usage VALUES (?, 0, 0, 0, 0, 0, 0, 0)",
                    (claims.lease_id,),
                )
                row = connection.execute(
                    "SELECT energy_mj, cpu_ms, memory_mb_s, storage_bytes, "
                    "network_bytes, action_count, financial_exposure_cents "
                    "FROM budget_usage WHERE lease_id = ?",
                    (claims.lease_id,),
                ).fetchone()
                if row is None:
                    raise ProofStoreError("budget state is unavailable")
                used = Budgets(*map(int, row[:6]))
                updated = used.add(cost)
                if not updated.is_no_more_than(lease_budget):
                    raise ProofStoreError("authority budget exceeded")
                updated_financial = int(row[6]) + context.requested_financial_exposure_cents
                if updated_financial > int(active[10]):
                    raise ProofStoreError("activated lease financial exposure exceeded")
                connection.execute(
                    "UPDATE budget_usage SET energy_mj=?, cpu_ms=?, memory_mb_s=?, "
                    "storage_bytes=?, network_bytes=?, action_count=?, "
                    "financial_exposure_cents=? WHERE lease_id=?",
                    (
                        *[getattr(updated, field) for field in _BUDGET_FIELDS],
                        updated_financial,
                        claims.lease_id,
                    ),
                )
                connection.execute(
                    "INSERT INTO certificates VALUES (?, ?, ?, 'COMMITTED')",
                    (proof.artifact_hash, proof.encoded, claims.lease_id),
                )
                connection.execute(
                    "INSERT INTO effects VALUES (?, ?, 'PENDING')",
                    (effect_id, proof.artifact_hash),
                )
                connection.commit()
        except ProofStoreError:
            raise
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed" in str(error):
                raise ProofStoreError(
                    "replay, duplicate certificate, or duplicate effect detected"
                ) from error
            raise ProofStoreError("atomic proof transaction failed") from error
        except sqlite3.DatabaseError as error:
            raise ProofStoreError("atomic proof transaction failed") from error
        return CommitReceipt(
            proof.artifact_hash,
            claims.lease_id,
            claims.nonce,
            effect_id,
            "COMMITTED",
        )

    def authorize_dispatch(self, *, artifact_hash: str, effect_id: str) -> CommitReceipt:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT c.lease_id, c.status, e.status FROM certificates c "
                    "JOIN effects e ON e.artifact_hash = c.artifact_hash "
                    "WHERE c.artifact_hash = ? AND e.effect_id = ?",
                    (artifact_hash, effect_id),
                ).fetchone()
                if row is None or row[1:] != ("COMMITTED", "PENDING"):
                    raise ProofStoreError("effect lacks a uniquely committed certificate")
                connection.execute(
                    "UPDATE certificates SET status='DISPATCHED' WHERE artifact_hash=?",
                    (artifact_hash,),
                )
                connection.execute(
                    "UPDATE effects SET status='DISPATCHED' WHERE effect_id=?",
                    (effect_id,),
                )
                connection.commit()
                return CommitReceipt(artifact_hash, str(row[0]), "", effect_id, "DISPATCHED")
        except ProofStoreError:
            raise
        except sqlite3.DatabaseError as error:
            raise ProofStoreError("dispatch authorization transaction failed") from error

    def nonce_consumed(self, replay_domain: str, nonce: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM consumed_nonces WHERE replay_domain=? AND nonce=?",
                (replay_domain, nonce),
            ).fetchone()
            return row is not None

    def budget_usage(self, lease_id: str) -> Budgets:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT energy_mj, cpu_ms, memory_mb_s, storage_bytes, "
                "network_bytes, action_count FROM budget_usage WHERE lease_id=?",
                (lease_id,),
            ).fetchone()
        return Budgets(0, 0, 0, 0, 0, 0) if row is None else Budgets(*map(int, row))

    def financial_exposure(self, lease_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT financial_exposure_cents FROM budget_usage WHERE lease_id=?",
                (lease_id,),
            ).fetchone()
        return 0 if row is None else int(row[0])
