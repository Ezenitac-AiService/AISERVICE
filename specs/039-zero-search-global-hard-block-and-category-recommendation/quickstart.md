# Quickstart & Verification Guide: Feature 039

**Feature**: `039-zero-search-global-hard-block-and-category-recommendation`  
**Created**: 2026-08-26  

---

## 1. Running Unit & Integration Tests

```bash
# 1. ChatA Directory Tests
cd c:\AISERVICE\bteam\Oliview_chatbot_a
uv run python -m pytest tests/test_feature_039_zero_search.py -v

# 2. ChatB Directory Tests
cd c:\AISERVICE\bteam\Oliview_chatbot_b
uv run python -m pytest tests/test_feature_039_zero_search.py -v
```

---

## 2. Dynamic Mode Testing (`APP_RUN_MODE`)

### Demo Mode (Default, Legacy PoC Tolerant SLA)
```bash
set APP_RUN_MODE=DEMO
uv run python main.py
# Query: "화성인 안드로메다 수분크림 추천해줘"
# Output: Returns ZERO_SEARCH_TEMPLATE in <= 3.0s with 0 hallucinated reviews
```

### Production Mode (High Performance SLA)
```bash
set APP_RUN_MODE=PRODUCTION
uv run python main.py
# Query: "화성인 안드로메다 수분크림 추천해줘"
# Output: Returns ZERO_SEARCH_TEMPLATE in <= 0.5s
```

---

## 3. Synchronizing Core Modules (`sync_core.py`)

```bash
cd c:\AISERVICE\bteam
uv run python sync_core.py --verify
# Output:
# [OK] bteam/oliview_core -> Oliview_chatbot_a/oliview_core (100% Synced)
# [OK] bteam/oliview_core -> Oliview_chatbot_b/oliview_core (100% Synced)
```
