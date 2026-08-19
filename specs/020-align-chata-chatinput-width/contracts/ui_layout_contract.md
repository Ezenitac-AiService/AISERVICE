# UI Layout & CSS Style Contract

**Feature**: `020-align-chata-chatinput-width`

## 1. CSS Selector and Rule Contract

Streamlit Chatbot A의 프론트엔드 스타일 주입 블록(`app.py` 내 `st.markdown(..., unsafe_allow_html=True)`)에 다음 계약 규칙이 준수되어야 합니다.

```css
/* ========================================================================== */
/* Spec 020: Bottom Chat Input Max-Width 1200px & Glassmorphism Blur Contract */
/* ========================================================================== */

/* 1. Main Block Container Consistency */
.block-container {
    padding-top: 2rem !important;
    padding-bottom: 5rem !important;
    max-width: 1200px !important;
    margin: 0 auto !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}

/* 2. Bottom Fixed Wrapper Styling & Backdrop Blur */
[data-testid="stBottom"],
div[data-testid="stBottom"] {
    background: rgba(255, 255, 255, 0.88) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border-top: 1px solid rgba(220, 232, 224, 0.6) !important;
}

/* 3. Bottom Block Container (Input Box Container) Max-Width & Center Alignment */
[data-testid="stBottomBlockContainer"],
.stBottomBlockContainer,
div[data-testid="stBottom"] > div {
    max-width: 1200px !important;
    margin-left: auto !important;
    margin-right: auto !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    box-sizing: border-box !important;
    width: 100% !important;
}

/* 4. Chat Input Widget Constraints */
[data-testid="stChatInput"],
.stChatInput {
    max-width: 1200px !important;
    margin: 0 auto !important;
}

/* 5. Mobile & Tablet Responsive Optimization */
@media (max-width: 768px) {
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 4.5rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }
    [data-testid="stBottomBlockContainer"],
    .stBottomBlockContainer {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }
}
```

---

## 2. Invariant Contracts

1. **Alignment Invariant**: 가로 해상도가 1200px 이상일 때, `.block-container`의 좌측 오프셋과 `[data-testid="stBottomBlockContainer"]`의 좌측 오프셋 간의 차이는 $0\text{px}$이어야 한다.
2. **Backdrop Invariant**: 대화 스크롤 발생 시 하단 고정 바 뒤로 지나가는 텍스트에 블러 필터(`blur(12px)`)와 반투명 알파 채널(`rgba(255, 255, 255, 0.88)`)이 항상 적용되어 텍스트 겹침이 방지되어야 한다.
3. **No Horizontal Overflow Invariant**: 360px부터 4K 해상도까지 수평 스크롤바(`overflow-x: hidden`)가 발생하지 않아야 한다.
