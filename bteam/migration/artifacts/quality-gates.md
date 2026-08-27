# Green quality gate results

기록 기준일: 2026-08-27 (Asia/Seoul)

비밀값은 기록하지 않았다.

| Gate | Command | Result |
| --- | --- | --- |
| Workspace | `uv sync --all-packages` | exit 0 |
| Python lint | `uv run ruff check packages pipelines services migration tests` | exit 0 |
| Python format | `uv run ruff format --check packages pipelines services migration tests` | exit 0 |
| Type check | `uv run mypy packages/core pipelines services migration` | exit 0, 54 files |
| Unit | `uv run pytest tests/unit -q` | 8 passed |
| Contract | `uv run pytest tests/contract -q` | 19 passed |
| Characterization | `uv run pytest tests/characterization -q` | 2 passed |
| Integration/E2E | `uv run pytest tests/integration tests/test_e2e_pipeline.py -q` | 17 passed |
| Security | `uv run pytest tests/security -q -m security` | 3 passed |
| Performance fixture | `uv run pytest tests/performance -q -m performance` | 1 passed |
| Frontend install | `npm ci --ignore-scripts` | exit 0, 135 packages |
| Frontend lint | `npm run lint` | exit 0 |
| Frontend build | `npm run build` | exit 0 |
| Frontend production audit | `npm audit --omit=dev` | 0 vulnerabilities |
| Green Compose | `docker compose ... config --no-interpolate --quiet` | exit 0 |
| Green image build | `docker compose ... build --quiet` with temporary redacted build variables | 5 application images built |
| Pipeline false-success guard | Green pipeline image without injected step handlers | exits with `StepHandlerNotConfigured`; no success run is recorded |
| Pipeline readiness failure output | rebuilt pipeline image, missing stage handler | exit 1; secret-free `pipeline_failed/FAILED` JSON event; Green compose runner restart policy `no` |
| Green candidate probe | dashboard/ChatA/ChatB/frontend localhost candidate endpoints | HTTP 200; frontend API proxy and direct RAG citation verified |
| Dashboard report contract | Green `/bteam/oliview/api/reports/1` plus `product_report_schema.json` validation | HTTP 200; schema v2 passed; 6 same-product attributes; abstained `LEGACY_UNVERIFIED` |
| Green MySQL restore | isolated `cosmetic_db` SQL restore plus additive schema | 21 legacy tables restored; additive migration rerunnable |
| Green Chroma restore | legacy SQLite/HNSW restore plus v2 batch migration | v1 57,435 = v2 57,435; 1,024-dimension vectors |
| Green runtime RAG | ChatA/ChatB query against Green v2 | both grounded with 5 citations and `source_review_id` |
| Chat compatibility regression | shared Core adapter, ChatA/ChatB sync + SSE + session routes | 50 Green tests passed; both runtime services HTTP 200, expected SSE events, session clear 200, Chroma v2 probe grounded |

성능 gate의 200회 실제 latency 측정, PRODUCTION GPU/Redis HA 판정, snapshot restore
실행 결과는 별도 operator gate로 남아 있다. 현재 performance 결과는 고정 fixture
구조 검증이며, 이를 실제 SLA 합격으로 해석하지 않는다.

`npm ci`가 표시한 취약점은 dev dependency 범위였고, production dependency audit은
0건이었다.

보존 대상 legacy 디렉터리까지 포함한 무차별 root `pytest -q`는 별도 historical
dependencies가 없어 collection 단계에서 실패하므로 Green 품질 게이트로 사용하지
않았다. legacy 테스트 파일과 Blue 운영 자산은 수정하지 않았다.
