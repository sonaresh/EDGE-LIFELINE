[CmdletBinding()]
param(
    [switch]$SkipContainers,
    [string]$EvidenceDir
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

uv sync --frozen --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy
$PytestArgs = @('--cov=edge_lifeline', '--cov-report=term-missing')
if ($EvidenceDir) {
    $PytestArgs += "--cov-report=xml:$EvidenceDir/coverage.xml"
    $PytestArgs += "--junitxml=$EvidenceDir/pytest-junit.xml"
}
uv run pytest @PytestArgs

if (-not $SkipContainers) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker is required unless -SkipContainers is supplied.'
    }
    $PythonImage = if ($env:PYTHON_IMAGE) { $env:PYTHON_IMAGE } else { 'python:3.12.13-slim-bookworm' }
    docker pull $PythonImage
    docker compose config --quiet
    try {
        docker compose up --build --detach --wait
        $Expected = @(
            @{ BaseUrl = 'http://127.0.0.1:18080'; NodeId = 'cloud'; Role = 'cloud' },
            @{ BaseUrl = 'http://127.0.0.1:18081'; NodeId = 'edge-a'; Role = 'edge' },
            @{ BaseUrl = 'http://127.0.0.1:18082'; NodeId = 'edge-b'; Role = 'edge' },
            @{ BaseUrl = 'http://127.0.0.1:18083'; NodeId = 'edge-c'; Role = 'edge' }
        )
        $HealthEvidence = @()
        foreach ($Entry in $Expected) {
            $Health = Invoke-RestMethod -Uri "$($Entry.BaseUrl)/healthz" -TimeoutSec 5
            $Version = Invoke-RestMethod -Uri "$($Entry.BaseUrl)/version" -TimeoutSec 5
            if ($Health.status -ne 'ok' -or $Health.node_id -ne $Entry.NodeId -or $Health.node_role -ne $Entry.Role) {
                throw "Unexpected health response from $($Entry.BaseUrl)"
            }
            if ($Version.revision -ne $env:BUILD_REVISION) {
                throw "Build revision mismatch at $($Entry.BaseUrl)"
            }
            $HealthEvidence += [pscustomobject]@{
                base_url = $Entry.BaseUrl
                health = $Health
                version = $Version
            }
        }
        docker compose ps
        if ($EvidenceDir) {
            docker compose config | Set-Content -Path (Join-Path $EvidenceDir 'compose-rendered.yaml') -Encoding utf8NoBOM
            docker compose ps --format json | Set-Content -Path (Join-Path $EvidenceDir 'compose-services.jsonl') -Encoding utf8NoBOM
            docker compose images --format json | Set-Content -Path (Join-Path $EvidenceDir 'compose-images.jsonl') -Encoding utf8NoBOM
            docker image inspect $PythonImage | Set-Content -Path (Join-Path $EvidenceDir 'base-image-inspect.json') -Encoding utf8NoBOM
            $HealthEvidence | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $EvidenceDir 'compose-health.json') -Encoding utf8NoBOM
        }
    }
    finally {
        try {
            docker compose down --volumes --remove-orphans
        }
        catch {
            Write-Warning "Compose cleanup failed and requires manual attention: $($_.Exception.Message)"
        }
    }
}

Write-Host 'Verification passed.'
