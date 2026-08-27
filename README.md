# EDGE-LIFELINE

Proof-Carrying Degraded Autonomy and Causal Recovery for Mission-Critical
Cloud-Edge Systems.

Release **v0.5.0** is the Phase 5 candidate. It adds bounded cached identity,
boot-aware authenticated time intervals, canonical policy-bundle hashing, and a pinned local
OPA/Rego enforcement boundary that fails safe on outage or mismatch.

Phase 4 was independently accepted against matching Windows and GitHub Actions evidence for
commit `6fb314effdc5e45145593bbdd582e19f60914d5f`. Phase 5 is not complete until its
own local and CI evidence are independently reviewed. Phase 6 is not authorized by an
automated gate.

The hospital emergency-continuity case study is a synthetic systems-resilience
experiment. This is not a clinically validated medical system and must not be used
for patient care.

## What identity, time, and policy mean in this candidate

A consequential decision is dispatchable only after the edge has verified a signed,
canonical decision certificate and its hash-linked authority chain, then atomically
committed the certificate, nonce, cumulative budgets, financial exposure, and pending
effect in SQLite. Ordinary logs do not satisfy this requirement.

Offline identity is usable only inside explicit cache, assurance, role, expiry, and
last-authenticated revocation-snapshot limits. The implementation does not claim that a
disconnected snapshot is current. Authority time comes from an authenticated UTC anchor plus
boot-aware elapsed time and drift bounds; the wall clock is diagnostic only. OPA decisions must
match the exact semantic policy hash and version.

The candidate does **not** prove application correctness, sensor truth, clinical
safety, hardware key protection, unbounded protocol correctness, causal recovery, or H5.
The TLA+ model treats cryptography ideally; byte-level cryptographic evidence and
model-checking evidence are deliberately kept separate.

See [the Phase 5 specification](docs/phase5/README.md) and
[its limitations](docs/phase5/limitations.md).

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

## Run the Phase 5 gate

```powershell
.\scripts\run_phase5_gate.ps1
```

The gate performs frozen dependency installation; formatting, lint, strict typing,
branch-aware coverage, security-negative tests, pinned OPA/Rego tests, byte-for-byte identity,
time, and policy fixture regeneration, provenance capture, SBOM generation, and dependency
auditing.

Evidence is written to `evidence/phase5/generated/<UTC timestamp>/`. A successful
automated run intentionally records `CONDITIONAL_PASS`, `phase5_complete: false`, and
`phase6_authorized: false` until independent review compares local and CI archives.

## Preserve the local Phase 5 evidence archive

```powershell
$LatestEvidence = Get-ChildItem .\evidence\phase5\generated -Directory |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
$EvidenceZip = Join-Path (Split-Path $PWD -Parent) `
    "EDGE-LIFELINE-Phase5-Local-Evidence-$($LatestEvidence.Name).zip"
Compress-Archive -Path "$($LatestEvidence.FullName)\*" `
    -DestinationPath $EvidenceZip -Force
Get-FileHash $EvidenceZip -Algorithm SHA256
Get-Content (Join-Path $LatestEvidence.FullName 'gate-decision.json') -Raw
```

Push the candidate and retain the `phase5-validation-evidence` artifact from the
GitHub Actions `identity-time-policy` job. Local and CI source manifests must resolve to the same
commit and every manifest entry must verify before Phase 4 can pass.

## Cleanup and rollback

Remove only reproducible Phase 5 generated state:

```powershell
Remove-Item .\evidence\phase5\generated -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\.venv -Recurse -Force -ErrorAction SilentlyContinue
```

Frozen vectors, source code, and evidence archives outside the repository are not
removed. To abandon the candidate, switch to the accepted Phase 4 commit on another
branch; do not reset or delete evidence that has already been cited.
