# Feature Specification: Oliview B-Team 통합 아키텍처 실운영 전환 및 컷오버 (Production Cutover & Transition)

**Feature Branch**: `042-bteam-production-cutover`  
**Created**: 2026-08-28  
**Status**: Clarified & Adversarially Hardened (Round 1 Approved)  
**Input**: User description: "바로 앞 스펙으로 구축된 구조로 전환하는 작업 내용을 위한, 분석, 검토, 계획, 리서치를 진행하고 스펙 작성"

---

## Clarifications & Design Decisions *(speckit-clarify & Multi-Persona Hardening)*

### Session 2026-08-28

- **Q1 (무중단 컷오버 범위 및 드레인 정책)**: 컷오버 시 '무중단(0초 다운타임)' 보장의 범위를 어떻게 정의하고 적용할 것인가?
  - **결정**: 사용자 대면 서비스(Dashboard UI/API, ChatA, ChatB)는 Nginx의 graceful reload(`nginx -s reload`) 및 `proxy_next_upstream` 3회 재시도 메커니즘을 통해 **0초 다운타임(HTTP 200 유지, 외부 5xx 0건)**으로 지속 서빙하며, 백그라운드 데이터 수집/인덱싱 파이프라인만 최종 델타 동기화 및 fresh backup을 위해 **최대 15~30초의 Graceful Drain 윈도우(현재 1개 500건 청크 커밋 완료 후 정지)**를 허용한다.
- **Q2 (실증 환경 최적화 레거시 자산 보존 정책)**: 24시간 안전 관찰(Soak) 통과 후 레거시 Blue 폐기 시, 기존 Docker 데이터 볼륨과 백업 스냅샷의 보존 정책을 어떻게 결정할 것인가?
  - **결정**: 현재 서버가 실증/테스트(PoC/DEMO) 모드임을 고려하여 무기한 영구 보존 대신, **비상 롤백 안전망을 완벽히 확보할 수 있는 7일 보존 기간(7-Day Retention Window)**을 적용한다. 24시간 Soak 통과 및 외부 승인 시 Blue 컨테이너는 중지하고 레거시 소스는 아카이브로 이동하되, 데이터 볼륨(`bteam_mysql_data` 등) 및 백업 스냅샷은 7일 동안 보존한 후 정리한다.
- **Q3 (환경별 운영 모드 이원화 - 헌법 원칙 VI)**: 단일 GPU(GTX 1070) 로컬 환경과 상용(PRODUCTION) 환경 간의 컷오버 사전 조건 충돌을 어떻게 처리할 것인가?
  - **결정**: `APP_RUN_MODE=DEMO`에서는 단일 GPU 및 로컬 단일 Redis 환경에서의 컷오버를 공식 허용하고 합리적 지연 기준(일반 RAG $\le 20$초)을 적용한다. `APP_RUN_MODE=PRODUCTION` 컷오버 시에만 2개 이상의 독립 GPU 인스턴스 Gateway 엔드포인트 및 Redis Sentinel HA 쿼럼 충족을 필수로 요구하여 fail-closed 통제한다.
- **Q4 (승인 아티팩트 거버넌스 및 위조 방지)**: 외부 변경 권한자의 승인 검증을 어떻게 위조 불가능하게 보증할 것인가?
  - **결정**: 승인 파일(`bteam/migration/approvals/cutover-approved.json`)은 필수 4대 필드(`approved_by`, `approval_authority`, `approval_reference`, `previous_gate_sha256`)를 요구하며, 이전 `preflight-gate.json`의 SHA-256 해시 체인과 완벽히 일치해야만 실행된다. 자동화는 승인 파일을 생성할 수 없다.
- **Q5 (4대 즉시 롤백 트리거 정량화)**: 24시간 관찰(Soak) 기간 중 롤백 발동 조건을 어떻게 객관화할 것인가?
  - **결정**: 다음 4가지 조건 중 1개라도 충족 시 30초 이내 즉각 사전 검증된 Blue 롤백 프로파일로 복귀한다:
    1. Green 라우팅 외부 HTTP 5xx 누적 **1건 이상** 발생 시
    2. 30초 주기 서비스 헬스 프로브 **2회 연속** 실패 시
    3. 5분 윈도우 P95 지연시간 SLA(DEMO: 20초, PROD: 5초) **2회 연속** 초과 시
    4. PII 유출 또는 가짜 리뷰 사실 주장(환각) **1건이라도** 감지 시

