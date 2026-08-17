# UI Contract: 게이트웨이 포털 웹 프론트엔드 인터페이스 (004-gateway-2x2-grid)

**Feature**: `004-gateway-2x2-grid`  
**Endpoint / File**: `gateway/html/index.html`

---

## 1. 그리드 레이아웃 CSS 계약 (CSS Rules Contract)

```css
/* 데스크톱 기본 (2x2 Grid) */
.grid-container {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.75rem;
  max-width: 1000px;
  width: 100%;
  margin-bottom: 3rem;
}

/* 모바일/소형 태블릿 반응형 (1 Column Stack) */
@media (max-width: 768px) {
  .grid-container {
    grid-template-columns: 1fr;
  }
}

/* 개별 카드 높이 균등화 */
.service-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
```

---

## 2. DOM 구조 계약 (Markup Hierarchy Contract)

```html
<main class="grid-container">
  <!-- Card 1: A-Team Pilos -->
  <a href="/ateam/pilos" class="service-card">...</a>

  <!-- Card 2: B-Team Oliview -->
  <a href="/bteam/oliview" class="service-card">...</a>

  <!-- Card 3: Oliview Chat A -->
  <a href="/bteam/chata" class="service-card">...</a>

  <!-- Card 4: Oliview Chat B -->
  <a href="/bteam/chatb" class="service-card">...</a>
</main>
```

> **규약**: `<main class="grid-container">`의 직계 자식 요소는 정확히 4개의 `<a class="service-card">`만 위치하며, `<br>` 등의 비시맨틱 태그는 포함하지 않는다.
