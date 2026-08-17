# Contract: Pilos Web & API Endpoints

**Component**: A-Team Pilos (`pilos-web:5000`)  
**Base URL (Public)**: `https://ezenitac.duckdns.org/ateam/pilos` & `https://ezenitac.duckdns.org`  
**Internal Port**: `5000`

---

## 1. Web Page Routes

### `GET /` & `GET /ateam/pilos/`
- **Description**: Pilos 종합 감성 지수 메인 대시보드 렌더링
- **Response**: `200 OK` (HTML - `templates/index.html`)

### `GET /stocks/<stock_code>` & `GET /ateam/pilos/stocks/<stock_code>`
- **Description**: 종목별 상세 감성 분석 화면 렌더링
- **Path Parameters**:
  - `stock_code` (string, required): 6자리 종목 코드 (예: `005930`)
- **Response**: `200 OK` (HTML - `templates/detail.html`)

### `GET /about` & `GET /ateam/pilos/about`
- **Description**: Pilos 서비스 소개 및 모델 v5 방법론 안내
- **Response**: `200 OK` (HTML - `templates/about.html`)

---

## 2. REST API Endpoints

### `GET /api/stocks`
- **Description**: 10개 종목의 최신 감성 지수 목록 조회
- **Response**: `200 OK`
  ```json
  [
    {
      "stock_code": "005930",
      "stock_name": "삼성전자",
      "model_date": "2026-08-16",
      "comment_count": 1420,
      "analysis_status": "COMPLETED",
      "actual_supply_demand_index": 62.4
    }
  ]
  ```

### `GET /api/stocks/<stock_code>`
- **Description**: 개별 종목의 7일간 감성 지수 히스토리 조회
- **Response**: `200 OK`
  ```json
  {
    "stock_code": "005930",
    "stock_name": "삼성전자",
    "latest": { ... },
    "history": [ ... ]
  }
  ```

### `GET /api/stocks/<stock_code>/llm-reports?model_date=YYYY-MM-DD`
- **Description**: 특정 일자의 종목 LLM 종합 분석 리포트 조회
- **Query Parameters**:
  - `model_date` (string, required): 조회 기준 일자 (`YYYY-MM-DD`)
- **Response**: `200 OK`
  ```json
  {
    "stock_code": "005930",
    "model_date": "2026-08-16",
    "summary": "삼성전자는 최근 반도체 수급 개선 기대감으로...",
    "positive_points": "외국인 순매수 유입 및 HBM 공급 확대...",
    "negative_points": "글로벌 매크로 불확실성 지속...",
    "generated_at": "2026-08-16T18:30:00"
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: `model_date` 누락 또는 포맷 오류
  - `404 Not Found`: 해당 날짜의 리포트 부재
