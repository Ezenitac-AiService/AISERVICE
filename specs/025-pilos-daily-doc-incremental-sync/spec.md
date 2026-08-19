# Feature Specification: Pilos 일별 문서 증분 집계 및 보고서 자동 갱신 동기화 (pilos-daily-doc-incremental-sync)

**Feature Branch**: `025-pilos-daily-doc-incremental-sync`

**Created**: 2026-08-20

**Status**: Draft

**Input**: User description: "댓글이 수집되면 보고서를 다시 생성해야지, 보고서 생성 작업은 언제 언제 하게 되어있어? 작업을 위한 스펙을 작성해줘 네가 분석한게 맞는지 C:\AISERVICE\ateam\pilos-sentiment-index\docs 의 원장도 확인해보고"

---

## 1. 개요 및 배경 (Overview & Context)

A-Team PILOS 서비스는 10개 주요 종목의 실시간 종목 토론방 댓글을 10분 주기로 수집하여, 장 마감 전(15:30) 댓글 코퍼스를 기반으로 일별 문서(`daily_document`)를 빌드하고 Ridge 감성 지수 추론 및 LLM 시장 해설 보고서를 자동 생성합니다.

`docs/work/archive/이주광.md` 및 시스템 설계 원장에 따르면:
1. **"신규 댓글이 추가되면 그 시점까지의 장 마감 전 댓글 전체로 새 문서를 만든다."**
2. **"10분 자동화에서 같은 날짜의 스냅샷과 매핑 데이터가 증가하는 저장비용은 서비스 목적을 위해 감수한다."**
3. **"후속 추론과 화면은 같은 종목·날짜의 최신 `daily_document_id`를 현재 상태로 사용한다."**
4. **"새 `daily_document_id`에는 새 보고서 행을 INSERT/UPDATE한다."**

그러나 현재 `daily_document_db.py` 내부의 대상 조회 쿼리(`select_pending_daily_document_targets`)에 `AND NOT EXISTS (SELECT 1 FROM daily_document ...)` 조건이 포함되어 있어, 자정(00:03) 최초 배치에서 1~2건의 극초기 댓글로 일별 문서가 한 번 생성되고 나면, 이후 낮 동안 수만 건의 댓글이 추가 수집되어도 일별 문서가 갱신되지 않고 후속 보고서 재생성도 차단되는 결함이 확인되었습니다.

본 기능 명세는 신규 댓글 수집 시 일별 문서 스냅샷이 누적 갱신되고, 변경된 데이터에 따라 Ridge AI 모델 추론 및 LLM 보고서가 10분 주기 파이프라인 내에서 정상적으로 자동 갱신되도록 보장하는 것을 목표로 합니다.

---

## Clarifications

### Session 2026-08-20
- Q: 당일 장중(09:00~15:30) 실시간으로 댓글이 추가 수집되어 일별 문서가 10분마다 갱신될 때, LLM 시장 해설 보고서(`llm_report`)의 LLM 호출 및 갱신 방식은 어떻게 운영할까요? → A: Option A (장중 10분 주기에는 지표/수급 추정 보고서를 즉시 갱신하고, 장 마감 확정 시점(15:30) 및 주요 신호 변경 시 정식 LLM 보고서를 생성하여 리소스 부하를 최적화함)

---

## 2. 사용자 시나리오 및 수용 기준 (User Scenarios & Testing)

### User Story 1 - 신규 댓글 수집에 따른 일별 문서 스냅샷 누적 갱신 (Priority: P1)

시스템 운영자 및 사용자는 10분 주기 크롤러를 통해 새로운 종목 댓글이 DB에 들어왔을 때, 해당 종목·날짜의 장 마감 전(15:30) 누적 댓글 전체가 포함된 최신 일별 문서 스냅샷이 자동으로 빌드되기를 원한다.

**Why this priority**: 일별 문서가 최신 수집 댓글을 반영하지 못하면 이후 모든 AI 감성 분석과 LLM 보고서의 근거 데이터가 왜곡되므로 최우선 구현되어야 한다.

**Independent Test**: 미반영 댓글이 존재하는 종목에 대해 `run_daily_document_building()`을 실행했을 때, 새로운 `daily_document_id`가 생성되고 최신 `comment_count`와 `tfidf_text`가 적재되는지 검증한다.

