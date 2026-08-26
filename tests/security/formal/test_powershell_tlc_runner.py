from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.security
def test_empty_negative_failure_set_is_forced_to_an_array() -> None:
    script = Path("scripts/run-tlc.ps1").read_text(encoding="utf-8")
    marker = "negative_counterexamples_passed = (@("
    assert marker in script
