# Data Model: 게이트웨이 포털 2x2 대칭 그리드 UI 컴포넌트 모델 (004-gateway-2x2-grid)

**Feature**: `004-gateway-2x2-grid`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/004-gateway-2x2-grid/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/004-gateway-2x2-grid/plan.md)

---

## 1. UI 컴포넌트 엔티티 (Entity Definitions)

### `GridContainer` (레이아웃 엔티티)
- **역할**: 4개의 `ServiceCard`를 2행 2열(2x2) 격자로 배치하는 최상위 그리드 컨테이너
- **속성 (CSS Properties)**:
  - `display`: `grid`
  - `grid-template-columns`: `repeat(2, 1fr)` (데스크톱 >= 768px) / `1fr` (모바일 < 768px)
  - `gap`: `1.75rem`
  - `max-width`: `1000px`
  - `width`: `100%`
  - `margin-bottom`: `3rem`

### `ServiceCard` (서비스 카드 엔티티)
- **역할**: 사용자가 서브서비스(A-Team Pilos, B-Team Oliview, 올리챗, 올원챗)로 진입할 수 있는 대화형 링크 카드
- **속성 (Attributes)**:
  - `href`: 대상 서브서비스 경로 (`/ateam/pilos`, `/bteam/oliview`, `/bteam/chata`, `/bteam/chatb`)
  - `icon`: 서비스 대표 이모지 (`📈`, `💄`, `🤖`, `💬`)
  - `badge`: 서비스 구분 배지 (`A-TEAM`, `B-TEAM`, `AI CHATBOT`, `RAG AGENT`)
  - `title`: 서비스 명칭 (`Pilos 감정지수 서비스`, `Oliview 메인 서비스`, `올리챗 (Oliview Chat A)`, `올원챗 (Oliview Chat B)`)
  - `description`: 2줄 내외의 서비스 개요 설명
  - `meta_left`: 기술 스택 요약 태그
  - `meta_right`: 이동 액션 텍스트
  - `height`: `100%` (각 행 내 자동 높이 균등화)
