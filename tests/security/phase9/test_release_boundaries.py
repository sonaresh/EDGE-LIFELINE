from __future__ import annotations

import json
from pathlib import Path

import pytest

from edge_lifeline.release import build_publication_package


@pytest.mark.security
def test_phase9_never_authorizes_itself(tmp_path: Path) -> None:
    build_publication_package(Path.cwd(), tmp_path)
    metadata = json.loads((tmp_path / "release-metadata.json").read_bytes())
    assert metadata["phase9_complete"] is False
    assert metadata["public_release_authorized"] is False


@pytest.mark.security
def test_generated_material_contains_no_clinical_or_production_claim(tmp_path: Path) -> None:
    build_publication_package(Path.cwd(), tmp_path)
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.iterdir()
        if path.suffix in {".md", ".json"}
    ).lower()
    assert "no clinical" in combined or "not a production or clinical certification" in combined
    assert "full-tcb-compromise prevention claim" in combined


@pytest.mark.security
def test_checksums_use_relative_names_only(tmp_path: Path) -> None:
    build_publication_package(Path.cwd(), tmp_path)
    for line in (tmp_path / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", maxsplit=1)
        assert len(digest) == 64
        assert "/" not in name
        assert "\\" not in name
        assert name not in {"CHECKSUMS.sha256", "ARTIFACT-MANIFEST.json"}
