from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from edge_lifeline.formal.authority import AuthorityEnvelope
from edge_lifeline.formal.emergency import EmergencyCapability


def _capability(
    envelope_factory: Callable[..., AuthorityEnvelope],
    **changes: object,
) -> EmergencyCapability:
    root = envelope_factory(delegation_depth_remaining=0)
    ceiling = replace(root, actions=frozenset({"monitor", "actuate"}))
    active = replace(ceiling, actions=frozenset({"actuate"}))
    values: dict[str, object] = {
        "capability_id": "override-1",
        "purpose": "synthetic-emergency-continuity",
        "active": active,
        "ceiling": ceiling,
        "emergency_root": root,
        "approvals_obtained": 2,
        "approvals_required": 2,
        "one_shot": True,
        "consumed": False,
        "delegable": False,
    }
    values.update(changes)
    return EmergencyCapability(**values)  # type: ignore[arg-type]


def test_bounded_emergency_branch_accepts_only_scoped_request(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    capability = _capability(envelope_factory)
    valid, failures = capability.validate(capability.active)
    assert valid
    assert not failures


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"approvals_obtained": 1}, "APPROVAL_THRESHOLD_NOT_MET"),
        ({"consumed": True}, "ONE_SHOT_UNAVAILABLE"),
        ({"delegable": True}, "EMERGENCY_DELEGATION_FORBIDDEN"),
        ({"purpose": ""}, "PURPOSE_BINDING_MISSING"),
    ],
)
def test_invalid_emergency_conditions_deny(
    envelope_factory: Callable[..., AuthorityEnvelope],
    changes: dict[str, object],
    expected: str,
) -> None:
    capability = _capability(envelope_factory, **changes)
    valid, failures = capability.validate(capability.active)
    assert not valid
    assert expected in failures


def test_emergency_request_cannot_exceed_active_branch(
    envelope_factory: Callable[..., AuthorityEnvelope],
) -> None:
    capability = _capability(envelope_factory)
    widened = replace(capability.active, actions=frozenset({"monitor", "actuate"}))
    valid, failures = capability.validate(widened)
    assert not valid
    assert "REQUEST_EXCEEDS_ACTIVE_OVERRIDE" in failures
