[CmdletBinding()]
param([string]$CiRunUrl)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$EvidenceDir = Join-Path $RepoRoot "evidence/phase8/generated/$Stamp"
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$Transcript = Join-Path $EvidenceDir 'phase8-gate.log'
Start-Transcript -Path $Transcript | Out-Null

$RuntimePassed = $false
$SecurityPassed = $false
$ProtocolPassed = $false
$FactorialPassed = $false
$ReproductionPassed = $false
$StatisticsPassed = $false
$PerformancePassed = $false
$EvidencePassed = $false
try {
    if ($PSVersionTable.PSVersion -lt [version]'7.4.0') {
        throw "PowerShell 7.4 or newer is required; found $($PSVersionTable.PSVersion)."
    }
    $Phase7Record = Get-Content `
        (Join-Path $RepoRoot 'evidence/phase7/phase7-external-acceptance.json') `
        -Raw | ConvertFrom-Json
    if ($Phase7Record.decision -ne 'PASS' -or -not [bool]$Phase7Record.phase8_authorized) {
        throw 'Accepted Phase 7 evidence does not authorize Phase 8.'
    }

    uv sync --frozen --all-groups
    uv run edge-lifeline source-manifest --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'source-manifest.json')
    uv run ruff check src tests scripts
    uv run ruff format --check src tests scripts
    uv run mypy src tests scripts
    uv run pytest --junitxml (Join-Path $EvidenceDir 'pytest-junit.xml') `
        --cov=edge_lifeline --cov-branch `
        --cov-report "xml:$EvidenceDir/coverage.xml" --cov-report term-missing
    $RuntimePassed = $true

    uv run pytest -m security --junitxml `
        (Join-Path $EvidenceDir 'security-tests-junit.xml')
    uv run pytest tests/unit/experiments tests/security/phase8 `
        --junitxml (Join-Path $EvidenceDir 'phase8-negative-tests-junit.xml')
    $SecurityPassed = $true

    $Protocol = Get-Content (Join-Path $RepoRoot 'experiments/phase8/protocol.json') `
        -Raw | ConvertFrom-Json
    if ($Protocol.stage -ne 'final' -or -not [bool]$Protocol.analysis_frozen_before_final_run) {
        throw 'Phase 8 final protocol is not frozen.'
    }
    if (@($Protocol.seeds).Count -lt 10 -or @($Protocol.scenarios).Count -ne 20 -or `
        @($Protocol.methods).Count -ne 8) {
        throw 'Phase 8 protocol does not declare the complete factorial design.'
    }
    $ProtocolPassed = $true

    $First = Join-Path $EvidenceDir 'experiment-first'
    $Second = Join-Path $EvidenceDir 'experiment-second'
    uv run python -m scripts.run_phase8_experiments --root $RepoRoot --output $First
    uv run python -m scripts.run_phase8_experiments --root $RepoRoot --output $Second
    $FirstManifest = Get-Content (Join-Path $First 'run-manifest.json') -Raw | ConvertFrom-Json
    if ($FirstManifest.run_count -ne 1600 -or $FirstManifest.trace_count -ne 200 -or `
        $FirstManifest.excluded_runs -ne 0 -or $FirstManifest.failed_infrastructure_runs -ne 0) {
        throw 'Phase 8 paired factorial is incomplete.'
    }
    $FactorialPassed = $true
    foreach ($Name in @('raw-results.csv', 'analysis.json', 'run-manifest.json', `
        'protocol.json', 'oracle.json', 'exclusions.json')) {
        $FirstHash = (Get-FileHash (Join-Path $First $Name) -Algorithm SHA256).Hash
        $SecondHash = (Get-FileHash (Join-Path $Second $Name) -Algorithm SHA256).Hash
        if ($FirstHash -ne $SecondHash) { throw "Phase 8 reproduction differs: $Name" }
    }
    $ReproductionPassed = $true
    $Analysis = Get-Content (Join-Path $First 'analysis.json') -Raw | ConvertFrom-Json
    if ($Analysis.run_count -ne 1600 -or @($Analysis.primary_comparisons).Count -ne 8 -or `
        $Analysis.multiplicity_control -ne 'Holm') {
        throw 'Phase 8 statistical analysis is incomplete.'
    }
    $StatisticsPassed = $true
    Copy-Item (Join-Path $First '*') $EvidenceDir -Force

    $RegeneratedVector = Join-Path $EvidenceDir 'regenerated-experiment-digest-v1.json'
    uv run python -m scripts.generate_phase8_vector --root $RepoRoot --output $RegeneratedVector
    $FrozenVector = Join-Path $RepoRoot 'tests/vectors/phase8/experiment-digest-v1.json'
    if ((Get-FileHash $FrozenVector -Algorithm SHA256).Hash -ne `
        (Get-FileHash $RegeneratedVector -Algorithm SHA256).Hash) {
        throw 'Regenerated Phase 8 digest vector differs.'
    }
    Copy-Item $FrozenVector (Join-Path $EvidenceDir 'experiment-digest-v1.json')

    uv run python -m scripts.benchmark_phase8 --output `
        (Join-Path $EvidenceDir 'performance.json') --iterations 1000 --warmup 100
    $PerformancePassed = $true

    Copy-Item (Join-Path $RepoRoot 'evidence/phase7/phase7-external-acceptance.json') `
        (Join-Path $EvidenceDir 'phase7-external-acceptance.json')
    Copy-Item (Join-Path $RepoRoot 'docs/phase8/limitations.md') `
        (Join-Path $EvidenceDir 'limitations.md')
    Copy-Item (Join-Path $RepoRoot 'docs/phase8/acceptance-map.md') `
        (Join-Path $EvidenceDir 'acceptance-map.md')
    uv run edge-lifeline capture-provenance --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'provenance.json')
    uv run cyclonedx-py environment --output-format JSON --output-file `
        (Join-Path $EvidenceDir 'sbom.cdx.json')
    $AuditCache = Join-Path ([IO.Path]::GetTempPath()) 'edge-lifeline-phase8-pip-audit'
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
    $GatePassed = $RuntimePassed -and $SecurityPassed -and $ProtocolPassed -and `
        $FactorialPassed -and $ReproductionPassed -and $StatisticsPassed -and `
        $PerformancePassed -and $EvidencePassed
    [ordered]@{
        schema_version = 'phase8-gate-v1'
        evaluated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        decision = if ($GatePassed) { 'CONDITIONAL_PASS' } else { 'FAIL' }
        runtime_gate_passed = $RuntimePassed
        security_negative_gate_passed = $SecurityPassed
        frozen_protocol_passed = $ProtocolPassed
        paired_factorial_passed = $FactorialPassed
        deterministic_reproduction_passed = $ReproductionPassed
        statistical_analysis_passed = $StatisticsPassed
        performance_measurement_passed = $PerformancePassed
        evidence_generation_passed = $EvidencePassed
        hypothesis_favorability_required_for_gate = $false
        ci_evidence_declared = $CiDeclared
        ci_run_url = if ($CiDeclared) { $CiRunUrl } else { $null }
        external_review_required = $true
        phase8_complete = $false
        phase9_authorized = $false
        scientific_claim_status = if ($GatePassed) {
            'Frozen synthetic experiment completed reproducibly; outcomes require external review.'
        } else { 'Phase 8 experiment gate failed.' }
        note = 'Synthetic nonclinical evidence only; Phase 9 packaging remains locked.'
    } | ConvertTo-Json -Depth 6 | Set-Content `
        (Join-Path $EvidenceDir 'gate-decision.json') -Encoding utf8NoBOM
}

if ($RuntimePassed -and $SecurityPassed -and $ProtocolPassed -and `
    $FactorialPassed -and $ReproductionPassed -and $StatisticsPassed -and `
    $PerformancePassed -and $EvidencePassed) {
    uv run edge-lifeline source-manifest --root $EvidenceDir --output `
        (Join-Path $EvidenceDir 'evidence-manifest.json')
}
else { throw "Phase 8 gate failed. Evidence retained at $EvidenceDir" }

Write-Host "Phase 8 gate evidence: $EvidenceDir"
