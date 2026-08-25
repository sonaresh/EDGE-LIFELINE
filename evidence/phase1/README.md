# Phase 1 evidence

Generated gate evidence is stored in timestamped directories and intentionally excluded from source control until reviewed and accepted.

Required accepted evidence:

- `phase1-gate.log`
- `gate-decision.json`
- `provenance.json`
- `source-manifest.json`
- `evidence-manifest.json`
- `sbom.cdx.json`
- `dependency-audit.json`
- CI run URL or exported logs
- Docker Compose rendered configuration, health responses, service/image inventory, and resolved base-image details

The current environment may validate the code gate without Docker, but Phase 1 cannot receive an unconditional pass until the four-service Compose smoke test and CI evidence have both been independently reviewed.
