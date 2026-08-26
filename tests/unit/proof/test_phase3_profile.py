from __future__ import annotations

import json
from pathlib import Path

from edge_lifeline.proof.artifact import DECISION_RESULTS
from edge_lifeline.proof.cose import COSE_SIGN1_TAG, EDDSA


def test_frozen_phase3_profile_matches_runtime_constants() -> None:
    profile = json.loads(Path("config/phase3.json").read_text(encoding="utf-8"))
    assert profile["clinical_use_permitted"] is False
    assert profile["cose_tag"] == COSE_SIGN1_TAG
    assert profile["cose_algorithm"] == EDDSA
    assert profile["key_algorithm"] == "Ed25519"
    assert profile["protected_headers"] == [1, 4]
    assert profile["unprotected_headers_permitted"] is False
    assert profile["root_authority_requires_explicit_trust_anchor"] is True
    assert set(profile["decision_results"]) == DECISION_RESULTS
