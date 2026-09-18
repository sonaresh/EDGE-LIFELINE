from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from edge_lifeline.ledger.model import CausalEvent, EventClass, EventKey, EventSigner
from edge_lifeline.proof.codec import sha256_hex

LEASE_HASH = "1" * 64
DECISION_HASH = "2" * 64
PRE_HASH = "3" * 64
POST_HASH = "4" * 64
PAYLOAD_HASH = "5" * 64
EPOCH = "epoch-phase6"

EDGE_A_PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
EDGE_B_PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65)))
EDGE_A_SIGNER = EventSigner("edge-a", b"edge-a-key", EDGE_A_PRIVATE)
EDGE_B_SIGNER = EventSigner("edge-b", b"edge-b-key", EDGE_B_PRIVATE)
KEYS: Mapping[bytes, EventKey] = {
    b"edge-a-key": EventKey("edge-a", EDGE_A_PRIVATE.public_key()),
    b"edge-b-key": EventKey("edge-b", EDGE_B_PRIVATE.public_key()),
}
REGISTERED: Mapping[str, EventClass] = {
    "observation": EventClass.OBSERVATIONAL,
    "counter": EventClass.COMMUTATIVE,
    "state-change": EventClass.COMPENSATABLE,
    "authoritative-record": EventClass.REVIEW_REQUIRED,
    "physical-effect": EventClass.IRREVERSIBLE_PHYSICAL,
}
PERMITTED = frozenset(
    {
        EventClass.COMMUTATIVE,
        EventClass.COMPENSATABLE,
        EventClass.REVIEW_REQUIRED,
        EventClass.IRREVERSIBLE_PHYSICAL,
    }
)


def make_event(
    *,
    edge: str = "edge-a",
    sequence: int = 0,
    previous: str | None = None,
    parents: tuple[str, ...] | None = None,
    vector_clock: Mapping[str, int] | None = None,
    event_class: EventClass = EventClass.OBSERVATIONAL,
    event_kind: str = "observation",
    conflict_key: str = "resource:1",
    event_id: str | None = None,
    idempotency_key: str | None = None,
    effect_id: str | None = None,
    compensation_kind: str | None = None,
    epoch: str = EPOCH,
) -> CausalEvent:
    if parents is None:
        parents = () if previous is None else (previous,)
    if vector_clock is None:
        vector_clock = {edge: sequence + 1}
    if event_class is EventClass.IRREVERSIBLE_PHYSICAL and effect_id is None:
        effect_id = f"effect-{edge}-{sequence}"
    if event_class is EventClass.COMPENSATABLE and compensation_kind is None:
        compensation_kind = "append-inverse"
    return CausalEvent(
        event_id=event_id or f"event-{edge}-{sequence}",
        edge_identity=edge,
        isolation_epoch=epoch,
        sequence=sequence,
        previous_event_hash=previous,
        causal_parent_hashes=parents,
        vector_clock=vector_clock,
        lease_hash=LEASE_HASH,
        decision_certificate_hash=DECISION_HASH,
        event_class=event_class,
        event_kind=event_kind,
        conflict_key=conflict_key,
        idempotency_key=idempotency_key or f"idempotency-{edge}-{sequence}",
        effect_id=effect_id,
        precondition_hash=PRE_HASH,
        postcondition_hash=POST_HASH,
        payload_hash=PAYLOAD_HASH,
        compensation_kind=compensation_kind,
    )


def sign_event(event: CausalEvent) -> bytes:
    signer = EDGE_A_SIGNER if event.edge_identity == "edge-a" else EDGE_B_SIGNER
    return signer.issue(event)


def child(parent_encoded: bytes, *, edge: str = "edge-a", **changes: Any) -> CausalEvent:
    parent_hash = sha256_hex(parent_encoded)
    base = make_event(
        edge=edge,
        sequence=1,
        previous=parent_hash,
        vector_clock={edge: 2},
        event_id=f"event-{edge}-1",
    )
    return replace(base, **changes)
