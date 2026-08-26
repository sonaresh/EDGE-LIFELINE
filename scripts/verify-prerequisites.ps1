[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest

$Checks = @(
    @{ Name = 'PowerShell74'; Command = $null; Action = {
        if ($PSVersionTable.PSVersion -lt [version]'7.4.0') {
            throw "PowerShell 7.4 or newer is required; found $($PSVersionTable.PSVersion)."
        }
        $PSVersionTable.PSVersion.ToString()
    } },
    @{ Name = 'Windows'; Command = 'Get-ComputerInfo'; Action = { (Get-ComputerInfo).WindowsProductName } },
    @{ Name = 'WSL'; Command = 'wsl'; Action = { wsl --status 2>&1 | Out-String } },
    @{ Name = 'Docker'; Command = 'docker'; Action = { docker version 2>&1 | Out-String } },
    @{ Name = 'Compose'; Command = 'docker'; Action = { docker compose version 2>&1 | Out-String } },
    @{ Name = 'Python312'; Command = 'py'; Action = { py -3.12 --version 2>&1 | Out-String } },
    @{ Name = 'UV'; Command = 'uv'; Action = { uv --version 2>&1 | Out-String } },
    @{ Name = 'Git'; Command = 'git'; Action = { git --version 2>&1 | Out-String } },
    @{ Name = 'Java17'; Command = 'java'; Action = {
        $VersionText = (java -version 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0) { throw "java -version exited with code $LASTEXITCODE" }
        if ($VersionText -notmatch 'version "(?<major>1\.)?(?<version>\d+)') {
            throw 'Could not determine the Java major version.'
        }
        $Major = [int]$Matches.version
        if ($Major -lt 17) { throw "Java 17 or newer is required; found Java $Major." }
        $VersionText
    } }
)

foreach ($Check in $Checks) {
    try {
        if ($Check.Command -and -not (Get-Command $Check.Command -ErrorAction SilentlyContinue)) {
            throw "Command '$($Check.Command)' was not found."
        }
        $Detail = (& $Check.Action).Trim()
        [pscustomobject]@{ Check = $Check.Name; Status = 'AVAILABLE'; Detail = $Detail }
    }
    catch {
        [pscustomobject]@{ Check = $Check.Name; Status = 'UNAVAILABLE'; Detail = $_.Exception.Message }
    }
}
