"""Transport-independent semantic hashing for pinned OPA/Rego bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any

from edge_lifeline.proof.codec import canonical_dumps, sha256_hex


def _path(value: str) -> str:
    if not value or "\\" in value:
        raise ValueError("policy paths must be nonempty normalized POSIX paths")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("policy path traversal or ambiguity is forbidden")
    normalized = candidate.as_posix()
    if normalized != value:
        raise ValueError("policy path must already be normalized")
    return normalized


def _entrypoint(value: str) -> str:
    if not value or value.startswith("/") or "\\" in value:
        raise ValueError("invalid policy entrypoint")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("invalid policy entrypoint")
    return value


def _source_bytes(value: bytes) -> bytes:
    normalized = value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    normalized.decode("utf-8")
    return normalized


def _freeze(value: Any) -> Any:
    """Copy JSON/CBOR-like policy data into an immutable representation."""

    if isinstance(value, Mapping):
        if any(not isinstance(key, str) or not key for key in value):
            raise ValueError("policy data document keys must be nonempty strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (str, bytes, int, bool)) or value is None:
        return value
    raise ValueError("policy data documents must contain deterministic data types")


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class PolicyBundle:
    sources: Mapping[str, bytes]
    data_documents: Mapping[str, Any]
    entrypoints: tuple[str, ...]
    policy_version: str
    opa_version: str
    schema_version: str = "edge-lifeline-policy-bundle-v1"

    def __post_init__(self) -> None:
        if not self.policy_version or not self.opa_version or not self.entrypoints:
            raise ValueError("policy version, OPA version, and entrypoints are required")
        normalized_sources = {
            _path(key): _source_bytes(value) for key, value in self.sources.items()
        }
        normalized_data = {_path(key): _freeze(value) for key, value in self.data_documents.items()}
        if not normalized_sources or len(normalized_sources) != len(self.sources):
            raise ValueError("policy source paths must be unique after normalization")
        if len(normalized_data) != len(self.data_documents):
            raise ValueError("policy data paths must be unique after normalization")
        normalized_entrypoints = tuple(_entrypoint(item) for item in self.entrypoints)
        if len(set(normalized_entrypoints)) != len(normalized_entrypoints):
            raise ValueError("invalid or duplicate policy entrypoint")
        for value in normalized_data.values():
            canonical_dumps(_thaw(value))
        object.__setattr__(self, "sources", MappingProxyType(normalized_sources))
        object.__setattr__(self, "data_documents", MappingProxyType(normalized_data))
        object.__setattr__(self, "entrypoints", normalized_entrypoints)

    def semantic_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "opa_version": self.opa_version,
            "entrypoints": sorted(self.entrypoints),
            "sources": {key: self.sources[key] for key in sorted(self.sources)},
            "data_documents": {
                key: _thaw(self.data_documents[key]) for key in sorted(self.data_documents)
            },
        }

    def policy_hash(self) -> str:
        return sha256_hex(canonical_dumps(self.semantic_obj()))

    def diagnostic_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "opa_version": self.opa_version,
            "entrypoints": sorted(self.entrypoints),
            "source_sha256": {key: sha256_hex(self.sources[key]) for key in sorted(self.sources)},
            "data_sha256": {
                key: sha256_hex(canonical_dumps(_thaw(self.data_documents[key])))
                for key in sorted(self.data_documents)
            },
            "policy_hash": self.policy_hash(),
            "transport_metadata_excluded": True,
        }
