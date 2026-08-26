# Research: ChatA 모바일 헤더 가림 현상 해결 및 반응형 레이아웃 최적화

**Branch**: `040-chata-mobile-header-and-layout-optimization`  
**Date**: 2026-08-26  
**Status**: Completed  

---

## 1. Streamlit 모바일 헤더 가림 현상 원인 및 해결 기법

### Problem (문제 분석)
- Streamlit은 기본적으로 최상단에 `header[data-testid="stHeader"]` (고정 높이 `2.875rem`, z-index `999990`) 요소를 렌더링합니다.
- `.block-container`의 `padding-top`이 `1rem` 또는 `2rem`으로 설정되어 있으면, 모바일 뷰포트에서 스크롤을 최상단으로 올렸을 때 메인 타이틀("🌿 Oliview")의 상단 약 20~30px이 `stHeader` 바 뒤로 들어가 잘리는 현상(Header Clipping)이 발생합니다.
- 또한 최신 스마트폰(iOS Safari Dynamic Island, Android Gesture Bar)의 노치 및 안전 여백(`safe-area-inset-top`)이 반영되지 않아 브라우저 상단 주소창과 타이틀이 충돌합니다.

### Solution (기술적 해결책)
```css
/* 1. Streamlit 기본 헤더 바 투명화 및 높이 무력화 */
header[data-testid="stHeader"],
[data-testid="stHeader"] {
    background: transparent !important;
    height: 0 !important;
    min-height: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    pointer-events: none !important;
    z-index: 0 !important;
    visibility: hidden !important;
}

/* 2. 본문 컨테이너 상단 안전 여백 및 모바일 동적 패딩 */
.block-container {
    padding-top: max(3.0rem, env(safe-area-inset-top) + 1.2rem) !important;
    padding-bottom: max(5.0rem, env(safe-area-inset-bottom) + 3.5rem) !important;
    max-width: 1200px !important;
    margin: 0 auto !important;
}

@media (max-width: 768px) {
    .block-container {
        padding-top: max(3.2rem, env(safe-area-inset-top) + 1.5rem) !important;
        padding-bottom: max(4.5rem, env(safe-area-inset-bottom) + 3.0rem) !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }
}
```

---

## 2. 모바일 카테고리 3x2 컴팩트 그리드 오버라이드

### Problem (문제 분석)
- Streamlit의 `st.columns(3)`는 뷰포트 폭 $\le 768$px에서 기본 반응형 규칙에 의해 `flex-direction: column`으로 강제 붕괴되어 6개의 버튼이 세로로 6줄 길게 늘어섭니다.
- 이로 인해 모바일 첫 화면에서 300px 이상의 스크롤 영역이 카테고리 버튼으로 낭비됩니다.

### Solution (CSS Flex/Grid 오버라이드)
- Streamlit 컬럼 컨테이너의 모바일 붕괴를 방어하기 위해 `[data-testid="column"]` 상위 부모 `[data-testid="stHorizontalBlock"]`에 모바일 미디어 쿼리를 적용하여 행당 3개의 버튼이 33.33% 너비(`flex: 1 1 0%`)로 유지되도록 강제합니다.

```css
@media (max-width: 768px) {
    /* 카테고리 버튼이 들어있는 2개 stHorizontalBlock을 3열로 유지 */
    div[data-testid="column"]:nth-of-type(1) div[data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 6px !important;
        margin-bottom: 6px !important;
    }

    div[data-testid="column"]:nth-of-type(1) div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        flex: 1 1 0% !important;
        min-width: 0 !important;
        width: auto !important;
    }

    div[data-testid="column"]:nth-of-type(1) div[data-testid="stHorizontalBlock"] .stButton > button {
        font-size: 13px !important;
        padding: 8px 4px !important;
        min-height: 42px !important;
        touch-action: manipulation !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
}
```

---

## 3. 참조 리뷰 원문 아코디언 모바일 모멘텀 스크롤

### Solution
- 다량의 리뷰가 한 번에 펼쳐질 때 모바일 대화창이 화면 밖으로 밀려나는 것을 방지:
```css
@media (max-width: 768px) {
    .stAccordion [data-testid="stExpanderDetails"] {
        max-height: 240px !important;
        overflow-y: auto !important;
        -webkit-overflow-scrolling: touch !important;
        padding: 8px !important;
        background: #fbfdfb !important;
        border-radius: 8px !important;
    }
}
```

---

## 4. 결론 및 적용 방안
- 별도의 프레임워크 변경 없이 `bteam/Oliview_chatbot_a/app.py` 내부의 Custom CSS 블록 및 모바일 미디어 쿼리 최적화를 통해 100% 클라이언트 사이드 즉각 반영이 가능하며, Docker 컨테이너 재빌드 없이 소스코드 마운트를 통해 0초 핫 리로드로 검증 가능.
