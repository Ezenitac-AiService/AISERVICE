# Quickstart: 007-pilos-report-data-restoration

## Verification Steps

### 1. Database Cleanup & Resilient Query Validation
Execute the cleanup and test script against `pilos-db`:
```bash
docker compose exec pilos_web python -c "
from datetime import date
from pilos.service.llm_report_service import get_llm_report_for_display
res = get_llm_report_for_display('005380', date(2026, 8, 11))
print('STATUS:', res.get('status'))
print('COMMENTARY PREVIEW:', res.get('market_commentary', '')[:100])
assert res.get('status') == 'ready'
"
```

### 2. HTTP Endpoint Verification
```bash
curl -i "http://localhost:8080/api/stocks/005380/llm-reports?model_date=2026-08-11"
```
**Expected Response**: HTTP 200 OK with `status: "ready"` and populated `market_commentary`.

### 3. Full E2E Service Integrity Check
```powershell
powershell -ExecutionPolicy Bypass -File specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1 -Mode Local
```
**Expected Outcome**: 10/10 PASS (100%).
