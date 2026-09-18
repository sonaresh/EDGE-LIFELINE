"""Deterministic reconciliation plan and receipt payload models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from edge_lifeline.proof.codec import canonical_dumps, sha256_hex, strict_loads


class EventDisposition(StrEnum):
    MERGE_OBSERVATION = "MERGE_OBSERVATION"
    MERGE_COMMUTATIVE = "MERGE_COMMUTATIVE"
    ACCEPT_STATE = "ACCEPT_STATE"
    EMIT_COMPENSATION = "EMIT_COMPENSATION"
    REQUIRE_HUMAN_REVIEW = "REQUIRE_HUMAN_REVIEW"
    PRESERVE_EFFECT_NO_REPLAY = "PRESERVE_EFFECT_NO_REPLAY"
    DEDUPLICATE_EFFECT_NO_REPLAY = "DEDUPLICATE_EFFECT_NO_REPLAY"
    QUARANTINE = "QUARANTINE"


@dataclass(frozen=True, slots=True)
class Resolution:
    event_hash: str
    disposition: EventDisposition
    reason: str
    related_event_hashes: tuple[str, ...] = ()
    compensation_kind: str | None = None

    def __post_init__(self) -> None:
        if not _is_hash(self.event_hash):
            raise ValueError("resolution event hash must be SHA-256")
        if not self.reason:
            raise ValueError("resolution reason cannot be empty")
        if len(self.related_event_hashes) != len(set(self.related_event_hashes)) or any(
            not _is_hash(item) for item in self.related_event_hashes
        ):
            raise ValueError("related event hashes must be unique SHA-256 values")

    def to_obj(self) -> dict[str, Any]:
        return {
            "event_hash": self.event_hash,
            "disposition": self.disposition.value,
            "reason": self.reason,
            "related_event_hashes": list(self.related_event_hashes),
            "compensation_kind": self.compensation_kind,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationPlan:
    episode_id: str
    isolation_epoch: str
    input_frontier: tuple[str, ...]
    resolutions: tuple[Resolution, ...]
    authority_restored: bool = False
    fresh_connected_epoch_lease_required: bool = True
    effect_replay_count: int = 0

    def __post_init__(self) -> None:
        if not self.episode_id or not self.isolation_epoch:
            raise ValueError("reconciliation identifiers cannot be empty")
        if self.authority_restored:
            raise ValueError("reconciliation cannot restore authority")
        if not self.fresh_connected_epoch_lease_required:
            raise ValueError("a fresh connected-epoch lease is mandatory")
        if self.effect_replay_count != 0:
            raise ValueError("reconciliation must not replay effects")
        hashes = tuple(item.event_hash for item in self.resolutions)
        if len(hashes) != len(set(hashes)):
            raise ValueError("a reconciliation plan cannot resolve an event twice")
        if hashes != tuple(sorted(hashes)):
            raise ValueError("reconciliation resolutions must use deterministic hash order")
        if tuple(self.input_frontier) != tuple(sorted(set(self.input_frontier))) or any(
            not _is_hash(item) for item in self.input_frontier
        ):
            raise ValueError("input frontier must be sorted unique SHA-256 values")

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": "edge-lifeline-reconciliation-plan-v1",
            "episode_id": self.episode_id,
            "isolation_epoch": self.isolation_epoch,
            "input_frontier": list(self.input_frontier),
            "resolutions": [item.to_obj() for item in self.resolutions],
            "authority_restored": self.authority_restored,
            "fresh_connected_epoch_lease_required": self.fresh_connected_epoch_lease_required,
            "effect_replay_count": self.effect_replay_count,
        }

    def payload(self) -> bytes:
        return canonical_dumps(self.to_obj())

    @property
    def digest(self) -> str:
        return sha256_hex(self.payload())


@dataclass(frozen=True, slots=True)
class ReconciliationReceipt:
    receipt_id: str
    reconciler_identity: str
    issued_at_ms: int
    plan_digest: str
    checkpoint_hash: str
    accepted_event_hashes: tuple[str, ...]
    quarantined_event_hashes: tuple[str, ...]
    authority_restored: bool = False
    fresh_connected_epoch_lease_required: bool = True
    effect_replay_count: int = 0

    def __post_init__(self) -> None:
        values = (self.receipt_id, self.reconciler_identity)
        if any(not value or len(value) > 256 for value in values) or self.issued_at_ms < 0:
            raise ValueError("invalid reconciliation receipt identity or time")
        for digest in (self.plan_digest, self.checkpoint_hash):
            if not _is_hash(digest):
                raise ValueError("receipt digest must be SHA-256")
        all_event_hashes = self.accepted_event_hashes + self.quarantined_event_hashes
        if len(all_event_hashes) != len(set(all_event_hashes)) or any(
            not _is_hash(item) for item in all_event_hashes
        ):
            raise ValueError("receipt event hashes must be unique SHA-256 values")
        if self.authority_restored or not self.fresh_connected_epoch_lease_required:
            raise ValueError("receipt cannot restore authority or waive a fresh lease")
        if self.effect_replay_count != 0:
            raise ValueError("receipt cannot attest to replayed effects")

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": "edge-lifeline-reconciliation-receipt-v1",
            "receipt_id": self.receipt_id,
            "reconciler_identity": self.reconciler_identity,
            "issued_at_ms": self.issued_at_ms,
            "plan_digest": self.plan_digest,
            "checkpoint_hash": self.checkpoint_hash,
            "accepted_event_hashes": list(self.accepted_event_hashes),
            "quarantined_event_hashes": list(self.quarantined_event_hashes),
            "authority_restored": self.authority_restored,
            "fresh_connected_epoch_lease_required": self.fresh_connected_epoch_lease_required,
            "effect_replay_count": self.effect_replay_count,
        }

    def payload(self) -> bytes:
        return canonical_dumps(self.to_obj())

    @classmethod
    def from_payload(cls, payload: bytes) -> ReconciliationReceipt:
        value = strict_loads(payload)
        if not isinstance(value, dict) or set(value) != _RECEIPT_KEYS:
            raise ValueError("reconciliation receipt has missing or unknown fields")
        if value["schema_version"] != "edge-lifeline-reconciliation-receipt-v1":
            raise ValueError("unsupported reconciliation-receipt schema")
        return cls(
            receipt_id=str(value["receipt_id"]),
            reconciler_identity=str(value["reconciler_identity"]),
            issued_at_ms=int(value["issued_at_ms"]),
            plan_digest=str(value["plan_digest"]),
            checkpoint_hash=str(value["checkpoint_hash"]),
            accepted_event_hashes=tuple(str(item) for item in value["accepted_event_hashes"]),
            quarantined_event_hashes=tuple(str(item) for item in value["quarantined_event_hashes"]),
            authority_restored=bool(value["authority_restored"]),
            fresh_connected_epoch_lease_required=bool(
                value["fresh_connected_epoch_lease_required"]
            ),
            effect_replay_count=int(value["effect_replay_count"]),
        )


@dataclass(frozen=True, slots=True)
class LedgerCheckpoint:
    checkpoint_id: str
    witness_identity: str
    issued_at_ms: int
    isolation_epoch: str
    frontier: tuple[str, ...]
    accepted_history_root: str
    prior_checkpoint_hash: str | None

    def __post_init__(self) -> None:
        if not self.checkpoint_id or not self.witness_identity or not self.isolation_epoch:
            raise ValueError("checkpoint identifiers cannot be empty")
        if self.issued_at_ms < 0 or not self.frontier:
            raise ValueError("checkpoint requires time and a nonempty frontier")
        hashes: tuple[str, ...] = (*self.frontier, self.accepted_history_root)
        if self.prior_checkpoint_hash is not None:
            hashes += (self.prior_checkpoint_hash,)
        if any(
            len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
            for item in hashes
        ):
            raise ValueError("checkpoint fields must use SHA-256 hashes")

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": "edge-lifeline-ledger-checkpoint-v1",
            "checkpoint_id": self.checkpoint_id,
            "witness_identity": self.witness_identity,
            "issued_at_ms": self.issued_at_ms,
            "isolation_epoch": self.isolation_epoch,
            "frontier": list(self.frontier),
            "accepted_history_root": self.accepted_history_root,
            "prior_checkpoint_hash": self.prior_checkpoint_hash,
        }

    def payload(self) -> bytes:
        return canonical_dumps(self.to_obj())

    @classmethod
    def from_payload(cls, payload: bytes) -> LedgerCheckpoint:
        value = strict_loads(payload)
        if not isinstance(value, dict) or set(value) != _CHECKPOINT_KEYS:
            raise ValueError("checkpoint has missing or unknown fields")
        if value["schema_version"] != "edge-lifeline-ledger-checkpoint-v1":
            raise ValueError("unsupported checkpoint schema")
        return cls(
            checkpoint_id=str(value["checkpoint_id"]),
            witness_identity=str(value["witness_identity"]),
            issued_at_ms=int(value["issued_at_ms"]),
            isolation_epoch=str(value["isolation_epoch"]),
            frontier=tuple(str(item) for item in value["frontier"]),
            accepted_history_root=str(value["accepted_history_root"]),
            prior_checkpoint_hash=value["prior_checkpoint_hash"],
        )


_RECEIPT_KEYS = {
    "schema_version",
    "receipt_id",
    "reconciler_identity",
    "issued_at_ms",
    "plan_digest",
    "checkpoint_hash",
    "accepted_event_hashes",
    "quarantined_event_hashes",
    "authority_restored",
    "fresh_connected_epoch_lease_required",
    "effect_replay_count",
}

_CHECKPOINT_KEYS = {
    "schema_version",
    "checkpoint_id",
    "witness_identity",
    "issued_at_ms",
    "isolation_epoch",
    "frontier",
    "accepted_history_root",
    "prior_checkpoint_hash",
}


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
