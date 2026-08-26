# Contract: PILOS Batch Report Execution Harness

**Component**: `ateam/pilos-sentiment-index/pilos/collection/ai_clients/llm_report_client.py`  
**Target Gateway**: `http://vllm-serv-gateway:8081/v1/chat/completions`

---

## 1. Batch Payload Specification

PILOS 일일/주간 감성 리포트 생성 시, 30~60건의 뉴스 기사 및 커뮤니티 데이터를 단일 프롬프트에 패키징하여 전송합니다:

```json
{
  "model": "qwen3.5-2b",
  "temperature": 0.2,
  "max_tokens": 4096,
  "messages": [
    {
      "role": "system",
      "content": "당신은 시장 감성 지수 및 산업 트렌드 분석 전문가입니다. 제공된 <market_documents>를 종합 분석하여 시장 감성 점수와 주요 요인 보고서를 마크다운으로 작성하세요."
    },
    {
      "role": "user",
      "content": "<market_documents total_count=\"50\">\n  <doc id=\"1\" date=\"2026-08-26\" source=\"연합뉴스\">\n    <title>반도체 수출 전월비 12% 증가</title>\n    <content>...</content>\n  </doc>\n  ...\n</market_documents>\n\n위 전체 50개 문서를 종합하여 일일 종합 감성 지수(-1.0 ~ +1.0)와 핵심 이슈 3가지를 요약하세요."
    }
  ],
  "extra_body": {
    "priority": "high",
    "context_tier": "16K_BASELINE"
  }
}
```

---

## 2. Response & Validation

- **성공 응답**: 4,096토큰 이내의 완결형 시장 감성 보고서 마크다운 스트리밍.
- **Pre-flight Guard**: 전송 전 문자 길이 기준 토큰 추정치가 12,000토큰(16K 모드) 또는 26,000토큰(32K 모드)을 초과하지 않도록 자동 검증.
