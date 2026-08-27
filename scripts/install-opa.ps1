[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest

$Version = '1.19.1'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
if ($Architecture -notin @('x64', 'arm64')) {
    throw "Unsupported OPA architecture: $Architecture"
}
$ArchSuffix = if ($Architecture -eq 'x64') { 'amd64' } else { 'arm64' }
if ($IsWindows) {
    $Asset = "opa_windows_$ArchSuffix.exe"
}
elseif ($IsLinux) {
    $Asset = "opa_linux_${ArchSuffix}_static"
}
else {
    throw 'The Phase 5 OPA installer supports Windows and Linux only.'
}

$ToolDirectory = Join-Path $RepoRoot ".tools/opa/$Version"
$Target = Join-Path $ToolDirectory $Asset
$BaseUrl = "https://openpolicyagent.org/downloads/v$Version/$Asset"
$ChecksumUrl = "$BaseUrl.sha256"
New-Item -ItemType Directory -Path $ToolDirectory -Force | Out-Null

$Nonce = [guid]::NewGuid().ToString('N')
$Download = Join-Path $ToolDirectory "$Asset.$Nonce.download"
$ChecksumDownload = Join-Path $ToolDirectory "$Asset.$Nonce.sha256"
try {
    Invoke-WebRequest -Uri $ChecksumUrl -OutFile $ChecksumDownload
    $ChecksumText = Get-Content -LiteralPath $ChecksumDownload -Raw
    if ($ChecksumText -notmatch '(?i)(?<digest>[a-f0-9]{64})') {
        throw 'The official OPA checksum response did not contain a SHA-256 digest.'
    }
    $ExpectedHash = $Matches.digest.ToLowerInvariant()

    if (Test-Path -LiteralPath $Target) {
        $ExistingHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ExistingHash -ne $ExpectedHash) {
            throw "Existing OPA binary hash mismatch: $Target"
        }
    }
    else {
        Invoke-WebRequest -Uri $BaseUrl -OutFile $Download
        $ActualHash = (Get-FileHash -LiteralPath $Download -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualHash -ne $ExpectedHash) {
            throw "Downloaded OPA binary hash mismatch: expected $ExpectedHash; found $ActualHash"
        }
        Move-Item -LiteralPath $Download -Destination $Target
    }
    if (-not $IsWindows) {
        & chmod 0755 $Target
    }
    $VersionOutput = (& $Target version 2>&1 | Out-String)
    if ($VersionOutput -notmatch [regex]::Escape($Version)) {
        throw "OPA version mismatch: expected $Version; output was $VersionOutput"
    }
    Write-Output $Target
}
finally {
    Remove-Item -LiteralPath $Download -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ChecksumDownload -Force -ErrorAction SilentlyContinue
}
