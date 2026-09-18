"""Independent validation for the fixed one-cloud/three-edge topology."""

from __future__ import annotations

from edge_lifeline.orchestration.model import ClusterRole, Topology


class ValidationError(ValueError):
    """Raised when orchestration evidence violates the frozen topology."""


EXPECTED_IDS = ("cloud", "edge-a", "edge-b", "edge-c")


def validate_topology(topology: Topology) -> None:
    ids = tuple(cluster.cluster_id for cluster in topology.clusters)
    if len(ids) != len(set(ids)):
        raise ValidationError("duplicate cluster identity")
    if tuple(sorted(ids)) != EXPECTED_IDS:
        raise ValidationError("topology must contain exactly cloud, edge-a, edge-b, and edge-c")
    clouds = [cluster for cluster in topology.clusters if cluster.role is ClusterRole.CLOUD]
    if len(clouds) != 1 or clouds[0].cluster_id != "cloud":
        raise ValidationError("topology must contain exactly one registered cloud cluster")