---

## 1. Executive Summary & Problem Definition

### 1.1 배경 및 목적 (Background & Objectives)
앞선 피처(`041-bteam-unified-pipeline-restructure`)를 통해 B팀의 6개 하위 프로젝트(`Oliview_Project`, `Oliview_aspect_sentence_split`, `Oliview_aspect_sentiment`, `Oliview_LLM`, `Oliview_chatbot_a`, `Oliview_chatbot_b`)는 4개 표준 계층(`packages/core`, `models/`, `pipelines/`, `services/`)과 단일 UV Workspace 기반의 독립 멀티 컨테이너(**Green 스택**)로 통합 재구성되었으며, 전체 품질 게이트와 계약 검증을 100% 통과하였습니다.

본 피처(`042-bteam-production-cutover`)의 목적은 현재 실제 사용자 트래픽을 처리하고 있는 기존 레거시 시스템(**Blue 스택**)에서 새로 검증 완료된 **Green 통합 스택**으로의 **무중단 실운영 컷오버(Zero-Downtime Production Cutover), 최종 데이터 델타 증분 동기화, 게이트웨이(Nginx) 원자적 전환, 24시간 안전 관찰(Soak Period), 비상 롤백(Rollback) 절차 및 7일 롤백 안전망을 갖춘 레거시 자산 아카이빙**을 체계적으로 완수하는 것입니다.

### 1.2 핵심 전환 원칙 (Core Transition Principles)
1. **무중단 사용자 서빙 (Zero-Downtime User Serving)**: 트래픽 전환 중 대시보드 및 챗봇 사용자가 경험하는 HTTP 5xx 에러 0건 및 읽기 서비스 중단 시간 0초를 달성한다. (Nginx `proxy_next_upstream` 3회 재시도 및 백그라운드 파이프라인 최대 30초 드레인 허용)
2. **데이터 유실 없는 원자적 동기화 (Zero Data Loss & Final Delta Sync)**: Blue와 Green 간 MySQL 정합성, ChromaDB v1/v2 동기화 랙(Lag) 0, Redis 캐시 표적 무효화를 완료한 후 전환한다.
3. **승인 기반 통제 게이트 (Approval-Gated Governance)**: 외부 변경 권한자의 정식 승인(`CUTOVER_APPROVED`, `DECOMMISSION_APPROVED`)이 4대 필드 해시 체인으로 확인된 경우에만 데이터 플레인 및 인프라 전환을 집행한다.
4. **즉시 롤백 보장 (Instant Rollback Capability)**: 전환 후 최소 24시간 동안 Blue 스택을 상시 대기 상태로 유지하고, 4대 이상 징후 발생 시 30초 이내에 즉각 원복할 수 있는 안전망을 가동한다.
5. **실증 환경 최적화 자산 보존 (7-Day Retention for PoC)**: 실증/테스트 서버 특성에 맞추어 데이터 볼륨 및 백업은 7일간 보존하여 롤백 가능성을 담보하고, 이후 안전하게 정리한다.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 무중단 실운영 컷오버 및 실시간 트래픽 전환 (Priority: P1) 🎯 MVP

운영 엔지니어 및 시스템 관리자는 사전 품질 게이트가 완료된 Green 스택으로 Nginx 업스트림을 원자적(Atomic)으로 전환하여, 외부 사용자가 어떠한 서비스 중단이나 5xx 에러 없이 대시보드와 챗봇 서비스를 원활하게 이용할 수 있도록 해야 한다.

**Why this priority**: 서비스의 가용성을 유지하면서 새 통합 아키텍처로 안전하게 교체하기 위한 가장 핵심적인 운영 전환 목표임.

