[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$EvidenceDir,
    [ValidateRange(1, 64)]
    [int]$Workers = 4
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelDirectory = Join-Path $RepoRoot 'formal/tla'
$ConfigDirectory = Join-Path $ModelDirectory 'configs'
$JarPath = & (Join-Path $PSScriptRoot 'install-tla-tools.ps1') | Select-Object -Last 1
$ExpectedJarHash = '936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88'
$ActualJarHash = (Get-FileHash -LiteralPath $JarPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualJarHash -ne $ExpectedJarHash) {
    throw 'TLA+ tool hash changed after installation.'
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    throw 'Java is required for TLC. Install Microsoft OpenJDK 17 or newer.'
}

New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$TlcEvidence = Join-Path $EvidenceDir 'tlc'
New-Item -ItemType Directory -Path $TlcEvidence -Force | Out-Null
$StateRoot = Join-Path ([IO.Path]::GetTempPath()) "edge-lifeline-tlc-$PID"
New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null

$Models = @(
    @{ Name = 'positive'; Config = 'positive.cfg'; ExpectedInvariant = $null },
    @{ Name = 'negative-parent'; Config = 'negative_parent.cfg'; ExpectedInvariant = 'I2_ParentBounded' },
    @{ Name = 'negative-time'; Config = 'negative_time.cfg'; ExpectedInvariant = 'I4_ConservativeTime' },
    @{ Name = 'negative-replay'; Config = 'negative_replay.cfg'; ExpectedInvariant = 'I5_AntiReplay' },
    @{ Name = 'negative-reconnect'; Config = 'negative_reconnect.cfg'; ExpectedInvariant = 'I9_NoReconnectGrant' },
    @{ Name = 'negative-proof'; Config = 'negative_proof.cfg'; ExpectedInvariant = 'I6_ProofBeforeEffect' },
    @{ Name = 'negative-auto-replay'; Config = 'negative_auto_replay.cfg'; ExpectedInvariant = 'I10_NoAutomaticEffectReplay' }
)

$Results = @()
$OriginalLocation = Get-Location
try {
    Set-Location $ModelDirectory
    foreach ($Model in $Models) {
        $StateDirectory = Join-Path $StateRoot $Model.Name
        $LogPath = Join-Path $TlcEvidence "$($Model.Name).log"
        $ConfigPath = Join-Path $ConfigDirectory $Model.Config
        $Output = & java '-XX:+UseParallelGC' '-Xmx2g' '-cp' $JarPath 'tlc2.TLC' `
            '-cleanup' '-deadlock' '-fp' '0' '-workers' $Workers `
            '-metadir' $StateDirectory '-config' $ConfigPath 'EdgeLifeline' 2>&1
        $ExitCode = $LASTEXITCODE
        $Text = ($Output | Out-String)
        Set-Content -LiteralPath $LogPath -Value $Text -Encoding utf8NoBOM

        $ExpectedInvariant = $Model.ExpectedInvariant
        if ($null -eq $ExpectedInvariant) {
            if ($ExitCode -ne 0 -or $Text -notmatch 'Model checking completed\. No error has been found\.') {
                throw "Positive TLC model failed. See $LogPath"
            }
            $Outcome = 'NO_COUNTEREXAMPLE'
        }
        else {
            $ExpectedText = "Invariant $ExpectedInvariant is violated"
            if ($ExitCode -eq 0 -or $Text -notmatch [regex]::Escape($ExpectedText)) {
                throw "Negative TLC model did not produce $ExpectedInvariant. See $LogPath"
            }
            $Outcome = 'EXPECTED_COUNTEREXAMPLE'
        }

        $StateMatches = [regex]::Matches(
            $Text,
            '(?m)^(\d+) states generated, (\d+) distinct states found'
        )
        $DepthMatch = [regex]::Match(
            $Text,
            '(?m)^The depth of the complete state graph search is (\d+)\.'
        )
        $LastStateMatch = if ($StateMatches.Count -gt 0) {
            $StateMatches[$StateMatches.Count - 1]
        }
        else {
            $null
        }
        $Results += [pscustomobject]@{
            name = $Model.Name
            config = $Model.Config
            config_sha256 = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash.ToLowerInvariant()
            expected_invariant = $ExpectedInvariant
            outcome = $Outcome
            exit_code = $ExitCode
            states_generated = if ($null -ne $LastStateMatch) { [long]$LastStateMatch.Groups[1].Value } else { $null }
            distinct_states = if ($null -ne $LastStateMatch) { [long]$LastStateMatch.Groups[2].Value } else { $null }
            depth = if ($DepthMatch.Success) { [int]$DepthMatch.Groups[1].Value } else { $null }
            log = "tlc/$($Model.Name).log"
        }
    }
}
finally {
    Set-Location $OriginalLocation
    $ResolvedTemp = [IO.Path]::GetFullPath($StateRoot)
    if ($ResolvedTemp.StartsWith([IO.Path]::GetTempPath(), [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $ResolvedTemp).StartsWith('edge-lifeline-tlc-', [StringComparison]::Ordinal)) {
        Remove-Item -LiteralPath $ResolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$JavaVersion = (& java -version 2>&1 | Out-String).Trim()
$Summary = [ordered]@{
    schema_version = 'phase2-tlc-summary-v1'
    generated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    module = 'formal/tla/EdgeLifeline.tla'
    module_sha256 = (Get-FileHash -LiteralPath (Join-Path $ModelDirectory 'EdgeLifeline.tla') -Algorithm SHA256).Hash.ToLowerInvariant()
    tlaplus_release = 'v1.7.4'
    tlc_version = '2.19 of 08 August 2024'
    tla2tools_sha256 = $ActualJarHash
    java = $JavaVersion
    workers = $Workers
    positive_passed = ($Results[0].outcome -eq 'NO_COUNTEREXAMPLE')
    negative_counterexamples_passed = (@(
        $Results | Where-Object {
            $_.expected_invariant -ne $null -and
            $_.outcome -ne 'EXPECTED_COUNTEREXAMPLE'
        }
    ).Count -eq 0)
    results = $Results
}
$Summary | ConvertTo-Json -Depth 8 | Set-Content `
    -LiteralPath (Join-Path $EvidenceDir 'tlc-summary.json') `
    -Encoding utf8NoBOM

Write-Output (Join-Path $EvidenceDir 'tlc-summary.json')
