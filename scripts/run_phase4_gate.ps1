[CmdletBinding()]
param(
    [string]$CiRunUrl,
    [ValidateRange(1, 10000)]
    [int]$BenchmarkIterations = 500,
    [ValidateRange(1, 1000)]
    [int]$OracleCases = 30
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$EvidenceDir = Join-Path $RepoRoot "evidence/phase4/generated/$Stamp"
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$Transcript = Join-Path $EvidenceDir 'phase4-gate.log'
Start-Transcript -Path $Transcript | Out-Null

$RuntimePassed = $false
$OraclePassed = $false
$VectorPassed = $false
$SecurityPassed = $false
$TimeoutPassed = $false
$EvidencePassed = $false
try {
    if ($PSVersionTable.PSVersion -lt [version]'7.4.0') {
        throw "PowerShell 7.4 or newer is required; found $($PSVersionTable.PSVersion)."
    }
    $Phase3Record = Get-Content `
        (Join-Path $RepoRoot 'evidence/phase3/phase3-external-acceptance.json') `
        -Raw | ConvertFrom-Json
    if ($Phase3Record.decision -ne 'PASS' -or -not [bool]$Phase3Record.phase4_authorized) {
        throw 'Accepted Phase 3 evidence does not authorize Phase 4.'
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
    $SecurityPassed = $true

    uv run python -m scripts.validate_phase4_oracle `
        --cases $OracleCases `
        --output (Join-Path $EvidenceDir 'oracle-conformance.json')
    $OracleReport = Get-Content `
        (Join-Path $EvidenceDir 'oracle-conformance.json') -Raw | ConvertFrom-Json
    if (-not [bool]$OracleReport.all_passed) {
        throw 'CP-SAT does not match the independent brute-force oracle.'
    }
    $OraclePassed = $true

    $GeneratedVector = Join-Path $EvidenceDir 'hospital-mvsg-v1.regenerated.json'
    uv run python scripts/generate_phase4_vectors.py --output $GeneratedVector
    $FrozenVector = Join-Path $RepoRoot 'tests/vectors/phase4/hospital-mvsg-v1.json'
    if ((Get-FileHash $FrozenVector -Algorithm SHA256).Hash -ne `
        (Get-FileHash $GeneratedVector -Algorithm SHA256).Hash) {
        throw 'Regenerated MVSG vector differs from the frozen vector.'
    }
    Copy-Item $FrozenVector (Join-Path $EvidenceDir 'hospital-mvsg-v1.json')
    $VectorPassed = $true

    uv run pytest `
        tests/unit/mission/test_optimizer.py::test_zero_timeout_fails_safe_without_prior_plan `
        tests/unit/mission/test_optimizer.py::test_invalid_previous_plan_is_not_used_as_timeout_fallback `
        tests/unit/mission/test_optimizer.py::test_resource_infeasibility_fails_safe `
        --junitxml (Join-Path $EvidenceDir 'timeout-safety-junit.xml')
    $TimeoutPassed = $true

    uv run python -m scripts.benchmark_phase4 `
        --iterations $BenchmarkIterations `
        --output (Join-Path $EvidenceDir 'mvsg-benchmark.json')
    Copy-Item `
        (Join-Path $RepoRoot 'evidence/phase3/phase3-external-acceptance.json') `
        (Join-Path $EvidenceDir 'phase3-external-acceptance.json')
    uv run edge-lifeline capture-provenance --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'provenance.json')
    uv run cyclonedx-py environment --output-format JSON --output-file `
        (Join-Path $EvidenceDir 'sbom.cdx.json')
    $AuditCache = Join-Path ([IO.Path]::GetTempPath()) 'edge-lifeline-phase4-pip-audit'
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
    $GatePassed = $RuntimePassed -and $OraclePassed -and $VectorPassed -and `
        $SecurityPassed -and $TimeoutPassed -and $EvidencePassed
    $Decision = [ordered]@{
        schema_version = 'phase4-gate-v1'
        evaluated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        decision = if ($GatePassed) { 'CONDITIONAL_PASS' } else { 'FAIL' }
        runtime_gate_passed = $RuntimePassed
        solver_oracle_gate_passed = $OraclePassed
        frozen_vector_gate_passed = $VectorPassed
        security_negative_gate_passed = $SecurityPassed
        timeout_safe_behavior_passed = $TimeoutPassed
        evidence_generation_passed = $EvidencePassed
        ci_evidence_declared = $CiDeclared
        ci_run_url = if ($CiDeclared) { $CiRunUrl } else { $null }
        external_review_required = $true
        phase4_complete = $false
        phase5_authorized = $false
        scientific_claim_status = if ($GatePassed) {
            'MVSG mechanism validated in synthetic engineering fixtures; H5 outcomes remain untested.'
        } else {
            'MVSG mechanism gate failed.'
        }
        note = if ($GatePassed) {
            'CP-SAT, independent validator, brute-force oracle, timeout safety, and evidence gates passed.'
        } else {
            'At least one Phase 4 gate failed.'
        }
    }
    $Decision | ConvertTo-Json -Depth 6 | Set-Content `
        -LiteralPath (Join-Path $EvidenceDir 'gate-decision.json') `
        -Encoding utf8NoBOM
}

if ($RuntimePassed -and $OraclePassed -and $VectorPassed -and `
    $SecurityPassed -and $TimeoutPassed -and $EvidencePassed) {
    uv run edge-lifeline source-manifest --root $EvidenceDir --output `
        (Join-Path $EvidenceDir 'evidence-manifest.json')
}
else {
    throw "Phase 4 gate failed. Evidence retained at $EvidenceDir"
}

Write-Host "Phase 4 gate evidence: $EvidenceDir"
