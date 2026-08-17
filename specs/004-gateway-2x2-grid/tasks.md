# Tasks: 게이트웨이 포털 2x2 대칭 그리드 레이아웃 개편 (004-gateway-2x2-grid)

**Feature**: `004-gateway-2x2-grid`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/004-gateway-2x2-grid/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/004-gateway-2x2-grid/plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 게이트웨이 정적 파일 및 환경 준비

- [X] T001 `gateway/html/index.html` 현재 CSS 그리드 및 마크업 구조 점검 in `gateway/html/index.html`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Nginx 게이트웨이 정적 파일 매핑 및 서빙 정합성 확인

- [X] T002 Nginx 게이트웨이의 `/usr/share/nginx/html/index.html` 볼륨 마운트 및 핫 리로드 설정 확인 in `gateway/nginx.conf`, `docker-compose.yml`

**Checkpoint**: 게이트웨이 정적 HTML 수정 즉시 반영 준비 완료

---

## Phase 3: User Story 1 - 게이트웨이 포털 2x2 균형 그리드 배치 (Priority: P1) 🎯 MVP

**Goal**: 데스크톱 화면에서 4개 서비스 카드가 2x2 대칭 정렬되고, 모바일(<= 768px)에서 1열로 자동 전환되며 불필요한 `<br>` 태그를 제거

**Independent Test**: 브라우저에서 `https://ezenitac.duckdns.org/` 및 `http://localhost:8080/` 접속 시 4개 카드가 우측 빈 슬롯 없이 2행 2열(2x2)로 완벽 대칭 렌더링되고 화면 축소 시 1열로 전환되는지 확인

### Implementation for User Story 1

- [X] T003 [US1] `gateway/html/index.html`의 `.grid-container` CSS를 `grid-template-columns: repeat(2, 1fr)` 및 `max-width: 1000px`로 수정 in `gateway/html/index.html`
- [X] T004 [US1] `gateway/html/index.html`에 `@media (max-width: 768px)` 반응형 미디어 쿼리(`grid-template-columns: 1fr`) 추가 in `gateway/html/index.html`
- [X] T005 [US1] `gateway/html/index.html`의 `<main class="grid-container">` 내부 비시맨틱 `<br>` 태그 제거 in `gateway/html/index.html`
- [X] T006 [US1] `gateway/html/index.html`의 `.service-card` Flexbox 및 `height: 100%` 행별 높이 자동 균등화 정합성 검증 in `gateway/html/index.html`

**Checkpoint**: User Story 1 (2x2 대칭 그리드 및 모바일 반응형) 구현 완료

---

## Phase 4: Polish & E2E 검증 (Cross-Cutting Concerns)

**Purpose**: 브라우저 시각적 렌더링 확인 및 기존 E2E 테스트 스위트 회귀 검증

- [X] T007 [P] Nginx 게이트웨이 릴로드 및 브라우저 새로고침(F5)을 통한 2x2 렌더링/호버 애니메이션 확인 in `gateway/html/index.html`
- [X] T008 `verify_e2e_services.ps1`을 실행하여 포털 랜딩(Checkpoint #1) 및 전체 10개 체크포인트 100% PASS 유지 확인 in `specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1`

---

## Dependencies & Execution Order

```mermaid
graph TD
    Phase1[Phase 1: Setup<br>T001] --> Phase2[Phase 2: Foundational<br>T002]
    Phase2 --> US1[Phase 3: User Story 1 (P1)<br>2x2 Grid & Responsive<br>T003-T006]
    US1 --> Phase4[Phase 4: Polish & E2E<br>T007-T008]
```

---

## Implementation Strategy

### MVP Scope (User Story 1)
1. `gateway/html/index.html`의 `.grid-container` CSS 2x2 및 1000px 수정 (T003)
2. `@media (max-width: 768px)` 반응형 1열 추가 (T004)
3. 불필요한 `<br>` 태그 제거 (T005)
4. 브라우저 및 `verify_e2e_services.ps1` 10/10 PASS 검증 (T007, T008)
