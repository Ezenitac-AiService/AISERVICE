# UI Component Contract: OllyChat Process Indicators & Accordion

**Feature**: `014-ollychat-process-visualization`  
**Targets**: 올리챗 A (`06.app.py`), 올리챗 B (`index.html`)  

---

## 1. 개요

올리챗 A(Streamlit)와 올리챗 B(웹 프론트엔드)에서 렌더링되는 시각적 진행 인디케이터, 완료 축약 뱃지, 실시간 타이핑 스트리밍 및 참조 리뷰 아코디언 컴포넌트의 UI 구조와 CSS 규격을 정의합니다.

---

## 2. 올리챗 A (Streamlit: `06.app.py`) UI 계약

### 2.1 실시간 진행 컨테이너 (`st.status`)
```python
# 1. 진행 중 상태
with st.status("🔍 질문 의도 및 화장품 속성 분석 중...", expanded=True) as status:
    # 단계별 완료 시마다 status.write 호출
    status.write("🔍 질문 의도 및 화장품 속성 분석 완료")
    status.write("📚 리뷰 하이브리드 검색 중 (BM25 + BGE-M3)...")
    ...
    
# 2. 완료 후 자동 축약 전환 (FR-004)
status.update(
    label=f"✅ 리뷰 종합 분석 완료 ({elapsed:.1f}초, {len(ref_reviews)}건 참조)",
    state="complete",
    expanded=False
)
```

### 2.2 참조 리뷰 원문 접이식 아코디언 (`st.expander`) (FR-012)
```python
with st.expander(f"📖 실제 참조 리뷰 원문 ({len(ref_reviews)}건)", expanded=False):
    for review in ref_reviews:
        st.markdown(
            f"""
            <div class="review-ref-card">
                <div class="review-ref-header">
                    <strong>#{review['rank']} {review['brand_name']} {review['product_name']}</strong>
                    <span class="score-badge">⭐ {review['review_score']}점 ({review['attribute_tag']})</span>
                </div>
                <div class="review-ref-text">"{review['separated_sentence']}"</div>
            </div>
            """,
            unsafe_allow_html=True
        )
```

### 2.3 과거 대화 기록 복원 렌더링 (FR-013)
- 과거 메시지(`messages` 세션)에 저장된 메타데이터가 있을 경우, 접힌 형태의 완료 뱃지(`st.status(state="complete", expanded=False)` 또는 스타일 박스)로 즉시 렌더링하고, 클릭 시에만 세부 내역을 펼칩니다.

### 2.4 에러 및 재시도 칩 UI (FR-010)
```python
# 0건 또는 에러 시
st.warning("⚠️ 일치하는 리뷰 데이터를 찾지 못했습니다.")
col_retry, col_chip1, col_chip2 = st.columns([1, 2, 2])
with col_retry:
    if st.button("🔄 다시 시도", key="btn_retry"):
        st.rerun()
# 추천 완화 검색어 칩 클릭 시 입력창 반영 및 즉시 실행
```

---

## 3. 올리챗 B (Web UI: `index.html`) UI 계약

### 3.1 4단계 진행 타임라인 컴포넌트 (`#stepProgressContainer`)
```html
<div id="stepProgressContainer" class="step-progress-wrapper">
    <div class="step-badge-header" onclick="toggleStepDetails()">
        <span id="stepOverallIcon">⏳</span>
        <span id="stepOverallLabel">AI 뷰티 가이드가 질문을 분석하고 있습니다...</span>
        <span id="stepElapsedBadge" class="elapsed-badge">0.4s</span>
    </div>
    <div id="stepDetailsBox" class="step-details-box">
        <div class="step-item" id="step-1"><span class="step-icon">🔍</span> 질문 의도 및 속성 분석</div>
        <div class="step-item" id="step-2"><span class="step-icon">📚</span> 하이브리드 리뷰 검색</div>
        <div class="step-item" id="step-3"><span class="step-icon">⚖️</span> BGE-Reranker 순위 정렬</div>
        <div class="step-item" id="step-4"><span class="step-icon">🧠</span> LLM 심층 생성</div>
    </div>
</div>
```

### 3.2 스타일 가이드 및 클래스 정의 (`CSS`)
```css
.step-progress-wrapper {
    background: #f8fafc;
    border: 1px solid #dce9df;
    border-radius: 12px;
    padding: 12px 18px;
    margin-bottom: 18px;
    transition: all 0.3s ease;
}
.step-progress-wrapper.completed {
    background: #f0fdf4;
    border-color: #86efac;
}
.step-item.active {
    color: #2e7d32;
    font-weight: 700;
}
.step-item.done .step-icon::after {
    content: " ✅";
}
.ref-accordion {
    margin-top: 20px;
    border-top: 1px solid #e2e8f0;
    padding-top: 14px;
}
.rec-chips {
    display: flex;
    gap: 8px;
    margin-top: 10px;
    flex-wrap: wrap;
}
.chip-btn {
    background: #e2e8f0;
    border: none;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 13px;
    cursor: pointer;
}
.chip-btn:hover {
    background: #2e7d32;
    color: white;
}
```

---

## 4. 반응형 및 모바일 최적화 규칙 (FR-009)

1. 화면 폭 768px 이하 모바일 환경에서는 `#stepDetailsBox`는 기본 접힘(Hidden) 상태이며, 헤더 한 줄 뱃지만 노출됩니다.
2. 텍스트 라벨과 상태 아이콘은 항상 나란히 배치하여 스크린 리더와 시각적 구분을 동시에 지원합니다 (NFR-003).
