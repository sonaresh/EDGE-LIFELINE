from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from edge_lifeline.policy import OpaPolicyClient

POLICY_HASH = "a" * 64
POLICY_VERSION = "phase5-policy-v1"
pytestmark = pytest.mark.security


def result(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "allow": True,
        "decision": "CONTINUE_LOCALLY",
        "obligations": {"proof_before_effect": True},
        "policy_hash": POLICY_HASH,
        "policy_version": POLICY_VERSION,
    }
    value.update(overrides)
    return {"result": value}


def client(handler: Callable[[httpx.Request], httpx.Response]) -> OpaPolicyClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url="http://127.0.0.1:8181", transport=transport)
    return OpaPolicyClient(
        base_url="http://127.0.0.1:8181",
        entrypoint="edge_lifeline/phase5/result",
        expected_policy_hash=POLICY_HASH,
        expected_policy_version=POLICY_VERSION,
        client=http,
    )


def test_exact_pinned_policy_decision_is_accepted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/data/edge_lifeline/phase5/result"
        assert request.read()
        return httpx.Response(200, json=result())

    decision = client(handler).evaluate({"action": "dispense"})
    assert decision.allow
    assert decision.failures == ()


def test_explicit_policy_denial_remains_denied() -> None:
    decision = client(
        lambda _: httpx.Response(200, json=result(allow=False, decision="DENY_UNSAFE_ACTION"))
    ).evaluate({})
    assert not decision.allow
    assert decision.failures == ("OPA_POLICY_DENIED",)


@pytest.mark.parametrize(
    ("payload", "failure"),
    [
        ({}, "OPA_RESPONSE_SCHEMA_MISMATCH"),
        ({"result": None}, "OPA_RESULT_MISSING"),
        ({"result": {"allow": True}}, "OPA_RESULT_SCHEMA_MISMATCH"),
        (result(allow=1), "OPA_RESULT_TYPE_MISMATCH"),
        (result(policy_hash="b" * 64), "OPA_POLICY_HASH_MISMATCH"),
        (result(policy_version="phase5-policy-v0"), "OPA_POLICY_VERSION_MISMATCH"),
    ],
)
def test_ambiguous_or_stale_policy_response_fails_safe(
    payload: dict[str, Any], failure: str
) -> None:
    decision = client(lambda _: httpx.Response(200, json=payload)).evaluate({})
    assert not decision.allow
    assert decision.decision == "DENY_UNSAFE_ACTION"
    assert decision.failures == (failure,)


def test_unavailable_policy_fails_safe() -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    decision = client(unavailable).evaluate({})
    assert not decision.allow
    assert decision.failures == ("OPA_UNAVAILABLE_OR_INVALID_RESPONSE",)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": "https://policy.example.com"},
        {"base_url": "http://user:password@127.0.0.1"},
        {"entrypoint": "../admin"},
        {"entrypoint": "edge//result"},
        {"expected_policy_hash": "A" * 64},
        {"expected_policy_version": ""},
        {"timeout_seconds": 0},
        {"unix_socket": "relative.sock"},
    ],
)
def test_nonlocal_or_ambiguous_client_configuration_is_rejected(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "base_url": "http://127.0.0.1:8181",
        "entrypoint": "edge/result",
        "expected_policy_hash": POLICY_HASH,
        "expected_policy_version": POLICY_VERSION,
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        OpaPolicyClient(**values)  # type: ignore[arg-type]
