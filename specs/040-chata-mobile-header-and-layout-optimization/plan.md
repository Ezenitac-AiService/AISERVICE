# Implementation Plan: ChatA 모바일 헤더 가림 현상 해결 및 반응형 레이아웃 최적화

**Branch**: `040-chata-mobile-header-and-layout-optimization` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)  
**Constitution Version**: v1.1.1 Compliant  

---

## Summary

본 피처는 Oliview ChatA(`bteam/Oliview_chatbot_a/app.py`)의 모바일 뷰포트($\le 768$px)에서 발생하는 **상단 헤더 잘림(Header Clipping) 현상**을 근본 해결하고, 6개의 카테고리 선택 버튼이 세로로 길게 무너져 화면을 독점하던 결함을 **3열 2행(3x2)의 컴팩트 반응형 그리드**로 개편합니다. 또한 2026년 대화형 AI 모바일 UX 트렌드에 맞추어 상단 설정 패널의 여백을 40% 압축하고, 참조 리뷰 원문 아코디언에 240px 최대 높이 및 네이티브 모멘텀 스크롤을 적용하며, 하단 채팅 입력바에 Safe-Area 인셋을 완벽히 연동합니다.

---

## Technical Context

- **Language/Framework**: Python 3.12, Streamlit 1.62.0, Vanilla CSS
- **Target Components**: `bteam/Oliview_chatbot_a/app.py` (Custom CSS & Responsive Layout Blocks)
- **Target Platforms**: Mobile Safari (iOS), Mobile Chrome/Samsung Internet (Android), Desktop Web (>768px)
- **Performance Goals**: 0ms 추가 지연시간, 순수 CSS 미디어 쿼리 기반 반응형 렌더링 (60fps)
- **Constraints**: 데스크톱($>768$px) 2컬럼 [1.6 : 1.4] 레이아웃 100% 무결성 유지, 무하드코딩 원칙 준수

---

## Constitution Check (v1.1.1)

- [X] **Principle I: 100% 무환각 RAG 불변 원칙** - UI/UX 개선 작업으로 RAG 무환각 파이프라인 및 인라인 인용 로직을 100% 보존함.
- [X] **Principle II: 엄격한 종단간 지연시간 및 하드웨어 적응형 SLA** - 추가 연산이나 백엔드 지연 없이 순수 CSS로 구동되어 SLA를 완벽 충족함.
- [X] **Principle III: 레이어별 캐싱 및 서비스 격리 보장** - 기존 Redis L1~L5 캐싱 계층 및 오케스트레이터 구조를 일체 훼손하지 않음.
- [X] **Principle IV: 테스트 주도 및 근거 기반 검증 (Zero Mocking in Target Logic)** - 반응형 CSS 계약 및 브라우저 레이아웃 실시간 검증 수행.
- [X] **Principle V: 한국어 뷰티 도메인 특화 정확성** - 뷰티 카테고리(스킨케어, 클렌징 등) 및 속성 칩의 가독성과 터치 조작성을 극대화함.
- [X] **Principle VI: 다중 런타임 환경 분리 및 무하드코딩 원칙** - 화면 크기에 따른 분기는 CSS 표준 미디어 쿼리(`@media (max-width: 768px)`)로 동적 처리.

---

## Project Structure & Target Files

```text
bteam/Oliview_chatbot_a/
├── app.py                          # [MODIFY] Custom CSS 주입, 3x2 카테고리 그리드, Safe-Area, 모바일 축약 플레이스홀더
└── tests/
    └── test_feature_039_zero_search.py  # [VERIFY] 기존 RAG 및 오케스트레이터 리그레션 방어
```

---

## Implementation Phases

### Phase 1: Custom CSS Header & Safe-Area Inset Enhancement
- `header[data-testid="stHeader"]` 가림/투명화 (`visibility: hidden; height: 0; pointer-events: none;`)
- `.block-container` 모바일 상단 안전 여백 (`padding-top: max(3.2rem, env(safe-area-inset-top) + 1.5rem) !important;`)
- 하단 고정바 Safe-Area (`[data-testid="stBottom"]` `padding-bottom: max(0.75rem, env(safe-area-inset-bottom));`)

### Phase 2: Category 3x2 Compact Responsive Grid
- `div[data-testid="column"]:nth-of-type(1) div[data-testid="stHorizontalBlock"]` 모바일 플렉스 오버라이드
- 6개 카테고리 버튼을 행당 3개씩(3열 2행) 균등 분할 (`flex: 1 1 0%`, 높이 42px)
- 터치 타깃 `min-height: 42px`, `touch-action: manipulation` 적용

### Phase 3: Analysis Panel & 1-Click Example Queries Slimming
- 브랜드 칩 박스(`.brand-box`) 및 분석 속성 카드(`.attribute-card`) 모바일 마진/패딩 축소
- 1클릭 질문 예시 버튼 패딩 및 폰트 크기 최적화

### Phase 4: Reference Review Accordion & Mobile Input UX
- 모바일 참조 리뷰 아코디언(`.stAccordion [data-testid="stExpanderDetails"]`) `max-height: 240px`, `-webkit-overflow-scrolling: touch` 적용
- 하단 채팅 입력창 플레이스홀더 축약형(`"브랜드, 제품, 속성을 입력해주세요"`) 적용

### Phase 5: Live Verification & Quality Audit
- Chrome DevTools 디바이스 모드 및 모바일 실기기에서 상단 0px 잘림, 3x2 그리드, 2컬럼 데스크톱 무결성 검증.
