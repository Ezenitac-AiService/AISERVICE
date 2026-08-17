# import_db_dump.ps1: 1회성 대용량 DB 덤프 복원 스크립트 (2.69GB pilos_v2.sql)
param (
    [string]$DumpFile = "pilos_v2.sql",
    [string]$ContainerName = "pilos-db",
    [string]$DbUser = "root",
    [string]$DbPassword = "pilos_root_pass",
    [string]$DbName = "pilos_v2"
)

$ErrorActionPreference = "Stop"

Write-Host "=== A-Team DB 덤프 복원 워크플로우 시작 ===" -ForegroundColor Cyan

# 1. 네트워크 초기화 확인
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$ScriptDir\init_network.ps1"

# 2. .env 파일 확인
$EnvFile = Join-Path (Split-Path -Parent $ScriptDir) "pilos-sentiment-index\.env"
$EnvExample = Join-Path (Split-Path -Parent $ScriptDir) "pilos-sentiment-index\.env.example"

if (-not (Test-Path $EnvFile)) {
    Write-Host ".env 파일이 없어 .env.example로부터 복사합니다..." -ForegroundColor Yellow
    Copy-Item $EnvExample $EnvFile
}

# 3. 덤프 파일 존재 확인
$RootPath = Split-Path -Parent $ScriptDir
$FullDumpPath = Join-Path $RootPath $DumpFile

if (-not (Test-Path $FullDumpPath)) {
    Write-Error "덤프 파일을 찾을 수 없습니다: $FullDumpPath"
    exit 1
}

$fileSizeMB = [math]::Round(((Get-Item $FullDumpPath).Length / 1MB), 2)
Write-Host "덤프 파일 발견: $DumpFile ($fileSizeMB MB)" -ForegroundColor Green

# 4. DB 서비스 기동
Write-Host "DBMS 컨테이너를 기동합니다..." -ForegroundColor Cyan
Push-Location $RootPath
docker compose up -d db

# 5. DB 헬스체크 대기
Write-Host "DBMS 헬스체크 대기 중..." -ForegroundColor Cyan
$maxRetries = 30
$retryCount = 0
$healthy = $false

while ($retryCount -lt $maxRetries) {
    Start-Sleep -Seconds 3
    $status = docker inspect --format="{{.State.Health.Status}}" $ContainerName 2>$null
    if ($status -eq "healthy") {
        $healthy = $true
        Write-Host "DBMS 컨테이너 준비 완료 (Status: healthy)" -ForegroundColor Green
        break
    }
    $retryCount++
    Write-Host "대기 중... ($retryCount/$maxRetries) [현재 상태: $status]" -ForegroundColor DarkGray
}

if (-not $healthy) {
    Write-Error "DBMS 컨테이너 헬스체크 타임아웃!"
    Pop-Location
    exit 1
}

# 6. SQL 덤프 스트리밍 복원
Write-Host "대용량 SQL 덤프 복원을 시작합니다 (수 분 소요될 수 있습니다)..." -ForegroundColor Yellow
$startTime = Get-Date

cmd /c "docker exec -i $ContainerName mysql -h 127.0.0.1 -u$DbUser -p$DbPassword --default-character-set=utf8mb4 --max_allowed_packet=512M $DbName < `"$FullDumpPath`""

if ($LASTEXITCODE -eq 0) {
    $duration = (Get-Date) - $startTime
    Write-Host "덤프 복원 완료! (소요 시간: $($duration.Minutes)분 $($duration.Seconds)초)" -ForegroundColor Green
} else {
    Write-Error "덤프 복원 중 오류가 발생했습니다."
    Pop-Location
    exit $LASTEXITCODE
}

# 7. 복원 결과 검증
Write-Host "데이터베이스 테이블 목록 확인:" -ForegroundColor Cyan
docker exec -i $ContainerName mysql -h 127.0.0.1 -u$DbUser -p$DbPassword -e "USE $DbName; SHOW TABLES;"

Pop-Location
Write-Host "=== A-Team DB 덤프 복원 완료 ===" -ForegroundColor Green
