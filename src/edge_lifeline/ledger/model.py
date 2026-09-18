"""Canonical signed causal events used by Phase 6 reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from edge_lifeline.proof.codec import canonical_dumps, sha256_hex, strict_loads
from edge_lifeline.proof.cose import (
    CoseVerificationError,
    SigningPrivateKey,
    SigningPublicKey,
    parse_sign1,
    sign1,
    verify_sign1,
)


class EventClass(StrEnum):
    OBSERVATIONAL = "S0_OBSERVATIONAL"
    COMMUTATIVE = "S1_COMMUTATIVE"
    COMPENSATABLE = "S2_COMPENSATABLE"
    REVIEW_REQUIRED = "S3_REVIEW_REQUIRED"
    IRREVERSIBLE_PHYSICAL = "S4_IRREVERSIBLE_PHYSICAL"
    INVALID_OR_MALICIOUS = "S5_INVALID_OR_MALICIOUS"


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True, slots=True)
class CausalEvent:
    event_id: str
    edge_identity: str
    isolation_epoch: str
    sequence: int
    previous_event_hash: str | None
    causal_parent_hashes: tuple[str, ...]
    vector_clock: Mapping[str, int]
    lease_hash: str
    decision_certificate_hash: str
    event_class: EventClass
    event_kind: str
    conflict_key: str
    idempotency_key: str
    effect_id: str | None
    precondition_hash: str
    postcondition_hash: str
    payload_hash: str
    compensation_kind: str | None = None

    def __post_init__(self) -> None:
        identifiers = (
            self.event_id,
            self.edge_identity,
            self.isolation_epoch,
            self.event_kind,
            self.conflict_key,
            self.idempotency_key,
        )
        if any(not value or len(value) > 256 for value in identifiers):
            raise ValueError("event identifiers must contain 1..256 characters")
        if self.sequence < 0:
            raise ValueError("event sequence cannot be negative")
        parents = tuple(self.causal_parent_hashes)
        if len(parents) != len(set(parents)) or any(not _is_hash(value) for value in parents):
            raise ValueError("causal parents must be unique SHA-256 hashes")
        if self.previous_event_hash is None:
            if self.sequence != 0:
                raise ValueError("non-genesis event requires a previous-event hash")
        elif not _is_hash(self.previous_event_hash):
            raise ValueError("previous-event hash must be SHA-256")
        elif self.previous_event_hash not in parents:
            raise ValueError("previous event must also be a causal parent")
        clock = dict(self.vector_clock)
        if (
            not clock
            or any(not key or len(key) > 256 for key in clock)
            or any(not isinstance(value, int) or value <= 0 for value in clock.values())
            or clock.get(self.edge_identity) != self.sequence + 1
        ):
            raise ValueError("vector clock must contain positive counters and exact local sequence")
        object.__setattr__(self, "vector_clock", MappingProxyType(clock))
        object.__setattr__(self, "causal_parent_hashes", parents)
        for value, label in (
            (self.lease_hash, "lease hash"),
            (self.decision_certificate_hash, "decision-certificate hash"),
            (self.precondition_hash, "precondition hash"),
            (self.postcondition_hash, "postcondition hash"),
            (self.payload_hash, "payload hash"),
        ):
            if not _is_hash(value):
                raise ValueError(f"{label} must be SHA-256")
        if self.event_class is EventClass.IRREVERSIBLE_PHYSICAL and not self.effect_id:
            raise ValueError("S4 event requires an effect identifier")
        if self.event_class is EventClass.COMPENSATABLE and not self.compensation_kind:
            raise ValueError("S2 event requires a registered compensation kind")
        if self.event_class is EventClass.INVALID_OR_MALICIOUS:
            raise ValueError("S5 is a verifier classification, not an issuable event class")
        for optional in (self.effect_id, self.compensation_kind):
            if optional is not None and (not optional or len(optional) > 256):
                raise ValueError("optional event identifiers must contain 1..256 characters")

    def to_obj(self) -> dict[str, Any]:
        return {
            "schema_version": "edge-lifeline-causal-event-v1",
            "event_id": self.event_id,
            "edge_identity": self.edge_identity,
            "isolation_epoch": self.isolation_epoch,
            "sequence": self.sequence,
            "previous_event_hash": self.previous_event_hash,
            "causal_parent_hashes": list(self.causal_parent_hashes),
            "vector_clock": dict(sorted(self.vector_clock.items())),
            "lease_hash": self.lease_hash,
            "decision_certificate_hash": self.decision_certificate_hash,
            "event_class": self.event_class.value,
            "event_kind": self.event_kind,
            "conflict_key": self.conflict_key,
            "idempotency_key": self.idempotency_key,
            "effect_id": self.effect_id,
            "precondition_hash": self.precondition_hash,
            "postcondition_hash": self.postcondition_hash,
            "payload_hash": self.payload_hash,
            "compensation_kind": self.compensation_kind,
        }

    def payload(self) -> bytes:
        return canonical_dumps(self.to_obj())

    @classmethod
    def from_payload(cls, payload: bytes) -> CausalEvent:
        value = strict_loads(payload)
        if not isinstance(value, dict) or set(value) != _EVENT_KEYS:
            raise ValueError("causal event has missing or unknown fields")
        if value["schema_version"] != "edge-lifeline-causal-event-v1":
            raise ValueError("unsupported causal-event schema")
        parents = value["causal_parent_hashes"]
        clock = value["vector_clock"]
        if not isinstance(parents, list) or not isinstance(clock, dict):
            raise ValueError("invalid causal-parent or vector-clock encoding")
        return cls(
            event_id=str(value["event_id"]),
            edge_identity=str(value["edge_identity"]),
            isolation_epoch=str(value["isolation_epoch"]),
            sequence=int(value["sequence"]),
            previous_event_hash=value["previous_event_hash"],
            causal_parent_hashes=tuple(str(item) for item in parents),
            vector_clock={str(key): int(item) for key, item in clock.items()},
            lease_hash=str(value["lease_hash"]),
            decision_certificate_hash=str(value["decision_certificate_hash"]),
            event_class=EventClass(value["event_class"]),
            event_kind=str(value["event_kind"]),
            conflict_key=str(value["conflict_key"]),
            idempotency_key=str(value["idempotency_key"]),
            effect_id=value["effect_id"],
            precondition_hash=str(value["precondition_hash"]),
            postcondition_hash=str(value["postcondition_hash"]),
            payload_hash=str(value["payload_hash"]),
            compensation_kind=value["compensation_kind"],
        )


@dataclass(frozen=True, slots=True)
class EventKey:
    edge_identity: str
    public_key: SigningPublicKey


@dataclass(frozen=True, slots=True)
class EventSigner:
    edge_identity: str
    key_id: bytes
    private_key: SigningPrivateKey

    def issue(self, event: CausalEvent) -> bytes:
        if event.edge_identity != self.edge_identity:
            raise ValueError("event identity does not match signing identity")
        return sign1(event.payload(), key_id=self.key_id, private_key=self.private_key)


@dataclass(frozen=True, slots=True)
class VerifiedEvent:
    event: CausalEvent
    encoded: bytes
    event_hash: str
    key_id: bytes


def verify_event(
    encoded: bytes,
    *,
    keys: Mapping[bytes, EventKey],
    expected_epoch: str,
    valid_lease_hashes: frozenset[str],
    valid_decision_hashes: frozenset[str],
    registered_classes: Mapping[str, EventClass],
    permitted_classes: frozenset[EventClass],
) -> VerifiedEvent:
    parsed = parse_sign1(encoded)
    key = keys.get(parsed.key_id)
    if key is None:
        raise CoseVerificationError("event key is not authorized")
    verified = verify_sign1(encoded, key.public_key)
    event = CausalEvent.from_payload(verified.payload)
    if event.edge_identity != key.edge_identity:
        raise ValueError("event signer is not authorized for the claimed edge")
    if event.isolation_epoch != expected_epoch:
        raise ValueError("event belongs to a different isolation epoch")
    if event.lease_hash not in valid_lease_hashes:
        raise ValueError("event references an unverified authority lease")
    if event.decision_certificate_hash not in valid_decision_hashes:
        raise ValueError("event references an unverified decision certificate")
    registered = registered_classes.get(event.event_kind)
    if registered is None or registered is not event.event_class:
        raise ValueError("event safety class differs from the registered schema class")
    if (
        event.event_class is not EventClass.OBSERVATIONAL
        and event.event_class not in permitted_classes
    ):
        raise ValueError("authority does not permit the event reconciliation class")
    return VerifiedEvent(event, encoded, sha256_hex(encoded), parsed.key_id)


_EVENT_KEYS = {
    "schema_version",
    "event_id",
    "edge_identity",
    "isolation_epoch",
    "sequence",
    "previous_event_hash",
    "causal_parent_hashes",
    "vector_clock",
    "lease_hash",
    "decision_certificate_hash",
    "event_class",
    "event_kind",
    "conflict_key",
    "idempotency_key",
    "effect_id",
    "precondition_hash",
    "postcondition_hash",
    "payload_hash",
    "compensation_kind",
}
