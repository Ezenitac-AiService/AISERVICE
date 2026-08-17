# Data Model: 007-pilos-report-data-restoration

## Entity Relational Architecture (Pilos Core Schema)

```mermaid
erDiagram
    stock ||--o{ daily_document : "has"
    stock ||--o{ supply_demand : "records"
    stock ||--o{ llm_report : "synthesizes"
    daily_document ||--o{ sentiment_index_result : "evaluated_by"
    daily_document ||--o{ llm_report : "summarized_by"
    artifacts ||--o{ sentiment_index_result : "trained_model"

    stock {
        int stock_id PK
        varchar stock_code UK
        varchar stock_name
        varchar stock_subject_id
    }

    daily_document {
        bigint daily_document_id PK
        int stock_id FK
        date model_date
        varchar tokenizer_version
        int comment_count
        mediumtext tfidf_text
        char document_hash
    }

    sentiment_index_result {
        bigint sentiment_index_result_id PK
        bigint daily_document_id FK
        int artifact_id FK
        double supply_demand_association_score
        double intercept
        double text_score
        double comment_count_contribution
        json positive_contribution_keywords
        json negative_contribution_keywords
        varchar inference_status
    }

    llm_report {
        bigint llm_report_id PK
        int stock_id FK
        date model_date
        bigint daily_document_id FK
        bigint positive_result_id FK
        bigint negative_result_id FK
        varchar prompt_version
        int report_schema_version
        varchar status
        json report_json
    }

    supply_demand {
        int supply_demand_id PK
        int stock_id FK
        date trade_date
        double supply_demand_index
        bigint buy_volume
        bigint sell_volume
        varchar data_status
    }
```

## Resolution & Integrity Rules

1. **Document-Report Join Invariant**:
   For any stock $S$ and date $D$, an LLM report is considered `ready` if there exists an `llm_report` row linked to `daily_document` that joins to valid `positive_result_id` and `negative_result_id` in `sentiment_index_result`.
2. **Worker Idempotency Invariant**:
   A daily document for stock $S$ and date $D$ with tokenizer version $T$ SHALL NOT be inserted if a document for $(S, D, T)$ already exists in `daily_document`.