**Independent Test**:
- 실제 트래픽 유입 상태에서 Nginx 업스트림 전환 명령을 실행하고, 전환 전후 지속적인 HTTP probe 요청을 전송하여 응답 코드 200 유지 및 HTTP 5xx 0건을 검증한다.

**Acceptance Scenarios**:
1. **Given** Blue 스택이 활성 서비스 중이고 Green 스택의 헬스체크가 모두 정상(`Healthy`)일 때, **When** 승인된 컷오버 절차를 실행하면, **Then** Nginx 라우팅이 Green 엔드포인트로 원자적으로 전환되고 외부 요청 실패가 0건이어야 한다.
2. **Given** 전환 완료 직후, **When** 대시보드(`https://ezenitac.duckdns.org/bteam/oliview/`), API(`/api/health`), ChatA(`/chata/`), ChatB(`/chatb/`)로 접속하면, **Then** 모든 서비스가 200 OK와 정상 UI/응답을 제공해야 한다.

---

### User Story 2 - 최종 데이터 델타 동기화 및 정합성 보증 (Priority: P1)

데이터 엔지니어는 컷오버 직전 Blue의 백그라운드 쓰기 작업을 일시 드레인(Drain, 최대 15~30초)하고, MySQL 최신 스냅샷 백업 및 호환 마이그레이션을 거쳐 ChromaDB 벡터 저장소와 Redis 캐시까지 최종 데이터 델타(Delta Lag = 0)를 완벽하게 일치시켜야 한다.

**Why this priority**: 트래픽 전환 시 사용자의 최근 리뷰 데이터, 생성된 보고서, 임베딩 벡터의 유실이나 불일치가 발생하지 않도록 하기 위함.

**Independent Test**:
- Blue DB의 최신 데이터와 Green DB의 데이터를 대조하고, ChromaDB v1과 v2 컬렉션 간의 레코드 카운트 및 Redis 캐시 정합성을 검증한다.

**Acceptance Scenarios**:
1. **Given** 컷오버 진입 시점, **When** 백그라운드 드레인, 최종 백업 및 델타 동기화를 수행하면, **Then** `BACKUP_READY`와 `DATA_MIGRATION_READY` 검증 아티팩트가 생성되고 데이터베이스 동기화 랙이 0이어야 한다.
2. **Given** 증분 동기화 완료 후, **When** 신규 수집된 리뷰 문장과 분석 결과가 확인되면, **Then** Green ChromaDB(`oliview_review_sentences_v2`)에 100% 반영되고 `reviews.vector_indexed=1` 플래그가 일관되게 갱신되어야 한다.

---

### User Story 3 - 24시간 안전 관찰(Soak) 및 긴급 롤백 가동 (Priority: P2)

운영팀은 컷오버 완료 후 최소 24시간 동안 시스템의 에러율, 응답 지연 시간(P95 SLA), 챗봇 무환각 상태, 인라인 인용 무결성을 집중 모니터링하며, 4대 임계치 초과 시 즉각 Blue 스택으로 롤백할 수 있어야 한다.

**Why this priority**: 상용 트래픽 하에서의 잠재적 병목, 메모리 누수, 환각 응답을 실시간 감지하여 비즈니스 위험을 원천 차단하기 위함.

**Independent Test**:
- 24시간 동안 30초 간격 헬스 프로브 및 5분 윈도우 응답 지연을 측정하고, 인위적 장애 주입 시 사전 검증된 롤백 프로파일로 30초 이내 Blue 복귀가 이루어지는지 검증한다.

**Acceptance Scenarios**:
1. **Given** Green 스택 전환 운영 중, **When** 24시간 관찰 기간 동안 모든 헬스 프로브가 통과하고 P95 지연시간이 SLA(DEMO: 일반 RAG $\le 20$초, 상용 P95 $\le 5$초)를 충족하면, **Then** Soak 모니터링 합격 리포트를 산출한다.
2. **Given** 관찰 기간 중 외부 5xx 에러 1건 발생, 프로브 2회 연속 실패, SLA 2회 연속 초과 또는 PII/환각 1건 발생 시, **Then** 시스템은 30초 이내에 즉각 Nginx를 Blue 업스트림으로 롤백하고 인용 비호환 경로는 안전한 기권(Abstention) 프로파일로 격리한다.

