# Phase 1: Frontend UI Layout & Viewport Data Model

**Feature**: `020-align-chata-chatinput-width`

## Overview

본 피처는 프론트엔드 CSS 레이아웃 및 뷰포트 정렬에 관한 것으로, 백엔드 데이터베이스 엔티티 변경은 수반하지 않습니다. 대신 UI 컴포넌트 렌더링 상태 및 뷰포트 레이아웃 모델을 명세합니다.

---

## 1. UI Layout Model Structure

```text
+-----------------------------------------------------------------------+
|  Viewport (Window Width: W px)                                        |
|                                                                       |
|  +-----------------------------------------------------------------+  |
|  |  .block-container (Max-Width: 1200px, Margin: 0 auto)            |  |
|  |  - Header & Title                                               |  |
|  |  - Main 2-Column Grid (Settings [1.6] : Examples [1.4])          |  |
|  |  - Chat Messages (User / Assistant / References)                |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  ===================================================================  |
|  |  [data-testid="stBottom"] (Fixed Bottom Wrapper with Blur)       |  |
|  |  +-------------------------------------------------------------+ |  |
|  |  |  [data-testid="stBottomBlockContainer"]                     | |  |
|  |  |  (Max-Width: 1200px, Margin: 0 auto, Padding: 0 1rem)      | |  |
|  |  |  - st.chat_input widget                                     | |  |
|  |  +-------------------------------------------------------------+ |  |
|  ===================================================================  |
+-----------------------------------------------------------------------+
```

---

## 2. Layout Property Specifications

### A. Main Content Container (`.block-container`)
- `max-width`: `1200px`
- `margin-left`: `auto`
- `margin-right`: `auto`
- `padding-top`: `2rem`
- `padding-bottom`: `3rem`
- `padding-left`: `1rem`
- `padding-right`: `1rem`

### B. Bottom Fixed Bar (`[data-testid="stBottom"]`)
- `position`: `fixed`
- `bottom`: `0`
- `left`: `0`
- `width`: `100%`
- `background`: `rgba(255, 255, 255, 0.88)`
- `backdrop-filter`: `blur(12px)`
- `border-top`: `1px solid rgba(220, 232, 224, 0.6)`
- `z-index`: `99`

### C. Bottom Input Wrapper (`[data-testid="stBottomBlockContainer"]`, `.stBottomBlockContainer`)
- `max-width`: `1200px`
- `margin-left`: `auto`
- `margin-right`: `auto`
- `padding-left`: `1rem`
- `padding-right`: `1rem`
- `box-sizing`: `border-box`
- `width`: `100%`

---

## 3. Responsive Breakpoints & State Transitions

| Viewport Width ($W$) | Main Container Width | Bottom Input Bar Width | Horizontal Alignment |
| :--- | :--- | :--- | :--- |
| **Desktop ($W \ge 1200\text{px}$)** | `1200px` | `1200px` | 중앙 정렬 (`margin: 0 auto`) |
| **Tablet ($768\text{px} \le W < 1200\text{px}$)** | $W - 2\text{rem}$ | $W - 2\text{rem}$ | 100% 비례 축소 (`padding: 0 1rem`) |
| **Mobile ($W < 768\text{px}$)** | $W - 1.5\text{rem}$ | $W - 1.5\text{rem}$ | 풀 와이드 반응형 패딩 |
