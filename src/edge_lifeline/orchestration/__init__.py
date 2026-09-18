"""Fail-safe Phase 7 orchestration model."""

from edge_lifeline.orchestration.model import (
    ClusterObservation,
    ClusterRole,
    Connectivity,
    LeaseState,
    RuntimeMode,
    Topology,
)
from edge_lifeline.orchestration.runtime import decide_runtime_mode
from edge_lifeline.orchestration.validator import ValidationError, validate_topology

__all__ = [
    "ClusterObservation",
    "ClusterRole",
    "Connectivity",
    "LeaseState",
    "RuntimeMode",
    "Topology",
    "ValidationError",
    "decide_runtime_mode",
    "validate_topology",
]