---

### User Story 4 - 레거시 Blue 자산의 안전 격리 및 7일 보존 아카이빙 (Priority: P3)

시스템 관리자는 24시간 관찰 기간이 성공적으로 종료되고 외부 권한자의 최종 폐기 승인(`DECOMMISSION_APPROVED`)이 발급된 경우에 한해, 기존 Blue 컨테이너를 안전하게 중지하고 레거시 소스 폴더를 7일간 롤백 가능한 아카이브로 보관 후 정리해야 한다.

**Why this priority**: 실증/테스트 서버의 리소스를 최적화하면서도 비상 복원을 위한 충분한 안전 유예 기간(7일)을 확보하기 위함.

**Independent Test**:
- `DECOMMISSION_APPROVED` 서명 검증 후 Blue 컨테이너 중지 스크립트를 실행하고, 볼륨 및 스냅샷이 온전히 보존된 상태에서 지정된 아카이브 경로로 이전 및 7일 retention 태그가 부여되는지 확인한다.

**Acceptance Scenarios**:
1. **Given** 24시간 Soak 성공 및 외부 `DECOMMISSION_APPROVED` artifact가 존재할 때, **When** 폐기 절차를 실행하면, **Then** Blue 컨테이너만 graceful하게 중지되고 기존 데이터 볼륨 및 백업 스냅샷은 7일간 보존된 채 레거시 폴더가 recoverable archive로 이동해야 한다.
2. **Given** 7일 보존 기간이 만료된 후, **When** 정리 정책이 트리거되면, **Then** 정상 운영 중인 Green 스택에 영향 없이 레거시 임시 볼륨 및 백업이 안전하게 회수되어야 한다.

---

### Edge Cases & Failure Handling

| 시나리오 / 경계 조건 | 기대 동작 및 방어 정책 |
| :--- | :--- |
| **컷오버 중 MySQL 락/동기화 실패** | Nginx 전환을 즉각 중단하고 이전 스냅샷 상태로 복구하며, Blue 운영 DB 쓰기 권한을 유지한다. |
| **Nginx reload 구문 오류 (`nginx -t` 실패)** | 원자적 롤백을 수행하고 기존 active 업스트림 설정을 유지하여 트래픽 단절을 방지한다. |
| **컷오버 직후 Green 서비스 5xx 발생** | 1건이라도 발생 시 즉시 Blue 롤백 프로파일을 가동하고 장애 원인 추적 로그를 아티팩트로 기록한다. |
| **전환 후 챗봇 검색 결과 0건 또는 인용 불가** | 가짜 후기를 창작하지 않고 정의된 기권 사유(`NO_REVIEWS`, `GROUNDING_FAILED` 등)를 즉각 반환한다. |
| **외부 변경 권한자 승인 서명 누락/위조** | 컷오버 및 레거시 폐기 단계를 일체 시작하지 않고 명시적인 `ACCESS_DENIED` 이벤트로 fail-closed 처리한다. |
| **24시간 관찰 중 네트워크 일시 단절** | 재시도 백오프를 수행하되 연속 2회 실패 시 즉각 알림을 발송하고 롤백 기준 부합 여부를 평가한다. |

---

## 3. Requirements *(mandatory)*

### Functional Requirements

