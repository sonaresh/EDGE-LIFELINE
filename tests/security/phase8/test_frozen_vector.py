from __future__ import annotations

from pathlib import Path

import pytest

from scripts.generate_phase8_vector import encoded_vector


@pytest.mark.security
def test_phase8_digest_vector_regenerates_exactly() -> None:
    frozen = Path("tests/vectors/phase8/experiment-digest-v1.json")
    assert frozen.read_bytes() == encoded_vector(Path.cwd())
