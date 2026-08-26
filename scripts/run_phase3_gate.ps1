[CmdletBinding()]
param(
    [string]$CiRunUrl,
    [ValidateRange(1, 100000)]
    [int]$BenchmarkIterations = 1000
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$EvidenceDir = Join-Path $RepoRoot "evidence/phase3/generated/$Stamp"
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$Transcript = Join-Path $EvidenceDir 'phase3-gate.log'
Start-Transcript -Path $Transcript | Out-Null

$RuntimePassed = $false
$VectorPassed = $false
$SecurityPassed = $false
$EvidencePassed = $false
try {
    if ($PSVersionTable.PSVersion -lt [version]'7.4.0') {
        throw "PowerShell 7.4 or newer is required; found $($PSVersionTable.PSVersion)."
    }
    $Phase2Record = Get-Content `
        (Join-Path $RepoRoot 'evidence/phase2/phase2-external-acceptance.json') `
        -Raw | ConvertFrom-Json
    if ($Phase2Record.decision -ne 'PASS' -or -not [bool]$Phase2Record.phase3_authorized) {
        throw 'Accepted Phase 2 evidence does not authorize Phase 3.'
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

    $GeneratedVector = Join-Path $EvidenceDir 'proof-chain-v1.regenerated.json'
    uv run python scripts/generate_phase3_vectors.py --output $GeneratedVector
    $FrozenVector = Join-Path $RepoRoot 'tests/vectors/phase3/proof-chain-v1.json'
    $FrozenHash = (Get-FileHash $FrozenVector -Algorithm SHA256).Hash
    $GeneratedHash = (Get-FileHash $GeneratedVector -Algorithm SHA256).Hash
    if ($FrozenHash -ne $GeneratedHash) {
        throw 'Regenerated proof vector differs from the frozen interoperability vector.'
    }
    Copy-Item $FrozenVector (Join-Path $EvidenceDir 'proof-chain-v1.json')
    $VectorPassed = $true

    uv run python -m scripts.benchmark_phase3 `
        --iterations $BenchmarkIterations `
        --output (Join-Path $EvidenceDir 'proof-benchmark.json')
    Copy-Item `
        (Join-Path $RepoRoot 'evidence/phase2/phase2-external-acceptance.json') `
        (Join-Path $EvidenceDir 'phase2-external-acceptance.json')
    uv run edge-lifeline capture-provenance --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'provenance.json')
    uv run cyclonedx-py environment --output-format JSON --output-file `
        (Join-Path $EvidenceDir 'sbom.cdx.json')
    $AuditCache = Join-Path ([IO.Path]::GetTempPath()) 'edge-lifeline-phase3-pip-audit'
    uv run pip-audit --local --cache-dir $AuditCache --progress-spinner off `
        --format json --output (Join-Path $EvidenceDir 'dependency-audit.json')
    $EvidencePassed = $true
}
finally {
    try { Stop-Transcript | Out-Null } catch { Write-Warning 'Transcript could not be finalized.' }
    $CiDeclared = -not [string]::IsNullOrWhiteSpace($CiRunUrl)
    $GatePassed = $RuntimePassed -and $VectorPassed -and $SecurityPassed -and $EvidencePassed
    $Decision = [ordered]@{
        schema_version = 'phase3-gate-v1'
        evaluated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        decision = if ($GatePassed) { 'CONDITIONAL_PASS' } else { 'FAIL' }
        runtime_gate_passed = $RuntimePassed
        cryptographic_vector_passed = $VectorPassed
        security_negative_gate_passed = $SecurityPassed
        evidence_generation_passed = $EvidencePassed
        ci_evidence_declared = $CiDeclared
        ci_run_url = if ($CiDeclared) { $CiRunUrl } else { $null }
        external_review_required = $true
        phase3_complete = $false
        phase4_authorized = $false
        scientific_claim_status = if ($GatePassed) {
            'Proof-carrying mechanism implemented; research claims remain pending independent evidence review.'
        } else {
            'Proof-carrying mechanism gate failed.'
        }
        note = if ($GatePassed) {
            'Cryptographic, persistence, vector, and evidence gates passed; independent review remains required.'
        } else {
            'At least one Phase 3 gate failed.'
        }
    }
    $Decision | ConvertTo-Json -Depth 6 | Set-Content `
        -LiteralPath (Join-Path $EvidenceDir 'gate-decision.json') `
        -Encoding utf8NoBOM
}

if ($RuntimePassed -and $VectorPassed -and $SecurityPassed -and $EvidencePassed) {
    uv run edge-lifeline source-manifest --root $EvidenceDir --output `
        (Join-Path $EvidenceDir 'evidence-manifest.json')
}
else {
    throw "Phase 3 gate failed. Evidence retained at $EvidenceDir"
}

Write-Host "Phase 3 gate evidence: $EvidenceDir"
