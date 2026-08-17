# Implementation Plan: 게이트웨이 포털 2x2 대칭 그리드 레이아웃 개편 (004-gateway-2x2-grid)

**Branch**: `004-gateway-2x2-grid` | **Date**: 2026-08-17 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/004-gateway-2x2-grid/spec.md)

**Input**: Feature specification from `specs/004-gateway-2x2-grid/spec.md`

---

## Summary

통합 AI 서비스 게이트웨이 포털(`gateway/html/index.html`)의 서비스 카드 그리드 레이아웃을 기존 3x2 비대칭 구도(`repeat(auto-fit, minmax(280px, 1fr))`)에서 **2x2 대칭 그리드(`repeat(2, 1fr)`)**로 개편합니다.
- 데스크톱 화면에서 최대 폭(`max-width: 1000px`)을 적용하여 4개의 카드가 상단 2개, 하단 2개로 완벽하게 대칭 정렬되도록 구성합니다.
- 모바일 화면(<= 768px)에서는 1열(`1fr`) 세로 스택으로 자동 반응형 전환됩니다.
- 컨테이너 내부의 비시맨틱 `<br>` 태그를 제거하고 카드 행별 높이 자동 균등화(`height: 100%`)를 유지합니다.

---

## Technical Context

- **Language/Version**: HTML5, Vanilla CSS3 (CSS Grid / Flexbox)
- **Primary Dependencies**: Nginx 1.25+ Alpine (`gateway` 컨테이너)
- **Storage**: N/A (정적 웹 리소스)
- **Testing**: 브라우저 렌더링 검증, E2E 스크립트(`verify_e2e_services.ps1`) Checkpoint #1 (Landing Portal) 회귀 테스트
- **Target Platform**: 데스크톱 (Chrome, Edge, Safari, Firefox), 모바일/태블릿 반응형 뷰포트
- **Project Type**: Web Frontend UI Layout Optimization
- **Performance Goals**: 0ms 렌더링 오버헤드, 레이아웃 시프트(CLS) 0
- **Constraints**: 기존 다크 글래스모피즘 테마 및 카드 호버/글로우 애니메이션 100% 보존

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Language Requirement)**: 명세서, 설계 문서, 주석 모두 한국어로 작성됨 (PASS).
- **Principle II (Test-Driven Discipline)**: 기존 10대 체크포인트 회귀 테스트 및 브라우저 시각적 검증 시나리오 완비 (PASS).
- **Principle III (Service Modularity & Isolation)**: 서브서비스 백엔드 코드 일체 무영향, 게이트웨이 정적 HTML/CSS 단독 변경 (PASS).
- **Principle IV (Observability & Production Safeguards)**: 무중단 핫 리로드 지원 (PASS).
- **Principle V (YAGNI & Scope Economy)**: 필요한 2x2 그리드 CSS 및 마크업 클린업에 정확히 한정 (PASS).

---

## Project Structure

### Documentation (this feature)

```text
specs/004-gateway-2x2-grid/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 research & technical decisions
├── data-model.md        # Phase 1 UI component definitions
├── quickstart.md        # Phase 1 validation guide
├── contracts/
│   └── gateway-ui.md    # Phase 1 CSS & DOM structure contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 task decomposition (/speckit-tasks)
```

### Source Code Touched

```text
gateway/
└── html/
    └── index.html       # Gateway portal landing HTML/CSS
```

---

## Implementation Steps & Phases

### Phase 1: CSS Grid 및 컨테이너 스타일 수정
- `gateway/html/index.html` 내 `.grid-container` CSS 규칙 수정:
  - `grid-template-columns: repeat(2, 1fr);`
  - `max-width: 1000px;`
- `@media (max-width: 768px)` 반응형 미디어 쿼리 추가:
  - `.grid-container { grid-template-columns: 1fr; }`
- `.service-card`의 `height: 100%` 및 Flexbox 정렬 확인.

### Phase 2: HTML 마크업 클린업
- `<main class="grid-container">` 내부의 불필요한 `<br>` 태그 제거.

### Phase 3: 검증 및 회귀 테스트
- 브라우저에서 `https://ezenitac.duckdns.org/` 및 `http://localhost:8080/` 접속하여 2x2 대칭 배치 확인.
- 브라우저 개발자도구 768px 이하 모바일 반응형 1열 전환 확인.
- `verify_e2e_services.ps1` 실행하여 포털 랜딩(Checkpoint #1) 및 서브시스템 10/10 PASS 유지 확인.
