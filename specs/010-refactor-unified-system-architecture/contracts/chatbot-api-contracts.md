# Interface Contract: 3대 챗봇 API 및 인터페이스 규격

---

## 1. PILOS Chatbot API (`POST /api/chat`)

- **URL**: `http://localhost:8080/api/chat`
- **Method**: `POST`
- **Request Body**:
```json
{
  "message": "PILOS 분석 결과 해석 방법",
  "stock_code": "005930"
}
```

- **Response Body (200 OK - Fast Cache Hit)**:
```json
{
  "status": "success",
  "answer": "PILOS 감정 지수는 -1.0(극단적 비관)부터 +1.0(극단적 낙관)까지의 정량 분석 지표입니다...",
  "source": "knowledge_cache",
  "latency_ms": 12.4
}
```

- **Response Body (200 OK - Dynamic RAG / SSE Stream)**:
  - Header: `Content-Type: text/event-stream; charset=utf-8`
  - Body: SSE chunked data tokens with TTFT < 2.0s

---

## 2. 올원챗 (B-Team AllOneChat) Search API (`POST /bteam/chatb/api/v1/search`)

- **URL**: `http://localhost:8080/bteam/chatb/api/v1/search`
- **Method**: `POST`
- **Request Body**:
```json
{
  "query": "차앤박 프로폴리스 앰플 수분감을 분석해줘",
  "top_n": 3
}
```

- **Response Body (200 OK)**:
```json
{
  "status": "success",
  "query": "차앤박 프로폴리스 앰플 수분감을 분석해줘",
  "search_results": [
    {
      "product_name": "차앤박 프로폴리스 에너지 액티브 앰플",
      "score": 0.94,
      "snippet": "촉촉하고 끈적임 없는 꿀보습..."
    }
  ],
  "llm_answer": "차앤박 프로폴리스 앰플은 보습감 만족도가 92% 이상으로 매우 높게 평가됩니다."
}
```

---

## 3. 올리챗 (B-Team OllyChat) Streamlit Web Portal (`GET /bteam/chata/`)

- **URL**: `http://localhost:8080/bteam/chata/`
- **Protocol**: HTTP 200 Initial Load + WebSocket upgrade on `_stcore/stream`
- **Validation**:
  - Initial HTTP status: `200 OK`
  - Streamlit Session Handshake: Complete within 2.0s
