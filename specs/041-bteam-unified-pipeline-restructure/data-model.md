# Data Model & Schema Specifications

**Feature**: `041-bteam-unified-pipeline-restructure`  
**Date**: 2026-08-26  

---

## 1. Entity-Relationship Model (MySQL `cosmetic_db`)

```mermaid
erDiagram
    BRAND ||--o{ PRODUCT : manufactures
    CATEGORY ||--o{ PRODUCT : categorizes
    PRODUCT ||--o{ REVIEW : has
    PRODUCT ||--o{ PRODUCT_REPORT : summarized_in
    REVIEW ||--o{ REVIEW_SENTENCE : split_into
    REVIEW_SENTENCE ||--o{ SENTIMENT_ANALYSIS : classified_as
    PIPELINE_RUN_HISTORY ||--o{ PRODUCT : processes

    PRODUCT {
        varchar goodsNo PK
        varchar brand_name
        varchar category
        varchar product_name
        datetime created_at
    }

    REVIEW {
        int id PK
        varchar goodsNo FK
        text review_text
        int review_score
        tinyint vector_indexed "0: pending, 1: indexed"
        datetime created_at
    }

    REVIEW_SENTENCE {
        int id PK
        int review_id FK
        text sentence_text
        varchar aspect "수분감, 발림성 등"
    }

    SENTIMENT_ANALYSIS {
        int id PK
        int sentence_id FK
        varchar sentiment "긍정, 부정, 중립"
        float confidence
    }

    PRODUCT_REPORT {
        int id PK
        varchar goodsNo FK
        varchar product_name
        json aspect_summary
        json improvement_suggestions
        mediumtext markdown_report
        datetime created_at
    }

    PIPELINE_RUN_HISTORY {
        int id PK
        varchar run_id
        varchar step_name
        varchar status "RUNNING, COMPLETED, FAILED"
        int processed_count
        text error_message
        datetime started_at
        datetime finished_at
    }
```

---

## 2. ChromaDB Vector Metadata Contract (`chroma_db_oliview`)

| Field | Type | Description |
| :--- | :--- | :--- |
| **`id`** | `str` | Format: `rev_{review_id}_{chunk_idx}` |
| **`document`** | `str` | Review sentence / full review text |
| **`metadata.product_id`** | `str` | Product `goodsNo` |
| **`metadata.product_name`**| `str` | Product title |
| **`metadata.brand_name`** | `str` | Brand name (차앤박, 헤라, 식물나라 등) |
| **`metadata.category`** | `str` | Category (스킨케어, 클렌징, 선케어 등) |
| **`metadata.aspect`** | `str` | Aspect tag (수분감, 발림성, 자극도 등) |
| **`metadata.sentiment`** | `str` | Sentiment tag (긍정, 부정, 중립) |
| **`metadata.review_score`**| `int` | User rating (1~5) |
| **`metadata.indexed_at`** | `str` | ISO 8601 timestamp |
