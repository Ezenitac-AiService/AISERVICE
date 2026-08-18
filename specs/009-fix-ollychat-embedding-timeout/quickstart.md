# Quickstart: 올리챗·올원챗 임베딩 타임아웃 해소 및 3대 챗봇 통합 회귀 검증 (009-fix-ollychat-embedding-timeout)

## 1. 사전 준비 (Prerequisites)
- Docker 컨테이너 실행 중 (`aiservice-gateway`, `vllm-serv-gateway`, `pilos-web`, `oliview_chatbot_a`, `oliview_chatbot_b`)

---

## 2. 검증 시나리오 1: Model Gateway 임베딩 포트(8090) 호출 검증

### 실행 명령
```powershell
docker exec vllm-serv-gateway python3 -c "import requests; res = requests.post('http://127.0.0.1:8090/v1/embeddings', json={'model': 'bge-m3', 'input': ['차앤박 프로폴리스 앰플 수분감']}, timeout=10); print('STATUS:', res.status_code); print('EMBEDDING DIM:', len(res.json()['data'][0]['embedding']))"
```

### 기대 결과
```text
STATUS: 200
EMBEDDING DIM: 1024
```

---

## 3. 검증 시나리오 2: 올리챗(ChromaDB RAG) 파이프라인 검증

### 실행 명령
```powershell
docker exec oliview_chatbot_a python3 -c "from common.embedding_client import HttpBgeM3Embeddings; emb = HttpBgeM3Embeddings(); res = emb.embed_query('차앤박 프로폴리스 앰플 수분감을 분석해줘'); print('EMBED OK:', len(res))"
```

### 기대 결과
```text
EMBED OK: 1024
```

---

## 4. 검증 시나리오 3: 3대 챗봇 통합 자동화 회귀 테스트 실행

### 실행 명령
```powershell
uv run python -m unittest tests/test_multi_chatbot_regression.py
```

### 기대 결과
```text
test_pilos_chatbot_cache_and_stream ... ok
test_ollychat_embedding_and_rag ... ok
test_allonechat_rag_api_endpoint ... ok
test_multi_chatbot_concurrent_isolation ... ok

----------------------------------------------------------------------
Ran 4 tests in X.XXXs

OK
```
