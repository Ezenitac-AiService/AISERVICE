[CmdletBinding()]
param(
    [string]$Domain = 'ezenitac',
    [string]$ConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Definition
    $ConfigPath = Join-Path $scriptDirectory 'duckdns-config.xml'
}

if ($Domain -notmatch '^[a-zA-Z0-9][a-zA-Z0-9,-]*$') {
    throw 'Domain must be a DuckDNS domain name or a comma-separated list without spaces.'
}

$configDirectory = Split-Path -Parent $ConfigPath
if (-not (Test-Path -LiteralPath $configDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
}

Write-Host "DuckDNS domain(s): $Domain"
$secureToken = Read-Host 'Enter DuckDNS token' -AsSecureString

[pscustomobject]@{
    Domain = $Domain
    Token  = ($secureToken | ConvertFrom-SecureString)
} | Export-Clixml -LiteralPath $ConfigPath -Force

Write-Host "Configuration saved: $ConfigPath"
Write-Host 'The token is encrypted with the current Windows user DPAPI.'
