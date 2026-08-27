"""Generate deterministic synthetic Phase 4 MVSG interoperability vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from edge_lifeline.mission.fixtures import context_for, synthetic_hospital_graph
from edge_lifeline.mission.optimizer import MissionOptimizer


def build_vector() -> dict[str, Any]:
    graph = synthetic_hospital_graph()
    context = context_for(graph)
    result = MissionOptimizer().optimize(graph, context, random_seed=0)
    if result.plan is None or result.certificate is None or not result.certificate.valid:
        raise RuntimeError("synthetic Phase 4 fixture did not produce a validated plan")
    return {
        "schema_version": "edge-lifeline-phase4-vector-v1",
        "synthetic_nonclinical": True,
        "graph": graph.to_obj(),
        "graph_hash": graph.graph_hash(),
        "context": context.to_obj(),
        "context_hash": context.context_hash(),
        "result": {
            "decision": result.decision,
            "reason": result.reason,
            "plan": result.plan.to_obj(),
            "plan_hash": result.plan.plan_hash(),
            "validation_certificate": result.certificate.to_obj(),
            "validation_certificate_hash": result.certificate.certificate_hash(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_vector(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
