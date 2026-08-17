[CmdletBinding()]
param(
    [string]$Domain,
    [string]$ConfigPath,
    [string]$LogPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# In Windows PowerShell 5.1, $PSScriptRoot can be empty while param defaults
# are being evaluated. Resolve defaults in the script body instead.
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Definition
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $scriptDirectory 'duckdns-config.xml'
}
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $scriptDirectory 'duckdns.log'
}

function Write-Log {
    param([Parameter(Mandatory = $true)][string]$Message)

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
    Add-Content -LiteralPath $LogPath -Value "[$timestamp] $Message" -Encoding UTF8
}

function Read-DotEnvFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    $values = @{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $values
    }

    foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith('#')) {
            continue
        }

        $pair = $trimmed -split '=', 2
        if ($pair.Count -ne 2) {
            continue
        }

        $key = $pair[0].Trim() -replace '\r',''
        $value = $pair[1].Trim() -replace '\r',''
        if ([string]::IsNullOrWhiteSpace($key)) {
            continue
        }

        if ($value.Length -ge 2) {
            $isDoubleQuoted = $value.StartsWith('"') -and $value.EndsWith('"')
            $isSingleQuoted = $value.StartsWith("'") -and $value.EndsWith("'")
            if ($isDoubleQuoted -or $isSingleQuoted) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        $values[$key] = $value
    }

    return $values
}

function Invoke-DuckDnsRequest {
    param([Parameter(Mandatory = $true)][string]$Uri)

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 30
        # In Windows PowerShell 5.1, .Content can be a Byte[] instead of a string.
        $raw = $response.Content
        if ($raw -is [byte[]]) {
            return ([System.Text.Encoding]::UTF8.GetString($raw)).Trim()
        }
        return ([string]$raw).Trim()
    }
    catch {
        $powershellError = $_.Exception.Message
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($null -eq $curl) {
            throw "PowerShell HTTPS request failed: $powershellError"
        }

        # Keep the token out of the curl process command line. The URL is passed via stdin.
        # Use an output file because Windows PowerShell 5.1 can expose curl stdout as byte values
        # (for example, "79 75" instead of the text "OK").
        $responseFile = [System.IO.Path]::GetTempFileName()
        try {
            $curlConfig = 'url = "' + $Uri + '"'
            $null = $curlConfig | & $curl.Source --silent --show-error --max-time 30 --output $responseFile --config - 2>&1
            $curlExitCode = $LASTEXITCODE
            if ($curlExitCode -ne 0) {
                throw "PowerShell HTTPS request failed: $powershellError; curl exit code: $curlExitCode"
            }

            return ([System.IO.File]::ReadAllText($responseFile)).Trim()
        }
        finally {
            if (Test-Path -LiteralPath $responseFile -PathType Leaf) {
                Remove-Item -LiteralPath $responseFile -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

try {
    $dotenvPath = Join-Path $scriptDirectory '.env'
    $dotenv = Read-DotEnvFile -Path $dotenvPath
    $hasDotEnvToken = $dotenv.ContainsKey('token') -and -not [string]::IsNullOrWhiteSpace([string]$dotenv['token'])

    if ($hasDotEnvToken) {
        # .env is intentionally preferred when present. The repository ignores this file.
        $token = [string]$dotenv['token']
        if ($dotenv.ContainsKey('domain') -and -not [string]::IsNullOrWhiteSpace([string]$dotenv['domain'])) {
            $domains = [string]$dotenv['domain']
        }
        elseif (-not [string]::IsNullOrWhiteSpace($Domain)) {
            $domains = $Domain
        }
        else {
            $domains = 'ezenitac'
        }
        $credentialSource = '.env'
    }
    else {
        if ($dotenv.ContainsKey('token')) {
            throw 'The token entry in ddns\.env is empty.'
        }
        if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
            throw "Configuration file not found: $ConfigPath. Put token=... in ddns\.env or run Install-DuckDns.ps1."
        }

        $config = Import-Clixml -LiteralPath $ConfigPath
        $encryptedToken = [string]$config.Token
        if ([string]::IsNullOrWhiteSpace($encryptedToken)) {
            throw 'DuckDNS token is empty.'
        }

        # Export-Clixml stores the SecureString protected by this Windows user's DPAPI.
        $secureToken = ConvertTo-SecureString -String $encryptedToken
        $token = [System.Net.NetworkCredential]::new('', $secureToken).Password
        $domains = if ([string]::IsNullOrWhiteSpace($Domain)) { [string]$config.Domain } else { $Domain }
        $credentialSource = 'DPAPI config'
    }

    if ([string]::IsNullOrWhiteSpace($domains)) {
        throw 'DuckDNS domain is empty.'
    }

    # Explicitly use TLS 1.2 for Windows PowerShell 5.1 and older systems.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $domainQuery = [Uri]::EscapeDataString($domains)
    $tokenQuery = [Uri]::EscapeDataString($token)
    $uri = "https://www.duckdns.org/update?domains=$domainQuery&token=$tokenQuery&ip="

    $result = Invoke-DuckDnsRequest -Uri $uri

    if ($result -ne 'OK') {
        Write-Log "Update failed: $result"
        throw "DuckDNS response was not OK: $result"
    }

    Write-Log "Update succeeded: domain(s)=$domains result=$result source=$credentialSource"
    Write-Output "DuckDNS update OK: $domains"
    exit 0
}
catch {
    try {
        Write-Log "Error: $($_.Exception.Message)"
    }
    catch {
        # If the log cannot be written, still report the original error.
    }

    Write-Error $_
    exit 1
}
