from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

from edge_lifeline import __version__


def test_release_versions_are_consistent() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    citation = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))
    assert project["project"]["version"] == "0.6.0"
    assert citation["version"] == "0.6.0"
    assert __version__ == "0.6.0"
