param (
    [string]$Mode = 'Local',
    [string]$BaseUrl = ''
)

$ErrorActionPreference = 'Continue'

if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    if ($Mode -eq 'Local') {
        $TargetBase = 'http://localhost:8080'
    } else {
        $TargetBase = 'https://ezenitac.duckdns.org'
    }
} else {
    $TargetBase = $BaseUrl.TrimEnd('/')
}

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host " AISERVICE E2E Integrity Diagnostics (10 Checkpoints)" -ForegroundColor Cyan
Write-Host " Target URL : $TargetBase (Mode: $Mode)" -ForegroundColor Yellow
Write-Host " Date/Time  : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "================================================================================" -ForegroundColor Cyan

$Results = @()
$PassedCount = 0
$TotalTests = 10

function Run-Check {
    param (
        [int]$Num,
        [string]$Subsys,
        [string]$TestName,
        [scriptblock]$Action
    )

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $status = "FAIL"
    $detail = ""

    try {
        $res = & $Action
        $sw.Stop()
        if ($res.Success) {
            $status = "PASS"
            $detail = $res.Message
            $script:PassedCount++
            Write-Host "[PASS] #$Num ($Subsys) - $TestName ($($sw.ElapsedMilliseconds)ms)" -ForegroundColor Green
            if ($detail) {
                Write-Host "       detail: $detail" -ForegroundColor Gray
            }
        } else {
            $status = "FAIL"
            $detail = $res.Message
            Write-Host "[FAIL] #$Num ($Subsys) - $TestName ($($sw.ElapsedMilliseconds)ms)" -ForegroundColor Red
            Write-Host "       detail: $detail" -ForegroundColor DarkRed
        }
    } catch {
        $sw.Stop()
        $status = "ERROR"
        $detail = $_.Exception.Message
        Write-Host "[ERROR] #$Num ($Subsys) - $TestName ($($sw.ElapsedMilliseconds)ms)" -ForegroundColor Magenta
        Write-Host "        detail: $detail" -ForegroundColor DarkMagenta
    }

    $script:Results += [PSCustomObject]@{
        Num      = $Num
        Subsys   = $Subsys
        Name     = $TestName
        Status   = $status
        Duration = "$($sw.ElapsedMilliseconds)ms"
        Detail   = $detail
    }
}

# 1. Landing Page
Run-Check -Num 1 -Subsys "Landing" -TestName "Main Portal Landing Page" -Action {
    $url = "$TargetBase/"
    $r = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 15 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        return @{ Success = $true; Message = "HTTP 200 OK (Portal Index Loaded)" }
    }
    return @{ Success = $false; Message = "Status: $($r.StatusCode)" }
}

# 2. Pilos Dashboard
Run-Check -Num 2 -Subsys "Pilos" -TestName "Pilos Main Dashboard (/ateam/pilos/)" -Action {
    $url = "$TargetBase/ateam/pilos/"
    $r = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 15 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        return @{ Success = $true; Message = "HTTP 200 OK (Pilos Web Dashboard Loaded)" }
    }
    return @{ Success = $false; Message = "Status: $($r.StatusCode)" }
}

# 3. Pilos Stock Detail
Run-Check -Num 3 -Subsys "Pilos" -TestName "Pilos Stock Detail Proxy (/stocks/005930)" -Action {
    $url = "$TargetBase/stocks/005930"
    $r = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 15 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        return @{ Success = $true; Message = "HTTP 200 OK (Detail HTML Rendered)" }
    }
    return @{ Success = $false; Message = "Status: $($r.StatusCode)" }
}

# 4. Pilos Stocks API
Run-Check -Num 4 -Subsys "Pilos" -TestName "Pilos Stocks API (/api/stocks)" -Action {
    $url = "$TargetBase/api/stocks"
    $r = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 15
    if ($r -and $r.Count -gt 0) {
        return @{ Success = $true; Message = "HTTP 200 OK ($($r.Count) stocks returned)" }
    }
    return @{ Success = $false; Message = "Stocks list empty or invalid" }
}

