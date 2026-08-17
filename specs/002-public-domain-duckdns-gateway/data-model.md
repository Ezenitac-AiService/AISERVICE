# Data Model Specification: 공인 DDNS 게이트웨이 및 통합 마이크로서비스 데이터 모델

**Feature Branch**: `002-public-domain-duckdns-gateway`  
**Date**: 2026-08-17  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/002-public-domain-duckdns-gateway/spec.md)

---

## 1. A-Team 데이터 엔티티 (`pilos_v2` DB)

### 1.1 `service_pipeline_run` (파이프라인 실행 상태 및 이력)

A-Team 백그라운드 워커(`pilos_worker`)가 실행하는 7단계 수집·분석 주기의 라이프사이클과 단계별 소요 시간을 기록하는 핵심 엔티티입니다.

| 컬럼명 | 데이터 타입 | 제약 조건 | 설명 |
|---|---|---|---|
| `service_pipeline_run_id` | BIGINT | PK, AUTO_INCREMENT | 파이프라인 실행 고유 식별자 |
| `status` | ENUM('running', 'completed', 'failed') | NOT NULL | 실행 상태 |
| `target` | VARCHAR(64) | NOT NULL, DEFAULT 'all_stocks' | 대상 범위 |
| `tokenizer_version` | VARCHAR(32) | NOT NULL | 사용된 Kiwi 토크나이저 버전 |
| `operation_start_date` | DATE | NOT NULL | 운영 기준 일자 |
| `started_at` | DATETIME(6) | NOT NULL | 실행 시작 시각 (KST) |
| `finished_at` | DATETIME(6) | NULL | 실행 완료/중단 시각 |
| `elapsed_seconds` | DECIMAL(10, 3) | NULL | 총 소요 시간 (초) |
| `stopped_stage` | VARCHAR(64) | NULL | 실패 또는 중단된 단계명 |
| `failure_type` | VARCHAR(128) | NULL | 예외/오류 분류 클래스 |
| `failure_message` | TEXT | NULL | 상세 오류 메시지 |
| `stage_summary` | JSON | NOT NULL | 7대 단계별 상태 및 소요시간 요약 JSON |
| `created_at` | TIMESTAMP(6) | DEFAULT CURRENT_TIMESTAMP(6) | 생성 시각 |
| `updated_at` | TIMESTAMP(6) | DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE | 갱신 시각 |

#### `stage_summary` JSON 내부 스키마 예시:
```json
{
  "incremental_comments": { "status": "completed", "elapsed_seconds": 12.4, "collected_count": 150 },
  "preprocess_comments": { "status": "completed", "elapsed_seconds": 3.1, "preprocessed_count": 150 },
  "tokenize_comments": { "status": "completed", "elapsed_seconds": 5.8, "tokenized_count": 150 },
  "build_daily_documents": { "status": "completed", "elapsed_seconds": 2.2, "documents_built": 10 },
  "collect_supply_demand": { "status": "completed", "elapsed_seconds": 1.5, "mode": "estimated" },
  "predict_model": { "status": "completed", "elapsed_seconds": 8.7, "inferred_documents": 10 },
  "generate_llm_reports": { "status": "completed", "elapsed_seconds": 18.3, "generated_reports": 10 }
}
```

---

## 2. B-Team 데이터 엔티티 (`cosmetic_db` DB)

### 2.1 `products` & `aspect_reviews` (화장품 상품 및 속성 감정 리뷰)

B-Team Oliview 웹 및 RAG 챗봇이 조회하는 상품 메타데이터 및 분석 리뷰 엔티티입니다.

| 필드명 | 데이터 타입 | 설명 |
|---|---|---|
| `product_id` | INT (PK) | 상품 고유 식별자 |
| `brand` | VARCHAR(100) | 브랜드명 (예: 브링그린, 닥터지, 차앤박 등) |
| `name` | VARCHAR(255) | 화장품 상품명 |
| `category` | VARCHAR(100) | 카테고리 (스킨케어, 선케어, 클렌징 등) |
| `aspect_category` | VARCHAR(50) | 속성 분류 (진정, 보습, 유분기, 발림성 등) |
| `sentiment_polarity` | VARCHAR(20) | 감정 극성 (Positive, Negative, Neutral) |
| `review_text` | TEXT | 정제된 실사용자 리뷰 원문 |
| `rating` | DECIMAL(2, 1) | 올리브영 평점 |

---

## 3. Model Gateway 통신 DTO (HTTP Embedding & LLM)

### 3.1 `EmbeddingRequest` & `EmbeddingResponse` (`http://vllm-serv-gateway:8090/v1/embeddings`)

```json
// Request Payload (OpenAI Compatible)
{
  "model": "bge-m3",
  "input": [
    "피부 진정에 좋고 성분이 순한 쿠션팩트 추천해줘"
  ]
}

// Response Payload
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [-0.0124, 0.0451, ..., 0.0892] // 1024-dimensional float vector
    }
  ],
  "model": "bge-m3",
  "usage": {
    "prompt_tokens": 18,
    "total_tokens": 18
  }
}
```

### 3.2 `RAGSearchPayload` (`POST /bteam/chatb/api/v1/search`)

```json
// Request Payload
{
  "query": "피부 진정에 좋고 성분이 순한 쿠션팩트 추천해줘",
  "brand": "닥터지",
  "keyword": null,
  "sentiment": "Positive",
  "fetch_k": 20,
  "top_n": 3
}

// Response Payload
{
  "llm_answer": "### 🧠 AI 전문 뷰티 가이드의 맞춤 솔루션\n\n**닥터지 레드 블레미쉬 클리어 수딩 쿠션**을 추천드립니다...",
  "search_results": [
    {
      "rank": 1,
      "brand": "닥터지",
      "name": "레드 블레미쉬 클리어 수딩 쿠션",
      "category": "베이스메이크업",
      "review": "민감성 피부인데 붉은 기를 잘 잡아주고 트러블이 안 생겨요.",
      "sentiment": "Positive",
      "similarity_score": 0.892
    }
  ]
}
```
