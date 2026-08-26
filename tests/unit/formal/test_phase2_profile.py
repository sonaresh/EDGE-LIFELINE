from __future__ import annotations

import json
from pathlib import Path

from edge_lifeline.formal.dae import HazardDimension
from edge_lifeline.formal.defaults import synthetic_hospital_policy


def test_frozen_profile_matches_executable_defaults() -> None:
    profile = json.loads(Path("config/phase2.json").read_text(encoding="utf-8"))
    policy = synthetic_hospital_policy()
    assert profile["clinical_use_permitted"] is False
    assert set(profile["required_hazards"]) == {dimension.value for dimension in HazardDimension}
    assert profile["bands"] == {
        "guarded_at": policy.guarded_at,
        "essential_at": policy.essential_at,
        "protective_at": policy.protective_at,
        "terminal_at": policy.terminal_at,
    }
    assert profile["budget_floor_per_mille"] == policy.budget_floor_per_mille
    assert profile["phase3_cryptography_implemented"] is False
