# EDGE-LIFELINE

Proof-Carrying Degraded Autonomy and Causal Recovery for Mission-Critical
Cloud-Edge Systems.

Release **v0.8.0** is the Phase 8 candidate. It adds the preregistered paired-factorial
synthetic evaluation, independent oracle, deterministic statistical analysis, and H4 benchmark.

Phase 7 was independently accepted and recorded at commit
`7a4e99bac496b66943c7cb573f3ec07cf50541db`. Phase 8 is not complete until its own local and
CI evidence are independently reviewed. Phase 9 packaging is not authorized by an automated gate.

The hospital emergency-continuity case study is a synthetic systems-resilience
experiment. This is not a clinically validated medical system and must not be used
for patient care.

## What causal recovery means in this candidate

A consequential decision is dispatchable only after the edge has verified a signed,
canonical decision certificate and its hash-linked authority chain, then atomically
committed the certificate, nonce, cumulative budgets, financial exposure, and pending
effect in SQLite. Ordinary logs do not satisfy this requirement.

An imported event is accepted only after its canonical signature, authorized edge identity,
isolation epoch, lease and decision references, causal parents, sequence, vector clock, schema,
and registered safety class verify. Invalid event subtrees are quarantined. S2 compensation is a
new event, S3 conflicts require review, and S4 effects are never dispatched by reconciliation.
Connectivity restoration and signed receipts do not restore authority; a fresh connected-epoch
lease is mandatory.

The candidate does **not** prove application correctness, sensor truth, clinical
safety, hardware key protection, unbounded protocol correctness, or production reliability.
The TLA+ model treats cryptography ideally; byte-level cryptographic evidence and
model-checking evidence are deliberately kept separate.

See [the Phase 8 protocol](docs/phase8/README.md) and
[its limitations](docs/phase8/limitations.md).

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

## Run the Phase 8 gate

```powershell
.\scripts\run_phase8_gate.ps1
```

The gate performs frozen dependency installation; formatting, lint, strict typing,
branch-aware coverage, security-negative tests, byte-for-byte event/recovery vector regeneration,
provenance capture, SBOM generation, and dependency auditing.

Evidence is written to `evidence/phase8/generated/<UTC timestamp>/`. A successful
automated run intentionally records `CONDITIONAL_PASS`, `phase8_complete: false`, and
`phase9_authorized: false` until independent review compares local and CI archives.

## Preserve the local Phase 7 evidence archive

```powershell
$LatestEvidence = Get-ChildItem .\evidence\phase7\generated -Directory |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
$EvidenceZip = Join-Path (Split-Path $PWD -Parent) `
    "EDGE-LIFELINE-Phase7-Local-Evidence-$($LatestEvidence.Name).zip"
Compress-Archive -Path "$($LatestEvidence.FullName)\*" `
    -DestinationPath $EvidenceZip -Force
Get-FileHash $EvidenceZip -Algorithm SHA256
Get-Content (Join-Path $LatestEvidence.FullName 'gate-decision.json') -Raw
```

Push the candidate and retain the `phase7-validation-evidence` artifact from the
GitHub Actions `orchestration` job. Local and CI source manifests must resolve to the same
commit and every manifest entry must verify before Phase 8 can be authorized.

## Cleanup and rollback

Remove only reproducible Phase 7 generated state:

```powershell
Remove-Item .\evidence\phase7\generated -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\.venv -Recurse -Force -ErrorAction SilentlyContinue
```

Frozen vectors, source code, and evidence archives outside the repository are not
removed. To abandon the candidate, switch to the accepted Phase 5 commit on another
branch; do not reset or delete evidence that has already been cited.
