# Quickstart Validation Guide: 012-restore-pilos-pipeline

**Feature**: [`012-restore-pilos-pipeline`](file:///c:/AISERVICE/specs/012-restore-pilos-pipeline/spec.md)  
**Date**: 2026-08-19  
**Status**: Specified  

---

## 1. 개요 (Overview)

본 가이드는 PILOS 파이프라인의 **수급 데이터 결함 허용(Graceful Fallback)**, **경량 LLM(`qwen3.5-2b`) VRAM 최적화**, **8월 12일~현재 누락 보고서 소급 생성(Backfill)** 및 **정기 파이프라인 정상 가동**을 단계별로 검증하는 실행 절차를 제공합니다.

---

## 2. 검증 절차 (Validation Steps)

### Step 1. 단위 및 통합 테스트 실행 (Unit & Regression Tests)
```bash
# 1. 수급 수집 Fallback 및 파이프라인 통합 테스트
docker exec pilos-web pytest /app/tests/test_supply_demand_job.py -v
docker exec pilos-web pytest /app/tests/test_pipeline_status.py -v
```
- **예상 결과**: 키움 API Key 미설정 시 `JobStatus.SKIPPED` 반환 및 파이프라인이 중단되지 않고 100% PASS.

---

### Step 2. LLM 게이트웨이 경량 모델(`qwen3.5-2b`) 서빙 및 VRAM 검증
```bash
# 1. 모델 게이트웨이 헬스체크 및 모델 확인
docker exec pilos-web python -c "import urllib.request; print(urllib.request.urlopen('http://vllm-serv-gateway:8081/v1/models').read().decode())"

# 2. 호스트 GPU VRAM 점유량 확인 (Windows PowerShell)
nvidia-smi
```
- **예상 결과**: `qwen3.5-2b` 모델 응답 확인 및 GPU VRAM 점유량이 4GB 이하로 안정화됨.

---

### Step 3. 8월 12일 ~ 현재 누락 데이터 소급 생성 (Backfill Execution)
```bash
# 1. 8월 12일 ~ 19일 감성 모델 추론 실행
docker exec pilos-worker python -m pilos.jobs.predict_model --start-date 2026-08-12 --end-date 2026-08-19

# 2. 8월 12일 ~ 19일 AI 시장 해설 보고서 일괄 소급 생성
docker exec pilos-worker python -m pilos.jobs.generate_llm_reports --start-date 2026-08-12 --end-date 2026-08-19
```
- **예상 결과**: 10개 전 종목에 대해 8월 12일~19일의 `sentiment_index_result` 및 `llm_report` 레코드가 100% 생성 완료됨.

---

### Step 4. 최상위 서비스 파이프라인 1회 전체 실행 검증
```bash
# 최상위 7단계 파이프라인 단독 실행
docker exec pilos-worker python -m pilos.jobs.run_service_pipeline
```
- **예상 결과**: `status: "completed"`, `stopped_stage: null`, 7개 단계 모두 정상 처리 또는 스킵 완료.

---

### Step 5. 웹 대시보드 최종 사용자 검증 (E2E Web Verification)
1. 브라우저에서 `http://localhost:8080/ateam/pilos/` 접속.
2. 종목 선택 (예: 현대차 `005380`, SK하이닉스 `000660`, 삼성전자 `005930`).
3. 날짜 선택기에서 `2026-08-12` ~ `2026-08-19` 일자를 선택.
4. 시장 해설 보고서 본문, 긍정/부정 키워드 기여도 및 감성 점수가 "추론 대기 중" 없이 즉시 정상 렌더링되는지 확인.
