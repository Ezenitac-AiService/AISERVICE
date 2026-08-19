# Feature Specification: A-Team Pilos 댓글 수집 로직 전면 재점검 및 18~19일 수집 결손 정합성 복원

**Feature Branch**: `023-pilos-crawler-collection-audit`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "ateam pilos의 수집 로직 재점검. 원본 프로젝트의 수집 내용을 보니, 지금 우리 프로젝트보다 훨씬 많은 댓글을 수집했음, 특히 18일 19일 댓글 수집량이 많이 차이남"

## Clarifications

### Session 2026-08-19
- Q: 2026-08-18 ~ 2026-08-19 결손 구간에 대한 소급 재수집(Catch-up Backfill)의 대상 종목 및 실행 범위를 어떻게 설정할까요? → A: Option A (10개 전 종목을 대상으로 2026-08-18 00:00(KST)까지 일괄 백필 소급 수집 후 전처리/DB 적재)
- Q: 토스 API 응답에서 작성자 프로필 정보(authorUserProfileId 또는 nickname)가 누락된 댓글의 비식별화 처리를 어떻게 진행할까요? → A: Option A (프로필 ID 누락 시 ANONYMOUS_USER, 닉네임 누락 시 익명으로 안전 치환 후 기존 솔트 해싱 적용)
- Q: 토스 증권 커뮤니티의 대댓글(답글/스레드 댓글)도 본문 수집 및 감성 분석 대상에 포함하여 수집할까요? → A: Option A (답글/대댓글도 독립된 댓글 레코드로 전수 수집하여 감성 분석 대상에 완전 포함)
- Q: 18~19일 소급 수집 및 전처리 완료 후, 후속 다운스트림 단계(토큰화, 일별 문서 생성, Ridge 감성 예측, LLM 보고서)의 연쇄 실행 방식을 어떻게 설정할까요? → A: Option A (소급 수집 및 전처리 완료 즉시 7단계 파이프라인을 엔드투엔드로 연속 실행하여 즉시 지표 갱신)
- Q: 대량 소급 백필 실행 시 토스 커뮤니티 API 차단(HTTP 429)을 방지하기 위한 요청 딜레이(Rate Limiting Throttling) 정책을 어떻게 설정할까요? → A: Option A (0.5초 ± 0.2초 랜덤 지터 기반 고속·안정 하이브리드 요청 + 429 시 Retry-After 자동 준수)

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 증분 및 백필 크롤링 필터링 결손 제거 및 수집량 정상화 (Priority: P1) 🎯 MVP

토스 증권 커뮤니티 API로부터 10개 종목의 댓글을 수집할 때, 불필요하거나 과도한 필드 검증(`authorUserProfileId`, `nickname` 등 비필수 메타데이터 누락 시 댓글 전체 버림 현상)으로 인해 원본 댓글이 대량 유실되던 문제를 해결하고, 실제 유효한 모든 댓글과 답글(대댓글)을 100% 온전히 수집한다.

**Why this priority**:
댓글 수집은 Pilos 감성지수 산출, Ridge 회귀 모델 추론, LLM 종합 분석 보고서 생성의 최상위 입력(원천 데이터)이다. 수집량이 누락되면 전체 감성지표의 신뢰도와 대표성이 훼손되므로 최우선 해결 대상이다.

**Independent Test**:
토스 API 응답 내 다양한 댓글 형태(일반 댓글, 답글/대댓글, 익명/프로필ID 형태 차이 등)를 모의 요청하여, 단 한 건의 유효 댓글도 버려지지 않고 원본 JSONL에 정상 기록되는지 독립 검증.

**Acceptance Scenarios**:
1. **Given** 토스 API 응답에 `authorUserProfileId`가 없는 댓글이나 답글 레코드가 포함되어 있을 때,
   **When** 크롤러(`_select_page`)가 해당 페이지를 파싱하면,
   **Then** 오류나 스킵 없이 안전하게 기본값 처리/익명화되어 `new_comments`에 포함되고 `last_cursor`가 정상 전진한다.
2. **Given** 특정 종목(SK하이닉스, 삼성전자, 두산에너빌리티 등)의 대화량이 급증한 날(2026-08-18, 2026-08-19),
   **When** 증분 크롤러가 실행되면,
   **Then** 조기 종료나 커서 고착 없이 직전 수집 경계점까지의 모든 신규 댓글을 빠짐없이 수집한다.

---

### User Story 2 - 18일~19일 결손 데이터 소급 재수집 및 파이프라인 정합성 복원 (Priority: P2)

기존 수집 실행에서 누락되었거나 조기 중단으로 유실된 2026-08-18 ~ 2026-08-19 기간의 원본 댓글을 소급 재수집(Catch-up Backfill)하고, `preprocessed_comment`, `tokenized_comment`, `daily_document`에 무결하게 재반영한다.

**Why this priority**:
현재 운영 DB 및 원본 파일에 18일, 19일 댓글 수집량이 원본 프로젝트 대비 현저히 부족한 상태이므로, 과거 결손 구간을 정밀하게 메워야 정확한 일별 감성 보고서가 산출된다.

**Independent Test**:
18일~19일 대상 타겟 백필/캐치업 스크립트를 실행하여 원본 JSONL의 줄 수와 `preprocessed_comment` 적재 건수가 원본 기대 수준으로 증분 복원되는지 확인.

**Acceptance Scenarios**:
1. **Given** 18일, 19일 결손 구간이 존재하는 종목 목록이 주어졌을 때,
   **When** 타겟 소급 재수집 모듈이 동작하면,
   **Then** 중복 댓글은 `INSERT IGNORE` 및 파일 dedup으로 안전하게 걸러지고, 누락된 댓글만 선별 추가된다.

