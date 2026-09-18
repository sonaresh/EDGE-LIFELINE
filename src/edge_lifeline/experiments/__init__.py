"""Phase 8 paired synthetic experiment harness."""

from edge_lifeline.experiments.analysis import analyze_results
from edge_lifeline.experiments.catalog import METHODS, SCENARIOS
from edge_lifeline.experiments.harness import run_experiment
from edge_lifeline.experiments.model import Method, RunResult, ScenarioSpec

__all__ = [
    "METHODS",
    "SCENARIOS",
    "Method",
    "RunResult",
    "ScenarioSpec",
    "analyze_results",
    "run_experiment",
]
