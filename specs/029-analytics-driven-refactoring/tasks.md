# Tasks: 분석 보고서 기반 서비스 및 시스템 최적화 리팩토링 (029-analytics-driven-refactoring)

**Input**: Feature specification from `/specs/029-analytics-driven-refactoring/spec.md` and design documents  
**Prerequisites**: `plan.md`, `data-model.md`, `research.md`, `contracts/portal_curation.json`, `quickstart.md`

---

## Phase 1: Setup & Pre-flight Checks

**Purpose**: 현재 실행 중인 도커 컨테이너 및 정적 자원 무결성 사전 검증

- [x] T001 [P] Docker 컨테이너 전체 런타임 상태 및 포트 바인딩 확인 (`docker ps`)
- [x] T002 [P] A-Team 주식 로고 이미지 96종 존재 여부 확인 (`ateam/pilos-sentiment-index/pilos/web/static/images/stock-logos/`)

---

## Phase 2: Foundational (Core Configuration Baseline)

**Purpose**: 서브 서비스 간 공통 정적 서빙 및 네트워크 설정 준비

- [x] T003 백업 및 구성 검증용 `gateway/nginx.conf` 사전 점검
- [x] T004 [P] 포털 큐레이션 계약 스키마 검증 (`specs/029-analytics-driven-refactoring/contracts/portal_curation.json`)

**Checkpoint**: 기본 인프라 준비 완료 - 각 사용자 스토리별 작업 진행 가능

---

## Phase 3: User Story 1 - 깨짐 없는 종목 로고 및 정적 서빙 복구 (Priority: P1) 🎯 MVP

**Goal**: 주식 감정지수 서비스의 로고 이미지 누락(404 에러 2,600여 건의 42%)을 원천 차단하고, 로드 실패 시 동적 컬러 아바타 폴백 제공

**Independent Test**: `curl -I http://localhost/static/images/stock-logos/000660.png` 호출 시 `200 OK` 및 `Cache-Control` 헤더를 반환하고, 이미지 누락 시 이니셜 원형 아바타가 정상 렌더링됨을 확인

### Implementation for User Story 1

- [x] T005 [US1] `gateway/nginx.conf`에 `/static/` 및 `/static/images/` 프록시 라우팅 규칙과 `Cache-Control: public, max-age=86400` 캐시 헤더 추가
- [x] T006 [P] [US1] `ateam/pilos-sentiment-index/pilos/web/static/js/common.js`에 이미지 `onerror` 시 종목 첫 글자 기반 동적 SVG/CSS 컬러 원형 아바타 생성 폴백 핸들러 구현
- [x] T007 [US1] `gateway` 컨테이너 Nginx 설정 리로드 (`docker exec aiservice-gateway nginx -s reload`)
- [x] T008 [US1] 주요 종목 로고(000660, 005930, 247540) 정적 호출 및 200 OK 응답 검증

**Checkpoint**: 주식 로고 404 오류가 100% 해결되고 동적 아바타 폴백이 정상 작동함 (MVP 완료)

---

## Phase 4: User Story 2 - 모바일/카카오톡 인앱 UX 및 Open Graph 메타태그 (Priority: P2)

**Goal**: 카카오톡 인앱 브라우저(19.3%) 및 모바일(27%) 유입 환경에 최적화된 반응형 뷰포트와 서비스별 맞춤 Open Graph 메타태그 적용

**Independent Test**: 각 서비스 메인 페이지 호출 시 `viewport-fit=cover`와 고유의 `og:title`, `og:description`, `og:image` 메타태그가 출력되는지 검증

### Implementation for User Story 2

- [x] T009 [P] [US2] `gateway/html/index.html`에 통합 포털 맞춤 Open Graph 메타태그 및 모바일 safe-area-inset 스타일 적용
- [x] T010 [P] [US2] `ateam/pilos-sentiment-index/pilos/web/templates/index.html`에 Pilos 주식 감정지수 맞춤 Open Graph 메타태그 적용
- [x] T011 [P] [US2] `bteam/Oliview_Project/frontend/index.html`에 Oliview 뷰티 리뷰 맞춤 Open Graph 메타태그 적용
- [x] T012 [US2] curl을 통한 각 서비스별 Open Graph 및 뷰포트 메타태그 출력 검증

