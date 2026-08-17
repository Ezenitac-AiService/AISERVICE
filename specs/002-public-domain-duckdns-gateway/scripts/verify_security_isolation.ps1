# PowerShell Security Isolation Verification Script
# Verifies that private database and model inference ports are NOT reachable from public internet.

param (
    [string]$TargetHost = "ezenitac.duckdns.org"
)

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  AISERVICE Security Isolation Verification: $TargetHost" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# Ports that MUST be CLOSED to the public internet
$privatePorts = @(
    @{ Port = 3306; Name = "MySQL B-Team (bteam_db)" },
    @{ Port = 3307; Name = "MySQL A-Team (pilos-db)" },
    @{ Port = 8081; Name = "LLM Serving Gateway" },
    @{ Port = 8090; Name = "BGE-M3 Embedding Gateway" },
    @{ Port = 8091; Name = "Reranker Gateway" },
    @{ Port = 5000; Name = "A-Team Internal Flask (pilos-web)" },
    @{ Port = 5050; Name = "B-Team Internal Flask (oliview_backend)" },
    @{ Port = 5173; Name = "B-Team Internal Vite (oliview_frontend)" },
    @{ Port = 8002; Name = "B-Team Internal FastAPI (oliview_chatbot_b)" },
    @{ Port = 8501; Name = "B-Team Internal Streamlit (oliview_chatbot_a)" }
)

# Ports that MUST be OPEN
$publicPorts = @(
    @{ Port = 80; Name = "Public HTTP Gateway (Redirects to 443)" },
    @{ Port = 443; Name = "Public HTTPS Gateway (Let's Encrypt)" },
    @{ Port = 8080; Name = "Direct Gateway Port" }
)

$allPassed = $true

Write-Host "`n[1] Verifying Public Port Accessibility..." -ForegroundColor Yellow
foreach ($p in $publicPorts) {
    $res = Test-NetConnection -ComputerName $TargetHost -Port $p.Port -WarningAction SilentlyContinue -InformationLevel Quiet
    if ($res) {
        Write-Host "  [PASS] Port $($p.Port) ($($p.Name)) is OPEN" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Port $($p.Port) ($($p.Name)) is NOT reachable (check service status or ingress)" -ForegroundColor Yellow
    }
}

Write-Host "`n[2] Verifying Private Infrastructure Isolation (MUST BE BLOCKED)..." -ForegroundColor Yellow
foreach ($p in $privatePorts) {
    $res = Test-NetConnection -ComputerName $TargetHost -Port $p.Port -WarningAction SilentlyContinue -InformationLevel Quiet
    if (-not $res) {
        Write-Host "  [PASS] Port $($p.Port) ($($p.Name)) is properly ISOLATED (Connection Refused/Blocked)" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Port $($p.Port) ($($p.Name)) is OPEN TO PUBLIC INTERNET!" -ForegroundColor Red
        $allPassed = $false
    }
}

Write-Host "`n================================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "  SECURITY VERIFICATION RESULT: 100% SECURE & ISOLATED" -ForegroundColor Green
} else {
    Write-Host "  SECURITY VERIFICATION RESULT: FAILED - OPEN PRIVATE PORTS DETECTED" -ForegroundColor Red
}
Write-Host "================================================================" -ForegroundColor Cyan

exit ($allPassed ? 0 : 1)
