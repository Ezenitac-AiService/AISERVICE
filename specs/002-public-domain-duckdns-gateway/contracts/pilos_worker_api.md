# Contract: A-Team Pipeline Worker & Status Contracts

**Component**: `pilos_worker` & `pilos-web`  
**Database**: `pilos-db:3306/pilos_v2`  
**Spec Reference**: [spec.md](file:///c:/AISERVICE/specs/002-public-domain-duckdns-gateway/spec.md) (FR-008 ~ FR-010)

---

## 1. Worker Lifecycle & Execution Daemon

- **Entrypoint Module**: `pilos.jobs.worker_daemon`
- **Environment Configuration**:
  - `PIPELINE_INTERVAL_SECONDS`: 정기 실행 주기 (초 단위, 기본값: `600`)
  - `DB_HOST`: `pilos-db`
  - `DB_PORT`: `3306`
  - `DB_NAME`: `pilos_v2`
  - `LLM_BASE_URL`: `http://vllm-serv-gateway:8081/v1`
  - `REPORT_LLM_MODEL`: `qwen3.5-4b`
- **Execution Workflow**:
  ```text
  1. 루프 시작 (interval 초 대기)
  2. pilos-sentiment-index-service-pipeline.lock 파일 락 획득 시도
  3. service_pipeline_run 테이블에 status='running' 레코드 삽입
  4. 순차 단계 실행:
     - 증분 댓글 수집 (incremental_comments)
     - 원본 파일 전처리 (preprocess_comments)
     - Kiwi 형태소 토큰화 (tokenize_comments)
     - 일별 문서 집계 (build_daily_documents)
     - 개인 수급 수집 (collect_supply_demand)
     - Ridge v4 감정 모델 추론 (predict_model)
     - v13 일별 LLM 보고서 생성 (generate_llm_reports)
  5. service_pipeline_run 테이블에 status='completed' (또는 'failed') 및 stage_summary 업데이트
  6. 락 해제 및 다음 주기 대기
  ```

---

## 2. Web Status API Contract (`GET /api/pipeline/status`)

### Response (200 OK)
```json
{
  "service_pipeline_run_id": 42,
  "status": "completed",
  "target": "all_stocks",
  "tokenizer_version": "kiwi_v1",
  "operation_start_date": "2026-08-17",
  "started_at": "2026-08-17T09:00:00.123456",
  "finished_at": "2026-08-17T09:01:15.654321",
  "elapsed_seconds": 75.531,
  "stopped_stage": null,
  "failure_type": null,
  "failure_message": null,
  "stages": {
    "incremental_comments": { "status": "completed", "elapsed_seconds": 12.4 },
    "preprocess_comments": { "status": "completed", "elapsed_seconds": 3.1 },
    "tokenize_comments": { "status": "completed", "elapsed_seconds": 5.8 },
    "build_daily_documents": { "status": "completed", "elapsed_seconds": 2.2 },
    "collect_supply_demand": { "status": "completed", "elapsed_seconds": 1.5 },
    "predict_model": { "status": "completed", "elapsed_seconds": 8.7 },
    "generate_llm_reports": { "status": "completed", "elapsed_seconds": 18.3 }
  }
}
```

### Initial State (No Runs Yet)
```json
{
  "status": "not_started"
}
```
