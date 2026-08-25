[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (Get-Command docker -ErrorAction SilentlyContinue) {
    if ($PSCmdlet.ShouldProcess('edge-lifeline-phase1 containers and named network', 'docker compose down')) {
        docker compose down --volumes --remove-orphans
    }
}

Write-Host 'Runtime resources removed. Source files and evidence were preserved.'
