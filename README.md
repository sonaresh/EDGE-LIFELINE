# EDGE-LIFELINE

Proof-Carrying Degraded Autonomy and Causal Recovery for Mission-Critical
Cloud-Edge Systems.

Release **v0.2.0** is the Phase 2 candidate. It adds an executable typed-authority
model, deterministic Degraded Autonomy Envelope (DAE) contraction, bounded-time
validation, isolation and recovery state transitions, a distinct emergency branch,
runtime invariants, and a finite TLA+ model with seeded negative variants.

Phase 1 was independently accepted against local Windows and GitHub Actions evidence.
Phase 2 is not complete until its local and CI evidence are independently reviewed.
Phase 3 cryptographic lease issuance and verification remain deliberately unimplemented.

The hospital emergency-continuity case study is a synthetic systems-resilience
experiment. This is not a clinically validated medical system and must not be used
for patient care.

## Required local environment

- Windows 10 or 11
- PowerShell 7.4 or newer (`pwsh`, not Windows PowerShell 5.1)
- Python 3.12
- `uv` 0.11.33
- Microsoft OpenJDK 17 or another compatible Java 17+ runtime
- Docker Desktop with the WSL2 backend for the retained Phase 1 Compose gate
- Git

Install missing Phase 2 tools from an elevated PowerShell terminal if needed:

```powershell
winget install --id Microsoft.PowerShell -e
winget install --id astral-sh.uv -e
winget install --id Microsoft.OpenJDK.17 -e
```

Close and reopen VS Code, select a PowerShell 7 terminal, and verify:

```powershell
$PSVersionTable.PSVersion
.\scripts\verify-prerequisites.ps1 | Format-Table -AutoSize
```

Every row needed for the selected gate must report `AVAILABLE`.

## Bootstrap and quick runtime check

```powershell
Set-Location C:\Users\nares\OneDrive\Desktop\Prototype\EDGE-LIFELINE
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Get-ChildItem .\scripts -Recurse -File -Filter *.ps1 | Unblock-File
.\scripts\bootstrap.ps1

$Hazards = @{
    isolation = 100; clock = 100; data = 100; sensor = 100
    energy = 100; resource = 100; security = 100; identity = 100
    revocation = 100; physical = 100; financial = 100; human = 100
} | ConvertTo-Json -Compress
uv run edge-lifeline phase2-evaluate --hazards-json $Hazards
```

The diagnostic output must identify the profile as synthetic and nonclinical. It is
an executable model, not an authorization certificate.

## Run the Phase 2 gate

```powershell
.\scripts\run_phase2_gate.ps1
```

The first run downloads the official TLA+ v1.7.4 `tla2tools.jar` and verifies its
pinned SHA-256 before execution. The gate runs formatting, lint, strict type checks,
runtime tests with branch coverage, the positive TLC model, six expected-counterexample
models, provenance capture, SBOM generation, and dependency auditing.

Evidence is written to `evidence/phase2/generated/<UTC timestamp>/`. A successful
local run intentionally records `CONDITIONAL_PASS`, `phase2_complete: false`, and
`phase3_authorized: false` until local and CI archives receive independent review.

The TLC search may take several minutes depending on CPU and the worker count:

```powershell
.\scripts\run_phase2_gate.ps1 -TlcWorkers 4
```

## Preserve a local evidence archive

```powershell
$LatestEvidence = Get-ChildItem .\evidence\phase2\generated -Directory |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
$EvidenceZip = Join-Path (Split-Path $PWD -Parent) `
    "EDGE-LIFELINE-Phase2-Local-Evidence-$($LatestEvidence.Name).zip"
Compress-Archive -Path "$($LatestEvidence.FullName)\*" `
    -DestinationPath $EvidenceZip -Force
Get-FileHash $EvidenceZip -Algorithm SHA256
Get-Content (Join-Path $LatestEvidence.FullName 'gate-decision.json') -Raw
```

Push the candidate and retain the `phase2-validation-evidence` artifact from the
`formal` GitHub Actions job. Local and CI source manifests must resolve to the same
commit before Phase 2 can be accepted.

## Formal-model boundary

The TLA+ model treats hashes and signatures as ideal primitives. It verifies protocol
state properties, not Ed25519 or COSE bytes. The runtime model does not issue a signed
lease and its diagnostic JSON is not a proof. Calling Phase 2 output “proof-carrying
authorization” would therefore be scientifically misleading. That claim becomes
eligible for testing only after Phase 3 implements canonical serialization, signing,
verification, replay persistence, and negative cryptographic tests.

See [docs/phase2/formal-model.md](docs/phase2/formal-model.md) for the model scope,
invariant mapping, expected counterexamples, acceptance criteria, and limitations.

## Cleanup and rollback

Remove only reproducible Phase 2 generated state:

```powershell
Remove-Item .\.tools\tla2tools-1.7.4.jar -Force -ErrorAction SilentlyContinue
Remove-Item .\evidence\phase2\generated -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\.venv -Recurse -Force -ErrorAction SilentlyContinue
```

Source files and archived evidence outside the repository are unaffected. To abandon
the candidate without destructive Git operations, switch back to the accepted Phase 1
commit on a new branch.
