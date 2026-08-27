"""Synthetic-only Phase 4 mission graph fixtures."""

from __future__ import annotations

from edge_lifeline.formal.authority import (
    ApprovalLevel,
    AuthorityEnvelope,
    Budgets,
    ImpactClass,
    ReconciliationClass,
    SecurityPosture,
    TimeWindow,
)
from edge_lifeline.mission.model import (
    CapabilityRequirement,
    LatencyConstraint,
    MissionContext,
    MissionGraph,
    RedundancyRequirement,
    ServiceNode,
    SiteCapacity,
)


def _budget(
    energy: int,
    cpu: int,
    memory: int,
    storage: int,
    network: int,
    actions: int = 1,
) -> Budgets:
    return Budgets(energy, cpu, memory, storage, network, actions)


def _node(
    service_id: str,
    service_class: str,
    *,
    capability: str | None = None,
    sites: frozenset[str] = frozenset({"edge-a", "edge-b"}),
    demand: Budgets | None = None,
    action: str = "read",
    resource: str = "platform",
    dependencies: frozenset[str] = frozenset(),
    alternatives: tuple[frozenset[str], ...] = (),
    data_id: str | None = None,
    data_max_age_ms: int = 60_000,
    startup_ms: int = 5,
    latency_ms: int = 5,
    exposure: int = 1,
    utility: int = 0,
    sensor_confidence: int = 0,
) -> ServiceNode:
    return ServiceNode(
        service_id=service_id,
        service_class=service_class,
        capability_units={} if capability is None else {capability: 1},
        allowed_sites=sites,
        demand=demand or Budgets(10, 10, 10, 1024, 1024, 1),
        required_actions=frozenset({action}),
        required_resources=frozenset({resource}),
        required_impact=ImpactClass.READ_ONLY,
        required_approval=ApprovalLevel.NONE,
        required_security_posture=SecurityPosture.HARDENED,
        min_sensor_confidence_per_mille=sensor_confidence,
        data_max_age_ms={} if data_id is None else {data_id: data_max_age_ms},
        and_dependencies=dependencies,
        alternative_groups=alternatives,
        startup_time_ms=startup_ms,
        response_latency_ms=latency_ms,
        authority_exposure_units=exposure,
        optional_utility=utility,
    )


def synthetic_hospital_graph() -> MissionGraph:
    """Declared nonclinical continuity graph with five mandatory capabilities."""

    services = (
        _node(
            "credential-db",
            "identity",
            resource="patient-index",
            data_id="identity-snapshot",
            demand=_budget(20, 20, 20, 4096, 1024),
        ),
        _node(
            "identity-cache",
            "identity",
            capability="identity",
            resource="patient-index",
            dependencies=frozenset({"credential-db"}),
            data_id="identity-snapshot",
            startup_ms=10,
            latency_ms=10,
        ),
        _node(
            "signed-safety-snapshot",
            "safety-data",
            resource="medication-snapshot",
            data_id="safety-snapshot",
            demand=_budget(20, 15, 20, 8192, 1024),
        ),
        _node(
            "medication-allergy-cache",
            "safety-data",
            capability="safety-data",
            resource="medication-snapshot",
            dependencies=frozenset({"identity-cache", "signed-safety-snapshot"}),
            data_id="safety-snapshot",
            startup_ms=10,
            latency_ms=15,
        ),
        _node(
            "sensor-gateway-a",
            "monitoring",
            sites=frozenset({"edge-a"}),
            resource="device-stream",
            data_id="sensor-attestation",
            sensor_confidence=800,
        ),
        _node(
            "sensor-gateway-b",
            "monitoring",
            sites=frozenset({"edge-b"}),
            resource="device-stream",
            data_id="sensor-attestation",
            sensor_confidence=800,
        ),
        _node(
            "essential-monitor-a",
            "monitoring",
            capability="monitoring",
            sites=frozenset({"edge-a"}),
            action="monitor",
            resource="device-stream",
            dependencies=frozenset({"sensor-gateway-a"}),
            sensor_confidence=800,
            startup_ms=10,
            latency_ms=10,
        ),
        _node(
            "essential-monitor-b",
            "monitoring",
            capability="monitoring",
            sites=frozenset({"edge-b"}),
            action="monitor",
            resource="device-stream",
            dependencies=frozenset({"sensor-gateway-b"}),
            sensor_confidence=800,
            startup_ms=10,
            latency_ms=10,
        ),
        _node(
            "local-network",
            "communications",
            resource="local-network",
            demand=_budget(10, 10, 10, 1024, 4096),
            exposure=1,
        ),
        _node(
            "external-route",
            "communications",
            resource="local-network",
            demand=_budget(20, 20, 10, 1024, 8192),
            exposure=50,
        ),
        _node(
            "emergency-communications",
            "communications",
            capability="communications",
            action="communicate",
            resource="local-network",
            dependencies=frozenset({"identity-cache"}),
            alternatives=(frozenset({"local-network", "external-route"}),),
            startup_ms=10,
            latency_ms=15,
            exposure=10,
        ),
        _node(
            "event-ledger",
            "recording",
            resource="event-ledger",
            demand=_budget(10, 15, 10, 16_384, 1024),
        ),
        _node(
            "storage-reserve",
            "recording",
            resource="event-ledger",
            demand=_budget(5, 5, 5, 32_768, 0),
        ),
        _node(
            "clinical-event-recorder",
            "recording",
            capability="recording",
            action="record",
            resource="event-ledger",
            dependencies=frozenset({"event-ledger", "storage-reserve"}),
            startup_ms=10,
            latency_ms=10,
        ),
        _node(
            "audit-dashboard",
            "optional-observability",
            capability="audit-view",
            resource="event-ledger",
            dependencies=frozenset({"clinical-event-recorder"}),
            utility=20,
            exposure=5,
        ),
    )
    return MissionGraph(
        graph_id="synthetic-hospital-continuity",
        graph_version="1.0.0",
        services=services,
        capabilities=(
            CapabilityRequirement("identity", 1, True, 150),
            CapabilityRequirement("safety-data", 1, True, 250),
            CapabilityRequirement("monitoring", 1, True, 200),
            CapabilityRequirement("communications", 1, True, 300),
            CapabilityRequirement("recording", 1, True, 300),
            CapabilityRequirement("audit-view", 1, False, 500, optional_utility=30),
        ),
        exclusions=(("local-network", "external-route"),),
        redundancy=(
            RedundancyRequirement(
                "dual-monitoring-sites",
                frozenset({"essential-monitor-a", "essential-monitor-b"}),
                2,
                distinct_sites=True,
            ),
        ),
        latency_constraints=(
            LatencyConstraint(
                "identity-to-safety-data",
                ("identity-cache", "medication-allergy-cache"),
                40,
            ),
        ),
    )


