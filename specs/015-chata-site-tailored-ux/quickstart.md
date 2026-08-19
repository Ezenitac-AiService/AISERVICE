# Quickstart & Verification Guide: 통합 3대 챗봇 맞춤형 UX 고도화

**Feature**: `015-unified-chatbots-tailored-ux`  
**Date**: 2026-08-19

---

## 1. 사전 검증 환경 및 엔드포인트 토폴로지

- **올리챗 A (Streamlit)**: `http://localhost:8501/` 또는 게이트웨이 `http://localhost:8080/bteam/chata/`
- **올원챗 B (Web / FastAPI)**: `http://localhost:8002/` 또는 게이트웨이 `http://localhost:8080/bteam/chatb/`
- **PILOS 챗봇 (FastAPI / Jinja2)**: `http://localhost:8000/` 또는 게이트웨이 `http://localhost:8080/`

---

## 2. 통합 자동화 테스트 실행

```bash
# 1. 3대 챗봇 계약 및 유닛 테스트 일괄 검증
uv run python tests/test_chata_stream.py
uv run python tests/test_chatb_noise_filter.py
uv run python tests/test_pilos_stream.py
uv run python tests/test_xss_escape.py
uv run python tests/test_cross_chatbot_latency.py
```

---

## 3. 브라우저 실서비스 E2E 시나리오 검증

### 시나리오 1: 올리챗 A (Streamlit)
1. 브라우저에서 `http://localhost:8501/` 또는 `http://localhost:8080/bteam/chata/` 접속.
2. 상단 질문 예시 칩(`차앤박 앰플 수분감`) 클릭.
3. `st.status` 4단계(의도 ➡️ 검색 ➡️ 리랭킹 ➡️ 생성)가 순차 갱신되고 답변이 타이핑 출력되는지 확인.
4. 답변 하단 `📖 실제 참조 리뷰 원문` 아코디언에서 `올리브영 상세보기 ↗` 버튼 클릭 시 `[브랜드 + 상품명]`으로 올리브영 검색 페이지가 새 탭에서 열리는지 확인.

### 시나리오 2: 올원챗 B (Web / FastAPI)
1. 브라우저에서 `http://localhost:8080/bteam/chatb/` 접속.
2. "컬러그램 탕후루 탱글 꿀로스 발림성 장단점" 질의 전송.
3. 4단계 타임라인 완료 후 요약 배지 축약 및 `올리브영 상세보기 ↗` 버튼의 노이즈 제거 여부 확인.

### 시나리오 3: PILOS 챗봇 (A-Team 금융)
1. 브라우저에서 `http://localhost:8080/` 접속.
2. 추천 칩(`📈 실제 수급지수 요약`) 클릭.
3. 4단계 금융 분석 타임라인과 첫 토큰 1.5초 이내 스트리밍, `네이버 증권 바로가기 ↗` 링크 유효성 확인.