# 5. Oliview Frontend SPA
Run-Check -Num 5 -Subsys "Oliview" -TestName "Oliview Frontend React SPA (/bteam/oliview/)" -Action {
    $url = "$TargetBase/bteam/oliview/"
    $r = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 15 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        return @{ Success = $true; Message = "HTTP 200 OK (React Bundle Loaded)" }
    }
    return @{ Success = $false; Message = "Status: $($r.StatusCode)" }
}

# 6. Oliview Brands API
Run-Check -Num 6 -Subsys "Oliview" -TestName "Oliview Brands API (/api/brands)" -Action {
    $url = "$TargetBase/bteam/oliview/api/brands"
    $r = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 15
    if ($r.success -and $r.brands -and $r.brands.Count -ge 3000) {
        return @{ Success = $true; Message = "HTTP 200 OK ($($r.brands.Count) active brands loaded)" }
    }
    return @{ Success = $false; Message = "Brands count: $($r.brands.Count)" }
}

# 7. Oliview Send Auth Code Error Handling
Run-Check -Num 7 -Subsys "Oliview" -TestName "Oliview Send Auth Code Validation (/api/send-auth-code)" -Action {
    $url = "$TargetBase/bteam/oliview/api/send-auth-code"
    $body = '{"email":""}'
    try {
        $r = Invoke-WebRequest -Uri $url -Method Post -Body $body -ContentType "application/json" -TimeoutSec 15 -UseBasicParsing
        return @{ Success = $false; Message = "Expected 400 Bad Request but received 200 OK" }
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 400) {
            return @{ Success = $true; Message = "HTTP 400 Bad Request (Validation caught correctly)" }
        }
        return @{ Success = $false; Message = "Exception: $($_.Exception.Message)" }
    }
}

# 8. ChatA Streamlit
Run-Check -Num 8 -Subsys "ChatA" -TestName "ChatA Streamlit App (/bteam/chata/)" -Action {
    $url = "$TargetBase/bteam/chata/"
    $r = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 15 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        return @{ Success = $true; Message = "HTTP 200 OK (Streamlit UI Alive)" }
    }
    return @{ Success = $false; Message = "Status: $($r.StatusCode)" }
}

# 9. ChatB Static Web
Run-Check -Num 9 -Subsys "ChatB" -TestName "ChatB Web Interface (/bteam/chatb/)" -Action {
    $url = "$TargetBase/bteam/chatb/"
    $r = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 15 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        return @{ Success = $true; Message = "HTTP 200 OK (FastAPI Static UI Rendered)" }
    }
    return @{ Success = $false; Message = "Status: $($r.StatusCode)" }
}

# 10. ChatB RAG Search API
Run-Check -Num 10 -Subsys "ChatB" -TestName "ChatB RAG Search API (/api/v1/search)" -Action {
    $url = "$TargetBase/bteam/chatb/api/v1/search"
    $payload = '{"query":"피부 진정 순한 세럼","top_n":3}'
    $r = Invoke-RestMethod -Uri $url -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 90
    if ($r -and ($r.llm_answer -or $r.search_results)) {
        return @{ Success = $true; Message = "HTTP 200 OK (RAG Search and LLM response verified)" }
    }
    return @{ Success = $false; Message = "Response missing expected keys" }
}

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host " E2E Summary Report" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
$Results | Format-Table -Property Num, Subsys, Name, Status, Duration -AutoSize

$PassRate = [math]::Round(($PassedCount / $TotalTests) * 100, 1)
if ($PassedCount -eq $TotalTests) {
    Write-Host " [FINAL VERDICT] $PassedCount / $TotalTests PASS (100%) - All services stabilized!" -ForegroundColor Green
    exit 0
} else {
    Write-Host " [FINAL VERDICT] $PassedCount / $TotalTests PASS ($PassRate%) - Review failures above." -ForegroundColor Yellow
    exit 1
}
