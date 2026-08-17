<#
.SYNOPSIS
    Windows 방화벽에 포트 80 인바운드 허용 규칙을 추가합니다.
.DESCRIPTION
    AISERVICE 플랫폼용 전용 방화벽 규칙 'AISERVICE-HTTP-In'을 생성합니다.
    TCP 80 포트의 인바운드 트래픽을 모든 프로필(도메인/개인/공용)에 대해 허용합니다.
    !! 관리자 권한(Administrator)으로 실행해야 합니다 !!
.NOTES
    실행 방법:
    1. PowerShell을 "관리자 권한으로 실행"
    2. cd C:\AISERVICE\ddns
    3. Set-ExecutionPolicy -Scope Process Bypass -Force
    4. .\Setup-Firewall-Http.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ruleName = 'AISERVICE-HTTP-In'

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
    Write-Host "현재 상태:" -ForegroundColor Cyan
    $existing | Select-Object DisplayName, Enabled, Action, Profile, Direction | Format-Table -AutoSize

    $portFilter = $existing | Get-NetFirewallPortFilter
    $portFilter | Select-Object Protocol, LocalPort | Format-Table -AutoSize

    if ($existing.Enabled -eq 'False') {
        Write-Host "규칙이 비활성 상태입니다. 활성화합니다..." -ForegroundColor Yellow
        Set-NetFirewallRule -DisplayName $ruleName -Enabled True
        Write-Host "규칙 '$ruleName' 활성화 완료." -ForegroundColor Green
    }
    else {
        Write-Host "규칙이 이미 활성 상태입니다. 추가 작업이 필요 없습니다." -ForegroundColor Green
    }
    exit 0
}

# Create the rule
Write-Host "방화벽 규칙 '$ruleName' 생성 중..." -ForegroundColor Cyan
New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort 80 `
    -Action Allow `
    -Profile Any `
    -Description "Allow inbound HTTP (port 80) for AISERVICE platform" `
    -Enabled True | Out-Null

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " 방화벽 규칙 생성 완료!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  규칙 이름 : $ruleName"
Write-Host "  방향      : 인바운드 (Inbound)"
Write-Host "  프로토콜  : TCP"
Write-Host "  포트      : 80"
Write-Host "  동작      : 허용 (Allow)"
Write-Host "  프로필    : 모든 네트워크 (Any)"
Write-Host ""

# Verify
$verify = Get-NetFirewallRule -DisplayName $ruleName
if ($verify.Enabled -eq 'True') {
    Write-Host "검증 완료: 규칙이 활성화되어 있습니다." -ForegroundColor Green
}
else {
    Write-Warning "규칙이 생성되었지만 활성화되지 않았습니다. 수동 확인이 필요합니다."
}

# Test port reachability
Write-Host ""
Write-Host "포트 80 리스닝 상태 확인:" -ForegroundColor Cyan
$listeners = Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue
if ($null -ne $listeners) {
    foreach ($l in $listeners) {
        $proc = Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue
        Write-Host "  $($l.LocalAddress):$($l.LocalPort) - PID $($l.OwningProcess) ($($proc.ProcessName))" -ForegroundColor White
    }
}
else {
    Write-Host "  포트 80에서 리스닝 중인 프로세스가 없습니다." -ForegroundColor Yellow
    Write-Host "  웹 서비스를 시작한 후 외부 접근이 가능합니다." -ForegroundColor Yellow
}
