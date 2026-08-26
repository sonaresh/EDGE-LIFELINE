"""Frozen Phase 2 synthetic hospital-continuity model profile."""

from __future__ import annotations

import hashlib

from edge_lifeline.formal.authority import (
    ApprovalLevel,
    AuthorityEnvelope,
    Budgets,
    ImpactClass,
    ReconciliationClass,
    SecurityPosture,
    TimeWindow,
)
from edge_lifeline.formal.dae import (
    ActionRule,
    ContractionPolicy,
    HazardDimension,
)


def _profile_hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def synthetic_hospital_envelope() -> AuthorityEnvelope:
    """Return a synthetic research profile; it is not clinical authorization."""

    return AuthorityEnvelope(
        actions=frozenset(
            {
                "patient_identity_read",
                "medication_safety_read",
                "device_monitor",
                "emergency_communication",
                "clinical_event_record",
                "device_actuate",
            }
        ),
        resources=frozenset(
            {
                "synthetic_patient_index",
                "synthetic_allergy_cache",
                "synthetic_device_stream",
                "synthetic_event_ledger",
            }
        ),
        sites=frozenset({"edge-a"}),
        time_window=TimeWindow(1_000, 86_401_000),
        max_lease_horizon_ms=86_400_000,
        max_data_age_ms=3_600_000,
        min_sensor_confidence_per_mille=800,
        budgets=Budgets(
            250_000,
            3_600_000,
            7_200_000,
            10_000_000_000,
            2_000_000_000,
            50_000,
        ),
        max_impact=ImpactClass.REVERSIBLE_PHYSICAL,
        max_financial_exposure_cents=100_000,
        min_approval=ApprovalLevel.NONE,
        min_security_posture=SecurityPosture.HARDENED,
        max_identity_cache_age_ms=86_400_000,
        max_revocation_staleness_ms=3_600_000,
        delegation_depth_remaining=2,
        reconciliation_classes=frozenset(ReconciliationClass),
        schema_version="authority-v1",
        policy_hash=_profile_hash("edge-lifeline-phase2-policy-v1"),
        mvsg_hash=_profile_hash("edge-lifeline-phase2-synthetic-mvsg-placeholder-v1"),
        verifier_profile_hash=_profile_hash("edge-lifeline-phase2-verifier-model-v1"),
        isolation_epoch="synthetic-epoch-1",
    )


def synthetic_hospital_policy() -> ContractionPolicy:
    zero = {dimension: 0 for dimension in HazardDimension}

    def rule(threshold: int, **weights: int) -> ActionRule:
        return ActionRule(
            {**zero, **{HazardDimension(name): value for name, value in weights.items()}},
            threshold,
        )

    return ContractionPolicy(
        action_rules={
            "patient_identity_read": rule(900, identity=800, revocation=600, security=900),
            "medication_safety_read": rule(850, data=900, security=900),
            "device_monitor": rule(900, sensor=700, energy=500, resource=600),
            "emergency_communication": rule(850, energy=600, resource=600, security=700),
            "clinical_event_record": rule(850, energy=500, resource=800, security=900),
            "device_actuate": rule(
                400,
                sensor=1000,
                physical=1000,
                security=1000,
                clock=800,
                data=900,
                human=600,
            ),
        },
        guarded_at=250,
        essential_at=500,
        protective_at=750,
        terminal_at=950,
        budget_floor_per_mille=100,
        essential_actions=frozenset(
            {
                "patient_identity_read",
                "medication_safety_read",
                "device_monitor",
                "emergency_communication",
                "clinical_event_record",
            }
        ),
        read_only_actions=frozenset(
            {
                "patient_identity_read",
                "medication_safety_read",
                "device_monitor",
            }
        ),
    )
