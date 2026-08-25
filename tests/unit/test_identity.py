from __future__ import annotations

import pytest

from edge_lifeline.foundation.identity import canonical_json, make_run_identity


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_run_identity_is_deterministic() -> None:
    first = make_run_identity(
        phase="phase1", scenario="smoke", method="foundation", seed=7, configuration={"b": 2}
    )
    second = make_run_identity(
        phase="phase1", scenario="smoke", method="foundation", seed=7, configuration={"b": 2}
    )
    assert first == second
    assert len(first.run_id) == 24


def test_run_identity_changes_with_seed() -> None:
    first = make_run_identity(
        phase="phase1", scenario="smoke", method="foundation", seed=7, configuration={}
    )
    second = make_run_identity(
        phase="phase1", scenario="smoke", method="foundation", seed=8, configuration={}
    )
    assert first.run_id != second.run_id


def test_negative_seed_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        make_run_identity(
            phase="phase1", scenario="smoke", method="foundation", seed=-1, configuration={}
        )
