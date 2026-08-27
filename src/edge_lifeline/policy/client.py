"""Fail-safe OPA sidecar client restricted to local transports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

import httpx


def _sha256(value: str) -> str:
    if len(value) != 64 or any(item not in "0123456789abcdef" for item in value):
        raise ValueError("expected policy hash must be lowercase SHA-256 hex")
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allow: bool
    decision: str
    obligations: Mapping[str, Any]
    policy_hash: str
    policy_version: str
    failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "obligations",
            _freeze(self.obligations),
        )


class OpaPolicyClient:
    """Call a pinned local OPA decision endpoint and deny on every ambiguity."""

    def __init__(
        self,
        *,
        base_url: str,
        entrypoint: str,
        expected_policy_hash: str,
        expected_policy_version: str,
        timeout_seconds: float = 1.0,
        unix_socket: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("OPA endpoint must use loopback or a local Unix socket")
        if parsed.username or parsed.password or not entrypoint or ".." in entrypoint.split("/"):
            raise ValueError("invalid OPA endpoint or entrypoint")
        if unix_socket is not None and not Path(unix_socket).is_absolute():
            raise ValueError("OPA Unix socket path must be absolute")
        normalized_entrypoint = entrypoint.strip("/")
        if not normalized_entrypoint or any(not part for part in normalized_entrypoint.split("/")):
            raise ValueError("invalid OPA entrypoint")
        if timeout_seconds <= 0 or not expected_policy_version:
            raise ValueError("OPA timeout and expected policy version must be positive/nonempty")
        self._entrypoint = normalized_entrypoint
        self._policy_hash = _sha256(expected_policy_hash)
        self._policy_version = expected_policy_version
        self._owns_client = client is None
        transport = httpx.HTTPTransport(uds=unix_socket) if unix_socket else None
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpaPolicyClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def evaluate(self, input_document: Mapping[str, Any]) -> PolicyDecision:
        request_input = dict(input_document)
        request_input["required_policy_hash"] = self._policy_hash
        request_input["required_policy_version"] = self._policy_version
        try:
            response = self._client.post(
                f"/v1/data/{self._entrypoint}", json={"input": request_input}
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return self._deny("OPA_UNAVAILABLE_OR_INVALID_RESPONSE")
        if not isinstance(payload, dict) or set(payload) != {"result"}:
            return self._deny("OPA_RESPONSE_SCHEMA_MISMATCH")
        result = payload["result"]
        if not isinstance(result, dict):
            return self._deny("OPA_RESULT_MISSING")
        required = {"allow", "decision", "obligations", "policy_hash", "policy_version"}
        if set(result) != required:
            return self._deny("OPA_RESULT_SCHEMA_MISMATCH")
        if (
            not isinstance(result["allow"], bool)
            or not isinstance(result["decision"], str)
            or not isinstance(result["obligations"], dict)
            or not isinstance(result["policy_hash"], str)
            or not isinstance(result["policy_version"], str)
        ):
            return self._deny("OPA_RESULT_TYPE_MISMATCH")
        if result["policy_hash"] != self._policy_hash:
            return self._deny("OPA_POLICY_HASH_MISMATCH")
        if result["policy_version"] != self._policy_version:
            return self._deny("OPA_POLICY_VERSION_MISMATCH")
        if not result["allow"]:
            return PolicyDecision(
                False,
                result["decision"],
                result["obligations"],
                self._policy_hash,
                self._policy_version,
                ("OPA_POLICY_DENIED",),
            )
        return PolicyDecision(
            True,
            result["decision"],
            result["obligations"],
            self._policy_hash,
            self._policy_version,
        )

    def _deny(self, failure: str) -> PolicyDecision:
        return PolicyDecision(
            False,
            "DENY_UNSAFE_ACTION",
            {},
            self._policy_hash,
            self._policy_version,
            (failure,),
        )
