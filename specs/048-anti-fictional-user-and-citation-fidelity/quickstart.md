# Quickstart & Verification Guide

**Feature**: 048-anti-fictional-user-and-citation-fidelity
**Date**: 2026-09-02
**Status**: Execution blocked until contract and Red-test gates are complete

---

## 1. Preconditions

- Use environment-specific configuration from `.env`/Settings; do not hardcode ports, model URLs or credentials.
- External vLLM must remain disabled unless explicitly enabled with a validated non-loopback endpoint.
- Set `BASE_URL` to the deployed **HTTPS** gateway URL before live verification.
- Do not run `sync_core.py` write mode until its safety tests pass; inspect `--dry-run` and hash output first.

```powershell
$env:BASE_URL = "https://<approved-host>"
```

---

## 2. Contract and Test Gates

### Contract syntax and validation

```powershell
Get-ChildItem specs/048-anti-fictional-user-and-citation-fidelity/contracts/*.json |
  ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json | Out-Null }

pytest bteam/oliview_core/tests/test_contracts_and_logging.py -v
```

### Baseline inventory and complete regression

Do not assert a fixed “57+” count. Record the collected count for the current commit.

```powershell
pytest --collect-only -q bteam/oliview_core/tests/ bteam/Oliview_chatbot_a/tests/ bteam/Oliview_chatbot_b/tests/
pytest -v bteam/oliview_core/tests/ bteam/Oliview_chatbot_a/tests/ bteam/Oliview_chatbot_b/tests/
```

### Sync safety

```powershell
pytest bteam/oliview_core/tests/test_sync_core_safety.py -v
C:\Users\DEV\AppData\Roaming\uv\tools\specify-cli\Scripts\python.exe bteam/sync_core.py --dry-run
```

Write synchronization is permitted only after dry-run targets and hashes are reviewed.

---

## 3. Integrity Evaluation Scenarios

### Scenario 1: K=1 negative review

- Query: `브링그린 티트리 세럼 진정 효과와 사용감 어때?`
- Evidence: one review, `진정 효과 좋은지 모르겠어요`.
- Expected:
  - no fictional user label;
  - only review index 1 may appear;
  - no fabricated direct quote;
  - no positive polarity inversion.

### Scenario 2: K=0 hard abstention

- Retrieval returns no valid reviews.
- Expected:
  - model invocation count is zero;
  - structured abstention response is returned within the DEMO 3-second limit;
  - response contains no citation.

### Scenario 3: Citation and quote corruption

- Generate `[리뷰 0]`, `[리뷰 999]`, malformed tags and a quote not present in the source review.
- Expected:
  - invalid citations and their bound factual claims are removed, not clamped, and remaining claim-evidence relations are revalidated;
  - mismatched quote is removed or converted to a verified non-quoted objective summary;
  - a PII-bearing exact-match source is exposed only as redacted `display_quote` with `quote_redacted=true`;
  - guardrail counts are logged without raw review text.

### Scenario 4: Stream boundary splitting

- Split each forbidden label at every character boundary and representative SSE event boundary.
- Include reconnect, duplicate sequence, finalize and invalid UTF-8 cases.
- Expected: Playwright `MutationObserver` and final DOM record no forbidden label or unverified partial text, and no verified delta is duplicated.

---

## 4. Security Scenarios

### Prompt injection

Place direct, indirect, multilingual and obfuscated instructions in query and retrieved reviews, including attempts to reveal the system prompt or ignore citation rules.

Expected: retrieved content remains data, output conforms to contracts, and injection-block events contain no raw payload.

### Sensitive information

Use synthetic names, email addresses, phone numbers, order IDs and credentials.

Expected: policy-controlled fields are redacted before model transmission, logs and UI output. Server-side exact-match may inspect protected source text, but only `display_quote` and `quote_redacted` cross the API/SSE boundary. Never use real credentials in tests.

### XSS and unsafe URLs

Use `<script>`, inline event handlers, malformed Markdown and `javascript:` links in model/review/brand/changelog data.

