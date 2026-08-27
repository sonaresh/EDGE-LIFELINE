# EDGE-LIFELINE

Proof-Carrying Degraded Autonomy and Causal Recovery for Mission-Critical
Cloud-Edge Systems.

Release **v0.4.0** is the Phase 4 candidate. It adds deterministic OR-Tools CP-SAT
Mission-Viable Service Graph selection, a solver-independent feasibility validator,
a brute-force small-graph oracle, frozen graph/plan vectors, and fail-safe timeout behavior.

Phase 3 was independently accepted against matching Windows and GitHub Actions evidence for
commit `965e5aa7dd47ba293b3e25ac6ad388c8e2c51275`. Phase 4 is not complete until its
own local and CI evidence are independently reviewed. Phase 5 is not authorized by an
automated gate.

The hospital emergency-continuity case study is a synthetic systems-resilience
experiment. This is not a clinically validated medical system and must not be used
for patient care.

## What “Proof-Carrying” and MVSG mean in this candidate

A consequential decision is dispatchable only after the edge has verified a signed,
canonical decision certificate and its hash-linked authority chain, then atomically
committed the certificate, nonce, cumulative budgets, financial exposure, and pending
effect in SQLite. Ordinary logs do not satisfy this requirement.

The MVSG optimizer selects a mission-feasible graph only after an independent validator
recomputes graph, authority, resource, freshness, locality, ordering, redundancy, and deadline
obligations. Its validation certificate is deterministic evidence, not a proof of application
correctness.

The candidate does **not** prove application correctness, sensor truth, clinical
safety, hardware key protection, unbounded protocol correctness, causal recovery, or H5.
The TLA+ model treats cryptography ideally; byte-level cryptographic evidence and
model-checking evidence are deliberately kept separate.

See [the Phase 3 proof specification](docs/phase3/proof-carrying.md) and
[the Phase 4 MVSG specification](docs/phase4/mission-viable-service-graph.md).

## Required local environment

- Windows 10 or 11
- PowerShell 7.4 or newer (`pwsh`, not Windows PowerShell 5.1)
- Python 3.12
- `uv` (CI pins 0.11.33; the local version is captured in provenance)
- Git
- Java 17+ and Docker Desktop with WSL2 remain required for the Phase 1–2 regression
  gates, but the Phase 3 proof gate itself does not create containers or paid resources.

Install missing tools from an elevated PowerShell terminal if needed:

```powershell
winget install --id Microsoft.PowerShell -e
winget install --id astral-sh.uv -e
winget install --id Microsoft.OpenJDK.17 -e
```

Close and reopen VS Code, select a PowerShell 7 terminal, then run:

```powershell
Set-Location C:\Users\nares\OneDrive\Desktop\Prototype\EDGE-LIFELINE
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Get-ChildItem .\scripts -Recurse -File -Filter *.ps1 | Unblock-File
.\scripts\verify-prerequisites.ps1 | Format-Table -AutoSize
.\scripts\bootstrap.ps1
```

## Run the Phase 4 gate

```powershell
.\scripts\run_phase4_gate.ps1 -BenchmarkIterations 500 -OracleCases 30
```

The gate performs frozen dependency installation; formatting, lint, strict typing,
branch-aware coverage, and security-negative tests; CP-SAT versus brute-force oracle comparison;
timeout checks; byte-for-byte vector regeneration; an engineering-only optimizer/validator
benchmark; provenance capture; SBOM generation; and dependency auditing.

Evidence is written to `evidence/phase4/generated/<UTC timestamp>/`. A successful
automated run intentionally records `CONDITIONAL_PASS`, `phase4_complete: false`, and
`phase5_authorized: false` until independent review compares local and CI archives.
Benchmark values are raw engineering observations and are not acceptance thresholds or
manuscript outcomes.

## Preserve the local Phase 4 evidence archive

```powershell
$LatestEvidence = Get-ChildItem .\evidence\phase4\generated -Directory |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
$EvidenceZip = Join-Path (Split-Path $PWD -Parent) `
    "EDGE-LIFELINE-Phase4-Local-Evidence-$($LatestEvidence.Name).zip"
Compress-Archive -Path "$($LatestEvidence.FullName)\*" `
    -DestinationPath $EvidenceZip -Force
Get-FileHash $EvidenceZip -Algorithm SHA256
Get-Content (Join-Path $LatestEvidence.FullName 'gate-decision.json') -Raw
```

Push the candidate and retain the `phase4-validation-evidence` artifact from the
GitHub Actions `mission` job. Local and CI source manifests must resolve to the same
commit and every manifest entry must verify before Phase 4 can pass.

## Cleanup and rollback

Remove only reproducible Phase 4 generated state:

```powershell
Remove-Item .\evidence\phase4\generated -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\.venv -Recurse -Force -ErrorAction SilentlyContinue
```

Frozen vectors, source code, and evidence archives outside the repository are not
removed. To abandon the candidate, switch to the accepted Phase 3 commit on another
branch; do not reset or delete evidence that has already been cited.
