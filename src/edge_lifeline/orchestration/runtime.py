"""Conservative mode selection from observed orchestration state."""

from __future__ import annotations

from edge_lifeline.orchestration.model import (
    ClusterObservation,
    Connectivity,
    LeaseState,
    RuntimeDecision,
    RuntimeMode,
)


def decide_runtime_mode(observation: ClusterObservation) -> RuntimeDecision:
    if not observation.proof_verifier_ready or not observation.policy_ready:
        return RuntimeDecision(
            cluster_id=observation.cluster_id,
            mode=RuntimeMode.QUARANTINED,
            effect_dispatch_allowed=False,
            reason="policy or proof verifier unavailable",
        )
    if observation.lease_state is not LeaseState.VALID:
        return RuntimeDecision(
            cluster_id=observation.cluster_id,
            mode=RuntimeMode.PROTECTIVE,
            effect_dispatch_allowed=False,
            reason="valid authority lease unavailable",
        )
    if observation.connectivity is Connectivity.UNKNOWN:
        return RuntimeDecision(
            cluster_id=observation.cluster_id,
            mode=RuntimeMode.PROTECTIVE,
            effect_dispatch_allowed=False,
            reason="connectivity state unknown",
        )
    if observation.connectivity is Connectivity.ISOLATED:
        return RuntimeDecision(
            cluster_id=observation.cluster_id,
            mode=RuntimeMode.DEGRADED,
            effect_dispatch_allowed=observation.workload_ready,
            reason="bounded degraded operation under existing lease",
        )
    if observation.recovery_complete and not observation.fresh_connected_epoch_lease:
        return RuntimeDecision(
            cluster_id=observation.cluster_id,
            mode=RuntimeMode.PROTECTIVE,
            effect_dispatch_allowed=False,
            reason="reconciliation cannot restore authority without a fresh lease",
        )
    if not observation.workload_ready:
        return RuntimeDecision(
            cluster_id=observation.cluster_id,
            mode=RuntimeMode.PROTECTIVE,
            effect_dispatch_allowed=False,
            reason="mission workload unavailable",
        )
    return RuntimeDecision(
        cluster_id=observation.cluster_id,
        mode=RuntimeMode.CONNECTED,
        effect_dispatch_allowed=True,
        reason="connected runtime with verified dependencies and valid lease",
    )
