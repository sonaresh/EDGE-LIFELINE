"""Independent declarative oracle for synthetic Phase 8 events."""

from __future__ import annotations

import hashlib
import json

from edge_lifeline.experiments.model import SyntheticEvent


def permitted(event: SyntheticEvent) -> bool:
    """Return the independently specified safe-and-authorized action set."""
    return (
        event.authorized
        and event.intrinsically_safe
        and not event.replayed
        and not event.child_expansion
        and (not event.consequential or event.proof_valid)
    )


def canonical_oracle() -> bytes:
    payload = {
        "schema_version": "edge-lifeline-phase8-oracle-v1",
        "independent_from_runtime": True,
        "synthetic_nonclinical": True,
        "permitted_if": [
            "authorized",
            "intrinsically_safe",
            "not_replayed",
            "not_child_expansion",
            "proof_valid_if_consequential",
        ],
        "mission_predicate": "critical_availability>=0.70 and unsafe_actions_executed==0",
        "recovery": {
            "conflict": "class-specific resolution",
            "malicious_or_invalid": "quarantine",
            "physical_effect": "never replay",
        },
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def oracle_sha256() -> str:
    return hashlib.sha256(canonical_oracle()).hexdigest()
