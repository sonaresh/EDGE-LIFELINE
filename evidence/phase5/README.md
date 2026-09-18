# Phase 5 evidence

`scripts/run_phase5_gate.ps1` creates timestamped evidence under `generated/`. Generated
directories are intentionally excluded from source control and source manifests.

Required evidence includes the full and security-negative JUnit reports, branch-aware coverage,
OPA version and test results, deterministic identity fixtures, boot-aware time traces, the
semantic policy manifest, source and evidence manifests, provenance, limitations, SBOM, and
dependency audit. External review must compare local Windows and GitHub Actions archives from
the same clean source commit before changing the conditional decision.

The completed review and immutable archive hashes are recorded in
`phase5-external-acceptance.json`.
