from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_phase6_vectors import main


def test_phase6_vectors_regenerate_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["generate_phase6_vectors", "--output-directory", str(tmp_path)],
    )
    assert main() == 0
    frozen = Path("tests/vectors/phase6")
    for path in sorted(frozen.glob("*.json")):
        assert path.read_bytes() == (tmp_path / path.name).read_bytes()


def test_recovery_vector_never_restores_authority_or_replays_effect() -> None:
    value = json.loads(Path("tests/vectors/phase6/recovery-vector-v1.json").read_text())
    assert value["plan"]["authority_restored"] is False
    assert value["plan"]["fresh_connected_epoch_lease_required"] is True
    assert value["plan"]["effect_replay_count"] == 0
    assert value["receipt"]["effect_replay_count"] == 0


def test_negative_vector_covers_required_attack_classes() -> None:
    value = json.loads(Path("tests/vectors/phase6/negative-cases-v1.json").read_text())
    assert set(value["cases"]) == {
        "missing_parent",
        "fork",
        "invalid_signature",
        "false_class",
        "effect_replay",
        "reconnect",
    }
