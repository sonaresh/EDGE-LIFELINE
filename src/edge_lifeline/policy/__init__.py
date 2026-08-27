"""Canonical OPA/Rego policy binding and fail-safe local client."""

from edge_lifeline.policy.bundle import PolicyBundle
from edge_lifeline.policy.client import OpaPolicyClient, PolicyDecision

__all__ = ["OpaPolicyClient", "PolicyBundle", "PolicyDecision"]
