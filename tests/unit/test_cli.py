from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from edge_lifeline.foundation import cli


def invoke(monkeypatch: pytest.MonkeyPatch, arguments: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["edge-lifeline", *arguments])
    cli.main()


def test_version_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    invoke(monkeypatch, ["version"])
    assert capsys.readouterr().out.strip() == "0.7.0"


def test_run_id_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    invoke(
        monkeypatch,
        [
            "run-id",
            "--phase",
            "phase1",
            "--scenario",
            "smoke",
            "--method",
            "foundation",
            "--seed",
            "7",
            "--config-json",
            '{"edges":3}',
        ],
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["seed"] == 7
    assert len(payload["run_id"]) == 24


def test_run_id_rejects_non_object_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit, match="must decode to an object"):
        invoke(
            monkeypatch,
            [
                "run-id",
                "--phase",
                "phase1",
                "--scenario",
                "smoke",
                "--method",
                "foundation",
                "--seed",
                "7",
                "--config-json",
                "[]",
            ],
        )


def test_manifest_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "source.txt").write_text("content", encoding="utf-8")
    output = tmp_path / "manifest.json"
    invoke(
        monkeypatch,
        ["manifest", "--root", str(tmp_path), "--output", str(output), "source.txt"],
    )
    assert output.is_file()
    assert "source.txt" in json.loads(output.read_text(encoding="utf-8"))["sha256"]
    assert str(output) in capsys.readouterr().out


def test_provenance_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "provenance.json"
    invoke(
        monkeypatch,
        ["capture-provenance", "--root", str(tmp_path), "--output", str(output)],
    )
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == (
        "edge-lifeline-provenance-v1"
    )
    assert str(output) in capsys.readouterr().out


def test_source_manifest_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("ignored\n", encoding="utf-8")
    output = tmp_path / "source-manifest.json"
    invoke(
        monkeypatch,
        ["source-manifest", "--root", str(tmp_path), "--output", str(output)],
    )
    manifest = json.loads(output.read_text(encoding="utf-8"))["sha256"]
    assert set(manifest) == {"src/app.py"}
    assert str(output) in capsys.readouterr().out


def test_phase2_evaluate_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hazards = {
        name: 100
        for name in (
            "isolation",
            "clock",
            "data",
            "sensor",
            "energy",
            "resource",
            "security",
            "identity",
            "revocation",
            "physical",
            "financial",
            "human",
        )
    }
    invoke(monkeypatch, ["phase2-evaluate", "--hazards-json", json.dumps(hazards)])
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "phase2-decision-diagnostic-v1"
    assert payload["synthetic_nonclinical"] is True
    assert payload["band"] == "NORMAL_DELEGATED"
    assert payload["result"] == "CONTINUE_LOCALLY"


def test_phase2_evaluate_rejects_missing_hazard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit, match="hazard vector must be complete"):
        invoke(monkeypatch, ["phase2-evaluate", "--hazards-json", '{"clock": 1}'])


def test_phase2_evaluate_rejects_non_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit, match="must decode to an object"):
        invoke(monkeypatch, ["phase2-evaluate", "--hazards-json", "[]"])
