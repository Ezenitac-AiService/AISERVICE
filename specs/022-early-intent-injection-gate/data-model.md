# Data Model: 선제적 하이브리드 의도 게이트 및 보안 데이터 구조체

**Feature Branch**: `022-early-intent-injection-gate`
**Date**: 2026-08-19

## Entities & Type Schemas

### 1. `EarlyGateDecision` (선제 게이트 판정 결과)
```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any

class GateVerdict(str, Enum):
    ALLOW = "ALLOW"                      # 정상 뷰티 상담 질의 (하이브리드 RAG 정상 진행)
    BLOCKED_INJECTION = "BLOCKED_INJECTION"  # 직접/우회 프롬프트 인젝션 및 탈옥 차단
    BLOCKED_OUT_OF_DOMAIN = "BLOCKED_OUT_OF_DOMAIN"  # 코딩, 게임, 수학, 번역 등 비도메인 차단
    BLOCKED_MEDICAL_TOXICITY = "BLOCKED_MEDICAL_TOXICITY"  # 유해 의약품/불법 제조 차단
    BLOCKED_DEFAMATION = "BLOCKED_DEFAMATION"  # 타사 브랜드 비방/허위 비교 차단

@dataclass
class EarlyGateDecision:
    verdict: GateVerdict
    is_blocked: bool
    refusal_message: str
    matched_rule: str
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    latency_ms: float
    guard_source: str  # "TIER_1A_RULE", "TIER_1B_MODEL", "SECURITY_CACHE"
    sanitized_query: str
```

### 2. `SecurityMetricsEvent` (Prometheus & 감사 로깅 페이로드)
```python
@dataclass
class SecurityMetricsEvent:
    timestamp: float
    event_id: str
    client_ip: Optional[str]
    session_id: Optional[str]
    masked_query: str          # PII(주민번호, 전화번호 등) 자동 마스킹된 질의
    verdict: GateVerdict
    matched_rule: str
    risk_level: str
    latency_ms: float
    action_taken: str          # "EARLY_EXIT_SAFE_RESPONSE"
```

---

## State Transition & Execution Flow

```text
[Raw Query Input]
       │
       ▼
[0. Raw Byte Sanitizer (NULL byte & Control Char Stripping, NFC Jamo Assembly)]
       │
       ▼
[1. Security Cache Check (Redis Exact-Match)] ──Hit──▶ [Return Cached ALLOW / BLOCK (0ms)]
       │ Miss
       ▼
[2. Tier 1A Contextual Rule Engine]
       ├── Matches Out-of-Domain Action Verbs (without Beauty context) ──▶ [BLOCKED_OUT_OF_DOMAIN] (0.1ms)
       ├── Matches Direct Attack Threat Signatures ──────────────────────▶ [BLOCKED_INJECTION] (0.1ms)
       ├── Matches Medical Toxicity / Defamation ───────────────────────▶ [BLOCKED_MEDICAL_TOXICITY] (0.1ms)
       └── Definite Beauty Query ────────────────────────────────────────▶ [ALLOW] (0.1ms)
       │ Ambiguous
       ▼
[3. Tier 1B Llama Prompt Guard 2 (86M) Local Classifier]
       ├── INJECTION / JAILBREAK Prob > 0.5 ─────────────────────────────▶ [BLOCKED_INJECTION] (15ms)
       └── BENIGN ───────────────────────────────────────────────────────▶ [ALLOW] (15ms)
       │
       ├── [If is_blocked == True]
       │     ├── Skip DB Connection (Connection Count = 0)
       │     ├── Skip Redis History Saving (History Poisoning Prevention)
       │     ├── Mask PII & Emit [SECURITY_ALERT] JSON Log
       │     └── Return EarlyGateDecision.refusal_message (selected_review_count=0)
       │
       └── [If is_blocked == False]
             └── Proceed to normal MySQL/Faiss Retrieval -> BGE Rerank -> 4B LLM Synthesis
```