**Acceptance Scenarios**:
1. **Given** 특정 종목·날짜에 아직 일별 문서에 포함되지 않은 토큰화 댓글이 존재하는 상태에서,
   **When** 4단계 일별 문서 생성 작업이 실행되면,
   **Then** 해당 시점까지의 장 마감 전 누적 댓글 전체로 구성된 새 `daily_document` 스냅샷이 생성된다.
2. **Given** 해당 종목·날짜에 새로운 댓글이 추가로 들어오지 않은 상태에서,
   **When** 4단계 일별 문서 생성 작업이 실행되면,
   **Then** 불필요한 중복 문서를 생성하지 않고 0건으로 정상 통과한다.

---

### User Story 2 - 최신 일별 문서 기반 AI 감성 모델 추론 및 LLM 보고서 자동 갱신 (Priority: P1)

사용자는 대시보드 및 상세 페이지에서 최신으로 누적된 댓글 데이터 기반의 Ridge 감성 지표(긍/부정 점수, 키워드 기여도)와 최신 LLM 해설 보고서를 실시간으로 확인할 수 있어야 한다.

**Why this priority**: 댓글 수집 및 일별 문서가 갱신되었을 때 최종 산출물인 지표와 보고서가 함께 갱신되어야 서비스의 실시간 인사이트 가치가 제공된다.

**Independent Test**: 새로운 일별 문서가 생성된 후 모델 추론(`run_database_inference`) 및 LLM 보고서 생성(`run_pending_llm_report_generation`)을 순차 실행하여 최신 `daily_document_id`와 연결된 결과가 적재되는지 확인한다.

**Acceptance Scenarios**:
1. **Given** 새로운 `daily_document` 스냅샷이 생성된 상태에서,
   **When** 모델 추론 단계가 실행되면,
   **Then** 최신 `daily_document_id`에 대해 긍정/부정 Ridge 모델 분석 결과가 `sentiment_index_result`에 적재된다.
2. **Given** 최신 모델 추론 결과와 수급 상태가 준비된 상태에서,
   **When** LLM 보고서 생성 단계가 실행되면,
   **Then** 장중 10분 주기에서는 추정 보고서(`estimated`)를 즉시 갱신하고, 장 마감(15:30) 및 주요 신호 변경 시 정식 LLM 해설 보고서(`ready`)를 생성/갱신한다.

---

### User Story 3 - 기존 누락된 대량 댓글 코퍼스 일괄 동기화 (Priority: P2)

운영자는 버그로 인해 1~2개 댓글 상태로 멈춰있던 과거/당일(예: 8월 19일 3.6만 건, 8월 20일 새벽 데이터)의 댓글들이 파이프라인 1회 가동만으로 완전하게 동기화되기를 원한다.

**Why this priority**: 기존에 수집되어 DB에 쌓여있던 유의미한 수만 건의 데이터가 즉시 대시보드에 온전히 반영되어 분석 신뢰도를 회복해야 한다.

**Independent Test**: 수정된 쿼리 상태에서 전체 파이프라인 1회 실행 후 8월 19일 및 8월 20일의 `daily_document.comment_count`가 실제 수집 건수와 일치하는지 확인한다.

**Acceptance Scenarios**:
1. **Given** 8월 19일에 수집된 35,999건의 미반영 댓글이 DB에 남아있는 상태에서,
   **When** 파이프라인이 1회 순차 실행되면,
   **Then** 8월 19일 각 종목별 일별 문서가 수천~수만 건의 실제 댓글 수로 갱신되고 대시보드에 즉시 반영된다.

---

### Edge Cases

- **장 마감 이후(15:30 이후) 야간 댓글 유입**:
  - 장 마감(15:30) 이후에 등록된 댓글은 당일 일별 문서(15:30 기준)에는 포함되지 않으며, 익일 일별 문서 집계 대상으로 안전하게 분리 관리된다.
- **댓글이 0건인 종목/휴일**:
  - 댓글 유입이 없는 날짜나 종목은 대상 목록에 잡히지 않으며 예외 없이 정상 pass 처리된다.
- **동일한 댓글 상태에서 재실행(Idempotency)**:
  - 이미 모든 토큰이 일별 문서에 매핑되어 있는 경우(`document_hash` 동일), 중복 INSERT 없이 기존 ID를 재사용하거나 건너뛴다.

---

## 3. 요구사항 (Requirements)

### Functional Requirements

