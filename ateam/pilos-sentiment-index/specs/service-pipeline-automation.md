# 서비스 최상위 자동화 실행기 기능 명세

## 상태

- 구현 상태: 배치·CLI, 단계 함수 조합, 중복 실행 잠금, 단계 실패 중단,
  최상위 로그와 DB 실행 상태 기록 구현 완료
- 통합 상태: `main@f80fdc2` 반영 완료(PR #14, #15, #17)
- 검증 상태: 기능별 자동 테스트와 실제 실행 ID 1·2 확인. 2026-08-11
  전체 suite는 챗봇 계약 drift로 실패했지만 `test_chat*` 제외 375개는 통과
- 실제 운영 실행: 2026-08-10 실행 ID 1·2가 `completed`로 종료됨

## 목적

독립 실행 가능한 기능별 `run_*` 함수를 정해진 순서로 호출하고, 한 번의
서비스 갱신 실행을 하나의 성공·실패 결과로 관측하게 한다.

## 실행 방법

Windows 작업 스케줄러는 저장소 루트의 배치 파일을 호출한다.

```text
run_service_pipeline.bat
```

Python CLI를 직접 실행할 수도 있다.

```powershell
.\.venv\Scripts\python.exe -m pilos.jobs.run_service_pipeline --target all
.\.venv\Scripts\python.exe -m pilos.jobs.run_service_pipeline --target sk
.\.venv\Scripts\python.exe -m pilos.jobs.run_service_pipeline --target others
```

배치 파일과 CLI는 같은 최상위 `run_service_pipeline()`을 사용한다. 하위 기능은
독립 CLI를 유지하지만 최상위 실행기는 subprocess가 아니라 Python 함수를
호출해 반환값과 예외를 직접 판단한다.

## 단계 순서

```text
comment_collection
→ comment_preprocessing
→ comment_tokenization
→ daily_document
→ supply_demand
→ sentiment_inference
→ llm_report_v13
```

- 앞 단계가 실패하거나 부분 실패를 반환하면 뒤 단계로 진행하지 않는다.
- 토큰화는 현재 `TOKENIZER_VERSION`, 추론은 활성 Positive·Negative 모델
  identity를 사용한다.
- 모델 학습과 calibration 생성은 주기 운영 파이프라인에 포함하지 않는다.

## 실행 기간과 멱등성

- 분석 운영 시작일은 `2026-07-25`, 종료일은 실행 당일 KST다.
- 각 단계는 자신의 미처리 대상만 조회한다.
- 기존 추론 결과는 `(daily_document_id, artifact_id)` 기준으로 UPDATE하지 않는다.
- v13은 동일 identity에서 허용된 `estimated → confirmed` 또는 최신 estimated
  갱신만 수행하며 `confirmed → estimated`로 강등하지 않는다.
- 처리 대상 0건은 실패가 아니라 정상 성공이다.

## 중복 실행

프로세스 단위 비차단 파일 잠금을 사용한다. 이전 실행이 10분을 넘겨 다음
스케줄 시각까지 진행 중이면 새 실행은 겹쳐 수행하지 않는다. 이전 실행이
끝난 다음 스케줄 시각에는 다시 정상 실행할 수 있다.

작업 스케줄러도 `작업이 이미 실행 중이면: 새 인스턴스 실행 안 함`으로
설정해 이중으로 보호한다.

## 설정 로드

최상위 실행기는 단계 모듈을 import하기 전에 저장소 루트 `.env`를 읽는다.
수집 비식별화 솔트와 DB·외부 서비스 설정은 저장소에 커밋하지 않는다.
필수 설정이 없으면 해당 단계에서 실패하며 뒤 단계를 실행하지 않는다.

## 로그와 DB 상태

최상위 실행기 자체의 단계 시작·종료·요약은 다음 파일에 기록한다.

```text
logs/service_pipeline_YYYY-MM-DD.log
```

하위 실행기의 공용 로그를 복사하지 않으며 최상위에서 받은 요약과 예외만
기록한다. 한 실행은 `service_pipeline_run` 한 행으로 추적한다.

- 시작 시 `running` INSERT
- 종료 시 같은 행을 `completed` 또는 `failed`로 UPDATE
- 단계별 상태·건수·경과 시간은 JSON 요약으로 저장
- Flask `GET /api/pipeline/status`가 최신 행의 안전한 공개 필드를 반환

## 실제 실행 근거

2026-08-10 KST 기준:

| 실행 ID | 결과 | 경과 | 주요 결과 |
|---|---|---:|---|
| 1 | completed | 2,083초 | 수집 15,283, 전처리·토큰화 14,227, 일별 문서 10, 추론 20, 신규 v13 20(LLM 18·deterministic 2) |
| 2 | completed | 95.188초 | 수집 438, 전처리·토큰화 384, 일별 문서·추론 신규 0, 기존 v13 100 |

두 번째 실행의 신규 일별 문서 0건은 당일 장 마감 기준 시각 이후 댓글이어서
정상이다. 이후 실행도 미처리 대상 0건을 성공으로 종료한다.

## 관련 코드와 정본

- [`run_service_pipeline.bat`](../run_service_pipeline.bat)
- [`pilos/jobs/run_service_pipeline.py`](../pilos/jobs/run_service_pipeline.py)
- [`pilos/storage/pipeline_run_db.py`](../pilos/storage/pipeline_run_db.py)
- [`pilos/service/pipeline_status_service.py`](../pilos/service/pipeline_status_service.py)
- [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
- [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md)
- [`docs/DECISIONS.md`](../docs/DECISIONS.md)
