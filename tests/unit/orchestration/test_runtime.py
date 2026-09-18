from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from edge_lifeline.orchestration import (
    ClusterObservation,
    ClusterRole,
    Connectivity,
    LeaseState,
    RuntimeMode,
    Topology,
    ValidationError,
    decide_runtime_mode,
    validate_topology,
)


def observation(**changes: object) -> ClusterObservation:
    values: dict[str, object] = {
        "cluster_id": "edge-a",
        "role": ClusterRole.EDGE,
        "connectivity": Connectivity.CONNECTED,
        "lease_state": LeaseState.VALID,
        "workload_ready": True,
        "policy_ready": True,
        "proof_verifier_ready": True,
    }
    values.update(changes)
    return ClusterObservation.model_validate(values)


def test_connected_runtime_can_dispatch_only_with_all_dependencies() -> None:
    decision = decide_runtime_mode(observation())
    assert decision.mode is RuntimeMode.CONNECTED
    assert decision.effect_dispatch_allowed
    assert not decision.authority_restored


@pytest.mark.parametrize("lease", [LeaseState.EXPIRED, LeaseState.MISSING])
def test_invalid_or_missing_lease_enters_protective_mode(lease: LeaseState) -> None:
    decision = decide_runtime_mode(observation(lease_state=lease))
    assert decision.mode is RuntimeMode.PROTECTIVE
    assert not decision.effect_dispatch_allowed


def test_isolation_preserves_only_existing_bounded_authority() -> None:
    decision = decide_runtime_mode(observation(connectivity=Connectivity.ISOLATED))
    assert decision.mode is RuntimeMode.DEGRADED
    assert decision.effect_dispatch_allowed
    assert not decision.authority_restored


def test_unknown_connectivity_fails_safe() -> None:
    decision = decide_runtime_mode(observation(connectivity=Connectivity.UNKNOWN))
    assert decision.mode is RuntimeMode.PROTECTIVE
    assert not decision.effect_dispatch_allowed


@pytest.mark.parametrize("dependency", ["policy_ready", "proof_verifier_ready"])
def test_missing_trust_dependency_quarantines(dependency: str) -> None:
    decision = decide_runtime_mode(observation(**{dependency: False}))
    assert decision.mode is RuntimeMode.QUARANTINED
    assert not decision.effect_dispatch_allowed


def test_recovery_does_not_restore_authority() -> None:
    decision = decide_runtime_mode(
        observation(recovery_complete=True, fresh_connected_epoch_lease=False)
    )
    assert decision.mode is RuntimeMode.PROTECTIVE
    assert not decision.authority_restored
    assert not decision.effect_dispatch_allowed


def test_fresh_connected_epoch_lease_allows_connected_mode() -> None:
    decision = decide_runtime_mode(
        observation(recovery_complete=True, fresh_connected_epoch_lease=True)
    )
    assert decision.mode is RuntimeMode.CONNECTED


def test_cluster_identity_and_role_are_bound() -> None:
    with pytest.raises(PydanticValidationError):
        observation(cluster_id="cloud", role=ClusterRole.EDGE)


def test_topology_requires_exact_registered_clusters() -> None:
    clusters = tuple(
        observation(
            cluster_id=cluster_id,
            role=ClusterRole.CLOUD if cluster_id == "cloud" else ClusterRole.EDGE,
        )
        for cluster_id in ("cloud", "edge-a", "edge-b", "edge-c")
    )
    validate_topology(Topology(schema_version="edge-lifeline-topology-v1", clusters=clusters))


def test_topology_rejects_duplicate_or_missing_clusters() -> None:
    topology = Topology(
        schema_version="edge-lifeline-topology-v1",
        clusters=(observation(), observation()),
    )
    with pytest.raises(ValidationError, match="duplicate"):
        validate_topology(topology)
