# check_ports.ps1: Host port conflict checker
param (
    [int]$WebPort = 8080,
    [int]$DbPort = 3307
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path (Split-Path -Parent $ScriptDir) "pilos-sentiment-index\.env"

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^(?:HOST_WEB_PORT|WEB_PORT)=(\d+)") { $WebPort = [int]$matches[1] }
        if ($_ -match "^(?:HOST_DB_PORT)=(\d+)") { $DbPort = [int]$matches[1] }
    }
}

Write-Host "=== A-Team 호스트 외부 노출 포트 점유 상태 확인 ===" -ForegroundColor Cyan
Write-Host "검사 대상 포트: Web ($WebPort), MySQL ($DbPort)"

function Test-PortAvailable([int]$port, [string]$name) {
    $occupied = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($occupied) {
        $pids = $occupied | Select-Object -ExpandProperty OwningProcess -Unique
        Write-Host "[NOTICE] 포트 $port ($name) 이(가) 현재 사용 중입니다. (PID: $($pids -join ', '))" -ForegroundColor Yellow
        Write-Host "  -> A-Team 컨테이너가 이미 실행 중이거나 다른 프로세스가 점유 중일 수 있습니다." -ForegroundColor DarkGray
    } else {
        Write-Host "[OK] 포트 $port ($name) 사용 가능 (충돌 없음)." -ForegroundColor Green
    }
}

Test-PortAvailable -port $WebPort -name "A-Team Web Service"
Test-PortAvailable -port $DbPort -name "A-Team MySQL DBMS"
Write-Host "=== 포트 점유 상태 확인 완료 ===" -ForegroundColor Cyan
