# Technical Research & Architecture Decisions: 016-system-codebase-refactoring

**Feature**: [spec.md](./spec.md) | **Date**: 2026-08-19 | **Status**: Complete

---

## 1. Research Topics & Findings

### Topic 1: Standard Python Package Layout vs Legacy Sequential Scripts
- **Context**: B-Team ChatA currently uses sequential tutorial script names (`01.xxx`, `02.xxx`, `03.03.xxx`, `04.reranking.py`, `05.chatbot.py`, `06.02.app.py`) loaded dynamically via `importlib.util.spec_from_file_location`.
- **Decision**: Establish `bteam/oliview_core/` as a standard, installable/importable Python package.
  - Submodules:
    - `oliview_core.config`: Centralized environment variable & settings management.
    - `oliview_core.client`: Shared sync/async `AiGatewayClient` for vLLM, BGE-M3, and BGE-Reranker.
    - `oliview_core.db`: MySQL connection factory and query helpers.
    - `oliview_core.sanitizer`: Text cleaning, noise filtering, sentiment normalization, Olive Young URL building.
    - `oliview_core.retrieval`: Hybrid search (Faiss dense vector + BM25 sparse index + DB metadata filter).
    - `oliview_core.rerank`: Remote GPU BGE-Reranker client (`port 8091`) + Lazy CrossEncoder fallback.
    - `oliview_core.pipeline`: End-to-end RAG orchestrator with 2-stage execution (`prepare_stream` + `generate_stream`).
    - `oliview_core.types`: Pydantic & dataclass schemas (`RagExecutionMetadata`, `StepCallbackEvent`, etc.).
- **Rationale**:
  - Eliminates dynamic `importlib` file loader fragility.
  - Enables clean static type checking (mypy/pyright), IDE navigation, and fast module caching in `sys.modules`.
  - Enables both ChatA (`Streamlit`) and ChatB (`FastAPI`) to import cleanly without duplication.
- **Alternatives Considered**:
  - *Option B (Individual src/ in each app)*: Rejected due to duplicate maintenance of retrieval, reranking, and client code.
  - *Option C (Root common/)*: Rejected to respect Constitution Principle III (Domain Modularity & Service Isolation).

---

### Topic 2: Dual Sync/Async AI Gateway Client Architecture
- **Context**: ChatA runs in Streamlit (synchronous multi-threaded model), whereas ChatB runs in FastAPI (asyncio event-loop model).
- **Decision**: Implement `AiGatewayClient` in `oliview_core.client` providing symmetric `sync` and `async` method pairs:
  - `embed(texts: list[str]) -> list[list[float]]` & `aembed(...)`
  - `rerank(query: str, documents: list[str]) -> list[float]` & `arerank(...)`
  - `generate_stream(prompt: str, ...) -> Iterator[str]` & `agenerate_stream(...) -> AsyncIterator[str]`
- **Rationale**:
  - Prevents `RuntimeError: This event loop is already running` in Streamlit and thread-blocking in FastAPI.
  - Utilizes `httpx.Client(limits=...)` for sync and `httpx.AsyncClient(limits=...)` for async with HTTP/1.1 connection pooling.
- **Alternatives Considered**:
  - *Async-only with `asyncio.run()` in Streamlit*: Rejected because calling `asyncio.run` inside Streamlit scripts causes event loop conflicts with Tornado/WebSockets.

---

### Topic 3: Streamlit 2-Stage Lifecycle Contract & Callback Decoupling
- **Context**: Streamlit's `st.status` container requires synchronous execution while open, but token generation requires a generator for `st.write_stream`.
- **Decision**: Define strict 2-phase pipeline interface:
  1. `prepare_chatbot_stream(chatbot, question, callback)`: Synchronously executes Steps 1~3 (Intent, Hybrid Search, Rerank) and notifies `callback.on_step()`. Returns `(token_generator, execution_metadata)`.
  2. `st.write_stream(token_generator)`: Consumes token stream below collapsed `st.status` container.
- **Rationale**:
  - Prevents the empty status box bug and guarantees 100% visual fidelity of the 4-step progress container.
- **Alternatives Considered**:
  - *Single monolithic generator*: Rejected because search retrieval would execute after `st.status` closes.

---

### Topic 4: Container Runtime `PYTHONPATH` & Backward Compatibility Shims
- **Context**: Docker container `oliview_chatbot_a` runs `streamlit run 06.02.app.py` and mounts `./bteam/Oliview_chatbot_a:/app`.
- **Decision**:
  - In `docker-compose.yml`, mount `./bteam:/bteam` or set `PYTHONPATH=/app:/bteam:/app/bteam` so `bteam.oliview_core` or `oliview_core` resolves seamlessly.
  - Convert `06.02.app.py` and `06.app.py` into thin backward-compatibility entry shims that import and delegate to `oliview_core`.
  - Move legacy redundant scripts (`01`, `02`, `03.03`, `05.01`) into `legacy_archive/`.
- **Rationale**:
  - Zero disruption to existing Docker runtime and zero downtime on container restart.

---

## 2. Decision Summary Table

| Category | Chosen Strategy | Key Benefit |
| :--- | :--- | :--- |
| **Package** | `bteam/oliview_core/` | Standardized modular imports, IDE support, zero dynamic loaders |
| **Client** | Dual Sync/Async `AiGatewayClient` | Event loop safety for both Streamlit & FastAPI |
| **Pipeline** | 2-Stage `prepare_stream` + `generate_stream` | 100% stable `st.status` live progress visualization |
| **Legacy** | Deprecation Shims + `legacy_archive/` | 100% backward compatibility for Docker & external callers |
| **Config** | `oliview_core.config.Settings` | Single Source of Truth (SSOT) for ports, DB, and models |
