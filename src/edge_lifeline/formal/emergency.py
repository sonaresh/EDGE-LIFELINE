"""Separate, preauthorized emergency authority branch."""

from __future__ import annotations

from dataclasses import dataclass

from edge_lifeline.formal.authority import AuthorityEnvelope


@dataclass(frozen=True, slots=True)
class EmergencyCapability:
    capability_id: str
    purpose: str
    active: AuthorityEnvelope
    ceiling: AuthorityEnvelope
    emergency_root: AuthorityEnvelope
    approvals_obtained: int
    approvals_required: int
    one_shot: bool
    consumed: bool
    delegable: bool

    def validate(self, requested: AuthorityEnvelope) -> tuple[bool, tuple[str, ...]]:
        failures: list[str] = []
        if not self.capability_id or not self.purpose:
            failures.append("PURPOSE_BINDING_MISSING")
        if self.approvals_obtained < self.approvals_required:
            failures.append("APPROVAL_THRESHOLD_NOT_MET")
        if not self.one_shot or self.consumed:
            failures.append("ONE_SHOT_UNAVAILABLE")
        if self.delegable or self.active.delegation_depth_remaining != 0:
            failures.append("EMERGENCY_DELEGATION_FORBIDDEN")
        if not self.active.is_no_more_authoritative_than(self.ceiling):
            failures.append("ACTIVE_OVERRIDE_EXCEEDS_CEILING")
        if not self.ceiling.is_no_more_authoritative_than(self.emergency_root):
            failures.append("CEILING_EXCEEDS_EMERGENCY_ROOT")
        if not requested.is_no_more_authoritative_than(self.active):
            failures.append("REQUEST_EXCEEDS_ACTIVE_OVERRIDE")
        return not failures, tuple(failures)
