# Data Model & Schema Specifications

**Feature**: `041-bteam-unified-pipeline-restructure`  
**Date**: 2026-08-27

---

## 1. Entity-Relationship Model (MySQL `cosmetic_db`)

```mermaid
erDiagram
    BRANDS ||--o{ PRODUCTS : owns
    PRODUCTS ||--o{ PRODUCT_CATEGORIES : classified_by
    CATEGORIES ||--o{ PRODUCT_CATEGORIES : contains
    PRODUCTS ||--o{ REVIEWS : has
    REVIEWS ||--o| REVIEW_PREPROCESSING : preprocessed_as
    REVIEW_PREPROCESSING ||--o{ REVIEW_ASPECT_SENTENCE : produces
    REVIEW_ASPECT_SENTENCE ||--o| ASPECT_SENTIMENT_RESULT : classified_as
    PRODUCTS ||--o{ LLM_PRODUCT_REPORTS : summarized_in
    LLM_PRODUCT_REPORTS ||--o{ LLM_PRODUCT_ATTRIBUTE_REPORTS : contains
    LLM_PRODUCT_REPORTS ||--o{ LLM_PRODUCT_REPORT_CLAIMS : grounds
    LLM_PRODUCT_REPORT_CLAIMS ||--o{ LLM_PRODUCT_REPORT_CITATIONS : cites
    REVIEWS ||--o{ LLM_PRODUCT_REPORT_CITATIONS : supports
    PRODUCTS ||--o{ PIPELINE_RUN_HISTORY : processed_by
    PIPELINE_RUN_HISTORY ||--o| PIPELINE_ACTIVE_LEASE : owns_current

    BRANDS {
        int brand_id PK
        varchar brand_name
    }

    CATEGORIES {
        int category_id PK
        int parent_category_id FK
        varchar category_name
    }

    PRODUCT_CATEGORIES {
        int product_id PK_FK
        int category_id PK_FK
    }

    PRODUCTS {
        int product_id PK
        varchar product_code UK "Olive Young goodsNo"
        int brand_id FK
        varchar product_name
        datetime first_collected_at
        datetime last_seen_at
        tinyint is_active
        datetime option_checked_at
        datetime review_checked_at
        datetime llm_analyzed_at
    }

    REVIEWS {
        bigint review_id PK
        bigint review_code UK
        int product_id FK
        int product_option_id FK
        text review_content
        tinyint review_score
        date review_date
        datetime collected_at
        datetime aspect_split_at
        datetime sentiment_analyzed_at
        tinyint vector_indexed "호환 migration으로 추가"
    }

    REVIEW_PREPROCESSING {
        bigint review_id PK_FK
        text cleaned_content
    }

    REVIEW_ASPECT_SENTENCE {
        bigint aspect_sentence_id PK
        bigint review_id FK
        int analysis_category_id FK
        varchar model_attribute_name
        int sequence_no
        text separated_sentence
        decimal confidence_score
    }

    ASPECT_SENTIMENT_RESULT {
        bigint aspect_sentence_id PK_FK
        varchar sentiment_label
        decimal confidence_score
    }

    LLM_PRODUCT_REPORTS {
        bigint llm_product_report_id PK
        int product_id FK
        text keep_summary
        text improvement_summary
        text overall_summary
        varchar report_status "grounded, abstained"
        varchar abstention_reason "nullable reason code"
        datetime generated_at
    }

    LLM_PRODUCT_ATTRIBUTE_REPORTS {
        bigint llm_product_attribute_report_id PK
        bigint llm_product_report_id FK
        int product_id FK
        int analysis_category_id FK
        varchar display_name
    }

    LLM_PRODUCT_REPORT_CLAIMS {
        bigint report_claim_id PK
        bigint llm_product_report_id FK
        varchar claim_key "API claim_id"
        varchar claim_kind "complaint, praise, premise"
        text claim_text
        int sort_order
    }

    LLM_PRODUCT_REPORT_CITATIONS {
        bigint report_citation_id PK
        bigint report_claim_id FK
        bigint source_review_id FK
        text quote_text "nullable, PII-sanitized"
        int sort_order
    }

    PIPELINE_RUN_HISTORY {
        bigint id PK
        varchar run_id
        varchar scope_key
        int product_id FK "nullable for all-products coordinator"
        varchar step_name
        varchar input_scope
        int checkpoint_version
        varchar status "RUNNING, COMPLETED, FAILED"
        int processed_count
        int retry_count
        text checkpoint_payload
        varchar error_code
        text error_message
        datetime started_at
        datetime finished_at
    }

    PIPELINE_ACTIVE_LEASE {
        varchar step_name PK
        varchar scope_key PK
        varchar owner_token
        varchar run_id
        datetime acquired_at
        datetime heartbeat_at
        datetime expires_at
    }
```

