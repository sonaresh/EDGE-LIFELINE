from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RunIdentity:
    phase: str
    scenario: str
    method: str
    seed: int
    config_hash: str
    run_id: str


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def make_run_identity(
    *, phase: str, scenario: str, method: str, seed: int, configuration: dict[str, Any]
) -> RunIdentity:
    if seed < 0:
        raise ValueError("seed must be non-negative")
    descriptor = {
        "phase": phase,
        "scenario": scenario,
        "method": method,
        "seed": seed,
        "configuration": configuration,
    }
    config_hash = sha256_bytes(canonical_json(configuration))
    run_id = sha256_bytes(canonical_json(descriptor))[:24]
    return RunIdentity(
        phase=phase,
        scenario=scenario,
        method=method,
        seed=seed,
        config_hash=config_hash,
        run_id=run_id,
    )


def identity_as_dict(identity: RunIdentity) -> dict[str, str | int]:
    return asdict(identity)
