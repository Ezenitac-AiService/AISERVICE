# Quickstart Validation Guide: 016-system-codebase-refactoring

**Feature**: [spec.md](./spec.md) | **Date**: 2026-08-19 | **Status**: Complete

---

## 1. Prerequisites

- Python 3.11+ / 3.12+
- Docker running with containers:
  - `vllm-serv-gateway` (Port 8081, 8090, 8091)
  - `bteam_db` (MySQL Port 3306)
  - `oliview_chatbot_a` (Port 8501)
  - `oliview_chatbot_b` (Port 8002)

---

## 2. Test Execution Commands

### Step 1: Run Unit Tests for `oliview_core`
```bash
# Test Core Module Imports & Schemas
pytest tests/unit/test_oliview_core_imports.py -v

# Test Dual AI Gateway Client (Sync & Async)
pytest tests/unit/test_ai_gateway_client.py -v
```

### Step 2: Run End-to-End Pipeline Integration Test
```bash
# Test 2-Stage Retrieval & Reranking Speed (Target: <= 150ms)
pytest tests/integration/test_pipeline_e2e.py -v
```

### Step 3: Verify Live Docker Container Health & UX
```bash
# Check Docker logs
docker logs --tail 25 oliview_chatbot_a

# Test HTTP 200 on ChatA & ChatB
python -c "import urllib.request; print('ChatA:', urllib.request.urlopen('http://127.0.0.1:8080/bteam/chata/').status); print('ChatB:', urllib.request.urlopen('http://127.0.0.1:8080/bteam/chatb/').status)"
```
