# Phase 0 Research: 게이트웨이 포털 2x2 대칭 그리드 레이아웃 개편 (004-gateway-2x2-grid)

**Feature**: `004-gateway-2x2-grid`  
**Date**: 2026-08-17  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/004-gateway-2x2-grid/spec.md)

---

## 1. 그리드 컬럼 및 레이아웃 구조 결정

### Decision 1: CSS Grid 2x2 명시적 컬럼 선언 (`repeat(2, 1fr)`)
- **선택된 방안**: `.grid-container { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.75rem; max-width: 1000px; width: 100%; margin-bottom: 3rem; }`
- **결정 근거 (Rationale)**:
  - 기존의 `repeat(auto-fit, minmax(280px, 1fr))`는 1200px 와이드 뷰포트에서 자동으로 3열을 생성하여 4개 카드가 배치될 때 2행의 우측 1칸이 비는 비대칭 여백을 발생시켰음.
  - 명시적으로 `repeat(2, 1fr)`을 적용하여 상단 2개, 하단 2개의 대칭 2x2 구도를 확정함.
- **검토된 대안 (Alternatives Considered)**:
  - *대안 A*: `flex-wrap: wrap` 및 `width: calc(50% - 1rem)` Flexbox 방식 → Grid에 비해 상하/좌우 gap 계산 및 행간 높이 동기화가 번거로움 (기각).
  - *대안 B*: 카드 2개를 추가하여 6개(3x2)로 확장 → 현재 실존하는 서브서비스가 4개이므로 불필요한 더미 카드 추가 금지(YAGNI 원칙) (기각).

---

## 2. 반응형 브레이크포인트 및 모바일 전환

### Decision 2: 768px 미디어 쿼리 1열 세로 스택 전환
- **선택된 방안**: `@media (max-width: 768px) { .grid-container { grid-template-columns: 1fr; } }`
- **결정 근거 (Rationale)**:
  - 태블릿 세로 및 스마트폰 화면에서는 2열 배치가 좁아져 카드 내 텍스트 줄바꿈이 빈번해지므로 768px 이하에서 자연스럽게 1열로 전환.

---

## 3. 마크업 클린업 및 시맨틱 정합성

### Decision 3: 불필요한 `<br>` 태그 제거
- **선택된 방안**: `gateway/html/index.html` 내 카드 2와 카드 3 사이의 `<br>` 제거.
- **결정 근거 (Rationale)**:
  - Grid 컨테이너 내부의 `<br>`은 비시맨틱 익명 블록 요소를 생성하여 CSS Grid 레이아웃 트리에 불필요한 항목으로 잡힐 수 있으므로 완전히 제거.