### 1.1 기존 운영 스키마 호환 원칙

- 내부 식별자는 `product_id`, 외부 Olive Young 상품코드는 `product_code(goodsNo)`로 구분한다.
- 물리 테이블은 기존 `products`, `reviews`, `llm_product_reports`, `llm_product_attribute_reports`를 보존한다. 기존 보고서 테이블에는 기본값이 안전한 `report_status`/`abstention_reason`만 additive하게 추가하고 claim/citation은 신규 자식 테이블에 저장한다.
- `product_report`는 도메인 모델명이며, 물리 테이블명 변경은 별도 versioned migration으로 수행한다.
- `vector_indexed`가 없는 기존 `reviews`에는 호환 migration으로 추가하며, `sentiment_analyzed_at`이 채워진 리뷰만 인덱싱 후보로 허용한다.

### 1.2 논리 모델과 물리 테이블 매핑

| 논리 모델 | 기존 물리 테이블 | 핵심 매핑 및 제약 |
| :--- | :--- | :--- |
| `Product` | `products` + `brands` + `product_categories` + `categories` | `products.product_id`와 `product_code`를 식별자로 사용한다. 브랜드·카테고리는 FK 조인 또는 read projection으로 제공한다. |
| `Review` | `reviews` | `review_id`, `review_code`, `product_id`, `review_content`를 보존한다. `vector_indexed`는 호환 migration으로 추가한다. |
| `ReviewSentence` | `review_aspect_sentences` | `aspect_sentence_id`, `analysis_category_id`, `model_attribute_name`, `separated_sentence`를 사용한다. 현재 FK가 `review_preprocessing.review_id`를 통하므로 ORM 매핑에서 이를 숨기지 않는다. |
| `SentimentAnalysis` | `aspect_sentiment_results` | `aspect_sentence_id` 1:1 PK/FK, `sentiment_label`, `confidence_score`를 사용한다. |
| `ProductReport` | `llm_product_reports` + `llm_product_attribute_reports` | 기존 summary와 속성 행을 보존한다. 기존/Blue writer가 citation 없이 생성한 행은 기본 `report_status=abstained`, `abstention_reason=LEGACY_UNVERIFIED`로 취급한다. |
| `ProductReportClaim` | 신규 `llm_product_report_claims` | `report_claim_id` PK, `(llm_product_report_id, claim_key)` unique, `claim_kind`, `claim_text`, `sort_order`를 저장한다. API의 `claim_id`는 `claim_key` projection이다. |
| `ProductReportCitation` | 신규 `llm_product_report_citations` | claim FK와 `reviews.review_id` FK를 모두 가지며 `(report_claim_id, source_review_id, sort_order)` unique를 사용한다. |
| `PipelineRunHistory` | 신규 애플리케이션 상태 테이블 | versioned migration으로 추가하며 기존 운영 테이블은 변경·삭제하지 않는다. |
| `PipelineActiveLease` | 신규 애플리케이션 active lease 테이블 | `(step_name, scope_key)`를 복합 PK/unique로 사용하여 run 간 동시 실행을 전역 차단한다. history 테이블의 unique 제약을 lock으로 오인하지 않는다. |

### 1.3 상태 및 무결성 규칙

