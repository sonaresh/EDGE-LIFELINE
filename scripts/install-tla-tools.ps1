[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ToolsDirectory = Join-Path $RepoRoot '.tools'
$JarPath = Join-Path $ToolsDirectory 'tla2tools-1.7.4.jar'
$DownloadUri = 'https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar'
$ExpectedSha256 = '936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88'

New-Item -ItemType Directory -Path $ToolsDirectory -Force | Out-Null

if (Test-Path -LiteralPath $JarPath) {
    $CurrentHash = (Get-FileHash -LiteralPath $JarPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($CurrentHash -eq $ExpectedSha256) {
        Write-Output $JarPath
        return
    }
    throw "Existing TLA+ tool has an unexpected SHA-256: $CurrentHash"
}

$TemporaryFile = Join-Path ([IO.Path]::GetTempPath()) "edge-lifeline-tla-$PID.jar"
try {
    Invoke-WebRequest -Uri $DownloadUri -OutFile $TemporaryFile -UseBasicParsing
    $DownloadedHash = (Get-FileHash -LiteralPath $TemporaryFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($DownloadedHash -ne $ExpectedSha256) {
        throw "Downloaded TLA+ tool SHA-256 mismatch: $DownloadedHash"
    }
    Move-Item -LiteralPath $TemporaryFile -Destination $JarPath
}
finally {
    if (Test-Path -LiteralPath $TemporaryFile) {
        Remove-Item -LiteralPath $TemporaryFile -Force
    }
}

Write-Output $JarPath
