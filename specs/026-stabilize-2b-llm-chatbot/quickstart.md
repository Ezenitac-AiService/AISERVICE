# Quickstart Validation Guide: 026-stabilize-2b-llm-chatbot

## 1. Prerequisites
- Docker containers running (`vllm-serv-gateway`, `oliview_chatbot_a`, `oliview_chatbot_b`, `bteam_db`, `aiservice-redis`).
- GPU VRAM <= 6.0 GB with `qwen3.5-2b`, `bge-m3`, and `bge-reranker-v2-m3` resident.

---

## 2. Validation Scenario 1: Model Gateway Single Model Mode Verification

```bash
# 1. 게이트웨이 헬스체크 및 현재 모델 확인 (qwen3.5-2b 상주 확인)
docker exec vllm-serv-gateway curl -s http://127.0.0.1:8081/health

# 2. 4B 요청을 보내더라도 프로세스 킬 없이 2B로 무중단 처리되는지 검증
docker exec vllm-serv-gateway python3 -c "
import urllib.request, json
payload = json.dumps({'model': 'qwen3.5-4b', 'messages': [{'role': 'user', 'content': '안녕'}], 'max_tokens': 512}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions', data=payload, headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req, timeout=10)
print(res.read().decode('utf-8'))
"
```
**Expected Outcome**: 프로세스 재시작 없이 2B 모델로 즉각(1초 이내) 200 OK 응답 반환.

---

## 3. Validation Scenario 2: Chatbot B RAG 스트리밍 완결성 검증

```bash
docker exec oliview_chatbot_b python3 -c "
import urllib.request, json
payload = json.dumps({
    'query': '여름철 기름기 잡고 모공 커버 잘되는 매트 쿠션 추천해줘',
    'brand': '이니스프리',
    'max_tokens': 2048
}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8002/api/v1/search', data=payload, headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req, timeout=30)
data = json.loads(res.read().decode('utf-8'))
print('Answer length:', len(data['llm_answer']))
print('Answer preview:', data['llm_answer'][:200])
assert len(data['llm_answer']) > 200, '답변이 절단되지 않고 완결되어야 함'
"
```
**Expected Outcome**: 문장 중간 절단 없이 1,000자 이상의 완성된 뷰티 솔루션 반환.

---

## 4. Validation Scenario 3: Chatbot A 및 보안 가드레일 오탐 검증

```bash
docker exec oliview_chatbot_a python3 -c "
from oliview_core.guardrail import PromptInjectionGuardrail
safe_query = '식물나라 토너 자극감과 기능/효과 분석해줘'
det = PromptInjectionGuardrail.detect_injection(safe_query)
print('Is blocked:', det.is_blocked)
assert not det.is_blocked, '정상 화장품 질문은 차단되지 않아야 함'
"
```
**Expected Outcome**: `Is blocked: False` 정상 통과.
