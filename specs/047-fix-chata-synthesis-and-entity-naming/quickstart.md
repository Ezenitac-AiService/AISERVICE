# Quickstart Validation Guide: 047-fix-chata-synthesis-and-entity-naming

## 1. Prerequisites
- Docker 컨테이너 기동: `aiservice-gateway`, `oliview_chatbot_a`, `oliview_chatbot_b`, `vllm-serv-gateway`, `bteam_db`, `aiservice-redis`
- 가상환경: `bteam/Oliview_chatbot_a/.venv`

---

## 2. Core Synchronization & Sanity Verification

### 1단계: 3-Way 단일 마스터 코어 동기화 검증
```bash
python bteam/sync_core.py
```
- **기대 결과**: `[SUCCESS] oliview_core 3-way synchronization complete.` 출력

### 2단계: 오염된 기존 Redis L5 캐시 키 일괄 정리
```bash
uv run --project bteam/Oliview_chatbot_a python -c "
import redis
r = redis.Redis(host='127.0.0.1', port=6379, db=0)
keys = r.keys('*l5:*')
if keys:
    print('Evicting poisoned L5 keys:', len(keys))
    r.delete(*keys)
print('Redis L5 cleanup complete.')
"
```

---

## 3. Automated Unit & Integration Tests

```bash
uv run --project bteam/Oliview_chatbot_a python -m pytest bteam/Oliview_chatbot_a/tests/ -v
```
- **기대 결과**: 모든 단위 및 회귀 테스트 100% 통과 (PASS)

---

## 4. End-to-End Live Scenario Testing

### 시나리오 1: 카테고리/추천 질의 시 실존 상품명 결속 검증
```bash
uv run --project bteam/Oliview_chatbot_a python -c "
import httpx

payload = {
    'query': '스킨케어에서 수분감 좋은 인기 앰플 추천해줘',
    'session_id': 'quickstart_test_001',
    'category_hint': '스킨케어',
    'bypass_cache': True
}

with httpx.stream('POST', 'http://127.0.0.1:8501/api/v1/chat/stream', json=payload, timeout=180.0) as r:
    print('Stream Status:', r.status_code)
    for line in r.iter_lines():
        if 'complete' in line or 'reference_reviews' in line:
            print('Complete payload snippet:', line[:200])
"
```
- **검증 항목**:
  1. `tag` 및 `product_name`에 질문 문장이 나타나지 않고 실제 제품명(예: `차앤박...`)으로 결속되는지 확인.
  2. `oliveyoung_search_url`에 질문 문장이 아닌 실제 제품명이 인코딩되는지 확인.

### 시나리오 2: L5 캐시 에러 방어 게이트 검증
- **검증 항목**:
  1. 에러 메시지(`[답변 생성 오류: ...`)가 발생해도 Redis에 L5 캐시 키가 생성되지 않는지 확인.
  2. 정상 답변만 L5 캐시 저장 후 2회차 호출 시 0.2초 이내 캐시 재생(`⚡ (L5 캐시)`)되는지 확인.