def context_for(graph: MissionGraph, *, energy_mj: int = 10_000) -> MissionContext:
    graph_hash = graph.graph_hash()
    envelope = AuthorityEnvelope(
        actions=frozenset({"read", "monitor", "record", "communicate"}),
        resources=frozenset(
            {
                "platform",
                "patient-index",
                "medication-snapshot",
                "device-stream",
                "local-network",
                "event-ledger",
            }
        ),
        sites=frozenset({"edge-a", "edge-b"}),
        time_window=TimeWindow(1_000, 61_000),
        max_lease_horizon_ms=60_000,
        max_data_age_ms=60_000,
        min_sensor_confidence_per_mille=700,
        budgets=_budget(energy_mj, 10_000, 10_000, 1_000_000, 1_000_000, 100),
        max_impact=ImpactClass.READ_ONLY,
        max_financial_exposure_cents=0,
        min_approval=ApprovalLevel.NONE,
        min_security_posture=SecurityPosture.HARDENED,
        max_identity_cache_age_ms=3_600_000,
        max_revocation_staleness_ms=600_000,
        delegation_depth_remaining=0,
        reconciliation_classes=frozenset({ReconciliationClass.COMMUTATIVE}),
        schema_version="authority-v1",
        policy_hash="a" * 64,
        mvsg_hash=graph_hash,
        verifier_profile_hash="c" * 64,
        isolation_epoch="epoch-phase4-fixture",
    )
    capacity = _budget(5_000, 5_000, 5_000, 500_000, 500_000, 100)
    return MissionContext(
        authority=envelope,
        site_capacities=(SiteCapacity("edge-a", capacity), SiteCapacity("edge-b", capacity)),
        available_sites=frozenset({"edge-a", "edge-b"}),
        unavailable_services=frozenset(),
        data_age_ms={
            "identity-snapshot": 1_000,
            "safety-snapshot": 1_000,
            "sensor-attestation": 100,
        },
        sensor_confidence_per_mille=950,
        approval_level=ApprovalLevel.THRESHOLD_LOCAL,
        security_posture=SecurityPosture.ATTESTED,
        starvation_ms={
            "identity": 0,
            "safety-data": 0,
            "monitoring": 0,
            "communications": 10_000,
            "recording": 5_000,
            "audit-view": 20_000,
        },
        context_id="phase4-synthetic-normal",
    )


def small_oracle_graph() -> MissionGraph:
    """Small AND/OR graph used for CP-SAT versus brute-force conformance."""

    return MissionGraph(
        graph_id="small-oracle",
        graph_version="1",
        services=(
            _node("base", "core", resource="platform"),
            _node("fast", "alternative", resource="platform", exposure=1),
            _node("slow", "alternative", resource="platform", exposure=20),
            _node(
                "mission",
                "mission",
                capability="mission",
                dependencies=frozenset({"base"}),
                alternatives=(frozenset({"fast", "slow"}),),
                resource="platform",
            ),
        ),
        capabilities=(CapabilityRequirement("mission", 1, True, 100),),
        exclusions=(("fast", "slow"),),
    )
