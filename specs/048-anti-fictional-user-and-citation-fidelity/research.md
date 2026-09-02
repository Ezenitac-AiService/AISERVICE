# Phase 0: Research & Architecture Decisions

**Feature**: 048-anti-fictional-user-and-citation-fidelity
**Research cutoff**: 2026-09-02
**Status**: Revised after adversarial cross-artifact review

---

## 1. Decision Summary

### Decision 1: Prompt SSOT and two presentation personas

- `bteam/oliview_core/prompts.py` is the canonical prompt source.
- `CONCIERGE` and `ANALYST` may change tone and layout, but not evidence, citation or security rules.
- Retrieved reviews are marked as untrusted data and cannot override system instructions.
- Per-service prompt copies are the runtime mechanism for this feature and must be hash-synchronized from the canonical source without mixing master/copy imports in one process. Direct shared-package migration is deferred to a separate feature.

### Decision 2: Boundary-safe streamed output validation

The existing class name `StreamingTokenInterceptor` is retained for compatibility, but its input contract is UTF-8-decoded text chunks rather than tokenizer tokens. Fixed 3-token or 4-token windows are rejected because tokenizer and SSE boundaries are not stable security boundaries.

The interceptor keeps a dynamic carry suffix at least as long as the longest registered forbidden-pattern prefix, validates completed text, and emits only the safe prefix. `finalize()` applies the same validation to the remaining suffix. A final `GroundednessSanitizer` validates the complete answer.

The WHATWG SSE format is UTF-8 and defines event framing independently from model tokenization, so split-boundary tests must cover character and SSE event boundaries: <https://html.spec.whatwg.org/multipage/server-sent-events.html>

### Decision 3: Citation fidelity and abstention

- Valid citations satisfy `1 <= N <= K`.
- Invalid citations and their bound factual claims are removed; citations are never clamped or reassigned to another review. Remaining claim-evidence relations are validated again.
- Direct excerpts must match a server-side source-review substring after Unicode NFC and line-ending normalization (CRLF/CR→LF) only. Whitespace, punctuation and compatibility characters are not collapsed or rewritten. A safe source substring is exposed as `display_quote`; a PII-bearing substring is exact-matched first and then exposed only through the shared redaction policy with `quote_redacted=true`.
- If a direct excerpt cannot be safely redacted or no valid evidence remains, return a verified non-quoted objective summary or abstain.
- `K=0` bypasses prompt construction and model invocation.

NIST AI RMF's Generative AI Profile treats confabulation and lifecycle measurement as risk-management concerns; deterministic label removal alone is not sufficient: <https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence>

Fine-grained RAG evaluation should include retrieval and generation diagnostics such as claim precision/recall and context utilization: <https://arxiv.org/abs/2408.08067>

### Decision 4: Retrieval thresholds are calibrated configuration

`document_score_threshold=0.85`, second-review score `0.60`, and `cliff_delta=0.25` are initial candidate values. They are not standards or verified truths. The approved values must come from a versioned evaluation corpus and be injected through configuration.

The API uses `document_score_threshold`; it does not overload `top_p`, which is conventionally the model's nucleus-sampling parameter in OpenAI-compatible APIs: <https://developers.openai.com/api/reference/resources/chat>

### Decision 5: Security and privacy boundaries

- Direct and indirect prompt injection, including retrieved-review instructions, are tested.
- System instructions, untrusted context and user input are explicitly delimited.
- PII and credentials are redacted before model transmission, logging and browser rendering. Exact quote matching may use the protected server-side source, but only `display_quote` and `quote_redacted` cross the response boundary.
- Generated and retrieved strings use safe DOM sinks by default; allowed Markdown is sanitized.
- Direct clients use Settings-injected Bearer validation. Browsers use a Secure/HttpOnly/SameSite opaque session cookie plus session-bound CSRF token; JavaScript storage never receives Bearer or session material.
- Both flows normalize to a principal. Redis atomic operation/TTL shares principal+service rate and concurrency leases across workers; PRODUCTION Redis failure is fail-closed.
- Query/output size and timeout use `effective=min(client_request, server_cap)`; errors use discriminated response/SSE contracts.

Primary references:

- OWASP LLM01 Prompt Injection: <https://genai.owasp.org/llmrisk/llm01-prompt-injection/>
- OWASP LLM02 Sensitive Information Disclosure: <https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/>
- OWASP LLM10 Unbounded Consumption: <https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/>
- OWASP XSS Prevention Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html>

### Decision 6: Mobile viewport and accessibility

