[CmdletBinding()]
param(
    [string]$TaskName = 'DuckDNS-ezenitac-Update',
    [switch]$RemoveConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "예약 작업 삭제 완료: $TaskName"
}
else {
    Write-Host "예약 작업이 없습니다: $TaskName"
}

if ($RemoveConfig) {
    $configPath = Join-Path $PSScriptRoot 'duckdns-config.xml'
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        Remove-Item -LiteralPath $configPath -Force
        Write-Host "암호화된 설정 파일 삭제 완료: $configPath"
    }
}