- **FR-001 (사전 전환 거버넌스 및 승인 체인 검증)**: 시스템은 외부 변경 권한자가 정식 발급한 `CUTOVER_APPROVED` 아티팩트의 4대 필수 필드(`approved_by`, `approval_authority`, `approval_reference`, `previous_gate_sha256`) 해시 체인을 검증해야 하며, 승인이 없거나 불일치할 경우 컷오버를 진행하지 않고 즉각 중단해야 한다.
- **FR-002 (백그라운드 15초 Graceful Drain 및 Fresh Backup)**: 시스템은 컷오버 시작 시 Blue의 백그라운드 데이터 수집 작업을 안전하게 드레인(현재 처리 중인 1개 청크 완료 후 정지, 최대 15~30초 제한)하고, MySQL 데이터베이스의 최신 스냅샷 백업을 생성하여 `BACKUP_READY` 상태를 기록해야 한다. 사용자 웹/API 읽기 트래픽은 0초 중단으로 계속 유지된다.
- **FR-003 (하위 호환 Additive 스키마 마이그레이션)**: 시스템은 기존 Blue 스키마를 파괴하지 않고 `reviews.vector_indexed`, `llm_product_report_claims`, `llm_product_report_citations` 및 파이프라인 이력/분산 락 테이블을 안전하게 반영해야 한다.
- **FR-004 (ChromaDB v1/v2 최종 델타 증분 동기화 및 랙 검증)**: 시스템은 Blue와 Green 간의 분석 완료 리뷰에 대해 ChromaDB v2(`oliview_review_sentences_v2`) 총 레코드 카운트 및 매핑을 쿼리하여 동기화 랙(Lag)이 0임을 검증하고 `DATA_MIGRATION_READY` 아티팩트를 생성해야 한다.
- **FR-005 (Redis 캐시 표적 무효화 및 바이패스 정책)**: 시스템은 컷오버 시 상품 식별자가 명확한 캐시 키에 대해서만 정밀 무효화를 수행하고, 해시 기반 캐시 키는 전역 삭제하지 않고 안전한 캐시 바이패스 프로파일을 적용해야 한다.
- **FR-006 (Nginx 게이트웨이 원자적 컷오버 및 재시도 보증)**: 시스템은 `nginx -t` 구문 검사를 통과한 candidate 설정을 사용하여 무중단(`nginx -s reload`)으로 트래픽을 Green 멀티 컨테이너 업스트림으로 전환해야 하며, Nginx 설정에 `proxy_next_upstream` 3회 재시도를 강제하여 전환 순간의 패킷 드롭을 원천 방어해야 한다.
- **FR-007 (전환 직후 Post-Cutover Smoke Gate)**: 시스템은 컷오버 직후 메인 대시보드, 백엔드 API, ChatA(Streamlit), ChatB(FastAPI) 및 20개 고정 Zero-search 픽스처에 대해 자동 프로브를 실행하여 외부 HTTP 5xx 발생 0건 및 정상 기권 응답을 검증해야 한다.
- **FR-008 (24시간 Soak 모니터링 자동화)**: 시스템은 컷오버 후 최소 24시간 동안 30초 주기 헬스체크, 5분 윈도우 P95 지연시간, 챗봇 무환각/인라인 인용 결속 상태를 지속 기록하고 이상 징후를 감시해야 한다.
- **FR-009 (4대 이상 징후 기반 30초 비상 롤백)**: 시스템은 Soak 기간 중 5xx 1건 발생, 연속 2회 프로브 실패, 5분 P95 SLA 2회 연속 초과, PII/환각 1건 감지 시 30초 이내에 사전 검증된 Blue 롤백 프로파일로 복귀하는 비상 롤백 기능을 제공해야 한다.
- **FR-010 (7일 보존 기반 레거시 Blue Decommissioning)**: 시스템은 24시간 Soak 통과 후 외부 변경 권한자의 `DECOMMISSION_APPROVED` artifact가 제공된 경우에만 Blue 컨테이너를 중지하고 레거시 소스 자산을 복구 가능한 아카이브 디렉토리로 이동한다. 데이터베이스 볼륨 및 백업 스냅샷은 7일 동안 안전 보존한 후 정리한다.
- **FR-011 (동적 운영 모드 및 감사 로그 무결성)**: 전환 및 운영 전 과정에서 민감정보(비밀번호, API 키, 원문 PII)가 로그나 아티팩트에 평문 노출되지 않도록 마스킹하고, `APP_RUN_MODE=DEMO`와 `PRODUCTION`의 컷오버 전제 조건을 명확히 분리하여 기록해야 한다.

---

### Key Entities

