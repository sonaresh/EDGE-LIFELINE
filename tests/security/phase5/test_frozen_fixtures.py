from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.security


def test_phase5_fixtures_regenerate_byte_for_byte(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed interpreter and module
        [
            sys.executable,
            "-m",
            "scripts.generate_phase5_fixtures",
            "--output-directory",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    frozen = Path("tests/vectors/phase5")
    for name in (
        "identity-fixtures-v1.json",
        "time-traces-v1.json",
        "policy-manifest-v1.json",
    ):
        assert (tmp_path / name).read_bytes() == (frozen / name).read_bytes()


def test_frozen_policy_fixture_pins_opa_and_semantic_content() -> None:
    value = json.loads(Path("tests/vectors/phase5/policy-manifest-v1.json").read_text())
    assert value["opa_version"] == "1.19.1"
    assert value["policy_version"] == "phase5-policy-v1"
    assert len(value["policy_hash"]) == 64
    assert value["transport_metadata_excluded"] is True


def test_frozen_identity_and_time_fail_safe_cases_are_present() -> None:
    identity = json.loads(Path("tests/vectors/phase5/identity-fixtures-v1.json").read_text())
    time = json.loads(Path("tests/vectors/phase5/time-traces-v1.json").read_text())
    assert identity["cases"]["valid_cached_identity"]["eligible"] is True
    assert identity["cases"]["stale_identity_and_revocation"]["eligible"] is False
    assert identity["cases"]["revoked_in_snapshot"]["eligible"] is False
    assert time["cases"]["normal"]["active"] is True
    assert time["cases"]["rollback"]["active"] is False
    assert time["cases"]["restart_without_retained_anchor"]["active"] is False
    assert time["cases"]["stale_anchor"]["active"] is False
