from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from edge_lifeline.mission.fixtures import context_for, synthetic_hospital_graph
from edge_lifeline.mission.optimizer import MissionOptimizer

pytestmark = pytest.mark.security


def test_frozen_mvsg_vector_is_reproducible_and_validated(tmp_path: Path) -> None:
    frozen_path = Path("tests/vectors/phase4/hospital-mvsg-v1.json")
    regenerated_path = tmp_path / "regenerated.json"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/generate_phase4_vectors.py",
            "--output",
            str(regenerated_path),
        ],
        check=True,
    )
    assert regenerated_path.read_bytes() == frozen_path.read_bytes()
    vector = json.loads(frozen_path.read_bytes())
    graph = synthetic_hospital_graph()
    context = context_for(graph)
    result = MissionOptimizer().optimize(graph, context, random_seed=0)
    assert result.plan is not None and result.certificate is not None
    assert result.certificate.valid
    assert vector["graph_hash"] == graph.graph_hash()
    assert vector["context_hash"] == context.context_hash()
    assert vector["result"]["plan_hash"] == result.plan.plan_hash()
    assert vector["result"]["validation_certificate_hash"] == result.certificate.certificate_hash()
