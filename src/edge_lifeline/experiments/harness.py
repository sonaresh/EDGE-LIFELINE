"""Deterministic paired-factorial Phase 8 simulator."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterable

from edge_lifeline.experiments.catalog import METHODS, SCENARIOS
from edge_lifeline.experiments.model import (
    Decision,
    Method,
    RunResult,
    ScenarioSpec,
    SyntheticEvent,
)
from edge_lifeline.experiments.oracle import oracle_sha256, permitted

EVENTS_PER_RUN = 64


def _seed_for(scenario_id: str, seed: int) -> int:
    material = f"edge-lifeline-phase8:{scenario_id}:{seed}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def generate_trace(scenario: ScenarioSpec, seed: int) -> tuple[SyntheticEvent, ...]:
    rng = random.Random(_seed_for(scenario.scenario_id, seed))  # noqa: S311
    axes = frozenset(scenario.axes)
    severity = scenario.severity_per_mille / 1000
    events: list[SyntheticEvent] = []
    for index in range(EVENTS_PER_RUN):
        critical = rng.random() < 0.45
        consequential = rng.random() < 0.42
        authorized = rng.random() >= 0.10
        intrinsically_safe = rng.random() >= (0.08 + (0.22 * ("security" in axes)))
        policy_signal = intrinsically_safe and authorized
        if "policy" in axes and rng.random() < severity:
            policy_signal = rng.random() < 0.62
        if "sensor" in axes and rng.random() < severity:
            policy_signal = not policy_signal
        replayed = "replay" in axes and rng.random() < severity
        expansion = ("expansion" in axes or "admin" in axes) and rng.random() < severity
        proof_valid = not ("proof" in axes and rng.random() < severity)
        time_valid = not ("time" in axes and rng.random() < severity)
        identity_fresh = not ("identity" in axes and rng.random() < severity)
        lease_valid = not ("staleness" in axes and rng.random() < severity)
        bounded_identity_valid = not ("identity" in axes and rng.random() < severity * 0.18)
        bounded_time_valid = not ("time" in axes and rng.random() < severity * 0.18)
        contracted_policy_valid = not ("policy" in axes and rng.random() < severity * 0.18)
        conflict = "conflict" in axes and rng.random() < severity
        confidence = rng.randint(820, 1000)
        if "sensor" in axes:
            confidence = rng.randint(150, 780)
        energy_cost = rng.randint(2, 12) + (0 if critical else 2)
        compute_cost = rng.randint(2, 10)
        utility = rng.randint(7, 15) if critical else rng.randint(1, 6)
        ground_truth_permits = (
            authorized
            and intrinsically_safe
            and not replayed
            and not expansion
            and (not consequential or proof_valid)
        )
        evidence_supports_action = ground_truth_permits and rng.random() >= 0.025
        if scenario.detection_only and not ground_truth_permits:
            # E9 includes a declared full-TCB-compromise profile. Prevention is not
            # claimed there; post-reconnect detection and containment are measured.
            evidence_supports_action = rng.random() < 0.30
        events.append(
            SyntheticEvent(
                event_id=f"{scenario.scenario_id}-{seed}-{index:03d}",
                critical=critical,
                consequential=consequential,
                authorized=authorized,
                intrinsically_safe=intrinsically_safe,
                policy_signal_permits=policy_signal,
                identity_fresh=identity_fresh,
                time_valid=time_valid,
                proof_valid=proof_valid,
                lease_valid=lease_valid,
                bounded_identity_valid=bounded_identity_valid,
                bounded_time_valid=bounded_time_valid,
                contracted_policy_valid=contracted_policy_valid,
                evidence_supports_action=evidence_supports_action,
                replayed=replayed,
                child_expansion=expansion,
                conflict=conflict,
                physical_effect=consequential and rng.random() < 0.35,
                confidence_per_mille=confidence,
                energy_cost=energy_cost,
                compute_cost=compute_cost,
                utility=utility,
            )
        )
    return tuple(events)


def trace_bytes(events: Iterable[SyntheticEvent]) -> bytes:
    payload = [item.model_dump(mode="json") for item in events]
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _cloud_available(scenario: ScenarioSpec) -> bool:
    return not bool({"network", "cloud"}.intersection(scenario.axes))


def decide(method: Method, scenario: ScenarioSpec, event: SyntheticEvent) -> Decision:
    cloud = _cloud_available(scenario)
    if method is Method.B0_FAIL_CLOSED:
        allow = cloud and event.policy_signal_permits and event.authorized
        return Decision(allow=allow, reason="cloud-dependent admission")
    if method is Method.B1_UNRESTRICTED:
        return Decision(allow=True, replayed_effect=event.replayed, reason="retained authority")
    if method is Method.B2_STATIC_POLICY:
        return Decision(allow=event.policy_signal_permits, reason="fixed offline rules")
    if method is Method.B3_FIXED_LEASE:
        allow = event.lease_valid and event.policy_signal_permits
        return Decision(allow=allow, reason="fixed-duration lease")
    if method is Method.B4_REPLICATION_ONLY:
        allow = event.policy_signal_permits and (cloud or event.critical)
        return Decision(
            allow=allow, replayed_effect=allow and event.replayed, reason="replicated state"
        )
    if method is Method.B5_LAST_WRITER_WINS:
        allow = event.policy_signal_permits or event.conflict
        return Decision(
            allow=allow, replayed_effect=allow and event.replayed, reason="timestamp winner"
        )
    if method is Method.B6_STATIC_PRIORITY:
        allow = event.critical and event.policy_signal_permits
        return Decision(allow=allow, reason="static critical priority")

    evidence_valid = (
        event.evidence_supports_action
        and event.bounded_identity_valid
        and event.bounded_time_valid
        and event.proof_valid
        and event.contracted_policy_valid
        and event.lease_valid
        and not event.replayed
        and not event.child_expansion
        and event.confidence_per_mille >= 700
    )
    quarantined = event.conflict and (
        event.replayed or event.child_expansion or not event.proof_valid
    )
    allow = evidence_valid and not quarantined
    return Decision(
        allow=allow,
        quarantined=quarantined,
        replayed_effect=False,
        reason="verified contracting envelope" if allow else "fail-safe evidence rejection",
    )


def _resource_budget(scenario: ScenarioSpec) -> int:
    return 190 if "energy" in scenario.axes else 10_000


def run_cell(
    method: Method,
    scenario: ScenarioSpec,
    seed: int,
    protocol_sha256: str,
) -> RunResult:
    events = generate_trace(scenario, seed)
    trace_sha = hashlib.sha256(trace_bytes(events)).hexdigest()
    budget = _resource_budget(scenario)
    used = 0
    allowed = unsafe_executed = unsafe_prevented = false_denials = 0
    violations = incorrect_conflicts = effect_replays = quarantines = 0
    critical_total = critical_allowed = utility = energy = compute = 0
    permitted_count = 0
    processing_events = events
    if method is Method.EDGE_LIFELINE and "energy" in scenario.axes:
        processing_events = tuple(
            sorted(
                events,
                key=lambda item: (
                    item.utility / (item.energy_cost + item.compute_cost),
                    item.critical,
                    item.event_id,
                ),
                reverse=True,
            )
        )
    for event in processing_events:
        expected = permitted(event)
        permitted_count += int(expected)
        decision = decide(method, scenario, event)
        resource_cost = event.energy_cost + event.compute_cost
        if decision.allow and used + resource_cost > budget:
            decision = Decision(allow=False, reason="resource budget exhausted")
        if decision.allow:
            used += resource_cost
            allowed += 1
            utility += event.utility
            energy += event.energy_cost
            compute += event.compute_cost
        if event.critical:
            critical_total += 1
            critical_allowed += int(decision.allow and expected)
        unsafe_executed += int(decision.allow and not expected)
        unsafe_prevented += int(not decision.allow and not expected)
        false_denials += int(not decision.allow and expected)
        violations += int(
            decision.allow
            and (
                event.replayed
                or event.child_expansion
                or (event.consequential and not event.proof_valid)
                or ("time" in scenario.axes and not event.bounded_time_valid)
                or ("identity" in scenario.axes and not event.bounded_identity_valid)
                or ("staleness" in scenario.axes and not event.lease_valid)
            )
        )
        incorrect_conflicts += int(
            event.conflict and decision.allow and method is Method.B5_LAST_WRITER_WINS
        )
        effect_replays += int(decision.replayed_effect and event.physical_effect)
        quarantines += int(decision.quarantined)
    availability = critical_allowed / critical_total if critical_total else 1.0
    resource_total = energy + compute
    utility_per_resource = utility / resource_total if resource_total else 0.0
    mission = availability >= 0.70 and unsafe_executed == 0
    run_id = hashlib.sha256(
        f"{protocol_sha256}:{method.value}:{scenario.scenario_id}:{seed}".encode()
    ).hexdigest()[:24]
    return RunResult(
        run_id=run_id,
        method=method,
        scenario_id=scenario.scenario_id,
        seed=seed,
        trace_sha256=trace_sha,
        oracle_sha256=oracle_sha256(),
        protocol_sha256=protocol_sha256,
        events=len(events),
        critical_events=critical_total,
        permitted_events=permitted_count,
        allowed_events=allowed,
        unsafe_actions_executed=unsafe_executed,
        unsafe_actions_prevented=unsafe_prevented,
        false_denials=false_denials,
        invariant_violations=violations,
        incorrect_conflict_resolutions=incorrect_conflicts,
        prohibited_effect_replays=effect_replays,
        quarantines=quarantines,
        critical_availability=availability,
        mission_outcome=mission,
        mission_utility=utility,
        energy_consumed_model_units=energy,
        compute_consumed_model_units=compute,
        utility_per_resource=utility_per_resource,
    )


def run_experiment(seeds: Iterable[int], protocol_sha256: str) -> tuple[RunResult, ...]:
    ordered_seeds = tuple(sorted(set(seeds)))
    if len(ordered_seeds) < 1:
        raise ValueError("at least one seed is required")
    return tuple(
        run_cell(method, scenario, seed, protocol_sha256)
        for scenario in SCENARIOS
        for seed in ordered_seeds
        for method in METHODS
    )
