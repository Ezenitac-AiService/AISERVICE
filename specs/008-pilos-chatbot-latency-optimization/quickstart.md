# Quickstart & Verification Guide: PILOS 챗봇 지연 해소 및 스트리밍 검증

## 1. 사전 준비 (Prerequisites)
- A-Team Pilos 컨테이너 또는 로컬 Flask 서버 실행
- Nginx 통합 게이트웨이 실행

---

## 2. 검증 시나리오 (Validation Scenarios)

### 시나리오 1: 15개 정본 지식 블록 고속 캐시 응답 검증 (목표: < 50ms)
등록된 서비스 지식 질문(`service_interpretation`, `service_overview`, `service_models` 등)을 호출하여 GPU 부하 없이 즉시 완결 응답이 반환되는지 확인합니다.

```powershell
# PowerShell 검증 요청
$payload = @{
    block_key = "service_interpretation"
} | ConvertTo-Json

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$response = Invoke-RestMethod -Uri "http://localhost:8080/api/chat" -Method Post -ContentType "application/json" -Body $payload
$stopwatch.Stop()

Write-Host "소요 시간: $($stopwatch.ElapsedMilliseconds) ms"
Write-Host "상태: $($response.status)"
Write-Host "답변 미리보기: $($response.answer.Substring(0, 50))..."
```
- **기대 결과**: 소요 시간 50ms 미만, `status == "ready"`, 올바른 마크다운 및 출처 표시.

---

### 시나리오 2: 동적 LLM 답변 실시간 SSE 스트리밍 검증
동적 분석 요청 시 첫 토큰이 수 초 내에 방출되고 SSE 이벤트 스트림으로 점진 전달되는지 검증합니다.

```bash
# curl 기반 SSE 청크 수신 확인
curl -N -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"block_key": "stock_summary", "stock_code": "005930", "model_date": "2026-08-14"}'
```
- **기대 결과**: 
  - `data: {"type": "token", "delta": "..."}` 이벤트가 실시간으로 수신됨
  - 마지막에 `data: {"type": "done", ...}` 및 `data: [DONE]`으로 정상 종료됨

---

### 시나리오 3: 고정 종목 상세 경로 (`/api/stocks/{code}/chat`) 404 방어 검증
종목 상세 화면의 고정 종목 API 경로가 Nginx 게이트웨이 및 백엔드에서 404 없이 정상 라우팅되는지 확인합니다.

```powershell
$payload = @{
    block_key = "service_models"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8080/api/stocks/005930/chat" -Method Post -ContentType "application/json" -Body $payload
Write-Host "종목 고정 챗봇 응답 성공 여부: $(if ($response) {'PASS'} else {'FAIL'})"
```
- **기대 결과**: 404 에러 없이 200 OK 수신 및 답변 정상 출력.

---

### 시나리오 4: 자동화 단위 및 통합 테스트 스위트 실행
```powershell
# A-Team 테스트 실행
uv run pytest ateam/pilos-sentiment-index/tests/test_chatbot_service.py -v
uv run pytest ateam/pilos-sentiment-index/tests/test_rag_service.py -v
```
- **기대 결과**: 모든 캐시, 스트리밍, 타임아웃 테스트 **100% PASS**.
