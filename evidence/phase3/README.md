# Phase 3 evidence boundary

Generated Phase 3 evidence is intentionally excluded from Git. Run
`scripts/run_phase3_gate.ps1` to create a timestamped directory here, archive that
directory outside the repository, and preserve its SHA-256 digest.

An automated `CONDITIONAL_PASS` does not complete Phase 3 or authorize Phase 4.
Independent review must validate both local Windows and GitHub Actions archives,
their internal manifests, and their shared source commit before an acceptance record
is added to this directory.
