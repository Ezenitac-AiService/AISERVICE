# Quickstart & Verification Guide: 챗봇 A/B 런타임 결함 해결 및 vLLM 서빙 게이트웨이 복원

**Feature**: `024-chatbot-gateway-stability-fix`
**Date**: 2026-08-20

---

## 1. Unit Test Verification

단위 테스트를 통해 챗봇 A/B의 `budget_context_documents()` 및 가드레일 함수가 `is_9b` 관련 `NameError` 없이 안전하게 동작함을 검증합니다.

```bash
# 챗봇 A/B 컨텍스트 트리밍 및 프롬프트 가드레일 단위 테스트 실행
c:\AISERVICE\ateam\pilos-sentiment-index\.venv\Scripts\python.exe -m unittest discover -s bteam/tests -p "test_*.py"
```

---

## 2. Gateway Subprocess Restart & Live Query Verification

1. `vllm-serv-gateway` 컨테이너 및 챗봇 A/B 컨테이너 재빌드/재기동:
```bash
docker compose build vllm-serv oliview_chatbot_a oliview_chatbot_b
docker compose up -d vllm-serv oliview_chatbot_a oliview_chatbot_b
```

2. 챗봇 A 질의 검증 (`스킨케어에서 수분감 좋은 인기 앰플 추천해줘`):
```bash
curl -X POST http://127.0.0.1:8080/bteam/chata/api/chat -H "Content-Type: application/json" -d "{\"question\":\"스킨케어에서 수분감 좋은 인기 앰플 추천해줘\"}"
```

3. 챗봇 B 질의 검증 (`속건조가 너무 심해서 하루 종일 촉촉하고...`):
```bash
curl -X POST http://127.0.0.1:8080/bteam/chatb/api/chat -H "Content-Type: application/json" -d "{\"question\":\"속건조가 너무 심해서 하루 종일 촉촉하고 보습감 좋은 스킨케어 추천해줘\"}"
```
