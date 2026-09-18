# Phase 1 evidence

Generated gate evidence is stored in timestamped directories and intentionally excluded from
source control. Phase 1 was independently accepted; the durable decision is
`phase1-external-acceptance.json`.

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

The four-service Compose smoke test and CI evidence were independently reviewed before the Phase 1
`PASS` was recorded. A new gate run remains conditional until separately reviewed.
