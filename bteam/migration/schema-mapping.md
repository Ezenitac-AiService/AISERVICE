# Blue-to-Green logical/physical mapping

| Green logical component | Preserved Blue table/path | Green write rule |
| --- | --- | --- |
| Product | `products`, `brands`, `product_categories`, `categories` | Upsert by existing `product_id`/`product_code`; no rename |
| Review | `reviews` | Keep `review_id`, add only `vector_indexed=0` by additive migration |
| ReviewSentence | `review_aspect_sentences` | Keep `aspect_sentence_id`, `review_id`, sentence text |
| SentimentAnalysis | `aspect_sentiment_results` | Keep one-to-one `aspect_sentence_id` mapping |
| ProductReport | `llm_product_reports`, `llm_product_attribute_reports` | Preserve rows; legacy uncited rows project as `abstained/LEGACY_UNVERIFIED` |
| ProductReportClaim | `llm_product_report_claims` | Additive child rows, unique `(report_id, claim_key)` |
| ProductReportCitation | `llm_product_report_citations` | Additive child rows; FK to claim and source `reviews` row |
| PipelineRunHistory | `pipeline_run_history` | New state/checkpoint table; unique `(run_id, step_name, scope_key)` |
| PipelineActiveLease | `pipeline_active_lease` | New global lease table; unique `(step_name, scope_key)` |
| Chroma v1 | `Oliview_chatbot_a/chroma_db_oliview` / `oliview_review_sentences` | Read-only during VALIDATION; exact shape only for approved rollback dual-write |
| Chroma v2 | Green `oliview_review_sentences_v2` | Canonical ID `str(aspect_sentence_id)` with integer `source_review_id` |
| Redis | Blue key classes in `oliview_core/redis_pool.py` | Green versioned namespace; legacy hash keys bypassed or isolated |

The SQL is additive and lives in `packages/core/schema.sql`. No Blue table, data file,
container, network, volume, bind mount, or active upstream is removed by this mapping.

