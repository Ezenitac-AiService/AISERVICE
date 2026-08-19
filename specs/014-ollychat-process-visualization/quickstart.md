# Quickstart & Verification Guide: OllyChat RAG 파이프라인 실시간 시각적 진행과정

**Feature**: `014-ollychat-process-visualization`  
**Date**: 2026-08-19  
**Status**: Ready for Implementation  

---

## 1. 개요

본 문서는 올리챗 A(Streamlit)와 올리챗 B(FastAPI/Web)에서 개발된 실시간 4단계 RAG 진행 상태 인디케이터, 토큰 타이핑 스트리밍, 완료 축약 뱃지, 참조 리뷰 아코디언 및 에러 복구 칩 기능이 올바르게 동작하는지 검증하기 위한 가이드입니다.

---

## 2. 사전 환경 확인 (Prerequisites)

1. Python 3.10+ 및 `uv` 패키지 매니저가 설치되어 있어야 합니다.
2. GPU 서버 또는 vLLM LLM API 서버가 활성화되어 있어야 합니다 (호스트: `http://192.168.0.151` 등 또는 로컬 모의 서버).
3. ChromaDB 및 MySQL 리뷰 데이터베이스가 준비되어 있어야 합니다.

---

## 3. 올리챗 A (Streamlit: `06.app.py`) 실행 및 검증

### 3.1 실행 명령어
```bash
cd c:\AISERVICE\bteam\Oliview_chatbot_a
uv run --active streamlit run 06.app.py --server.port 8501
```

### 3.2 검증 시나리오 및 기대 결과

#### 시나리오 1: 4단계 실시간 순차 진행 및 자동 축약 검증
1. 브라우저에서 `http://localhost:8501` 접속.
2. 질문창에 `"컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘"` 입력 후 전송.
3. **기대 결과**:
   - 질문 즉시 화면에 `st.status` 컨테이너가 열리며 4단계(의도 분석 ➡️ 하이브리드 검색 ➡️ 리랭킹 ➡️ LLM 생성)가 순차적으로 진행 로그를 출력함.
   - 4단계 진입 시 LLM 답변이 한 글자씩 실시간 타이핑 스트리밍(`st.write_stream`)으로 화면에 렌더링됨.
   - 생성이 완료되면 `st.status`가 자동으로 접히며 `✅ 리뷰 종합 분석 완료 (소요시간, N건 참조)` 한 줄 뱃지로 축약됨.
   - 축약 뱃지 클릭 시 4단계 세부 진행 내역이 다시 펼쳐짐.

#### 시나리오 2: 참조 리뷰 원문 아코디언 열람
1. 시나리오 1 완료 후 답변 하단 확인.
2. `📖 실제 참조 리뷰 원문 (5건)` 아코디언을 클릭하여 펼침.
3. **기대 결과**:
   - 상위 5건의 실제 구매자 리뷰 원문, 평점, 피부타입/속성 정보가 깔끔하게 렌더링됨.

#### 시나리오 3: 0건 검색 및 재시도 칩 검증
1. 존재하지 않는 더미 키워드(`"없는브랜드 9999"` 등) 질문 전송.
2. **기대 결과**:
   - 상태 박스가 `⚠️ 경고` 상태로 변경되며, 하단에 `🔄 다시 시도` 버튼 및 `추천 검색어 칩`이 나타남.
   - 칩 클릭 시 해당 키워드로 즉시 재검색이 수행됨.

---

## 4. 올리챗 B (FastAPI / Web UI) 실행 및 검증

### 4.1 실행 명령어
```bash
cd c:\AISERVICE\bteam\Oliview_chatbot_b
uv run uvicorn project_ragapi:app --host 0.0.0.0 --port 8000 --reload
```

### 4.2 검증 시나리오 및 기대 결과

#### 시나리오 1: SSE 엔드포인트 수명 주기 검증
```bash
curl -N -X POST "http://localhost:8000/api/v1/search/stream" \
  -H "Content-Type: application/json" \
  -d '{"query": "식물나라 선크림 지속력 어때?", "fetch_k": 10, "top_n": 3}'
```
- **기대 결과**:
  - `event: step` (Phase 1 ~ 4) 데이터가 순차 수신됨.
  - `event: token` 토큰 스트림이 연속 수신됨.
  - `event: complete` 최종 메타데이터와 참조 리뷰 배열이 수신되고 스트림이 종료됨.

#### 시나리오 2: 웹 대시보드 인터랙션 검증
1. 브라우저에서 `http://localhost:8000/index.html` 접속.
2. 상단 질문 입력창에 `"식물나라 선크림 지속력 분석해줘"` 입력 후 [분석 요청] 클릭.
3. **기대 결과**:
   - 상단 진행 타임라인에서 4단계가 순차적으로 녹색 뱃지로 전환됨.
   - 실시간 타이핑 애니메이션으로 AI 답변이 완성된 후 완료 뱃지로 깔끔하게 축약됨.
   - 하단에 참조 리뷰 원문 아코디언 및 상품 카드가 정상 표시됨.

---

## 5. 단위 및 계약 테스트 실행

```bash
# 올리챗 A 단위 테스트
uv run pytest tests/test_step_callback_a.py -v

# 올리챗 B SSE 엔드포인트 계약 테스트
uv run pytest tests/test_sse_contract_b.py -v
```
