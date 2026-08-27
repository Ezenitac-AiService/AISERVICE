# Green Rollback Rehearsal

- Date: 2026-08-27
- Scope: Green-only disposable rollback volumes
- Blue containers, volumes, source files, and active upstreams: unchanged

## MySQL

The Green `cosmetic_db` was streamed into a separate `bteam-green-rollback-mysql`
container and `bteam-green-rollback-mysql-data` volume. Legacy invalid views were
excluded from the dump because MySQL reported broken underlying references; all
base and additive tables needed for application rollback were restored.

| Table | Green source | Rollback target |
|---|---:|---:|
| `products` | 262 | 262 |
| `reviews` | 50,103 | 50,103 |
| `review_aspect_sentences` | 59,407 | 59,407 |
| `aspect_sentiment_results` | 59,407 | 59,407 |
| `llm_product_reports` | 709 | 709 |
| `pipeline_run_history` | 0 | 0 |

The target also contains `llm_product_report_claims`,
`llm_product_report_citations`, and `pipeline_active_lease`.

## Chroma

The complete legacy SQLite/HNSW snapshot was restored into a separate
`bteam-green-rollback-chroma-data` volume using `chromadb:1.5.9`. Heartbeat was
HTTP 200 and `oliview_review_sentences` count was 57,435, matching Green source.

The rollback containers remain stopped/running only as Green rehearsal assets;
they are not connected to Blue traffic.
