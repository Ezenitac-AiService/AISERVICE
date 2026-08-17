# Phase 1 Data Model: E2E 서비스 안정화 및 서브서비스 종합 점검 (003-e2e-service-stabilization)

**Feature Branch**: `003-e2e-service-stabilization`  
**Created**: 2026-08-17  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/003-e2e-service-stabilization/spec.md)

---

## 1. A-Team Pilos 데이터 모델 (`pilos_v2` DB)

```mermaid
erDiagram
    STOCK ||--o{ SENTIMENT_INDEX_RESULT : has
    STOCK ||--o{ LLM_REPORT : has
    STOCK ||--o{ ARTIFACTS : references

    STOCK {
        string stock_code PK "종목 코드 (6자리 숫자, 예: 005930)"
        string stock_name "종목명 (예: 삼성전자)"
        string market_type "시장 구분 (KOSPI/KOSDAQ)"
    }

    SENTIMENT_INDEX_RESULT {
        string stock_code FK
        date model_date PK "분석 기준 일자"
        float actual_supply_demand_index "실제 수급 지수"
        bigint actual_buy_volume "매수량"
        bigint actual_sell_volume "매도량"
        int comment_count "수집 댓글 수"
        string analysis_status "분석 상태 (COMPLETED/PENDING)"
    }

    LLM_REPORT {
        string stock_code FK
        date model_date PK "리포트 기준 일자"
        text summary "일별 종합 분석 요약문"
        text positive_points "긍정 요인 분석"
        text negative_points "부정 요인 분석"
        datetime generated_at "생성 일시"
    }

    ARTIFACTS {
        int artifact_id PK
        string model_variant "모델 버전 (v5)"
        json metadata "모델 가중치 및 설정 메타데이터"
    }
```

### Validation Rules
- `stock_code`: 6자리 숫자 정규식 (`^\d{6}$`). 빈 문자열 불허.
- `model_date`: `YYYY-MM-DD` ISO 8601 포맷.
- `analysis_status`: `COMPLETED`, `PENDING`, `ERROR` 중 하나.

---

## 2. B-Team Oliview 데이터 모델 (`oliview_project` DB & In-Memory)

```mermaid
erDiagram
    BRANDS ||--o{ BRAND_ACCOUNTS : identifies
    BRANDS ||--o{ BRAND_MANAGERS : manages
    BRANDS ||--o{ PRODUCTS : owns
    BRAND_ACCOUNTS ||--o{ PAYMENT_METHODS : pays

    BRANDS {
        int brand_id PK "브랜드 고유 ID"
        string brand_name "브랜드 공식 명칭"
        string brand_code "브랜드 코드 (3,062개 고유 식별자)"
        tinyint is_active "활성 상태 (1: 활성, 0: 비활성)"
    }

    BRAND_ACCOUNTS {
        int account_id PK
        int brand_id FK "1:1 관계"
        string brand_pw_hash "비밀번호 해시 (pbkdf2:sha256/werkzeug)"
        string status "상태 (ACTIVE/WITHDRAWING/WITHDRAWN)"
        datetime withdrawn_at "탈퇴 신청 일시 (30일 유예)"
    }

    BRAND_MANAGERS {
        int manager_id PK
        int brand_id FK
        string name "담당자 이름"
        string email "담당자 이메일 (인증 대상)"
        string manager_pw_hash "담당자 비밀번호 해시"
    }
```

### In-Memory Entity: `AuthCodeSession` (이메일 인증 세션)

| 필드 | 타입 | 설명 | 유효성 검증 / 제약 |
|---|---|---|---|
| `email` | `string` | 인증 대상 이메일 | 표준 이메일 형식 정규식 |
| `code` | `string` | 6자리 난수 인증코드 | `^\d{6}$` (100000 ~ 999999) |
| `created_at` | `float` | 생성 Unix timestamp | 현재 시각 |
| `expires_at` | `float` | 만료 Unix timestamp | `created_at + 300` (TTL 5분) |
| `attempts` | `int` | 검증 실패 시도 횟수 | 최대 5회 초과 시 강제 무효화 |

---

## 3. Model Gateway & Embedding/LLM DTO (`vllm-serv-gateway`)

### 1) HTTP Embedding Request & Response (BGE-M3 Port 8090)
- **Endpoint**: `POST /v1/embeddings`
- **Request DTO**:
  ```json
  {
    "model": "bge-m3",
    "input": ["건성 피부 보습 앰플 추천", "컬러그램 탕후루 꿀로스 발림성"]
  }
  ```
- **Response DTO**:
  ```json
  {
    "object": "list",
    "data": [
      {
        "object": "embedding",
        "embedding": [0.0123, -0.0456, "... 1024차원 float 배열 ..."],
        "index": 0
      }
    ],
    "model": "bge-m3",
    "usage": { "prompt_tokens": 12, "total_tokens": 12 }
  }
  ```

---

## 4. 올원챗 (ChatB FastAPI) RAG 검색 엔티티

### 1) `RagSearchRequest` & `RagSearchResponse`
- **Endpoint**: `POST /bteam/chatb/api/v1/search`
- **Request DTO**:
  ```json
  {
    "query": "건성 피부 보습 앰플",
    "top_n": 5,
    "model": null
  }
  ```
- **Response DTO**:
  ```json
  {
    "llm_answer": "건성 피부 보습을 위해 추천하는 상위 앰플 제품은...",
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