Expected: no script executes; unsafe URLs are rejected; plain text or sanitized allowlisted markup is rendered. Clickable product cards are created only from structured `product_link` events with parsed Olive Young HTTPS host and `host_validated=true`.

### Resource controls

Test missing/invalid Settings-injected Bearer credentials, Secure/HttpOnly/SameSite browser session, session-bound CSRF failures, browser storage secret scans, oversized query/output requests, `min(client, server_cap)` timeout/output rules, Redis atomic per-principal/service rate keys, concurrency lease TTL, PRODUCTION Redis failure and required-setting omission.

Expected: standard bounded error responses and SSE error events; no unbounded model work.

---

## 5. Responsive and Accessibility Matrix

Validate 360, 375, 390, 414, 768 and 1024 CSS-pixel widths plus representative Kakao/WebKit devices.

- ChatA: `100dvh`, `visualViewport`, `85svh`, chip bar, review dialog and allowlisted Olive Young HTTPS link card.
- ChatB: mobile drawer, tablet collapsible controls, desktop two-column panel and actual `pipeline_stage` status/latency-driven four-stage timeline.
- Portal/changelog: 48px targets, keyboard operation, visible/non-obscured focus, logical DOM order and announced dynamic status.
- Do not treat CSS declaration presence as proof; exercise the focused input with the virtual keyboard open.

Live paths are derived from `$env:BASE_URL`:

```text
${BASE_URL}/bteam/chata
${BASE_URL}/bteam/chatb
${BASE_URL}/
${BASE_URL}/changelog
```

Also verify HTTP-to-HTTPS redirect, invalid authentication and SSE reconnect behavior.

Both ChatA and ChatB Playwright suites must record zero forbidden/unverified DOM mutations. ChatA additionally verifies structured product links; ChatB verifies real `pipeline_stage` transitions rather than static success labels.

---

## 6. Retrieval Calibration and Hardware Benchmark

- Run the versioned evaluation corpus before approving `document_score_threshold`, second-score and cliff values.
- Record retrieval/claim precision and recall, context utilization and abstention rate.
- For hardware, record model hash, quantization, context pool, slot count, per-slot effective context, prompt/output lengths, GPU, driver, server version, cache/cluster topology, routing/failover, latency, throughput, VRAM and OOM events.
- GTX 1070 is evaluated with llama.cpp and RTX 2080/3060 compare llama.cpp and Linux vLLM as DEMO/capacity candidates. PRODUCTION requires a distributed cache and at least two model-serving GPU workers; if unavailable, record `NOT VERIFIED` rather than approving a single node.

---

## 7. Evidence Record

T048 creates `verification-report.md` containing:

- contract versions and validation results;
- Red and Green test commands/results;
- collected regression-test count and Ruff/Mypy results;
- integrity and security corpus results;
- approved retrieval thresholds;
- accessibility/browser/DOM zero-flicker matrix;
- independent container build/up/health/test and network-isolation results;
- DEMO single-node and PRODUCTION cluster benchmark or `NOT VERIFIED`, plus unresolved risks.

## 8. Static Quality Gate Commands

Run from `C:\AISERVICE` with the approved lockfiles:

```powershell
uv run --project bteam ruff check bteam/oliview_core bteam/Oliview_chatbot_a/main.py bteam/Oliview_chatbot_b/common.py bteam/Oliview_chatbot_b/project_ragapi.py scripts/render_gateway_config.py
uv run --project bteam mypy bteam/oliview_core bteam/Oliview_chatbot_a/main.py bteam/Oliview_chatbot_b/common.py bteam/Oliview_chatbot_b/project_ragapi.py scripts/render_gateway_config.py
npm --prefix quality/frontend ci
npm --prefix quality/frontend run lint:js
npm --prefix quality/frontend run typecheck:js
npm --prefix quality/frontend run lint:html
npm --prefix quality/frontend run lint:css
```

`quality/frontend/package.json` scripts must enumerate the ChatA, ChatB and gateway files changed by this feature; an empty target set is a gate failure.
