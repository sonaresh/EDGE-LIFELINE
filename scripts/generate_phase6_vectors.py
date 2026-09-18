"""Generate deterministic Phase 6 event, reconciliation, and recovery vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from edge_lifeline.ledger.dag import DAGImportResult
from edge_lifeline.ledger.model import CausalEvent, EventClass, EventSigner, VerifiedEvent
from edge_lifeline.proof.codec import canonical_dumps, sha256_hex
from edge_lifeline.reconcile.engine import ReconciliationEngine
from edge_lifeline.reconcile.model import LedgerCheckpoint, ReconciliationReceipt
from edge_lifeline.reconcile.receipt import RecoverySigner


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _event(
    edge: str,
    event_class: EventClass,
    event_kind: str,
    conflict_key: str,
    *,
    effect_id: str | None = None,
    compensation_kind: str | None = None,
) -> CausalEvent:
    return CausalEvent(
        event_id=f"fixture-{edge}",
        edge_identity=edge,
        isolation_epoch="epoch-phase6-fixture",
        sequence=0,
        previous_event_hash=None,
        causal_parent_hashes=(),
        vector_clock={edge: 1},
        lease_hash="1" * 64,
        decision_certificate_hash="2" * 64,
        event_class=event_class,
        event_kind=event_kind,
        conflict_key=conflict_key,
        idempotency_key=f"fixture-idempotency-{edge}",
        effect_id=effect_id,
        precondition_hash="3" * 64,
        postcondition_hash="4" * 64,
        payload_hash="5" * 64,
        compensation_kind=compensation_kind,
    )


def _verified(event: CausalEvent, seed: int) -> VerifiedEvent:
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(seed, seed + 32)))
    encoded = EventSigner(
        event.edge_identity, f"{event.edge_identity}-key".encode(), private
    ).issue(event)
    return VerifiedEvent(event, encoded, sha256_hex(encoded), f"{event.edge_identity}-key".encode())


def _vectors() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    existing = _verified(
        _event(
            "edge-a",
            EventClass.COMPENSATABLE,
            "state-change",
            "state:ward-a",
            compensation_kind="append-inverse",
        ),
        1,
    )
    imported = (
        _verified(
            _event(
                "edge-b",
                EventClass.COMPENSATABLE,
                "state-change",
                "state:ward-a",
                compensation_kind="append-inverse",
            ),
            33,
        ),
        _verified(
            _event(
                "edge-c",
                EventClass.IRREVERSIBLE_PHYSICAL,
                "physical-effect",
                "actuator:door-1",
                effect_id="effect-door-1",
            ),
            65,
        ),
        _verified(
            _event(
                "edge-d",
                EventClass.OBSERVATIONAL,
                "observation",
                "telemetry:ward-a",
            ),
            97,
        ),
    )
    frontier = tuple(sorted(item.event_hash for item in imported))
    dag = DAGImportResult(imported, (), {"f" * 64: ("INVALID_SIGNATURE",)}, frontier)
    plan = ReconciliationEngine().plan(
        episode_id="fixture-recovery-1",
        isolation_epoch="epoch-phase6-fixture",
        dag=dag,
        existing={existing.event_hash: existing},
    )
    history = tuple(sorted((existing.event_hash, *frontier)))
    checkpoint = LedgerCheckpoint(
        checkpoint_id="fixture-checkpoint-1",
        witness_identity="fixture-reconciler",
        issued_at_ms=20_000,
        isolation_epoch="epoch-phase6-fixture",
        frontier=frontier,
        accepted_history_root=sha256_hex(canonical_dumps(list(history))),
        prior_checkpoint_hash=None,
    )
    recovery_key = Ed25519PrivateKey.from_private_bytes(bytes(range(129, 161)))
    signer = RecoverySigner("fixture-reconciler", b"fixture-reconciler-key", recovery_key)
    checkpoint_encoded = signer.issue(checkpoint)
    receipt = ReconciliationReceipt(
        receipt_id="fixture-receipt-1",
        reconciler_identity="fixture-reconciler",
        issued_at_ms=20_001,
        plan_digest=plan.digest,
        checkpoint_hash=sha256_hex(checkpoint_encoded),
        accepted_event_hashes=history,
        quarantined_event_hashes=("f" * 64,),
    )
    receipt_encoded = signer.issue(receipt)
    event_archive = {
        "schema_version": "edge-lifeline-phase6-event-archive-v1",
        "synthetic_nonclinical": True,
        "events": [
            {
                "event_hash": item.event_hash,
                "encoded_cose_sign1_hex": item.encoded.hex(),
                "event": item.event.to_obj(),
            }
            for item in (existing, *imported)
        ],
    }
    recovery = {
        "schema_version": "edge-lifeline-phase6-recovery-vector-v1",
        "plan": plan.to_obj(),
        "plan_digest": plan.digest,
        "checkpoint": checkpoint.to_obj(),
        "checkpoint_cose_sign1_hex": checkpoint_encoded.hex(),
        "checkpoint_hash": sha256_hex(checkpoint_encoded),
        "receipt": receipt.to_obj(),
        "receipt_cose_sign1_hex": receipt_encoded.hex(),
        "receipt_hash": sha256_hex(receipt_encoded),
    }
    negative = {
        "schema_version": "edge-lifeline-phase6-negative-cases-v1",
        "cases": {
            "missing_parent": "QUARANTINE:CAUSAL_PARENT_MISSING",
            "fork": "QUARANTINE:EDGE_HISTORY_FORK",
            "invalid_signature": "QUARANTINE:INVALID_EVENT",
            "false_class": "QUARANTINE:REGISTERED_CLASS_MISMATCH",
            "effect_replay": "DEDUPLICATE_EFFECT_NO_REPLAY",
            "reconnect": "RECONCILIATION_PENDING_AND_FRESH_LEASE_REQUIRED",
        },
        "authority_restored": False,
        "effect_replay_count": 0,
    }
    return event_archive, recovery, negative


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    event_archive, recovery, negative = _vectors()
    _write(args.output_directory / "event-archive-v1.json", event_archive)
    _write(args.output_directory / "recovery-vector-v1.json", recovery)
    _write(args.output_directory / "negative-cases-v1.json", negative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
