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
$EvidenceDir = Join-Path $RepoRoot "evidence/phase5/generated/$Stamp"
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$Transcript = Join-Path $EvidenceDir 'phase5-gate.log'
Start-Transcript -Path $Transcript | Out-Null

$RuntimePassed = $false
$SecurityPassed = $false
$OpaPassed = $false
$FixturePassed = $false
$EvidencePassed = $false
try {
    if ($PSVersionTable.PSVersion -lt [version]'7.4.0') {
        throw "PowerShell 7.4 or newer is required; found $($PSVersionTable.PSVersion)."
    }
    $Phase4Record = Get-Content `
        (Join-Path $RepoRoot 'evidence/phase4/phase4-external-acceptance.json') `
        -Raw | ConvertFrom-Json
    if ($Phase4Record.decision -ne 'PASS' -or -not [bool]$Phase4Record.phase5_authorized) {
        throw 'Accepted Phase 4 evidence does not authorize Phase 5.'
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
        tests/security/phase5 `
        tests/security/policy `
        tests/integration/test_phase5_admission.py `
        --junitxml (Join-Path $EvidenceDir 'phase5-negative-tests-junit.xml')
    $SecurityPassed = $true

    $OpaPath = (& (Join-Path $PSScriptRoot 'install-opa.ps1') | Select-Object -Last 1).Trim()
    (& $OpaPath version 2>&1 | Out-String) | Set-Content `
        -LiteralPath (Join-Path $EvidenceDir 'opa-version.txt') `
        -Encoding utf8NoBOM
    $OpaReport = (& $OpaPath test policy/rego --fail-on-empty --format json 2>&1 | Out-String)
    $OpaReport | Set-Content `
        -LiteralPath (Join-Path $EvidenceDir 'opa-tests.json') `
        -Encoding utf8NoBOM
    $OpaPassed = $true

    $GeneratedFixtures = Join-Path $EvidenceDir 'regenerated-fixtures'
    uv run python -m scripts.generate_phase5_fixtures `
        --output-directory $GeneratedFixtures `
        --repo-root $RepoRoot
    $FrozenFixtures = Join-Path $RepoRoot 'tests/vectors/phase5'
    foreach ($Frozen in Get-ChildItem -LiteralPath $FrozenFixtures -File) {
        $Regenerated = Join-Path $GeneratedFixtures $Frozen.Name
        if (-not (Test-Path -LiteralPath $Regenerated)) {
            throw "Regenerated Phase 5 fixture is missing: $($Frozen.Name)"
        }
        $FrozenHash = (Get-FileHash -LiteralPath $Frozen.FullName -Algorithm SHA256).Hash
        $RegeneratedHash = (Get-FileHash -LiteralPath $Regenerated -Algorithm SHA256).Hash
        if ($FrozenHash -ne $RegeneratedHash) {
            throw "Regenerated Phase 5 fixture differs: $($Frozen.Name)"
        }
        Copy-Item -LiteralPath $Frozen.FullName -Destination $EvidenceDir
    }
    $FixturePassed = $true

    Copy-Item `
        (Join-Path $RepoRoot 'evidence/phase4/phase4-external-acceptance.json') `
        (Join-Path $EvidenceDir 'phase4-external-acceptance.json')
    Copy-Item `
        (Join-Path $RepoRoot 'docs/phase5/limitations.md') `
        (Join-Path $EvidenceDir 'limitations.md')
    Copy-Item `
        (Join-Path $RepoRoot 'docs/phase5/acceptance-map.md') `
        (Join-Path $EvidenceDir 'acceptance-map.md')
    uv run edge-lifeline capture-provenance --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'provenance.json')
    uv run cyclonedx-py environment --output-format JSON --output-file `
        (Join-Path $EvidenceDir 'sbom.cdx.json')
    $AuditCache = Join-Path ([IO.Path]::GetTempPath()) 'edge-lifeline-phase5-pip-audit'
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
    $GatePassed = $RuntimePassed -and $SecurityPassed -and $OpaPassed -and `
        $FixturePassed -and $EvidencePassed
    $Decision = [ordered]@{
        schema_version = 'phase5-gate-v1'
        evaluated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        decision = if ($GatePassed) { 'CONDITIONAL_PASS' } else { 'FAIL' }
        runtime_gate_passed = $RuntimePassed
        security_negative_gate_passed = $SecurityPassed
        opa_tests_passed = $OpaPassed
        deterministic_fixtures_passed = $FixturePassed
        evidence_generation_passed = $EvidencePassed
        ci_evidence_declared = $CiDeclared
        ci_run_url = if ($CiDeclared) { $CiRunUrl } else { $null }
        external_review_required = $true
        phase5_complete = $false
        phase6_authorized = $false
        scientific_claim_status = if ($GatePassed) {
            'Identity, bounded-time, and pinned-policy mechanisms pass synthetic nonclinical tests.'
        } else {
            'Phase 5 identity/time/policy mechanism gate failed.'
        }
        note = if ($GatePassed) {
            'Offline revocation exposure remains explicitly bounded; current revocation is not claimed.'
        } else {
            'At least one Phase 5 gate failed.'
        }
    }
    $Decision | ConvertTo-Json -Depth 6 | Set-Content `
        -LiteralPath (Join-Path $EvidenceDir 'gate-decision.json') `
        -Encoding utf8NoBOM
}

if ($RuntimePassed -and $SecurityPassed -and $OpaPassed -and `
    $FixturePassed -and $EvidencePassed) {
    uv run edge-lifeline source-manifest --root $EvidenceDir --output `
        (Join-Path $EvidenceDir 'evidence-manifest.json')
}
else {
    throw "Phase 5 gate failed. Evidence retained at $EvidenceDir"
}

Write-Host "Phase 5 gate evidence: $EvidenceDir"
