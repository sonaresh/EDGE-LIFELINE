"""Append-only SQLite persistence for verified causal events and quarantine evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from edge_lifeline.ledger.model import EventClass, VerifiedEvent


class LedgerError(ValueError):
    """A durable causal-ledger transaction was rejected."""


class CausalLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS causal_events (
                    event_hash TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    edge_identity TEXT NOT NULL,
                    isolation_epoch TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    previous_event_hash TEXT,
                    encoded BLOB NOT NULL,
                    event_class TEXT NOT NULL,
                    effect_id TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    UNIQUE(edge_identity, isolation_epoch, sequence)
                );
                CREATE TABLE IF NOT EXISTS irreversible_effects (
                    effect_id TEXT PRIMARY KEY,
                    event_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status = 'RECORDED_NO_REPLAY'),
                    FOREIGN KEY(event_hash) REFERENCES causal_events(event_hash)
                );
                CREATE TABLE IF NOT EXISTS quarantined_events (
                    event_hash TEXT PRIMARY KEY,
                    reasons_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signed_receipts (
                    receipt_hash TEXT PRIMARY KEY,
                    encoded BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signed_checkpoints (
                    checkpoint_hash TEXT PRIMARY KEY,
                    encoded BLOB NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def append_verified(self, events: tuple[VerifiedEvent, ...]) -> None:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                present = {
                    str(row[0])
                    for row in connection.execute("SELECT event_hash FROM causal_events").fetchall()
                }
                for verified in events:
                    event = verified.event
                    if (
                        event.previous_event_hash is not None
                        and event.previous_event_hash not in present
                    ):
                        raise LedgerError("previous event is not durably present in causal order")
                    connection.execute(
                        "INSERT INTO causal_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            verified.event_hash,
                            event.event_id,
                            event.edge_identity,
                            event.isolation_epoch,
                            event.sequence,
                            event.previous_event_hash,
                            verified.encoded,
                            event.event_class.value,
                            event.effect_id,
                            event.idempotency_key,
                        ),
                    )
                    if event.event_class is EventClass.IRREVERSIBLE_PHYSICAL:
                        connection.execute(
                            "INSERT INTO irreversible_effects VALUES (?, ?, 'RECORDED_NO_REPLAY')",
                            (event.effect_id, verified.event_hash),
                        )
                    present.add(verified.event_hash)
                connection.commit()
        except LedgerError:
            raise
        except sqlite3.IntegrityError as error:
            raise LedgerError("event replay, fork, sequence collision, or effect replay") from error
        except sqlite3.DatabaseError as error:
            raise LedgerError("atomic causal-ledger transaction failed") from error

    def record_quarantine(self, quarantined: dict[str, tuple[str, ...]]) -> None:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for event_hash, reasons in sorted(quarantined.items()):
                    connection.execute(
                        "INSERT OR IGNORE INTO quarantined_events VALUES (?, ?)",
                        (event_hash, json.dumps(reasons, separators=(",", ":"))),
                    )
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise LedgerError("quarantine evidence transaction failed") from error

    def event_hashes(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_hash FROM causal_events ORDER BY event_hash"
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def irreversible_effect_ids(self) -> frozenset[str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT effect_id FROM irreversible_effects").fetchall()
        return frozenset(str(row[0]) for row in rows)

    def persist_receipt(self, receipt_hash: str, encoded: bytes) -> None:
        self._persist_signed("signed_receipts", "receipt_hash", receipt_hash, encoded)

    def persist_checkpoint(self, checkpoint_hash: str, encoded: bytes) -> None:
        self._persist_signed("signed_checkpoints", "checkpoint_hash", checkpoint_hash, encoded)

    def _persist_signed(self, table: str, key_column: str, digest: str, encoded: bytes) -> None:
        if table not in {"signed_receipts", "signed_checkpoints"}:
            raise LedgerError("unsupported signed-artifact table")
        try:
            with self._connect() as connection:
                connection.execute(
                    f"INSERT INTO {table} ({key_column}, encoded) VALUES (?, ?)",  # noqa: S608
                    (digest, encoded),
                )
        except sqlite3.IntegrityError as error:
            raise LedgerError("signed artifact replay detected") from error
        except sqlite3.DatabaseError as error:
            raise LedgerError("signed artifact persistence failed") from error
