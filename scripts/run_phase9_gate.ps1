[CmdletBinding()]
param([string]$CiRunUrl)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$EvidenceDir = Join-Path $RepoRoot "evidence/phase9/generated/$Stamp"
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$Transcript = Join-Path $EvidenceDir 'phase9-gate.log'
Start-Transcript -Path $Transcript | Out-Null

$RuntimePassed = $false
$SecurityPassed = $false
$AcceptancePassed = $false
$PublicationPassed = $false
$ReproductionPassed = $false
$EvidencePassed = $false
try {
    if ($PSVersionTable.PSVersion -lt [version]'7.4.0') {
        throw "PowerShell 7.4 or newer is required; found $($PSVersionTable.PSVersion)."
    }
    $Phase8Record = Get-Content `
        (Join-Path $RepoRoot 'evidence/phase8/phase8-external-acceptance.json') `
        -Raw | ConvertFrom-Json
    if ($Phase8Record.decision -ne 'PASS' -or -not [bool]$Phase8Record.phase9_authorized) {
        throw 'Accepted Phase 8 evidence does not authorize Phase 9.'
    }
    $AcceptancePassed = $true

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
    uv run pytest tests/unit/release tests/security/phase9 `
        --junitxml (Join-Path $EvidenceDir 'phase9-negative-tests-junit.xml')
    $SecurityPassed = $true

    $First = Join-Path $EvidenceDir 'publication-first'
    $Second = Join-Path $EvidenceDir 'publication-second'
    uv run python -m scripts.generate_phase9_publication --root $RepoRoot --output $First
    uv run python -m scripts.generate_phase9_publication --root $RepoRoot --output $Second
    $ExpectedNames = @(
        'ARTIFACT-MANIFEST.json', 'CHECKSUMS.sha256', 'CLAIM-EVIDENCE-MATRIX.md',
        'REPRODUCIBILITY.md', 'RESULTS.md', 'accepted-results.json',
        'comparison-effects.svg', 'phase8-external-acceptance.json',
        'release-metadata.json', 'results-table.csv'
    )
    foreach ($Name in $ExpectedNames) {
        $FirstPath = Join-Path $First $Name
        $SecondPath = Join-Path $Second $Name
        if (-not (Test-Path $FirstPath) -or -not (Test-Path $SecondPath)) {
            throw "Phase 9 publication artifact is missing: $Name"
        }
        if ((Get-FileHash $FirstPath -Algorithm SHA256).Hash -ne `
            (Get-FileHash $SecondPath -Algorithm SHA256).Hash) {
            throw "Phase 9 publication reproduction differs: $Name"
        }
    }
    $PublicationPassed = $true
    $ReproductionPassed = $true

    Copy-Item (Join-Path $RepoRoot 'evidence/phase8/phase8-external-acceptance.json') `
        (Join-Path $EvidenceDir 'phase8-external-acceptance.json')
    Copy-Item (Join-Path $RepoRoot 'docs/phase9/limitations.md') `
        (Join-Path $EvidenceDir 'limitations.md')
    Copy-Item (Join-Path $RepoRoot 'docs/phase9/README.md') `
        (Join-Path $EvidenceDir 'phase9-readme.md')
    uv run edge-lifeline capture-provenance --root $RepoRoot --output `
        (Join-Path $EvidenceDir 'provenance.json')
    uv run cyclonedx-py environment --output-format JSON --output-file `
        (Join-Path $EvidenceDir 'sbom.cdx.json')
    $AuditCache = Join-Path ([IO.Path]::GetTempPath()) 'edge-lifeline-phase9-pip-audit'
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
    $GatePassed = $RuntimePassed -and $SecurityPassed -and $AcceptancePassed -and `
        $PublicationPassed -and $ReproductionPassed -and $EvidencePassed
    [ordered]@{
        schema_version = 'phase9-gate-v1'
        evaluated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        decision = if ($GatePassed) { 'CONDITIONAL_PASS' } else { 'FAIL' }
        runtime_gate_passed = $RuntimePassed
        security_negative_gate_passed = $SecurityPassed
        phase8_acceptance_linkage_passed = $AcceptancePassed
        publication_package_passed = $PublicationPassed
        deterministic_reproduction_passed = $ReproductionPassed
        evidence_generation_passed = $EvidencePassed
        experiment_rerun = $false
        outcome_based_exclusions_added = 0
        ci_evidence_declared = $CiDeclared
        ci_run_url = if ($CiDeclared) { $CiRunUrl } else { $null }
        external_review_required = $true
        phase9_complete = $false
        public_release_authorized = $false
        note = 'Publication package only; accepted Phase 8 results were not rerun or changed.'
    } | ConvertTo-Json -Depth 6 | Set-Content `
        (Join-Path $EvidenceDir 'gate-decision.json') -Encoding utf8NoBOM
}

if ($RuntimePassed -and $SecurityPassed -and $AcceptancePassed -and `
    $PublicationPassed -and $ReproductionPassed -and $EvidencePassed) {
    uv run edge-lifeline source-manifest --root $EvidenceDir --output `
        (Join-Path $EvidenceDir 'evidence-manifest.json')
}
else { throw "Phase 9 gate failed. Evidence retained at $EvidenceDir" }

Write-Host "Phase 9 gate evidence: $EvidenceDir"
