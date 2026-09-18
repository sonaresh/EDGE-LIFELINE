# Phase 5: deterministic identity, bounded time, and pinned policy

Phase 5 admits an offline action only when three independent predicates agree:

1. An already-authenticated pseudonymous identity assertion remains inside explicit
   cache-age, assurance, role, expiry, and revocation-snapshot bounds.
2. An authenticated UTC anchor plus boot-aware elapsed time yields an active conservative
   interval. The wall clock is diagnostic only.
3. a local OPA 1.19.1 Rego decision returns the exact expected semantic policy hash and
   policy version.

Any unavailable, malformed, stale, rolled-back, discontinuous, or mismatched input produces
`DENY_UNSAFE_ACTION` or `PROTECTIVE_READ_ONLY`. Restart without an explicitly
hardware-retained anchor requires re-anchoring. The runtime never describes a disconnected
revocation snapshot as current; revocations issued after the last authenticated snapshot are
unknowable until connectivity returns.

## Semantic policy binding

`PolicyBundle` hashes canonical semantic content: normalized Rego paths and LF source bytes,
canonical data documents, sorted entrypoints, schema version, exact OPA version, and policy
version. Archive ordering, gzip timestamps, and other transport metadata are excluded. The
OPA policy obtains its active hash/version from runtime labels, while the client injects the
required hash/version and rejects any unequal response.

## Validation

Run from PowerShell 7.4 or newer:

```powershell
./scripts/run_phase5_gate.ps1
```

The gate runs Ruff, strict Mypy, branch-aware Pytest, security-negative tests, official OPA
Rego tests, byte-for-byte frozen fixture regeneration, provenance, CycloneDX SBOM generation,
and dependency auditing. The first run downloads OPA from the official project URL and checks
the binary against the adjacent official SHA-256 file before execution.

The automated result remains `CONDITIONAL_PASS` by design. Independent Windows/CI review recorded
Phase 5 `PASS` at source commit `150bf42abd864cb793a2c1de5eb8110b36034162` and authorized
Phase 6. Rerunning the gate does not replace that external decision.
