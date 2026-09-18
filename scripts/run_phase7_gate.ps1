[CmdletBinding()]
param([string]$CiRunUrl)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$EvidenceDir = Join-Path $RepoRoot "evidence/phase7/generated/$Stamp"
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$Transcript = Join-Path $EvidenceDir 'phase7-gate.log'
Start-Transcript -Path $Transcript | Out-Null

$RuntimePassed = $false
$SecurityPassed = $false
$TopologyPassed = $false
$FaultsPassed = $false
$FixturePassed = $false
$EvidencePassed = $false
try {
    if ($PSVersionTable.PSVersion -lt [version]'7.4.0') {
        throw "PowerShell 7.4 or newer is required; found $($PSVersionTable.PSVersion)."
    }
    foreach ($Command in @('docker', 'kubectl')) {
        if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
            throw "Required Phase 7 command is unavailable: $Command"
        }
    }
    $Phase6Record = Get-Content `
        (Join-Path $RepoRoot 'evidence/phase6/phase6-external-acceptance.json') `
        -Raw | ConvertFrom-Json
    if ($Phase6Record.decision -ne 'PASS' -or -not [bool]$Phase6Record.phase7_authorized) {
        throw 'Accepted Phase 6 evidence does not authorize Phase 7.'
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
    uv run pytest tests/unit/orchestration tests/security/phase7 `
        --junitxml (Join-Path $EvidenceDir 'phase7-negative-tests-junit.xml')
    $SecurityPassed = $true

    uv run python -m scripts.validate_phase7_topology --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'topology-validation.json')
    $TopologyPassed = $true

    $GeneratedFixtures = Join-Path $EvidenceDir 'regenerated-vectors'
    uv run python -m scripts.generate_phase7_vectors --output-directory $GeneratedFixtures
    $FrozenFixtures = Join-Path $RepoRoot 'tests/vectors/phase7'
    foreach ($Frozen in Get-ChildItem -LiteralPath $FrozenFixtures -File) {
        $Regenerated = Join-Path $GeneratedFixtures $Frozen.Name
        if ((Get-FileHash $Frozen.FullName -Algorithm SHA256).Hash -ne `
            (Get-FileHash $Regenerated -Algorithm SHA256).Hash) {
            throw "Regenerated Phase 7 vector differs: $($Frozen.Name)"
        }
        Copy-Item -LiteralPath $Frozen.FullName -Destination $EvidenceDir
    }
    $FixturePassed = $true

    $K3dPath = (& (Join-Path $RepoRoot 'scripts/install-k3d.ps1') | Select-Object -Last 1)
    & (Join-Path $RepoRoot 'scripts/run_phase7_topology.ps1') `
        -EvidenceDir $EvidenceDir -K3dPath $K3dPath
    $FaultsPassed = $true

    Copy-Item (Join-Path $RepoRoot 'evidence/phase6/phase6-external-acceptance.json') `
        (Join-Path $EvidenceDir 'phase6-external-acceptance.json')
    Copy-Item (Join-Path $RepoRoot 'docs/phase7/limitations.md') `
        (Join-Path $EvidenceDir 'limitations.md')
    Copy-Item (Join-Path $RepoRoot 'docs/phase7/acceptance-map.md') `
        (Join-Path $EvidenceDir 'acceptance-map.md')
    Copy-Item (Join-Path $RepoRoot 'infra/k3d/fault-plan.yaml') `
        (Join-Path $EvidenceDir 'fault-plan.yaml')
    uv run edge-lifeline capture-provenance --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'provenance.json')
    uv run cyclonedx-py environment --output-format JSON --output-file `
        (Join-Path $EvidenceDir 'sbom.cdx.json')
    $AuditCache = Join-Path ([IO.Path]::GetTempPath()) 'edge-lifeline-phase7-pip-audit'
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
    $GatePassed = $RuntimePassed -and $SecurityPassed -and $TopologyPassed -and `
        $FaultsPassed -and $FixturePassed -and $EvidencePassed
    [ordered]@{
        schema_version = 'phase7-gate-v1'
        evaluated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        decision = if ($GatePassed) { 'CONDITIONAL_PASS' } else { 'FAIL' }
        runtime_gate_passed = $RuntimePassed
        security_negative_gate_passed = $SecurityPassed
        four_cluster_topology_passed = $TopologyPassed
        deterministic_faults_passed = $FaultsPassed
        deterministic_vectors_passed = $FixturePassed
        evidence_generation_passed = $EvidencePassed
        ci_evidence_declared = $CiDeclared
        ci_run_url = if ($CiDeclared) { $CiRunUrl } else { $null }
        external_review_required = $true
        phase7_complete = $false
        phase8_authorized = $false
        scientific_claim_status = if ($GatePassed) {
            'Local four-cluster orchestration mechanisms pass controlled tests.'
        } else { 'Phase 7 orchestration gate failed.' }
        note = 'Kubernetes readiness grants no authority; Phase 8 experiments remain locked.'
    } | ConvertTo-Json -Depth 6 | Set-Content `
        (Join-Path $EvidenceDir 'gate-decision.json') -Encoding utf8NoBOM
}

if ($RuntimePassed -and $SecurityPassed -and $TopologyPassed -and `
    $FaultsPassed -and $FixturePassed -and $EvidencePassed) {
    uv run edge-lifeline source-manifest --root $EvidenceDir --output `
        (Join-Path $EvidenceDir 'evidence-manifest.json')
}
else { throw "Phase 7 gate failed. Evidence retained at $EvidenceDir" }

Write-Host "Phase 7 gate evidence: $EvidenceDir"
