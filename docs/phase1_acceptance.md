# Phase 1 acceptance gate

## Scope

Phase 1 establishes repository structure, dependency locking, a minimal local service topology, CI, deterministic run identifiers, provenance capture, SBOM generation, tests, and cleanup. It does not implement any Phase 2 or later research mechanism.

Phase 1 was subsequently accepted by independent review on 2026-08-26. The immutable
archive hashes, accepted source commit, and review basis are recorded in
`evidence/phase1/phase1-external-acceptance.json`. The automated Phase 1 gate remains
historical and conditional by design; it does not rewrite its own external decision.

## Acceptance criteria

| Criterion | Pass condition | Evidence |
|---|---|---|
| Python environment | Python 3.12 and frozen `uv.lock` install successfully | bootstrap/gate log, `uv.lock`, provenance |
| Static validation | Ruff and strict Mypy report no errors | gate log, CI log |
| Tests | Unit, integration, and security-negative suites pass with at least 90% branch-aware coverage | gate log, coverage report |
| Local topology | One cloud and three distinct edge services become healthy | Compose service inventory and health responses |
| Container restrictions | Loopback ports, non-root UID, read-only root, all capabilities dropped, no-new-privileges | Compose tests and rendered config |
| Reproducibility | Seeded run IDs are deterministic; environment and every source/configuration file are hashed | tests, provenance, complete source manifest |
| Dependency evidence | CycloneDX SBOM generated and dependency audit has no unresolved known vulnerability | SBOM and audit JSON |
| Cleanup | Named Compose resources are removed while source/evidence remain | cleanup command and gate transcript |
| Phase boundary | No authority, proof, formal, experiment, clinical, or AWS implementation is present | config scope flags and repository review |

## Expected outputs

- 38 or more passing tests and at least 90% coverage
- Four healthy local endpoints on ports 18080 through 18083
- A timestamped evidence directory containing logs, provenance, manifests, SBOM, audit results, and container inventory
- `phase_2_authorized: false` regardless of the Phase 1 outcome
- A conditional automated decision pending independent evidence review

These are acceptance expectations, not prefilled experimental findings.

## Known limitations

- The Compose gate requires Docker Desktop with the WSL2 backend and cannot run where Docker is unavailable.
- Phase 1 uses an exact Python base-image tag and frozen runtime lock. The accepted evidence must record the architecture-specific resolved image digest after pull/build.
- GitHub Actions run the same gate, but cannot be claimed as passed until the workflow URL and uploaded evidence are reviewed.
- The topology validates packaging and isolation only. It is not evidence for degraded autonomy, proof verification, reconciliation, security containment, or mission preservation.

## Cleanup

```powershell
.\scripts\cleanup.ps1 -Confirm:$false
```

The cleanup target is limited to the `edge-lifeline-phase1` Compose project.
