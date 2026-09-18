# Phase 6 evidence

Generated evidence is excluded from source control. Run `scripts/run_phase6_gate.ps1` only after
committing the candidate. An automated pass remains conditional until independent review compares
the Windows archive with the GitHub Actions `phase6-validation-evidence` artifact.

That comparison is complete; `phase6-external-acceptance.json` records the accepted source and
archive hashes. A rerun remains a separate conditional result.
