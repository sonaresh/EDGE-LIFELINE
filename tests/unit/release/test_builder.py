from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from edge_lifeline.release import build_publication_package, validate_release_inputs


def test_release_inputs_bind_to_external_acceptance() -> None:
    acceptance, results = validate_release_inputs(Path.cwd())
    assert acceptance["decision"] == "PASS"
    assert results["accepted_source_commit"] == acceptance["accepted_source_commit"]
    assert len(results["primary_comparisons"]) == 8


def test_publication_package_reproduces_exactly(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert build_publication_package(Path.cwd(), first) == build_publication_package(
        Path.cwd(), second
    )
    assert sorted(path.name for path in first.iterdir()) == sorted(
        path.name for path in second.iterdir()
    )
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()


def test_manifest_hashes_every_publication_artifact(tmp_path: Path) -> None:
    build_publication_package(Path.cwd(), tmp_path)
    manifest = json.loads((tmp_path / "ARTIFACT-MANIFEST.json").read_bytes())
    assert manifest["file_count"] == 9
    assert len(manifest["sha256"]) == 9
    for name, expected in manifest["sha256"].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == expected


def test_release_preserves_scientific_boundaries(tmp_path: Path) -> None:
    build_publication_package(Path.cwd(), tmp_path)
    results = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    metadata = json.loads((tmp_path / "release-metadata.json").read_bytes())
    assert "detection-only" in results
    assert "no prevention claim" in results
    assert metadata["experiment_rerun"] is False
    assert metadata["outcome_based_exclusions"] == 0
    assert metadata["public_release_authorized"] is False


def test_acceptance_mismatch_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    acceptance_path = root / "evidence/phase8/phase8-external-acceptance.json"
    results_path = root / "publication/phase9/accepted-results.json"
    acceptance_path.parent.mkdir(parents=True)
    results_path.parent.mkdir(parents=True)
    acceptance = json.loads(Path("evidence/phase8/phase8-external-acceptance.json").read_bytes())
    results = json.loads(Path("publication/phase9/accepted-results.json").read_bytes())
    results["analysis_sha256"] = "0" * 64
    acceptance_path.write_text(json.dumps(acceptance), encoding="utf-8")
    results_path.write_text(json.dumps(results), encoding="utf-8")
    with pytest.raises(ValueError, match="analysis_sha256"):
        validate_release_inputs(root)
