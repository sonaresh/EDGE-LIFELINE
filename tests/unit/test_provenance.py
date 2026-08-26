from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from edge_lifeline.foundation.provenance import (
    build_manifest,
    capture_environment,
    discover_source_files,
    write_json,
)


def test_manifest_hashes_exact_bytes(tmp_path: Path) -> None:
    target = tmp_path / "input.txt"
    target.write_bytes(b"edge-lifeline\n")
    manifest = build_manifest(tmp_path, ["input.txt"])
    assert manifest == {"input.txt": hashlib.sha256(b"edge-lifeline\n").hexdigest()}


def test_manifest_rejects_missing_required_input(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="required manifest input"):
        build_manifest(tmp_path, ["missing.txt"])


def test_manifest_rejects_path_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        build_manifest(tmp_path, ["../outside.txt"])


def test_source_discovery_excludes_generated_and_virtual_environment(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("source", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "package.py").write_text("ignored", encoding="utf-8")
    generated = tmp_path / "evidence" / "phase1" / "generated" / "run"
    generated.mkdir(parents=True)
    (generated / "report.json").write_text("{}", encoding="utf-8")
    generated_phase2 = tmp_path / "evidence" / "phase2" / "generated" / "run"
    generated_phase2.mkdir(parents=True)
    (generated_phase2 / "report.json").write_text("{}", encoding="utf-8")
    (tmp_path / "archive.zip").write_bytes(b"not-source")
    assert discover_source_files(tmp_path) == ["src/app.py"]


def test_source_discovery_rejects_empty_tree(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no manifestable files"):
        discover_source_files(tmp_path)


def test_write_json_is_stably_sorted(tmp_path: Path) -> None:
    target = tmp_path / "record.json"
    write_json(target, {"z": 1, "a": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2, "z": 1}
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_environment_capture_has_required_fields() -> None:
    record = capture_environment(Path.cwd())
    assert record["schema_version"] == "edge-lifeline-provenance-v1"
    assert record["python"]["version"].startswith("3.12")
    assert "docker" in record