**Checkpoint**: 메신저 링크 공유 시 각 서비스별 맞춤 카드 노출 및 모바일 safe-area 레이아웃 정상 동작 확인

---

## Phase 5: User Story 3 - 통합 포털 실시간 큐레이션 위젯 구현 (Priority: P3)

**Goal**: 포털 랜딩(`/`)에 실시간 주식 감정 핫 종목 및 뷰티 핫 키워드 비동기 Fetch 큐레이션 위젯을 탑재하여 서브 서비스 유입 전환율 극대화

**Independent Test**: `http://localhost/` 접속 시 비동기로 주식 및 뷰티 큐레이션 카드가 로드되고 클릭 시 서브 서비스로 즉시 이동하는지 확인

### Implementation for User Story 3

- [x] T013 [US3] `gateway/html/index.html`에 실시간 핫 종목 및 뷰티 키워드 큐레이션 UI 카드 마크업 및 CSS 스타일 추가
- [x] T014 [US3] `gateway/html/index.html`에 `/api/stocks` 및 `/bteam/oliview/api/brands` 비동기 Fetch 및 동적 카드 렌더링 JavaScript 로직 구현
- [x] T015 [US3] 브라우저 및 curl을 통한 포털 큐레이션 위젯 로딩 및 딥링크 이동 동작 검증

**Checkpoint**: 통합 포털 메인 화면에서 실시간 큐레이션 정보가 부드럽게 렌더링되고 서브 서비스로의 유입 전환 연결 완성

---

## Phase 6: User Story 4 - B-Team 백엔드 API Graceful Fallback (Priority: P4)

**Goal**: 브랜드 상품 및 카테고리 조회 시 데이터 미존재/초기화 상황에서도 500 서버 크래시를 방지하고 200 OK 빈 데이터 응답 제공

**Independent Test**: 미등록 브랜드 ID(`999999`)로 `/api/brands/999999/products` 호출 시 500 에러 없이 `200 OK`와 `{"success": true, "products": []}`를 반환하는지 확인

### Implementation for User Story 4

- [x] T016 [US4] `bteam/Oliview_Project/backend/app.py`의 `get_products` 및 `get_brand_categories` 엔드포인트에 예외 방어 로직 및 Graceful Fallback 처리 추가
- [x] T017 [US4] `oliview_backend` 컨테이너 재시작 또는 소스 핫리로드 적용
- [x] T018 [US4] 미등록 브랜드 ID 호출 시 500 에러 미발생 및 정상 fallback JSON 응답 검증

**Checkpoint**: 백엔드 API 500 에러가 완전 차단되고 안정적인 기본 응답 보장

---

## Phase 7: Polish & E2E Verification

**Purpose**: 전체 변경사항의 통합 검증 및 회귀 테스트

- [x] T019 [P] `specs/029-analytics-driven-refactoring/quickstart.md`에 명시된 4대 검증 시나리오 전체 실행 및 통과 확인
- [x] T020 [P] 게이트웨이 액세스 로그 모니터링하여 404 및 500 에러 제거 여부 최종 확인 (`docker logs --tail 50 aiservice-gateway`)
- [x] T021 [P] `docs/service_access_analytics_report.md`에 리팩토링 적용 결과 및 해결 내역 업데이트 기록

---

## Dependencies & Execution Order

### Phase Dependencies

1. **Phase 1 & 2 (Setup & Foundational)**: 즉시 시작 가능 [완료]
2. **Phase 3 (User Story 1 - MVP)**: Phase 2 완료 후 즉시 실행 (핵심 404 오류 해결) [완료]
3. **Phase 4 (User Story 2)**: Phase 2 완료 후 병렬 실행 가능 (메타태그 & 모바일 최적화) [완료]
4. **Phase 5 (User Story 3)**: Phase 3 및 4와 연계하여 포털 랜딩 고도화 [완료]
5. **Phase 6 (User Story 4)**: 독립적으로 실행 가능 (백엔드 API 안전망) [완료]
6. **Phase 7 (Polish & Verification)**: 모든 사용자 스토리 완료 후 최종 통합 검증 [완료]
