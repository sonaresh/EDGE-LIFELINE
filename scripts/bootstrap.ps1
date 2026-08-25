[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required. Install it with: winget install --id=astral-sh.uv -e'
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'The Windows Python launcher is required. Install Python 3.12 first.'
}

$PythonVersion = (& py -3.12 --version 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.12 is required. Install it before continuing.'
}

Write-Host "Using $PythonVersion"
uv sync --frozen --all-groups
uv run edge-lifeline version
Write-Host 'Bootstrap complete.'
