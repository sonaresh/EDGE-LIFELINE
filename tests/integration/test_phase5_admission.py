from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from edge_lifeline.identity import (
    AssuranceLevel,
    CachedIdentityPolicy,
    IdentityAssertion,
    RevocationSnapshot,
)
from edge_lifeline.phase5 import Phase5AdmissionDecision, evaluate_phase5_admission
from edge_lifeline.policy import OpaPolicyClient
from edge_lifeline.time import AuthenticatedTimeAnchor, TimeObservation

POLICY_HASH = "a" * 64
POLICY_VERSION = "phase5-policy-v1"


def identity() -> IdentityAssertion:
    return IdentityAssertion(
        subject_id="pseudonym:ward-a:operator-7",
        roles=frozenset({"operator"}),
        assurance=AssuranceLevel.CACHED_MULTIFACTOR,
        issued_at_ms=1_000,
        expires_at_ms=10_000,
        issuer="hospital-idp",
        source_artifact_hash="b" * 64,
        revocation_snapshot_id="snapshot-17",
    )


def snapshot() -> RevocationSnapshot:
    return RevocationSnapshot(
        snapshot_id="snapshot-17",
        issuer="hospital-idp",
        generated_at_ms=1_500,
        next_update_ms=8_000,
        revoked_subject_hashes=frozenset(),
        source_artifact_hash="c" * 64,
    )


def anchor() -> AuthenticatedTimeAnchor:
    return AuthenticatedTimeAnchor(
        anchor_id="anchor-1",
        source_artifact_hash="d" * 64,
        utc_estimate_ms=1_500,
        initial_error_ms=10,
        boot_id="boot-a",
        boottime_anchor_ms=0,
        drift_parts_per_million=0,
        maximum_anchor_age_ms=5_000,
        restart_suspend_penalty_ms=500,
    )


def opa(handler: Callable[[httpx.Request], httpx.Response]) -> OpaPolicyClient:
    http = httpx.Client(base_url="http://127.0.0.1:8181", transport=httpx.MockTransport(handler))
    return OpaPolicyClient(
        base_url="http://127.0.0.1:8181",
        entrypoint="edge_lifeline/phase5/result",
        expected_policy_hash=POLICY_HASH,
        expected_policy_version=POLICY_VERSION,
        client=http,
    )


def identity_policy() -> CachedIdentityPolicy:
    return CachedIdentityPolicy(
        max_cache_age_ms=4_000,
        max_revocation_staleness_ms=3_500,
        minimum_assurance=AssuranceLevel.CACHED_MULTIFACTOR,
        permitted_roles=frozenset({"operator"}),
    )


def evaluate(
    client: OpaPolicyClient, *, observation: TimeObservation | None = None
) -> Phase5AdmissionDecision:
    return evaluate_phase5_admission(
        assertion=identity(),
        snapshot=snapshot(),
        identity_policy=identity_policy(),
        required_role="operator",
        time_anchor=anchor(),
        observation=observation or TimeObservation("boot-a", 1_000),
        previous_observation=None,
        policy_client=client,
        action="dispense",
        resource="pump-1",
        authority_actions=frozenset({"dispense"}),
        authority_resources=frozenset({"pump-1"}),
    )


def test_all_three_phase5_predicates_are_required() -> None:
    def allow(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        assert body["input"]["required_policy_hash"] == POLICY_HASH
        assert body["input"]["required_policy_version"] == POLICY_VERSION
        return httpx.Response(
            200,
            json={
                "result": {
                    "allow": True,
                    "decision": "CONTINUE_LOCALLY",
                    "obligations": {"proof_before_effect": True},
                    "policy_hash": POLICY_HASH,
                    "policy_version": POLICY_VERSION,
                }
            },
        )

    result = evaluate(opa(allow))
    assert result.allow
    assert result.identity is not None and result.identity.eligible
    assert result.policy is not None and result.policy.allow
    assert len(result.decision_hash()) == 64


def test_time_failure_short_circuits_identity_and_policy() -> None:
    calls = 0

    def unexpected(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    result = evaluate(opa(unexpected), observation=TimeObservation("boot-b", 1))
    assert not result.allow
    assert result.identity is None
    assert result.policy is None
    assert calls == 0


def test_stale_policy_response_denies_after_identity_and_time_pass() -> None:
    client = opa(
        lambda _: httpx.Response(
            200,
            json={
                "result": {
                    "allow": True,
                    "decision": "CONTINUE_LOCALLY",
                    "obligations": {},
                    "policy_hash": "f" * 64,
                    "policy_version": POLICY_VERSION,
                }
            },
        )
    )
    result = evaluate(client)
    assert not result.allow
    assert result.failures == ("OPA_POLICY_HASH_MISMATCH",)
