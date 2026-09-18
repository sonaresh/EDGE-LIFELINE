[CmdletBinding()]
param([string]$Version = '5.9.0')

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ToolDir = Join-Path $RepoRoot ".tools/k3d/v$Version"
New-Item -ItemType Directory -Path $ToolDir -Force | Out-Null

$IsWindowsHost = $PSVersionTable.Platform -eq 'Win32NT'
if ($IsWindowsHost) {
    $Asset = 'k3d-windows-amd64.exe'
    $ExpectedHash = '49d0b9c796f5b8ba6f58a1dd5469e8b7b34bf9b6ce9078633eedb2789680a034'
    $Destination = Join-Path $ToolDir 'k3d.exe'
}
elseif ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'X64') {
    $Asset = 'k3d-linux-amd64'
    $ExpectedHash = '06d8f25bc3a971c4eb29e0ff08429b180402db0f4dec838c9eac427e296800a0'
    $Destination = Join-Path $ToolDir 'k3d'
}
else {
    throw 'Phase 7 supports only Windows AMD64 and Linux AMD64 hosts.'
}

$Url = "https://github.com/k3d-io/k3d/releases/download/v$Version/$Asset"
if (-not (Test-Path -LiteralPath $Destination)) {
    Invoke-WebRequest -Uri $Url -OutFile $Destination
}
$ActualHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $ExpectedHash) {
    throw "k3d checksum mismatch: expected $ExpectedHash, received $ActualHash"
}
if (-not $IsWindowsHost) { chmod +x $Destination }
& $Destination version
Write-Output $Destination
