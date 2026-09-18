"""Generate the deterministic Phase 9 publication package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from edge_lifeline.release import build_publication_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_publication_package(args.root.resolve(), args.output.resolve())
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
