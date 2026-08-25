# EDGE-LIFELINE

Proof-Carrying Degraded Autonomy and Causal Recovery for Mission-Critical Cloud-Edge Systems.

This repository is currently limited to **Phase 1: reproducibility foundation**. It creates a minimal FastAPI process, a one-cloud/three-edge Docker Compose topology, deterministic run identifiers, provenance capture, CI, test gates, and cleanup commands. It does not yet implement authority leases, proof verification, the DAE, MVSG optimization, disconnected identity, trusted-time logic, causal reconciliation, experiments, or AWS deployment.

Release: **v0.1.1**, the reviewed Phase 1 foundation. Phase 1 remains conditional until the Compose and CI evidence are independently reviewed.

The hospital emergency-continuity case study is synthetic systems-resilience research. This is not a clinically validated medical system and must not be used for patient care.

## Required local environment

- Windows 11
- PowerShell 7
- Python 3.12
- `uv` 0.11.33
- Docker Desktop using the WSL2 backend for the Compose gate
- Git

Install `uv` from PowerShell if needed:

```powershell
winget install --id=astral-sh.uv -e
```

## Bootstrap

```powershell
Set-Location .\edge-lifeline
.\scripts\verify-prerequisites.ps1 | Format-Table -AutoSize
.\scripts\bootstrap.ps1
```

## Run the complete Phase 1 gate

Start Docker Desktop first, then run:

```powershell
.\scripts\run_phase_gate.ps1
```

The command runs linting, formatting checks, strict type checking, unit/integration/security tests, Compose validation, four-service smoke tests, provenance capture, SBOM generation, dependency auditing, complete source hashing, resolved base-image capture, and evidence-manifest creation. Evidence is written under `evidence/phase1/generated/<UTC timestamp>/`.

The script intentionally returns `CONDITIONAL_PASS`. A final Phase 1 pass requires independent review of the generated Compose evidence and a successful CI run. After pushing the repository, the workflow runs the same Phase 1 gate and publishes its evidence archive.

For exact replay after the first accepted run, set `PYTHON_IMAGE` to the captured `repository@sha256:digest` value before rerunning the gate.

To validate code on a host without Docker, use:

```powershell
.\scripts\run_phase_gate.ps1 -SkipContainers
```

That is a code-only gate and does not satisfy the Compose or CI acceptance criteria.

## Manual development mode

```powershell
docker compose up --build --detach --wait
Invoke-RestMethod http://127.0.0.1:18080/healthz
Invoke-RestMethod http://127.0.0.1:18081/healthz
Invoke-RestMethod http://127.0.0.1:18082/healthz
Invoke-RestMethod http://127.0.0.1:18083/healthz
docker compose down --volumes --remove-orphans
```

## Cleanup

```powershell
.\scripts\cleanup.ps1 -Confirm:$false
```

Cleanup removes only the named Phase 1 Compose runtime resources. Source files and evidence remain intact.

## Phase boundary

Phase 2 is not authorized by repository state. The Phase 1 gate records `phase_2_authorized: false` even when validation passes. Formal modeling begins only after explicit review and approval of the Phase 1 evidence.
