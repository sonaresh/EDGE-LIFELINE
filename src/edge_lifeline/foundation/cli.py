from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from edge_lifeline import __version__
from edge_lifeline.formal.dae import HazardDimension, HazardVector, calculate_envelope
from edge_lifeline.formal.defaults import synthetic_hospital_envelope, synthetic_hospital_policy
from edge_lifeline.foundation.identity import identity_as_dict, make_run_identity
from edge_lifeline.foundation.provenance import (
    build_manifest,
    capture_environment,
    discover_source_files,
    write_json,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edge-lifeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")

    provenance = sub.add_parser("capture-provenance")
    provenance.add_argument("--root", type=Path, default=Path.cwd())
    provenance.add_argument("--output", type=Path, required=True)

    manifest = sub.add_parser("manifest")
    manifest.add_argument("--root", type=Path, default=Path.cwd())
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("paths", nargs="+")

    source_manifest = sub.add_parser("source-manifest")
    source_manifest.add_argument("--root", type=Path, default=Path.cwd())
    source_manifest.add_argument("--output", type=Path, required=True)

    identity = sub.add_parser("run-id")
    identity.add_argument("--phase", required=True)
    identity.add_argument("--scenario", required=True)
    identity.add_argument("--method", required=True)
    identity.add_argument("--seed", type=int, required=True)
    identity.add_argument("--config-json", default="{}")

    phase2 = sub.add_parser("phase2-evaluate")
    phase2.add_argument(
        "--hazards-json",
        required=True,
        help="JSON object containing all twelve hazard dimensions as integer per-mille values",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "version":
        print(__version__)
        return
    if args.command == "capture-provenance":
        write_json(args.output, capture_environment(args.root.resolve()))
        print(args.output)
        return
    if args.command == "manifest":
        write_json(args.output, {"sha256": build_manifest(args.root.resolve(), args.paths)})
        print(args.output)
        return
    if args.command == "source-manifest":
        root = args.root.resolve()
        write_json(args.output, {"sha256": build_manifest(root, discover_source_files(root))})
        print(args.output)
        return
    if args.command == "phase2-evaluate":
        raw_hazards = json.loads(args.hazards_json)
        if not isinstance(raw_hazards, dict):
            raise SystemExit("--hazards-json must decode to an object")
        try:
            hazards = HazardVector(
                {HazardDimension(name): int(value) for name, value in raw_hazards.items()}
            )
        except (TypeError, ValueError) as error:
            raise SystemExit(f"invalid hazard vector: {error}") from error
        envelope = synthetic_hospital_envelope()
        decision = calculate_envelope(
            previous=envelope,
            parent=envelope,
            lease=envelope,
            hazards=hazards,
            policy=synthetic_hospital_policy(),
        )
        print(
            json.dumps(
                {
                    "schema_version": "phase2-decision-diagnostic-v1",
                    "synthetic_nonclinical": True,
                    "band": decision.band.name,
                    "result": decision.result.value,
                    "allowed_actions": sorted(decision.envelope.actions),
                    "denied_actions": list(decision.denied_actions),
                    "budgets": asdict(decision.envelope.budgets),
                    "justification": list(decision.justification),
                },
                sort_keys=True,
            )
        )
        return
    configuration = json.loads(args.config_json)
    if not isinstance(configuration, dict):
        raise SystemExit("--config-json must decode to an object")
    identity = make_run_identity(
        phase=args.phase,
        scenario=args.scenario,
        method=args.method,
        seed=args.seed,
        configuration=configuration,
    )
    print(json.dumps(identity_as_dict(identity), sort_keys=True))


if __name__ == "__main__":
    main()
