# EDGE-LIFELINE

Proof-Carrying Degraded Autonomy and Causal Recovery for Mission-Critical
Cloud-Edge Systems.

Release **v0.9.0** is the independently accepted research release. It packages the accepted
Phase 8 results into deterministic publication, reproducibility, traceability, checksum, and
archival artifacts.

All ten planned phases, Phase 0 through Phase 9, are complete. Phase 9 passed independent
Windows/Linux evidence review and was recorded at commit
`0ca92e3a7d2bc870033d7eaeaff80ac3b13de354`. The accepted implementation is tagged
[`v0.9.0`](https://github.com/sonaresh/EDGE-LIFELINE/tree/v0.9.0). Phase 9 did not rerun
or modify the accepted experiment.

## Accepted release evidence

| Item | Accepted value |
|---|---|
| Implementation commit | `d17ba0956d73cc301a4ded939293966843ea8af9` |
| External acceptance commit | `0ca92e3a7d2bc870033d7eaeaff80ac3b13de354` |
| Source archive SHA-256 | `6441ee2ddac5e97cf22bd7a3e0d5d8af2733f789308d3420ba0ac5cd54b4863a` |
| Local evidence SHA-256 | `d5fd742aaf1d4df96825e58edfe33133b8c5d50815f7e096f8687e1fc66e0279` |
| CI evidence SHA-256 | `82519c1a9d42f3f37342abdf18e7ebde11780dfa0d4f0c95d4f68309840a8048` |
| Tests | 392 complete, 159 security, 8 Phase 9 |
| Coverage | 94.77% lines, 85.61% branches |
| Supply chain | CycloneDX 1.6, 93 components, 0 known vulnerabilities |

See [release status](docs/release-status.md) for the phase-by-phase acceptance record.

The hospital emergency-continuity case study is a synthetic systems-resilience
experiment. This is not a clinically validated medical system and must not be used
for patient care.

## What causal recovery means in this release

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

The release does **not** prove application correctness, sensor truth, clinical
safety, hardware key protection, unbounded protocol correctness, or production reliability.
The TLA+ model treats cryptography ideally; byte-level cryptographic evidence and
model-checking evidence are deliberately kept separate.

See [the Phase 9 release specification](docs/phase9/README.md) and
[its limitations](docs/phase9/limitations.md).

## Required local environment

- Windows 10 or 11
- PowerShell 7.4 or newer (`pwsh`, not Windows PowerShell 5.1)
- Python 3.12
- `uv` (CI pins 0.11.33; the local version is captured in provenance)
- Git
- Java 17+ is required for the Phase 2 TLC gate. Docker Desktop with WSL2 is required for
  the Phase 1 Compose gate and Phase 7 k3d topology gate. No phase provisions paid cloud resources.

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

## Run the Phase 9 gate

```powershell
.\scripts\run_phase9_gate.ps1
```

The gate performs frozen dependency installation; formatting, lint, strict typing,
branch-aware coverage, security-negative tests, accepted-result linkage checks,
byte-for-byte publication-package reproduction, provenance capture, SBOM generation,
and dependency auditing.

Evidence is written to `evidence/phase9/generated/<UTC timestamp>/`. Automated runs intentionally
record `CONDITIONAL_PASS`; they cannot overwrite the independent `PASS` recorded in
`evidence/phase9/phase9-external-acceptance.json`.

## Preserve the local Phase 9 evidence archive

```powershell
$LatestEvidence = Get-ChildItem .\evidence\phase9\generated -Directory |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
$EvidenceZip = Join-Path (Split-Path $PWD -Parent) `
    "EDGE-LIFELINE-Phase9-Local-Evidence-$($LatestEvidence.Name).zip"
Compress-Archive -Path "$($LatestEvidence.FullName)\*" `
    -DestinationPath $EvidenceZip -Force
Get-FileHash $EvidenceZip -Algorithm SHA256
Get-Content (Join-Path $LatestEvidence.FullName 'gate-decision.json') -Raw
```

For a new reproduction, retain the `phase9-validation-evidence` artifact from the GitHub Actions
`release-packaging` job. The accepted review matched all 238 source entries and all 33 evidence
manifest entries per environment. The accepted CI run is
[35401455434](https://github.com/sonaresh/EDGE-LIFELINE/actions/runs/35401455434).

## Cleanup and rollback

Remove only reproducible Phase 9 generated state:

```powershell
Remove-Item .\evidence\phase9\generated -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\.venv -Recurse -Force -ErrorAction SilentlyContinue
```

Frozen vectors, source code, and evidence archives outside the repository are not
removed. To reproduce the accepted source, check out tag `v0.9.0` on another branch or worktree;
do not reset or delete evidence that has already been cited.