- `reviews.vector_indexed=1`은 `aspect_split_at`과 `sentiment_analyzed_at`이 존재하고 ChromaDB Upsert가 성공한 뒤에만 기록한다. 기존 행은 migration 시 기본값 `0`으로 시작하며 검증된 벡터만 별도 backfill한다.
- `PipelineRunHistory.scope_key`는 제품 작업의 `product:{product_id}` 또는 coordinator history의 `all:{cycle_id}` 형식의 필수 값이며, `(run_id, step_name, scope_key)`는 유일해야 한다.
- ER 다이어그램의 `scope_key`에는 단독 unique 의미를 부여하지 않는다. 실제 유일성은 `(run_id, step_name, scope_key)` 복합 unique 제약으로 보장한다.
- `PipelineActiveLease`는 history와 별도로 `(step_name, scope_key)`를 전역 유일하게 보장한다. 전체 cycle coordinator는 `(cycle, all)`을 사용하여 batch ID가 다른 동시 cycle도 차단하고, 단일/전체 실행의 실제 제품 작업은 선택 단계 전체 동안 `(product_pipeline, product:{product_id})`를 사용하여 같은 제품의 서로 다른 단계도 충돌시킨다. `owner_token`, `run_id`, `heartbeat_at`, `expires_at`을 필수로 기록하며 기본 heartbeat는 15초, TTL은 60초이고 TTL은 heartbeat의 3배 이상이어야 한다. 시간 비교는 MySQL server UTC를 사용하고 lease를 해제할 때 owner token이 일치해야 한다.
- 만료 lease를 회수할 때는 이전 `RUNNING` history를 `FAILED`와 `error_code=LEASE_EXPIRED`로 전환하고 새 owner가 lease를 획득하는 작업을 동일 트랜잭션에서 수행한다. 유효 lease가 있으면 새 실행은 쓰기 전에 거부한다.
- 상태 전이는 `RUNNING -> COMPLETED|FAILED`, `FAILED -> RUNNING`(Resume)만 허용한다. Resume은 정확한 `--resume-run-id`로 지정한 실패 실행과 원래 selector·canonical steps가 일치할 때만 허용하며, 다중 실패 후보 중 하나를 자동 선택하지 않는다. `COMPLETED`는 새 `run_id` 없이 재실행하지 않는다.
- checkpoint는 처리 범위, 마지막 성공 식별자, 입력 checksum, 출력 건수, checkpoint version을 포함한다. 상태 변경과 checkpoint 저장은 같은 트랜잭션 경계에서 처리한다.
- `llm_product_reports.llm_product_report_id`는 API projection의 `report_id`로 노출하며 실제 MySQL 타입인 `bigint unsigned`를 보존한다.
- `ProductReport` API projection은 `report_id := llm_product_report_id`, `created_at := generated_at`을 UTC ISO 8601로 노출한다. `report_status=grounded`이면 `abstention_reason=null`, `claims[]`가 1개 이상이고 각 claim의 `citations[]`가 1개 이상이어야 한다. `report_status=abstained`이면 사유가 `NO_REVIEWS|NO_CITABLE_SOURCE|LEGACY_UNVERIFIED|GROUNDING_FAILED` 중 하나이고 claims·complaints·praises·suggestions는 모두 빈 배열이어야 한다.
- 새 보고서는 `llm_product_reports`, 속성 행, claim, citation을 한 DB 트랜잭션으로 기록한다. claim이나 citation 검증이 실패하면 summary만 commit하지 않고 전체 보고서 write를 rollback하거나 명시적 abstained 보고서로 다시 기록한다.
- 각 citation의 `source_review_id`는 실존 `reviews.review_id`여야 하며 report의 `product_id`와 같은 제품에 속해야 한다. 선택 `quote`는 PII 처리 후 Unicode NFKC·공백 정규화한 `reviews.review_content` 또는 해당 분리 문장의 substring이어야 한다. 타제품 ID, 존재하지 않는 ID, 원문에 없는 quote는 DB/API 출력 전에 거부한다.
- `key_complaints[]`와 `key_praises[]`는 자유 텍스트 사실 목록이 아니라 동일 projection의 `claims[].claim_id` 참조만 포함한다. 각 `improvement_suggestions[]` 항목은 `basis_claim_ids[]`로 존재하는 cited claim을 1개 이상 참조한다. 순환·dangling claim reference는 거부한다.
- migration 시 기존 보고서 행은 `abstained/LEGACY_UNVERIFIED`로 backfill한다. 모델이 기존 summary에서 citation을 추측해 `grounded`로 승격해서는 안 되며, 원천 리뷰를 다시 검증해 새 claim/citation transaction을 생성한 경우에만 승격한다.

### 1.4 주기 실행 selection 및 watermark 규칙

- 각 주기 cycle은 시작 시 immutable `cycle_started_at`을 history/checkpoint에 기록한다.
- `crawl`은 `products.is_active=1 AND (review_checked_at IS NULL OR review_checked_at <= cycle_started_at - interval)`인 due product만 선택한다.
- `sentence_split`, `sentiment`, `report`, `index`는 전역 product freshness timestamp 하나를 공유하지 않고 각 단계의 마지막 성공 checkpoint 이후 생성·변경된 입력을 선택한다.
- 일부 단계가 실패하면 cycle watermark를 전진시키지 않는다. 재개는 같은 run의 checkpoint와 immutable watermark를 사용하여 신규 입력 누락과 자기 기아(self-starvation)를 방지한다.

---

## 2. ChromaDB Versioned Collection Contract (`chroma_db_oliview`)

