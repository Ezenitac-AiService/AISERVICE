# Quickstart & Verification Guide: 038-product-series-resolution-and-citation-enforcement

**Feature Branch**: `038-product-series-resolution-and-citation-enforcement`  

---

## 1. Run Unit Tests (TDD Verification)

```bash
uv run --with pytest --with pydantic --with numpy --with fastapi --with httpx pytest bteam/Oliview_chatbot_a/tests/ -v -o pythonpath=bteam/Oliview_chatbot_a
```

---

## 2. Launch ChatA FastAPI Web Server

```bash
uv run uvicorn bteam.Oliview_chatbot_a.main:app --host 0.0.0.0 --port 8501 --reload
```

---

## 3. End-to-End Validation Scenarios

### Scenario 1: Series Query Resolution & Review Citation
- **URL**: `http://localhost:8501`
- **Query**: `"헤라 센슈얼 립 촉촉함과 각질부각 분석해줘"`
- **Expected Outcome**:
  - 상태 박스: `✅ 리뷰 분석 완료 (1.X초, 4건 선별)`
  - 본문: "헤라 센슈얼 누드 밤" 및 "헤라 센슈얼 누드 글로스" 등 실존 상품 2종이 비교 분석되며, `[헤라 센슈얼 누드 밤 리뷰 1]`, `[헤라 센슈얼 누드 밤 리뷰 2]` 인용 태그가 명기됨.
  - "각질부각"이 "아쉬운 점/주의할 점"에 올바르게 배치되며 긍정 효과로 오역되지 않음.
  - 하단 `📚 참조 리뷰 원문 (4건 선별)` 아코디언이 제품별로 펼쳐짐.

### Scenario 2: Zero-Search Hard Block (No Hallucination)
- **Query**: `"화성인 안드로메다 은하수 수분크림 분석해줘"`
- **Expected Outcome**:
  - 가짜 리뷰 창작 없이 즉시 "현재 올리브영 데이터베이스에 등록된 실제 구매자 리뷰를 찾을 수 없습니다" 정직한 부재 안내 출력.

### Scenario 3: 2026 Mobile Responsive View
- **Mobile Emulation** (F12 $\rightarrow$ iPhone 14 Pro, 393px):
  - 상단 2열이 상단 가로 스크롤 칩 필터로 컴팩트 전환.
  - 본문의 `[리뷰 1]` 탭 시 하단에서 부드러운 글래스모피즘 **바텀 시트 드로어(Bottom Sheet)** 슬라이드업 확인.
  - '⏹️ 생성 중단' 클릭 시 즉시 중단 확인.
