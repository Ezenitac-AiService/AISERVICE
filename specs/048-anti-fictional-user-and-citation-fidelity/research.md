# Phase 0: Research & Architecture Decisions

**Feature**: 048-anti-fictional-user-and-citation-fidelity
**Research cutoff**: 2026-09-02
**Status**: Revised after adversarial cross-artifact review

---

## 1. Decision Summary

### Decision 1: Prompt SSOT and two presentation personas

- `bteam/oliview_core/prompts.py` is the sole prompt source.
- `CONCIERGE` and `ANALYST` may change tone and layout, but not evidence, citation or security rules.
- Retrieved reviews are marked as untrusted data and cannot override system instructions.
- Per-service prompt copies are a temporary compatibility mechanism only; direct package use is preferred.

### Decision 2: Boundary-safe streamed output validation

The existing class name `StreamingTokenInterceptor` is retained for compatibility, but its input contract is UTF-8-decoded text chunks rather than tokenizer tokens. Fixed 3-token or 4-token windows are rejected because tokenizer and SSE boundaries are not stable security boundaries.

The interceptor keeps a dynamic carry suffix at least as long as the longest registered forbidden-pattern prefix, validates completed text, and emits only the safe prefix. `finalize()` applies the same validation to the remaining suffix. A final `GroundednessSanitizer` validates the complete answer.

The WHATWG SSE format is UTF-8 and defines event framing independently from model tokenization, so split-boundary tests must cover character and SSE event boundaries: <https://html.spec.whatwg.org/multipage/server-sent-events.html>

### Decision 3: Citation fidelity and abstention

- Valid citations satisfy `1 <= N <= K`.
- Invalid citations are removed; they are never clamped or reassigned to another review.
- Direct excerpts must match a normalized source-review substring under the documented Unicode/whitespace policy.
- If no valid evidence remains, return an objective summary only or abstain.
- `K=0` bypasses prompt construction and model invocation.

NIST AI RMF's Generative AI Profile treats confabulation and lifecycle measurement as risk-management concerns; deterministic label removal alone is not sufficient: <https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence>

Fine-grained RAG evaluation should include retrieval and generation diagnostics such as claim precision/recall and context utilization: <https://arxiv.org/abs/2408.08067>

### Decision 4: Retrieval thresholds are calibrated configuration

`document_score_threshold=0.85`, second-review score `0.60`, and `cliff_delta=0.25` are initial candidate values. They are not standards or verified truths. The approved values must come from a versioned evaluation corpus and be injected through configuration.

The API uses `document_score_threshold`; it does not overload `top_p`, which is conventionally the model's nucleus-sampling parameter in OpenAI-compatible APIs: <https://developers.openai.com/api/reference/resources/chat>

### Decision 5: Security and privacy boundaries

- Direct and indirect prompt injection, including retrieved-review instructions, are tested.
- System instructions, untrusted context and user input are explicitly delimited.
- PII and credentials are redacted before model transmission, logging and browser rendering.
- Generated and retrieved strings use safe DOM sinks by default; allowed Markdown is sanitized.
- Query/output size, timeout, concurrency, rate limit and authentication are enforced in code and contracts.

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
- VRAM, TTFT, full latency and throughput claims remain hypotheses until the reproducible benchmark completes.

References:

- vLLM GPU requirements: <https://docs.vllm.ai/en/v0.18.0/getting_started/installation/gpu/>
- llama.cpp server parameters: <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md>
- llama.cpp parallel context example: <https://github.com/ggml-org/llama.cpp>
- llama.cpp server benchmark: <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/bench/README.md>

### Decision 8: Contract dialect and observability

- JSON contracts use Draft 2020-12 and reject unexpected properties where practical.
- Request, response, SSE event and structured log contracts are separate.
- Structured logs record correlation ID, service, event, latency, model invocation, abstention and guardrail counters; raw query, review, prompt and tokens are prohibited.

Reference: JSON Schema Draft 2020-12 release notes: <https://json-schema.org/draft/2020-12/release-notes>

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

---

## 3. Evidence Required Before Release

1. Contract validation and recorded Red/Green test evidence.
2. Versioned normal, edge and adversarial evaluation corpus.
3. Threshold calibration report with retrieval and generation metrics.
4. PII/prompt-injection/XSS/resource-limit security report.
5. Hardware benchmark with exact model, quantization, context, slot, driver and server versions.
6. HTTPS mobile/browser/accessibility E2E matrix.
