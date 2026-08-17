# Contract: Oliview ChatB (올원챗) API Endpoints

**Component**: B-Team Oliview Chatbot B (`oliview_chatbot_b:8002`)  
**Base URL (Public)**: `https://ezenitac.duckdns.org/bteam/chatb`  
**Internal Port**: `8002`

---

## 1. Web Page & Swagger

### `GET /` & `GET /bteam/chatb/`
- **Description**: 올원챗 RAG 검색 인터랙티브 웹 UI (`index.html`) 서빙
- **Response**: `200 OK` (HTML)

### `GET /docs` & `GET /bteam/chatb/docs`
- **Description**: FastAPI Swagger UI 대화형 API 문서
- **Response**: `200 OK` (Swagger UI HTML)

---

## 2. RAG Search API

### `POST /bteam/chatb/api/v1/search` & `POST /api/v1/search`
- **Description**: BGE-M3 밀집 벡터 임베딩(8090) + 키워드 검색 + BGE-Reranker(8091) + Qwen LLM(8081) 합성 하이브리드 RAG 검색
- **Request Body**:
  ```json
  {
    "query": "건성 피부 보습 앰플 추천",
    "top_n": 5,
    "model": null
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "llm_answer": "건성 피부의 보습 개선을 위해 가장 추천하는 상품은...",
    "search_results": [
      {
        "product_id": 1024,
        "product_name": "토리든 다이브인 저분자 히알루론산 세럼",
        "brand_name": "토리든",
        "category": "에센스/세럼/앰플",
        "review_score": 4.8,
        "separated_sentence": "속건조를 꽉 잡아줘서 사계절 내내 사용하기 좋아요.",
        "display_name": "보습력",
        "sentiment_label": "positive"
      }
    ],
    "model_used": "qwen3.5-9b"
  }
  ```
- **Fallback Response (검색 결과 부재 시)**:
  ```json
  {
    "llm_answer": "관련 리뷰 데이터를 찾을 수 없습니다. 올리브영 등록 상품명으로 다시 검색해주세요.",
    "search_results": [],
    "model_used": "fallback-system"
  }
  ```