---

### User Story 3 - 크롤러 안정성 강화 및 관측 지표 로깅 (Priority: P3)

크롤링 실행 시 일별 수집량, API 호출 페이지 수, 필터링/스킵된 사유, 종목별 최근 수집 ID(`recent_comment_id`)를 상세 로깅하여 향후 수집 누락 여부를 운영자가 즉시 진단할 수 있도록 한다.

**Why this priority**:
주기적 백그라운드 워커 데몬이 동작할 때 수집 결손이 재발하지 않도록 상시 모니터링 체계를 확보한다.

**Independent Test**:
크롤러 실행 로그에 종목별 수집 건수, 스킵 건수, 경계 커서 정보가 구조화되어 출력되는지 검증.

**Acceptance Scenarios**:
1. **Given** 정기 파이프라인 워커가 실행될 때,
   **When** 증분 수집이 완료되면,
   **Then** 각 종목별 수집 성공/실패 여부와 신규 수집 건수가 요약 매트릭스로 기록된다.

---

## Edge Cases

- **Toss API 페이징 중 동일 커서 반환 (Cursor Stuck)**: API 응답의 `lastCommentId`가 이전과 동일하여 무한 루프에 빠질 위험이 있을 때 안전하게 루프를 탈출하고 경고 로그를 기록해야 함.
- **API Rate Limit (HTTP 429)**: `Retry-After` 헤더 값을 파싱하여 지수 백오프로 대기 후 최대 3회 재시도.
- **비정형 작성자 필드**: `author` 객체가 비어있거나, `nickname`이 `None`, `userProfileId`가 미존재하는 경우에도 `익명` 또는 식별자 해시로 안전 대체하여 댓글 본문 유실을 방지.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 크롤러는 토스 API로부터 수신된 최상위 댓글 및 모든 하위 답글(대댓글)을 포함하여 본문(`content` 또는 `commentId`)이 존재하는 모든 유효 댓글을 누락 없이 수집해야 한다.
- **FR-002**: 작성자 프로필 정보(`authorUserProfileId`, `nickname`)가 누락되었거나 비정형 구조인 경우에도 댓글 레코드를 폐기하지 않고, 프로필 ID는 `ANONYMOUS_USER`, 닉네임은 `익명`으로 안전 치환 후 기존 솔트 해싱을 적용하여 저장해야 한다.
- **FR-003**: 증분 크롤러는 직전 수집 최신 지점(`recent_comment_id`)까지 빠짐없이 역방향 페이지네이션을 수행해야 한다.
- **FR-004**: 18일, 19일 결손 데이터 복구를 위해 특정 날짜 범위를 타겟팅하여 안전하게 재수집할 수 있는 전용 캐치업(Backfill) 메커니즘을 제공해야 한다.
- **FR-005**: 재수집된 데이터는 기존 저장소의 append-only 원칙과 DB의 `INSERT IGNORE` 중복 방지 규칙을 엄격히 준수하여 중복 레코드를 생성하지 않아야 한다.
- **FR-006**: 소급 수집 및 전처리 완료 시, 후속 다운스트림 7단계 파이프라인(전처리 -> Kiwi 토큰화 -> 일별 문서 빌드 -> 수급 지표 -> Ridge 모델 추론 -> v13 LLM 보고서 생성)을 즉시 엔드투엔드로 연속 실행하여 웹 서비스 대시보드 지표를 즉각 복원해야 한다.
- **FR-007**: 10개 화이트리스트 종목(SK하이닉스, 삼성전자, 두산에너빌리티, NAVER, 카카오, LG에너지솔루션, 에코프로비엠, 셀트리온, 현대차, 포스코홀딩스) 전체에 대해 균일한 수집 정합성을 보장해야 한다.
- **FR-008**: 수집 상태와 일별 댓글 수 통계를 매니페스트(`manifest.json`) 및 DB에 투명하게 기록해야 한다.

---

### Key Entities

- **RawCommentRecord**: 토스 커뮤니티 API 원본 댓글 엔티티 (`commentId`, `createdAt`, `content`, `author`, `likeCount`, `replyCount` 등).
- **SourceCommentFile**: `data/raw/` 경로에 저장된 작성일별 JSONL 파일 메타데이터 (`file_name`, `stock_id`, `record_count`).
- **CrawlManifest**: 각 종목의 백필 커서, 증분 최근 ID, 작성일별 수집 건수 관리 엔티티.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 2026-08-18 및 2026-08-19 대상 댓글 수집량이 원본 소스 대비 누락 없이 100% 일치하도록 복원된다.
- **SC-002**: 크롤러의 비정상 댓글 폐기율(드롭률)이 0.0%로 감소한다.
- **SC-003**: 재수집 및 증분 수집 과정에서 기존 DB와의 중복 충돌률 0.0% 보장.
- **SC-004**: 10개 전 종목의 18~19일 일별 감성지표 및 LLM 보고서가 정상 복원된다.

---

## Assumptions

- 토스 증권 API (`https://wts-cert-api.tossinvest.com/api/v4/comments`)의 엔드포인트와 기본 응답 스키마는 유효하게 접근 가능하다.
- 데이터베이스 `pilos_v2`의 `preprocessed_comment` 테이블은 `comment_id` 및 `stock_id`에 대한 고유 인덱스를 가지고 있어 중복 삽입을 안전하게 방지한다.
- 비식별화 솔트(`SECRET_SALT`, `SECRET_SALT2`)는 기존 환경 설정을 그대로 유지하여 과거 해시와 일관성을 유지한다.
