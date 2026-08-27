from __future__ import annotations

from dataclasses import replace

import pytest

from edge_lifeline.mission.fixtures import small_oracle_graph, synthetic_hospital_graph
from edge_lifeline.mission.model import (
    CapabilityRequirement,
    LatencyConstraint,
    MissionGraph,
    RedundancyRequirement,
)


def test_graph_hash_is_deterministic_and_content_bound() -> None:
    first = synthetic_hospital_graph()
    second = synthetic_hospital_graph()
    assert first.graph_hash() == second.graph_hash()
    changed = replace(first, graph_version="1.0.1")
    assert changed.graph_hash() != first.graph_hash()


def test_graph_rejects_unknown_dependency() -> None:
    graph = small_oracle_graph()
    service = replace(graph.services[0], and_dependencies=frozenset({"unknown"}))
    with pytest.raises(ValueError, match="unknown dependency"):
        replace(graph, services=(service, *graph.services[1:]))


def test_graph_rejects_dependency_cycle() -> None:
    graph = small_oracle_graph()
    base = replace(graph.services[0], and_dependencies=frozenset({"mission"}))
    with pytest.raises(ValueError, match="acyclic"):
        replace(graph, services=(base, *graph.services[1:]))


def test_capability_schema_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        CapabilityRequirement("", 1, True, 10)
    with pytest.raises(ValueError):
        CapabilityRequirement("x", 0, True, 10)
    with pytest.raises(ValueError):
        CapabilityRequirement("x", 1, True, 10, optional_utility=1)


def test_graph_rejects_duplicate_service_ids() -> None:
    graph = small_oracle_graph()
    with pytest.raises(ValueError, match="unique"):
        MissionGraph(
            graph_id="duplicate",
            graph_version="1",
            services=(graph.services[0], graph.services[0]),
            capabilities=graph.capabilities,
        )


def test_graph_rejects_duplicate_constraint_identifiers() -> None:
    graph = small_oracle_graph()
    redundancy = RedundancyRequirement("copies", frozenset({"fast", "slow"}), 1)
    with pytest.raises(ValueError, match="redundancy requirement IDs must be unique"):
        replace(graph, redundancy=(redundancy, redundancy))
    latency = LatencyConstraint("path", ("base", "mission"), 100)
    with pytest.raises(ValueError, match="latency constraint IDs must be unique"):
        replace(graph, latency_constraints=(latency, latency))


def test_graph_rejects_duplicate_normalized_exclusions() -> None:
    graph = small_oracle_graph()
    with pytest.raises(ValueError, match="exclusions must be unique"):
        replace(graph, exclusions=(("fast", "slow"), ("slow", "fast")))
