# Implementation Plan: Oliview Chatbot A 대화 입력창 가로 너비 정렬 최적화

**Branch**: `020-align-chata-chatinput-width` | **Date**: 2026-08-19 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/020-align-chata-chatinput-width/spec.md)

**Input**: Feature specification from `/specs/020-align-chata-chatinput-width/spec.md`

## Summary

Streamlit 기반 Oliview Chatbot A(`bteam/Oliview_chatbot_a/app.py`)에서 화면 하단의 `st.chat_input` 및 하단 고정 컨테이너(`[data-testid="stBottomBlockContainer"]`, `[data-testid="stBottom"]`)가 메인 본문 컨테이너(`.block-container`, 최대 1200px)와 무관하게 화면 전체로 퍼져 시각적 불일치가 발생하는 문제를 해결합니다. 본 계획을 통해 하단 입력창의 최대 너비를 1200px 중앙 정렬로 고정하고 반투명 글래스모피즘 블러 효과를 적용하여 스크롤 겹침 방지 및 멀티 해상도 반응형 일체감을 완벽히 제공합니다.

## Technical Context

**Language/Version**: Python 3.12, CSS3 (Vanilla CSS with CSS Grid & Flexbox)

**Primary Dependencies**: Streamlit (>=1.30.0), bteam.oliview_core

**Storage**: Redis (Session & Vector cache, Spec 019 유지)

**Testing**: Python unittest & Browser UI Viewport Manual/Automated Inspection

**Target Platform**: Web Browsers (Chrome, Edge, Safari, Firefox) on Desktop/Tablet/Mobile

**Project Type**: Streamlit Web Application (`bteam/Oliview_chatbot_a`)

**Performance Goals**: 0ms CSS 렌더링 오버헤드, 60fps 부드러운 반응형 리사이징 및 스크롤

**Constraints**: Streamlit DOM 구조 불변성 유지, 서브모듈 독립성 보장, 0px 정렬 오차

**Scale/Scope**: `bteam/Oliview_chatbot_a/app.py` CSS 스타일 및 레이아웃 정의 영역

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. 언어 및 커뮤니케이션 정책**: 모든 산출물(명세서, 계획서, 문서, 주석)을 한국어로 작성 준수. (PASS)
- **II. TDD 및 계약 검증**: UI 레이아웃 계약(`ui_layout_contract.md`) 및 검증 가이드(`quickstart.md`) 수립 준수. (PASS)
- **III. 서비스 모듈화 및 격리**: B-Team Chatbot A 서브모듈 내에 국한된 안전한 변경으로 타 서비스 영향도 0. (PASS)
- **IV. 관측 가능성 및 로깅**: 기존 세션 관리 및 에러 핸들링 무손실 보존. (PASS)
- **V. 단순성 및 YAGNI**: 불필요한 프레임워크 도입 없이 순수 CSS 주입으로 가장 직관적이고 경량화된 솔루션 채택. (PASS)

## Project Structure

### Documentation (this feature)

```text
specs/020-align-chata-chatinput-width/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan
├── research.md          # Technical research and decisions
├── data-model.md        # UI layout and viewport model
├── quickstart.md        # Verification and testing guide
├── contracts/
│   └── ui_layout_contract.md  # CSS layout contract
└── tasks.md             # Tasks list (generated in next phase)
```

### Source Code Layout

```text
bteam/
└── Oliview_chatbot_a/
    └── app.py           # Streamlit Web Application (CSS injection block update)
```

**Structure Decision**: 기존 Streamlit 단일 앱 진입점인 `bteam/Oliview_chatbot_a/app.py`의 `st.markdown("<style>...</style>")` 섹션에 `ui_layout_contract.md`에 정의된 CSS 규칙을 추가/개선하여 배포합니다.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| :--- | :--- | :--- |
| 없음 (None) | N/A | 가장 단순하고 직관적인 CSS 인라인 주입 표준 방식 채택 |
