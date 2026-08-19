# Technical Research & Architectural Decisions: 012-restore-pilos-pipeline

**Feature**: [`012-restore-pilos-pipeline`](file:///c:/AISERVICE/specs/012-restore-pilos-pipeline/spec.md)  
**Date**: 2026-08-19  
**Status**: Completed  

---

## 1. 근본 원인 분석 및 의존성 격리 조사 (Root Cause & Isolation Research)

### 1.1 파이프라인 연쇄 장애 메커니즘
- **현상**:
  - `pilos-worker`는 10분마다 `run_service_pipeline.py`를 실행함.
  - 1~4단계(댓글 증분 수집, 전처리, Kiwi 토큰화, 일별 문서 생성)는 8월 19일까지 정상 수행되어 DB에 매일 수천 건의 댓글이 축적됨.
  - 5단계인 `collect_supply_demand.py`의 `run_supply_demand_collection`이 장중 또는 장 마감 후 키움 OpenAPI 키 부재 시 `ValueError: 키움 App Key와 Secret Key가 필요합니다.`를 발생시킴.
  - 최상위 실행기(`run_service_pipeline.py`)가 5단계 예외를 치명적 오류(`failed`)로 판단하여 파이프라인을 중단하고 프로세스를 종료함.
  - 이로 인해 6단계(`model_inference`) 및 7단계(`llm_report`)가 8월 12일 이후 단 한 번도 호출되지 못함.
- **결정 (Decision)**:
  - `collect_supply_demand.py` 내부에서 API 인증키 부재 또는 외부 통신 예외 발생 시 `JobStatus.SKIPPED` 및 `JobReason.NO_CREDENTIALS` / `JobReason.API_UNAVAILABLE` 결과 객체를 반환하도록 우아한 스킵(Graceful Fallback)을 구현.
  - `run_service_pipeline.py`에서 수급 단계의 `SKIPPED` 상태를 정상 상태로 인식하고 후속 모델 추론 및 보고서 생성 단계로 안전하게 진행하도록 보장.

---

## 2. LLM 서빙 게이트웨이 및 GPU VRAM 최적화 조사 (VRAM & Lightweight Model)

### 2.1 GPU 메모리 예산 분석 (GTX 1070 8GB 기준)
- **현재 점유 분석**:
  - 4B 모델(`qwen3.5-4b`): 모델 가중치 2.8GB + 4096 컨텍스트 KV 캐시 + CUDA 컨텍스트 = 약 5.5GB
  - Windows 호스트 환경(DWM, 데스크톱 UI): 약 1.8~2.0GB
  - 총합: 약 7.8GB (95% 포화)
- **경량 모델(`qwen3.5-2b`) 전환 시 메모리 프로파일**:
  - 모델 가중치: 1.6GB (Q4_K_M 양자화 GGUF)
  - 4096 컨텍스트 KV 캐시 + CUDA 컨텍스트: 약 1.2GB
  - 총 모델 VRAM 점유량: **약 2.8 ~ 3.0GB**
  - OS 점유 포함 총합: **약 4.8GB** (GTX 1070 기준 3.2GB 이상의 여유 VRAM 확보)
- **결정 (Decision)**:
  - `model_gateway/config/server_config.json`의 기본 모델을 `qwen3.5-2b`로 설정하고 `vram_limit_mb`를 4000으로 조정.
  - `docker-compose.yml`의 서비스 환경변수(`SYNTHESIS_LLM_MODEL`, `FAST_LLM_MODEL`, `CHAT_LLM_MODEL`, `REPORT_LLM_MODEL`)를 `qwen3.5-2b`로 통일.

---

## 3. 누락 구간(8월 12일~현재) 소급 생성(Backfill) 전략 조사

### 3.1 소급 대상 데이터 현황
- `preprocessed_comment`: 8월 12일 ~ 19일 전 종목 댓글 정상 수집 완료.
- `daily_document`: 8월 12일 ~ 19일 일별 문서 정상 적재 완료.
- `sentiment_index_result`: 8월 11일까지 산출됨 → **8월 12일~19일 (8일치 * 10개 종목 = 약 80건) 미산출 상태**.
- `llm_report`: 8월 11일까지 산출됨 → **8월 12일~19일 (8일치 * 10개 종목 = 약 80건) 미생성 상태**.

### 3.2 소급 실행 방안
- **추론 소급**: `run_database_inference(inference_start_date=date(2026, 8, 12), inference_end_date=date(2026, 8, 19))` 호출로 Ridge 감성 지표 일괄 산출.
- **보고서 소급**: `run_pending_llm_report_generation(report_start_date=date(2026, 8, 12), report_end_date=date(2026, 8, 19))` 호출로 LLM 시장 해설 보고서 일괄 합성.
- **단일 종목 예외 격리**: LLM 호출 시 특정 종목에서 타임아웃/오류 발생 시 최대 2회 재시도 후 해당 종목만 격리하고 나머지 9개 종목은 정상 생성 완료.

---

## 4. 아키텍처 및 복원력 검증 종합 요약

| 검토 항목 | 채택 방안 | 기각된 대안 및 사유 |
|---|---|---|
| 수급 데이터 API 부재 처리 | `collect_supply_demand`에서 Graceful Fallback (`JobStatus.SKIPPED`) 반환 | 예외 강제 발생 유지: 파이프라인 연쇄 중단 유발로 기각 |
| LLM 기본 모델 | `qwen3.5-2b` 경량 모델 기본화 (< 3.0GB VRAM) | 4B 모델 유지: 8GB VRAM 환경에서 메모리 여유 부족으로 기각 |
| 누락 데이터 복구 | 8/12~현재 전수 자동 소급(Backfill) | 수동 건별 복구: 운영 비용 과다 및 데이터 공백 장기화로 기각 |
| LLM 실패 격리 | 최대 2회 재시도 후 개별 격리 | 파이프라인 전체 중단: 단일 장애가 전체에 전파되므로 기각 |
