[CmdletBinding()]
param(
    [string]$CiRunUrl
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$EvidenceDir = Join-Path $RepoRoot "evidence/phase6/generated/$Stamp"
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$Transcript = Join-Path $EvidenceDir 'phase6-gate.log'
Start-Transcript -Path $Transcript | Out-Null

$RuntimePassed = $false
$SecurityPassed = $false
$DagPassed = $false
$FixturePassed = $false
$EvidencePassed = $false
try {
    if ($PSVersionTable.PSVersion -lt [version]'7.4.0') {
        throw "PowerShell 7.4 or newer is required; found $($PSVersionTable.PSVersion)."
    }
    $Phase5Record = Get-Content `
        (Join-Path $RepoRoot 'evidence/phase5/phase5-external-acceptance.json') `
        -Raw | ConvertFrom-Json
    if ($Phase5Record.decision -ne 'PASS' -or -not [bool]$Phase5Record.phase6_authorized) {
        throw 'Accepted Phase 5 evidence does not authorize Phase 6.'
    }

    uv sync --frozen --all-groups
    uv run edge-lifeline source-manifest --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'source-manifest.json')
    uv run ruff check src tests scripts
    uv run ruff format --check src tests scripts
    uv run mypy src tests scripts
    uv run pytest --junitxml (Join-Path $EvidenceDir 'pytest-junit.xml') `
        --cov=edge_lifeline --cov-branch `
        --cov-report "xml:$EvidenceDir/coverage.xml" `
        --cov-report term-missing
    $RuntimePassed = $true

    uv run pytest -m security --junitxml `
        (Join-Path $EvidenceDir 'security-tests-junit.xml')
    uv run pytest `
        tests/unit/ledger `
        tests/unit/reconcile `
        tests/security/phase6 `
        tests/integration/test_phase6_reconciliation.py `
        --junitxml (Join-Path $EvidenceDir 'phase6-negative-tests-junit.xml')
    $SecurityPassed = $true
    $DagPassed = $true

    $GeneratedFixtures = Join-Path $EvidenceDir 'regenerated-vectors'
    uv run python -m scripts.generate_phase6_vectors `
        --output-directory $GeneratedFixtures
    $FrozenFixtures = Join-Path $RepoRoot 'tests/vectors/phase6'
    foreach ($Frozen in Get-ChildItem -LiteralPath $FrozenFixtures -File) {
        $Regenerated = Join-Path $GeneratedFixtures $Frozen.Name
        if (-not (Test-Path -LiteralPath $Regenerated)) {
            throw "Regenerated Phase 6 vector is missing: $($Frozen.Name)"
        }
        $FrozenHash = (Get-FileHash -LiteralPath $Frozen.FullName -Algorithm SHA256).Hash
        $RegeneratedHash = (Get-FileHash -LiteralPath $Regenerated -Algorithm SHA256).Hash
        if ($FrozenHash -ne $RegeneratedHash) {
            throw "Regenerated Phase 6 vector differs: $($Frozen.Name)"
        }
        Copy-Item -LiteralPath $Frozen.FullName -Destination $EvidenceDir
    }
    $FixturePassed = $true

    Copy-Item `
        (Join-Path $RepoRoot 'evidence/phase5/phase5-external-acceptance.json') `
        (Join-Path $EvidenceDir 'phase5-external-acceptance.json')
    Copy-Item `
        (Join-Path $RepoRoot 'docs/phase6/limitations.md') `
        (Join-Path $EvidenceDir 'limitations.md')
    Copy-Item `
        (Join-Path $RepoRoot 'docs/phase6/acceptance-map.md') `
        (Join-Path $EvidenceDir 'acceptance-map.md')
    uv run edge-lifeline capture-provenance --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'provenance.json')
    uv run cyclonedx-py environment --output-format JSON --output-file `
        (Join-Path $EvidenceDir 'sbom.cdx.json')
    $AuditCache = Join-Path ([IO.Path]::GetTempPath()) 'edge-lifeline-phase6-pip-audit'
    $AuditPython = (uv run python -c 'import sys; print(sys.executable)').Trim()
    $env:PIPAPI_PYTHON_LOCATION = $AuditPython
    uv run pip-audit --local --cache-dir $AuditCache --progress-spinner off `
        --format json --output (Join-Path $EvidenceDir 'dependency-audit.json')
    Remove-Item Env:PIPAPI_PYTHON_LOCATION -ErrorAction SilentlyContinue
    $EvidencePassed = $true
}
finally {
    Remove-Item Env:PIPAPI_PYTHON_LOCATION -ErrorAction SilentlyContinue
    try { Stop-Transcript | Out-Null } catch { Write-Warning 'Transcript could not be finalized.' }
    $CiDeclared = -not [string]::IsNullOrWhiteSpace($CiRunUrl)
    $GatePassed = $RuntimePassed -and $SecurityPassed -and $DagPassed -and `
        $FixturePassed -and $EvidencePassed
    $Decision = [ordered]@{
        schema_version = 'phase6-gate-v1'
        evaluated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        decision = if ($GatePassed) { 'CONDITIONAL_PASS' } else { 'FAIL' }
        runtime_gate_passed = $RuntimePassed
        security_negative_gate_passed = $SecurityPassed
        causal_dag_gate_passed = $DagPassed
        deterministic_vectors_passed = $FixturePassed
        evidence_generation_passed = $EvidencePassed
        ci_evidence_declared = $CiDeclared
        ci_run_url = if ($CiDeclared) { $CiRunUrl } else { $null }
        external_review_required = $true
        phase6_complete = $false
        phase7_authorized = $false
        scientific_claim_status = if ($GatePassed) {
            'Causal-ledger and class-specific reconciliation mechanisms pass synthetic tests.'
        } else {
            'Phase 6 causal-ledger or reconciliation gate failed.'
        }
        note = if ($GatePassed) {
            'Reconciliation grants no authority and dispatches no irreversible effect.'
        } else {
            'At least one Phase 6 gate failed.'
        }
    }
    $Decision | ConvertTo-Json -Depth 6 | Set-Content `
        -LiteralPath (Join-Path $EvidenceDir 'gate-decision.json') `
        -Encoding utf8NoBOM
}

if ($RuntimePassed -and $SecurityPassed -and $DagPassed -and `
    $FixturePassed -and $EvidencePassed) {
    uv run edge-lifeline source-manifest --root $EvidenceDir --output `
        (Join-Path $EvidenceDir 'evidence-manifest.json')
}
else {
    throw "Phase 6 gate failed. Evidence retained at $EvidenceDir"
}

Write-Host "Phase 6 gate evidence: $EvidenceDir"
