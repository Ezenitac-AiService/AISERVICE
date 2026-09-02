# Quickstart Validation Guide: 모델 게이트웨이 LLM/보조 모델 온로드 검증

**Feature**: `044-fix-model-gateway-onload`
**Date**: 2026-09-02
**Status**: Ready

## 1. 사전 준비 (Prerequisites)
- Docker 컨테이너(`vllm-serv-gateway`)가 실행 중이거나 로컬 테스트 환경이 준비되어 있어야 합니다.
- `models/` 디렉토리에 `qwen3.5-2b`, `bge-m3`, `bge-reranker-v2-m3` GGUF 파일이 존재해야 합니다.

---

## 2. 검증 시나리오 및 명령어

### 시나리오 1: 백엔드 프로세스 리슨 포트 및 PID 검증
게이트웨이 기동 후 3종 모델의 서브프로세스가 실제 포트에서 리슨 중인지 확인합니다.

```bash
# 컨테이너 내부 포트 상태 확인
docker exec vllm-serv-gateway python3 -c "import socket
for p in [8081, 8089, 8090, 8091]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    r = s.connect_ex(('127.0.0.1', p))
    print(f'Port {p}:', 'OPEN (PASS)' if r == 0 else 'CLOSED (FAIL)')
    s.close()
"
```
**기대 결과**: 8081, 8089, 8090, 8091 모두 `OPEN (PASS)`.

---

### 시나리오 2: 서비스 준비도(Readiness) 및 종합 헬스체크
```bash
# 1. Readiness 확인 (HTTP 200)
docker exec vllm-serv-gateway python3 -c "import httpx; r=httpx.get('http://127.0.0.1:8081/health/readiness'); print('Readiness:', r.status_code, r.json())"

# 2. 종합 상태 확인 (HTTP 200, 3종 모델 READY)
docker exec vllm-serv-gateway python3 -c "import httpx; r=httpx.get('http://127.0.0.1:8081/health'); print('Health:', r.status_code, r.json())"
```
**기대 결과**: `status_code: 200`, `status: "ready"`, `is_ready: True`.

---

### 시나리오 3: LLM 추론 E2E 테스트 (`POST /v1/chat/completions`)
```bash
docker exec vllm-serv-gateway python3 -c "import httpx
payload = {
    'model': 'qwen3.5-2b',
    'messages': [{'role': 'user', 'content': '안녕하세요! 테스트 메시지입니다.'}],
    'max_tokens': 50
}
r = httpx.post('http://127.0.0.1:8081/v1/chat/completions', json=payload, timeout=30.0)
print('Status:', r.status_code)
print('Response:', r.json()['choices'][0]['message']['content'])
"
```
**기대 결과**: `Status: 200`, AI 생성 한국어 답변 정상 출력.

---

### 시나리오 4: 임베딩 및 리랭킹 E2E 테스트
```bash
# 임베딩 테스트
docker exec vllm-serv-gateway python3 -c "import httpx
payload = {'input': '올리뷰 화장품 추천', 'model': 'bge-m3'}
r = httpx.post('http://127.0.0.1:8081/v1/embeddings', json=payload, timeout=10.0)
print('Embedding Status:', r.status_code, 'Dim:', len(r.json()['data'][0]['embedding']))
"

# 리랭킹 테스트
docker exec vllm-serv-gateway python3 -c "import httpx
payload = {
    'model': 'bge-reranker-v2-m3',
    'query': '민감성 피부에 좋은 로션',
    'documents': ['순한 성분의 보습 로션입니다.', '화려한 파티용 메이크업 제품']
}
r = httpx.post('http://127.0.0.1:8081/v1/rerank', json=payload, timeout=10.0)
print('Rerank Status:', r.status_code, 'Results:', r.json()['results'])
"
```
**기대 결과**: 각각 `Status: 200`, 유효한 벡터 및 순위화 점수 반환.
