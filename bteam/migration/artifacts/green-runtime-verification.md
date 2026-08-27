# Green Runtime Verification

- Date: 2026-08-27
- Green Compose project: `bteam-green`
- Blue state: not changed; Blue containers remain in service

| Probe | Result |
|---|---|
| Green MySQL | healthy; restored `cosmetic_db` with 21 original tables plus additive tables |
| Green MySQL core rows | products 262; reviews 51,152; review sentences 59,407; sentiment rows 59,407; reports 678 |
| Green Chroma v1/v2 | 57,435 / 57,435 vectors; embedding dimension 1,024 |
| Dashboard report API | HTTP 200; legacy report projected as `abstained/LEGACY_UNVERIFIED` |
| Dashboard frontend route/proxy | `/bteam/oliview/`, `/bteam/oliview/api/health`, `/bteam/oliview/api/search` | HTTP 200; search grounded with source review citation |
| ChatA direct v2 retrieval | HTTP 200; grounded; 3 citations from Green read-only MySQL (`4656`, `7308`, `45957`) |
| ChatB direct v2 retrieval | HTTP 200; grounded; 3 citations from Green read-only MySQL (`4656`, `7308`, `45957`) |
| Green Redis | healthy; isolated Green volume/profile |
| Green pipeline runner registry | `--product-id 1 --steps index`; DB-backed product lease/checkpoint | `COMPLETED`; 500-row limit; 315 sentences upserted; 156 reviews flagged; active lease count 0 |
| Green pipeline failure gate | `--product-id 1 --steps all` with no `CRAWLER_ENDPOINT` | `crawl` failed closed as `StageDependencyError`; no stage was falsely completed |
| Green all-products lease | `--all-products --steps crawl`; coordinator plus 246 product leases | `FAILED` closed at missing crawler adapter; due products 246; active lease count after run 0 |
| Green actual Transformer probe | Temporary review `9990000001`; `sentence_split,sentiment` | `COMPLETED`; local Transformer adapters loaded on CPU; 1 review processed by each stage; temporary data removed |
| Green Redis version publish | Product 37 in two one-shot runner processes | durable `current` advanced `2→3`; `v3:version=3` |
| Green v2 freshness (Dashboard/ChatA/ChatB) | Product 137, source review 98 after index event | citation visible in all three; 0.112s / 0.242s / 0.319s |

The Chroma v1 collection and source snapshot remain preserved. All probes used
Green-only ports and service identities; no active Blue endpoint was changed.

## Pipeline Registry Runtime Evidence

The latest `pipeline_runner` image injected the canonical five-stage registry
and executed the Green `index` stage against the restored MySQL and Chroma v2
services. Run `e2a205c7-851b-467e-a430-b371c82709c3` recorded this completed
checkpoint:

- `batch_size`: 500
- `collection_id`: `7ebb1569-59d8-49cf-bd78-c16afec17768`
- `indexed_sentences`: 315
- `indexed_reviews`: 156
- `cache_version`: 2
- Green MySQL product 1 metrics after the run: 375 indexed reviews and 102
  sentiment-complete reviews still awaiting vector indexing
- Chroma v2 collection count: 57,435
- Product 37 Redis restart probe: `bteam:DEMO:product:37:rag:current` advanced from 2 to 3 across two one-shot runner processes, with `bteam:DEMO:product:37:rag:v3:version=3`.
- Freshness probe event `2026-08-27T03:45:14.140950+00:00`: source review 98
  from product 137 appeared in Dashboard, ChatA, and ChatB citations in 0.112s,
  0.242s, and 0.319s respectively (HTTP 200). Dashboard uses
  `/bteam/oliview/api/search`, backed by the shared Core grounding path.

The latest full five-step probe run `62ce83bd-382c-4b9e-9fc9-445a025376fa`
stopped at `crawl` with `StageDependencyError: review crawler adapter is not
configured`; it did not record a false crawl success and the runner remained
`restart: "no"`. The earlier Gateway fail-closed report probe remains retained
in run history, but is superseded as the latest full-run gate by the crawler
dependency check.

This is a real registry/index, transactional model-stage, and fail-closed
runtime proof, not completion of the entire production pipeline: Green still
needs an approved crawler endpoint and healthy report Gateway for full E2E;
the isolated model probe returned zero spans, and all-products changed-input /
DB exact-resume remain open convergence work.

## ChatA/ChatB Compatibility Runtime Evidence

The shared Core compatibility adapter was rebuilt into both Green chatbot images
and exercised on 2026-08-27. The raw result is stored in
`migration/artifacts/chat-compatibility-runtime.json`.

- ChatA: `/api/v1/chat` and `/bteam/chata/api/v1/chat/stream` returned grounded/
  HTTP 200 responses with the expected `step_update`, `token`, and `complete`
  SSE events.
- ChatB: `/api/v1/chat` and `/bteam/chatb/api/v1/search/stream` returned the same
  contract and event sequence.
- Both services persisted a session history of four messages, exposed
  `/api/session/{session_id}/history`, and returned HTTP 200 from the clear route.
- A 1,024-dimension Chroma v2 query returned three product-scoped vector rows;
  both ChatA and ChatB validated the source review existence, product scope, and
  normalized PII-safe quote substring against Green read-only MySQL before
  returning three grounded citations.
- The test scope `bteam/tests` passed 77/77. Blue containers, folders, volumes,
  network, and external routes were not changed.