- **FR-001**: 시스템은 `tokenized_comment` 중 아직 `daily_document_comment`에 매핑되지 않은 댓글이 존재하는 `(stock_id, model_date)` 대상을 정확히 감지해야 한다 (`daily_document_db.select_pending_daily_document_targets`).
- **FR-002**: 일별 문서 대상 조회 쿼리는 기존에 `daily_document` 레코드가 존재하더라도, 미반영 신규 토큰이 남아있다면 대상을 제외하지 않고 반환해야 한다.
- **FR-003**: 일별 문서 생성기(`run_daily_document_building`)는 감지된 대상에 대해 당일 장 마감 전(15:30)까지의 전체 토큰 댓글을 모아 신규 `daily_document` 스냅샷을 생성하고 매핑을 적재해야 한다.
- **FR-004**: 모델 추론기(`run_database_inference`)는 각 종목·날짜별 가장 최신의 `daily_document_id`를 대상으로 Ridge 회귀 분석을 수행해야 한다.
- **FR-005**: LLM 보고서 생성기(`run_pending_llm_report_generation`)는 최신 `daily_document_id`와 추론 결과를 감지하여 장중 10분 주기에서는 추정 보고서(`estimated`)를 즉시 갱신하고, 장 마감(15:30) 및 주요 신호 변경 시 정식 LLM 보고서를 갱신해야 한다.
- **FR-006**: 웹 API(`sentiment_index_service`, `app.py`) 및 메인 대시보드는 종목별 가장 최신 `daily_document_id`의 댓글 수(`comment_count`)와 분석 상태를 클라이언트에 반환해야 한다.

---

## 4. 핵심 데이터 엔티티 (Key Entities)

- **`tokenized_comment`**: 형태소 분석 및 토큰화가 완료된 개별 댓글 레코드 (`tokenized_comment_id`, `preprocessed_comment_id`, `tokens`, `tokenizer_version`).
- **`daily_document`**: 특정 종목·날짜의 장 마감 전(15:30) 누적 토큰을 결합한 모델 입력 문서 스냅샷 (`daily_document_id`, `stock_id`, `model_date`, `comment_count`, `document_hash`).
- **`daily_document_comment`**: 일별 문서 스냅샷과 개별 토큰화 댓글 간의 1:N 매핑 관계 (`daily_document_comment_id`, `daily_document_id`, `tokenized_comment_id`, `sequence_number`).
- **`sentiment_index_result`**: 일별 문서 스냅샷에 대한 Ridge 긍정/부정 모델 추론 결과 (`sentiment_index_result_id`, `daily_document_id`, `artifact_id`, `supply_demand_association_score`, `keywords`).
- **`llm_report`**: 일별 문서 및 모델 추론 지표를 기반으로 LLM이 작성한 종합 시장 해설 보고서 (`llm_report_id`, `stock_id`, `model_date`, `daily_document_id`, `input_hash`, `status`, `report_json`).

---

## 5. 성공 기준 (Success Criteria)

- **SC-001**: 8월 19일 기준 대시보드 표시 댓글 수가 1~2개에서 실제 수집된 장 마감 전 누적 수치(삼성전자 6,900+건, SK하이닉스 10,000+건 등)로 100% 정상 갱신된다.
- **SC-002**: 10분 주기 워커 데몬 실행 시, 신규 댓글이 수집되면 다음 주기에서 일별 문서 생성(`daily_document`) ➔ 모델 추론 ➔ LLM 보고서 재생성이 중단 없이 순차 완료된다.
- **SC-003**: 신규 댓글이 없는 주기에서는 불필요한 중복 문서나 LLM 호출 없이 대상 0건(`existing`)으로 안전하게 유지된다.
- **SC-004**: 전체 단위/통합 테스트 스위트가 결함 없이 통과한다.

---

## 6. 가설 및 제약 사항 (Assumptions & Constraints)

- **원장 준수 (Immutability)**: 기존 `daily_document`의 행을 `UPDATE`하여 과거 이력을 유실시키지 않고, 새 스냅샷을 `INSERT`하는 아키텍처 원칙을 엄격히 준수한다.
- **성능 및 인덱스**: `daily_document_comment`의 `tokenized_comment_id` 인덱스를 효율적으로 활용하여 400만 건 이상의 대용량 테이블에서도 대상 판정 쿼리가 수 밀리초(ms) 내에 즉시 완료되도록 최적화한다.
