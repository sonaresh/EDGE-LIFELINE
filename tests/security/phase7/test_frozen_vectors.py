from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_phase7_vectors import encoded_vector, vector


@pytest.mark.security
def test_frozen_runtime_vector_matches_generator() -> None:
    path = Path("tests/vectors/phase7/runtime-vector-v1.json")
    frozen = json.loads(path.read_text(encoding="utf-8"))

    assert vector() == frozen
    assert encoded_vector() == path.read_bytes()


@pytest.mark.security
def test_vector_never_restores_authority() -> None:
    assert all(not decision["authority_restored"] for decision in vector()["decisions"])


@pytest.mark.security
def test_recovery_requires_fresh_lease() -> None:
    edge_c = next(item for item in vector()["decisions"] if item["cluster_id"] == "edge-c")

    assert edge_c["mode"] == "protective"
    assert edge_c["effect_dispatch_allowed"] is False
