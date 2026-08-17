<#
.SYNOPSIS
    Windows 방화벽에 포트 443 (HTTPS) 인바운드 허용 규칙을 추가합니다.
.DESCRIPTION
    AISERVICE 플랫폼용 전용 방화벽 규칙 'AISERVICE-HTTPS-In'을 생성합니다.
    !! 관리자 권한(Administrator)으로 실행해야 합니다 !!
.NOTES
    실행: 관리자 PowerShell → cd C:\AISERVICE\ddns → .\Setup-Firewall-Https.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ruleName = 'AISERVICE-HTTPS-In'

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "이 스크립트는 관리자 권한으로 실행해야 합니다. PowerShell을 '관리자 권한으로 실행'한 뒤 다시 시도하세요."
    exit 1
}

# Check if rule already exists
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    Write-Host "방화벽 규칙 '$ruleName'이(가) 이미 존재합니다." -ForegroundColor Yellow
    if ($existing.Enabled -eq 'False') {
        Write-Host "규칙이 비활성 상태입니다. 활성화합니다..." -ForegroundColor Yellow
        Set-NetFirewallRule -DisplayName $ruleName -Enabled True
        Write-Host "규칙 '$ruleName' 활성화 완료." -ForegroundColor Green
    }
    else {
        Write-Host "규칙이 이미 활성 상태입니다." -ForegroundColor Green
    }
    exit 0
}

# Create the rule
Write-Host "방화벽 규칙 '$ruleName' 생성 중..." -ForegroundColor Cyan
New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort 443 `
    -Action Allow `
    -Profile Any `
    -Description "Allow inbound HTTPS (port 443) for AISERVICE platform" `
    -Enabled True | Out-Null

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " HTTPS 방화벽 규칙 생성 완료!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  규칙 이름 : $ruleName"
Write-Host "  포트      : 443 (TCP)"
Write-Host "  동작      : 허용 (Allow)"
Write-Host ""

# Verify
$verify = Get-NetFirewallRule -DisplayName $ruleName
if ($verify.Enabled -eq 'True') {
    Write-Host "검증 완료: 규칙이 활성화되어 있습니다." -ForegroundColor Green
}
