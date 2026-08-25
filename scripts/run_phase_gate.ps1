[CmdletBinding()]
param(
    [switch]$SkipContainers,
    [string]$CiRunUrl
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$EvidenceDir = Join-Path $RepoRoot "evidence/phase1/generated/$Stamp"
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$Transcript = Join-Path $EvidenceDir 'phase1-gate.log'
Start-Transcript -Path $Transcript | Out-Null

$GatePassed = $false
try {
    uv sync --frozen --all-groups
    uv run edge-lifeline source-manifest --root $RepoRoot --output (Join-Path $EvidenceDir 'source-manifest.json')
    $env:BUILD_REVISION = (Get-FileHash -Algorithm SHA256 (Join-Path $EvidenceDir 'source-manifest.json')).Hash.ToLowerInvariant()
    $env:BUILD_TIMESTAMP = (Get-Date).ToUniversalTime().ToString('o')
    $env:IMAGE_TAG = "phase1-v0.1.1-$($env:BUILD_REVISION.Substring(0, 12))"
    & (Join-Path $PSScriptRoot 'verify.ps1') -SkipContainers:$SkipContainers -EvidenceDir $EvidenceDir
    uv run edge-lifeline capture-provenance --root $RepoRoot --output (Join-Path $EvidenceDir 'provenance.json')
    uv run cyclonedx-py environment --output-format JSON --output-file (Join-Path $EvidenceDir 'sbom.cdx.json')
    $AuditCache = Join-Path ([IO.Path]::GetTempPath()) 'edge-lifeline-pip-audit'
    uv run pip-audit --local --cache-dir $AuditCache --progress-spinner off --format json --output (Join-Path $EvidenceDir 'dependency-audit.json')
    $GatePassed = $true
}
finally {
    try { Stop-Transcript | Out-Null } catch { Write-Warning 'Transcript could not be finalized.' }
    $CiEvidenceDeclared = -not [string]::IsNullOrWhiteSpace($CiRunUrl)
    $Phase1Complete = $false
    $Decision = @{
        schema_version = 'phase1-gate-v1'
        evaluated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        decision = if ($GatePassed) { 'CONDITIONAL_PASS' } else { 'FAIL' }
        code_gate_passed = $GatePassed
        compose_gate_passed = $GatePassed -and -not [bool]$SkipContainers
        ci_gate_passed = $false
        ci_evidence_declared = $CiEvidenceDeclared
        ci_run_url = if ($CiEvidenceDeclared) { $CiRunUrl } else { $null }
        external_review_required = $true
        phase1_complete = $Phase1Complete
        containers_skipped = [bool]$SkipContainers
        phase_2_authorized = $false
        note = if ($SkipContainers) { 'Code gate only; Compose smoke test remains required.' } elseif (-not $CiEvidenceDeclared) { 'Code and Compose gates completed; CI evidence and external review remain required.' } else { 'Code and Compose gates completed; declared CI evidence requires external verification.' }
    } | ConvertTo-Json -Depth 5
    Set-Content -Path (Join-Path $EvidenceDir 'gate-decision.json') -Value $Decision -Encoding utf8NoBOM
}

if ($GatePassed) {
    uv run edge-lifeline source-manifest --root $EvidenceDir --output (Join-Path $EvidenceDir 'evidence-manifest.json')
}

if (-not $GatePassed) {
    throw "Phase 1 gate failed. Evidence retained at $EvidenceDir"
}

Write-Host "Phase 1 gate evidence: $EvidenceDir"
