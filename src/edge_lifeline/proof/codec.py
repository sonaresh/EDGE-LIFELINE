"""Strict deterministic CBOR and authority-envelope codecs."""

from __future__ import annotations

import hashlib
from typing import Any

import cbor2

from edge_lifeline.formal.authority import (
    ApprovalLevel,
    AuthorityEnvelope,
    Budgets,
    ImpactClass,
    ReconciliationClass,
    SecurityPosture,
    TimeWindow,
)


class CanonicalCborError(ValueError):
    """Raised when bytes are malformed or not the unique canonical encoding."""


def canonical_dumps(value: Any) -> bytes:
    return cbor2.dumps(value, canonical=True)


def strict_loads(data: bytes) -> Any:
    try:
        value = cbor2.loads(data)
    except (cbor2.CBORDecodeError, UnicodeDecodeError, ValueError) as error:
        raise CanonicalCborError("malformed CBOR") from error
    try:
        canonical = canonical_dumps(value)
    except (cbor2.CBOREncodeError, TypeError, ValueError) as error:
        raise CanonicalCborError("malformed CBOR") from error
    if canonical != data:
        raise CanonicalCborError("CBOR is not canonical or contains trailing bytes")
    return value


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def envelope_to_obj(envelope: AuthorityEnvelope) -> dict[str, Any]:
    return {
        "actions": sorted(envelope.actions),
        "resources": sorted(envelope.resources),
        "sites": sorted(envelope.sites),
        "time_window": {
            "not_before_ms": envelope.time_window.not_before_ms,
            "expires_at_ms": envelope.time_window.expires_at_ms,
        },
        "max_lease_horizon_ms": envelope.max_lease_horizon_ms,
        "max_data_age_ms": envelope.max_data_age_ms,
        "min_sensor_confidence_per_mille": envelope.min_sensor_confidence_per_mille,
        "budgets": {
            "energy_mj": envelope.budgets.energy_mj,
            "cpu_ms": envelope.budgets.cpu_ms,
            "memory_mb_s": envelope.budgets.memory_mb_s,
            "storage_bytes": envelope.budgets.storage_bytes,
            "network_bytes": envelope.budgets.network_bytes,
            "action_count": envelope.budgets.action_count,
        },
        "max_impact": int(envelope.max_impact),
        "max_financial_exposure_cents": envelope.max_financial_exposure_cents,
        "min_approval": int(envelope.min_approval),
        "min_security_posture": int(envelope.min_security_posture),
        "max_identity_cache_age_ms": envelope.max_identity_cache_age_ms,
        "max_revocation_staleness_ms": envelope.max_revocation_staleness_ms,
        "delegation_depth_remaining": envelope.delegation_depth_remaining,
        "reconciliation_classes": sorted(envelope.reconciliation_classes),
        "schema_version": envelope.schema_version,
        "policy_hash": envelope.policy_hash,
        "mvsg_hash": envelope.mvsg_hash,
        "verifier_profile_hash": envelope.verifier_profile_hash,
        "isolation_epoch": envelope.isolation_epoch,
        "artifact_family": envelope.artifact_family,
    }


def envelope_from_obj(value: object) -> AuthorityEnvelope:
    if not isinstance(value, dict):
        raise ValueError("authority envelope must be a map")
    try:
        window = value["time_window"]
        budgets = value["budgets"]
        if not isinstance(window, dict) or not isinstance(budgets, dict):
            raise TypeError
        return AuthorityEnvelope(
            actions=frozenset(_strings(value["actions"])),
            resources=frozenset(_strings(value["resources"])),
            sites=frozenset(_strings(value["sites"])),
            time_window=TimeWindow(int(window["not_before_ms"]), int(window["expires_at_ms"])),
            max_lease_horizon_ms=int(value["max_lease_horizon_ms"]),
            max_data_age_ms=int(value["max_data_age_ms"]),
            min_sensor_confidence_per_mille=int(value["min_sensor_confidence_per_mille"]),
            budgets=Budgets(
                energy_mj=int(budgets["energy_mj"]),
                cpu_ms=int(budgets["cpu_ms"]),
                memory_mb_s=int(budgets["memory_mb_s"]),
                storage_bytes=int(budgets["storage_bytes"]),
                network_bytes=int(budgets["network_bytes"]),
                action_count=int(budgets["action_count"]),
            ),
            max_impact=ImpactClass(int(value["max_impact"])),
            max_financial_exposure_cents=int(value["max_financial_exposure_cents"]),
            min_approval=ApprovalLevel(int(value["min_approval"])),
            min_security_posture=SecurityPosture(int(value["min_security_posture"])),
            max_identity_cache_age_ms=int(value["max_identity_cache_age_ms"]),
            max_revocation_staleness_ms=int(value["max_revocation_staleness_ms"]),
            delegation_depth_remaining=int(value["delegation_depth_remaining"]),
            reconciliation_classes=frozenset(
                ReconciliationClass(item) for item in _strings(value["reconciliation_classes"])
            ),
            schema_version=str(value["schema_version"]),
            policy_hash=str(value["policy_hash"]),
            mvsg_hash=str(value["mvsg_hash"]),
            verifier_profile_hash=str(value["verifier_profile_hash"]),
            isolation_epoch=str(value["isolation_epoch"]),
            artifact_family=str(value["artifact_family"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid authority envelope") from error


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError("expected string array")
    if len(value) != len(set(value)):
        raise ValueError("duplicate set member")
    return tuple(value)
