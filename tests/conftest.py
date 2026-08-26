from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from edge_lifeline.formal.authority import (
    ApprovalLevel,
    AuthorityEnvelope,
    Budgets,
    ImpactClass,
    ReconciliationClass,
    SecurityPosture,
    TimeWindow,
)


@pytest.fixture
def envelope_factory() -> Callable[..., AuthorityEnvelope]:
    base = AuthorityEnvelope(
        actions=frozenset({"monitor", "record", "communicate", "actuate"}),
        resources=frozenset({"patient-index", "device-stream", "event-ledger"}),
        sites=frozenset({"edge-a"}),
        time_window=TimeWindow(1_000, 101_000),
        max_lease_horizon_ms=100_000,
        max_data_age_ms=60_000,
        min_sensor_confidence_per_mille=700,
        budgets=Budgets(10_000, 20_000, 30_000, 40_000, 50_000, 100),
        max_impact=ImpactClass.REVERSIBLE_PHYSICAL,
        max_financial_exposure_cents=50_000,
        min_approval=ApprovalLevel.NONE,
        min_security_posture=SecurityPosture.BASIC,
        max_identity_cache_age_ms=86_400_000,
        max_revocation_staleness_ms=3_600_000,
        delegation_depth_remaining=2,
        reconciliation_classes=frozenset(ReconciliationClass),
        schema_version="authority-v1",
        policy_hash="p" * 64,
        mvsg_hash="m" * 64,
        verifier_profile_hash="v" * 64,
        isolation_epoch="epoch-1",
    )

    def factory(**changes: Any) -> AuthorityEnvelope:
        return replace(base, **changes)

    return factory
