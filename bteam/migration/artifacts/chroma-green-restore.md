# Green Chroma Restore Result

- Date: 2026-08-27
- Green image: `chromadb/chroma:1.5.9`
- Green persistence path: `/data`
- Source snapshot: `Oliview_chatbot_a/chroma_db_oliview` (SQLite plus HNSW files)
- Source collection: `oliview_review_sentences`
- Green v2 collection: `oliview_review_sentences_v2`

| Check | Result |
|---|---:|
| Legacy collection count | 57,435 |
| Green v2 collection count | 57,435 |
| Sample canonical IDs | `"1"`, `"2"`, `"3"` |
| Sample `aspect_sentence_id` metadata | `1`, `2`, `3` |
| Sample `source_review_id` metadata | `1`, `1`, `1` |
| Sample embedding dimensions | 1,024 each |

The legacy collection remains read-only. The v2 collection is Green-only and
uses the legacy aspect sentence ID as its canonical string ID while adding
integer `source_review_id` and `review_id` metadata for citation joins.
Blue containers and source files were not modified.
