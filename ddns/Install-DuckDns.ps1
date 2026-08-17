[CmdletBinding()]
param(
    [string]$Domain = 'ezenitac',
    [string]$TaskName = 'DuckDNS-ezenitac-Update',
    [switch]$ResetConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$configScript = Join-Path $PSScriptRoot 'Set-DuckDnsConfig.ps1'
$updateScript = Join-Path $PSScriptRoot 'Update-DuckDns.ps1'
$configPath = Join-Path $PSScriptRoot 'duckdns-config.xml'
$dotenvPath = Join-Path $PSScriptRoot '.env'

if (-not (Test-Path -LiteralPath $configScript -PathType Leaf)) {
    throw "Configuration script not found: $configScript"
}
if (-not (Test-Path -LiteralPath $updateScript -PathType Leaf)) {
    throw "Update script not found: $updateScript"
}

if (Test-Path -LiteralPath $dotenvPath -PathType Leaf) {
    Write-Host "Using token from .env: $dotenvPath"
}
elseif ($ResetConfig -or -not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    & $configScript -Domain $Domain -ConfigPath $configPath
}
else {
    Write-Host "Using existing encrypted configuration: $configPath"
}

$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
Write-Host ''
Write-Host 'Testing DuckDNS update...'
& $powerShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File $updateScript -Domain $Domain
if ($LASTEXITCODE -ne 0) {
    throw 'The first DuckDNS update failed. Check duckdns.log.'
}

$quotedUpdateScript = '"' + $updateScript + '"'
$quotedDomain = '"' + $Domain + '"'
$action = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $quotedUpdateScript -Domain $quotedDomain"

# Run as the current user because DPAPI protects the token for this user.
$userDomain = if ([string]::IsNullOrWhiteSpace($env:USERDOMAIN)) { $env:COMPUTERNAME } else { $env:USERDOMAIN }
$userId = "$userDomain\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "DuckDNS public IP update for $Domain (every 5 minutes)" `
    -Force | Out-Null

Write-Host ''
Write-Host "Scheduled task registered: $TaskName"
Write-Host "Run as: $userId"
Write-Host 'Interval: 5 minutes'
Write-Host "Log: $(Join-Path $PSScriptRoot 'duckdns.log')"
