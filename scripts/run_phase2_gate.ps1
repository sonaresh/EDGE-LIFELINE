[CmdletBinding()]
param(
    [string]$CiRunUrl,
    [ValidateRange(1, 64)]
    [int]$TlcWorkers = 4
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$EvidenceDir = Join-Path $RepoRoot "evidence/phase2/generated/$Stamp"
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$Transcript = Join-Path $EvidenceDir 'phase2-gate.log'
Start-Transcript -Path $Transcript | Out-Null

$RuntimePassed = $false
$TlcPassed = $false
$EvidencePassed = $false
try {
    if ($PSVersionTable.PSVersion -lt [version]'7.4.0') {
        throw "PowerShell 7.4 or newer is required; found $($PSVersionTable.PSVersion)."
    }
    uv sync --frozen --all-groups
    uv run edge-lifeline source-manifest --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'source-manifest.json')
    uv run ruff check src tests
    uv run ruff format --check src tests
    uv run mypy src tests
    $JunitPath = Join-Path $EvidenceDir 'pytest-junit.xml'
    uv run pytest --junitxml $JunitPath `
        --cov=edge_lifeline --cov-branch `
        --cov-report "xml:$EvidenceDir/coverage.xml" `
        --cov-report term-missing
    $RuntimePassed = $true

    & (Join-Path $PSScriptRoot 'run-tlc.ps1') `
        -EvidenceDir $EvidenceDir `
        -Workers $TlcWorkers
    $TlcSummary = Get-Content (Join-Path $EvidenceDir 'tlc-summary.json') -Raw | ConvertFrom-Json
    $TlcPassed = [bool]$TlcSummary.positive_passed -and `
        [bool]$TlcSummary.negative_counterexamples_passed
    if (-not $TlcPassed) {
        throw 'TLC acceptance checks did not pass.'
    }

    Copy-Item -LiteralPath (Join-Path $RepoRoot 'formal/runtime-invariant-map.json') `
        -Destination (Join-Path $EvidenceDir 'runtime-invariant-map.json')
    uv run edge-lifeline capture-provenance --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'provenance.json')
    uv run cyclonedx-py environment --output-format JSON --output-file `
        (Join-Path $EvidenceDir 'sbom.cdx.json')
    $AuditCache = Join-Path ([IO.Path]::GetTempPath()) 'edge-lifeline-phase2-pip-audit'
    uv run pip-audit --local --cache-dir $AuditCache --progress-spinner off `
        --format json --output (Join-Path $EvidenceDir 'dependency-audit.json')
    $EvidencePassed = $true
}
finally {
    try { Stop-Transcript | Out-Null } catch { Write-Warning 'Transcript could not be finalized.' }
    $CiDeclared = -not [string]::IsNullOrWhiteSpace($CiRunUrl)
    $GatePassed = $RuntimePassed -and $TlcPassed -and $EvidencePassed
    $Decision = [ordered]@{
        schema_version = 'phase2-gate-v1'
        evaluated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        decision = if ($GatePassed) { 'CONDITIONAL_PASS' } else { 'FAIL' }
        runtime_gate_passed = $RuntimePassed
        tlc_positive_passed = $TlcPassed
        negative_counterexamples_passed = $TlcPassed
        evidence_generation_passed = $EvidencePassed
        ci_evidence_declared = $CiDeclared
        ci_run_url = if ($CiDeclared) { $CiRunUrl } else { $null }
        external_review_required = $true
        phase2_complete = $false
        phase3_authorized = $false
        note = if ($GatePassed) {
            'Runtime and TLC gates passed; independent evidence review remains required.'
        }
        else {
            'At least one Phase 2 runtime or formal-model gate failed.'
        }
    }
    $Decision | ConvertTo-Json -Depth 6 | Set-Content `
        -LiteralPath (Join-Path $EvidenceDir 'gate-decision.json') `
        -Encoding utf8NoBOM
}

if ($RuntimePassed -and $TlcPassed -and $EvidencePassed) {
    uv run edge-lifeline source-manifest --root $EvidenceDir --output `
        (Join-Path $EvidenceDir 'evidence-manifest.json')
}
else {
    throw "Phase 2 gate failed. Evidence retained at $EvidenceDir"
}

Write-Host "Phase 2 gate evidence: $EvidenceDir"