- `100dvh`, `85svh` and `visualViewport` are implementation tools, not guarantees.
- Browser validation covers 360, 375, 390, 414, 768 and 1024 CSS-pixel widths and representative Kakao/WebKit environments.
- Mobile is `<768`, tablet is `768..1023`, desktop is `>=1024`.
- 48px targets are accompanied by keyboard operation, visible/non-obscured focus, logical DOM order, dialog semantics and status announcements.

References:

- WCAG 2.2: <https://www.w3.org/TR/WCAG22/>
- CSS Values and Units Level 4 viewport units: <https://www.w3.org/TR/css-values-4/>
- CSSOM View `VisualViewport`: <https://www.w3.org/TR/cssom-view-1/#visualviewport>

### Decision 7: Hardware backend selection is benchmark-driven

- GTX 1070 (compute capability 6.1) does not meet current vLLM's CUDA minimum of 7.0, so only llama.cpp is evaluated there.
- RTX 2080 and RTX 3060 meet that minimum; llama.cpp and Linux vLLM are compared under the same workload.
- llama.cpp `-c` is a server context pool shared by slots. A 64K pool with four slots is not described as 64K per slot.
- Continuous batching is currently enabled by default in llama.cpp; `--cont-batching` is redundant but may remain explicit. Flash attention defaults to `auto`; forcing `-fa on` requires hardware/build evidence.
- VRAM, TTFT, full latency and throughput claims remain hypotheses until the reproducible benchmark completes. Single-node GTX/RTX results are DEMO/capacity evidence only. PRODUCTION approval additionally requires a distributed cache and at least two model-serving GPU workers, with routing/failover and one-worker-failure evidence, before applying the 4-slot P95 TTFT ≤1.5 seconds, P95 full response ≤8 seconds, aggregate throughput ≥25 tokens/s and zero OOM gates. Missing topology is reported as `NOT VERIFIED`.

References:

- vLLM GPU requirements: <https://docs.vllm.ai/en/v0.18.0/getting_started/installation/gpu/>
- llama.cpp server parameters: <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md>
- llama.cpp parallel context example: <https://github.com/ggml-org/llama.cpp>
- llama.cpp server benchmark: <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/bench/README.md>

### Decision 8: Contract dialect and observability

- JSON contracts use Draft 2020-12 and reject unexpected properties where practical.
- Request, response, SSE event and structured log contracts are separate.
- Persona is endpoint-bound and absent from the client request contract. Response status branches are discriminated, product cards use structured allowlisted `product_link` data, and ChatB receives actual `pipeline_stage` status/latency events.
- Structured logs record correlation ID, service, event, latency, model invocation, abstention and guardrail counters; raw query, review, prompt and tokens are prohibited.

Reference: JSON Schema Draft 2020-12 release notes: <https://json-schema.org/draft/2020-12/release-notes>

### Decision 9: Cross-runtime configuration and frontend quality gates

- `contracts/runtime_environment_schema.json` validates the feature-owned environment subset and is the shared SSOT for Pydantic Settings and Nginx template rendering.
- `gateway/nginx.conf` is generated from `gateway/nginx.conf.template`; unresolved variables, arbitrary defaults and generated-file drift fail closed.
- Python uses Ruff/Mypy. Vanilla JavaScript, HTML and CSS use lockfile-based ESLint, TypeScript `checkJs`, html-validate and Stylelint commands from `quality/frontend/`.

---

## 2. Rejected Assumptions

- A 3-token or 4-token window can guarantee streamed-string safety.
- Invalid citation numbers may be clamped to a valid number.
- `0.85/0.60/0.25` are universally correct retrieval thresholds.
- One negative review query proves a universal 0% hallucination rate.
- UI charts satisfy the constitution's structured-logging requirement.
- A 64K context pool means every one of four slots receives 64K context.
- GTX 1070, RTX 2080 and RTX 3060 should use the same backend solely by VRAM size.
- `http://` public URLs are acceptable live-verification defaults.
- A single-GPU benchmark can substitute for the constitution's distributed-cache/GPU-cluster PRODUCTION gate.

---

## 3. Evidence Required Before Release

1. Contract validation and recorded Red/Green test evidence.
2. Versioned normal, edge and adversarial evaluation corpus.
3. Threshold calibration report with retrieval and generation metrics.
4. PII/prompt-injection/XSS/resource-limit security report.
5. DEMO single-node and PRODUCTION distributed-cache/GPU-cluster benchmark with exact model, quantization, context, slot, topology, driver and server versions.
6. HTTPS Playwright mobile/browser/accessibility and DOM zero-flicker E2E matrix.
7. Ruff/Mypy exit-code-zero evidence and independent ChatA/ChatB/Model Gateway/Nginx Gateway container build/up/health/test evidence.