- **CutoverApproval**: 외부 변경 권한자가 발급한 운영 전환 승인 메타데이터 (승인자, 권한, 티켓 참조, 이전 게이트 SHA-256 해시).
- **MigrationStateArtifact**: 백업 완료(`BACKUP_READY`), 데이터 동기화 완료(`DATA_MIGRATION_READY`), 폐기 승인(`DECOMMISSION_APPROVED`) 등의 상태 전이 기록.
- **UpstreamRouteMap**: Nginx 게이트웨이가 라우팅하는 서비스별(대시보드 프론트/백, ChatA, ChatB) 활성 컨테이너 엔드포인트 매핑.
- **SoakHealthMetric**: 24시간 관찰 기간 동안 수집되는 HTTP 응답률, Latency P95, 인용 무결성 지표 시계열 데이터.
- **RollbackProfile**: 장애 발생 시 즉각 Blue 활성 상태로 원복하기 위한 Nginx 설정 및 캐시 바이패스 정의체.

---

## 4. Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (무중단 전환 가용성)**: Nginx 트래픽 컷오버 및 전환 후 관찰 기간 동안 외부 라우팅 요청의 HTTP 5xx 에러율이 0.0%이며 사용자 읽기 가용성이 100% 유지되어야 한다. (백그라운드 파이프라인 일시 드레인은 최대 30초 이내)
- **SC-002 (데이터 동기화 무결성)**: 컷오버 시점 기준 Blue-Green 간 데이터베이스 레코드 차이 0건, ChromaDB 벡터 동기화 랙 0건이어야 한다.
- **SC-003 (신규 서비스 응답 신선도)**: 파이프라인 인덱싱 후 신규 리뷰 데이터가 대시보드 및 챗봇 검색 풀에 노출되기까지의 지연 시간이 60초 이내여야 한다.
- **SC-004 (SLA 지연시간 기준 충족)**: 24시간 관찰 기간 동안 DEMO 모드 일반 RAG 답변 $\le 20.0$초, 상용 모드 챗봇 P95 $\le 5.0$초를 유지해야 한다.
- **SC-005 (무환각 및 100% 인용 결속)**: 전환 후 모든 챗봇 및 대시보드 보고서의 사실 주장은 100% 실존 리뷰 식별자에 결속되어야 하며, 검색 0건 시 환각 창작이 0건이어야 한다.
- **SC-006 (신속한 비상 롤백 시간)**: 4대 이상 징후 감지 시 Nginx 및 서비스가 Blue 복구 프로파일로 완전히 복귀하는 데 소요되는 시간이 30초 이내여야 한다.
- **SC-007 (7일간 롤백 가능 자산 보존)**: Blue 레거시 컨테이너 중지 후에도 최소 7일간 기존 운영 DB 볼륨 및 백업 스냅샷이 온전히 보존되어 비상 원복이 가능해야 한다.
- **SC-008 (보안 및 개인정보 무유출)**: 전환 아티팩트 및 로그 상의 개인식별정보(PII)와 인증 시크릿 평문 노출이 0건이어야 한다.

---

## 5. Assumptions

- **인프라 환경**: Nginx 리버스 프록시가 호스트 상에서 구동 중이거나 게이트웨이 컨테이너로 동작하며, `nginx -s reload`를 통한 무중단 설정 리로드가 지원된다.
- **사전 구축 완료 상태**: `041` 피처를 통해 Green 멀티 컨테이너 스택, `packages/core`, 파이프라인 러너 및 계약 테스트가 이미 100% 구축되어 준비되어 있다.
- **권한 체계**: 프로덕션 컷오버(`CUTOVER_APPROVED`) 및 레거시 폐기(`DECOMMISSION_APPROVED`) 승인 서명은 시스템 내부가 아닌 외부 운영 책임자/변경 관리자에 의해 명시적으로 투입된다.
- **롤백 보장**: 24시간 관찰 기간 동안 Blue 스택 컨테이너와 네트워크 및 데이터 볼륨은 상시 가동 가능한 상태로 유지되며, 폐기 후에도 7일 동안 볼륨/스냅샷이 보존된다.