### 2.1 Legacy v1 — read/rollback compatibility only

현재 `oliview_review_sentences`는 `id=str(sentence_id)`이고 metadata가 `product_id`, `product_name`, `brand_name`, `analysis_category_name`, `category_names`, `attribute_name`, `sentiment`, `review_date`만 가진다. 현재 builder는 `review_id`를 조회하거나 저장하지 않으므로 이 collection에서 `source_review_id`를 추측해서는 안 된다. Green VALIDATION은 snapshot의 v1을 read-only로 유지한다.

승인된 CUTOVER/soak에서 v1 호환 dual-write를 수행할 때에는 기존 ID와 metadata 이름·타입을 그대로 생성한다. v1 성공은 citation 성공을 뜻하지 않으며, 별도 collection checkpoint와 lag로만 rollback 호환성을 판정한다.

### 2.2 Green v2 — canonical citation collection

| Field | Type | Description |
| :--- | :--- | :--- |
| **collection** | `str` | `oliview_review_sentences_v2` |
| **`id`** | `str` | `str(review_aspect_sentences.aspect_sentence_id)`; idempotent upsert key |
| **`document`** | `str` | PII-sanitized `review_aspect_sentences.separated_sentence` |
| **`metadata.product_id`** | `int` | MySQL 내부 `products.product_id` |
| **`metadata.product_code`** | `str` | Olive Young `goodsNo` |
| **`metadata.product_name`**| `str` | Product title |
| **`metadata.brand_name`** | `str` | Brand name |
| **`metadata.analysis_category_name`** | `str` | 기존 retriever 호환 category 이름 |
| **`metadata.category_names`** | `str` | 카테고리 경로 projection |
| **`metadata.attribute_name`** | `str` | Aspect tag |
| **`metadata.sentiment`** | `str` | Sentiment tag |
| **`metadata.source_review_id`** | `int` | canonical `reviews.review_id`; citation 결속용 |
| **`metadata.review_id`** | `int` | `source_review_id`와 동일한 명시적 compatibility alias |
| **`metadata.review_date`** | `str` | ISO 8601 date |
| **`metadata.indexed_at`** | `str` | UTC ISO 8601 timestamp |

`source_review_id`가 없거나 `review_id` alias와 다르거나 같은 product의 원천 리뷰로 검증되지 않은 벡터는 v2 성공으로 표시하지 않는다. `reviews.vector_indexed=1`은 v2 write 성공만 의미하며 v1 dual-write 상태는 deployment checkpoint에서 별도로 추적한다.

---

## 3. Redis Cache Namespace & Version Contract

| Item | Contract |
| :--- | :--- |
| Key format | `bteam:{APP_RUN_MODE}:product:{product_id}:{report|rag}:v{version}` |
| Version source | 제품·cache kind별 현재 version을 원자적으로 조회·증가시킨다. |
| Report invalidation | 보고서 DB commit이 성공한 제품 범위만 report version을 증가·publish한다. |
| RAG invalidation | ChromaDB Upsert와 MySQL `vector_indexed=1` 정합 처리가 성공한 제품 범위만 rag version을 증가·publish한다. |
| Legacy addressable key | `v1:rag:pool:{target_slug}:{attr_slug}`처럼 inventory에서 product/target의 결정적 역매핑을 검증한 exact key만 표적 무효화한다. |
| Legacy non-addressable key | `emb:bge-m3:{hash}`, `rerank:{query_hash}:{docs_hash}`, `olliview:l5:{tenant}:{hash}` 등은 제품 단위 삭제가 불가능하므로 scan/delete하지 않는다. rollback profile에서 cache read를 bypass하거나 격리 empty Redis를 사용한다. |
| Partial failure | version을 증가시키지 않고 실패 범위와 retry checkpoint를 기록한다. |
| Forbidden operations | `FLUSHDB`, 전역 wildcard 삭제, production `KEYS` scan |

DEMO와 PRODUCTION은 `APP_RUN_MODE` namespace로 분리한다. 캐시 version publication은 원천 DB/v2 벡터 상태보다 먼저 일어나서는 안 되며, 소비자는 현재 version key만 읽어 이전 세대의 유령 데이터를 노출하지 않는다. inventory는 key pattern과 분류만 기록하고 실제 key payload나 secret을 기록하지 않는다. rollback rehearsal은 각 legacy class에 대해 `TARGETED_INVALIDATION` 또는 `BYPASS_OR_ISOLATED` 판정 증거를 남기며, 검증되지 않은 class가 하나라도 있으면 cutover를 차단한다.
