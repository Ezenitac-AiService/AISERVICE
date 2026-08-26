# Data Model & Schema Specifications: Spec 035

**Feature Title**: Agentic AI Architecture, Harness Engineering, Living Process Inspector & Dynamic Context Window (16K/32K+) Expansion  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. Core Data Entities & Pydantic Schemas

### 1.1 ContextHarnessProfile (동적 컨텍스트 예산 모델)
```python
from pydantic import BaseModel, Field

class ContextHarnessProfile(BaseModel):
    """실시간 게이트웨이 하드웨어 프로파일에 기반한 3-Tier 컨텍스트 예산."""
    total_n_ctx: int = Field(default=16384, description="게이트웨이 유효 컨텍스트 윈도우")
    tier_name: str = Field(default="16K_BASELINE", description="16K_BASELINE | 32K_STANDARD | ULTRA")
    max_input_tokens: int = Field(default=10000, description="입력 컨텍스트 최대 할당 토큰 (85% 안전 마진)")
    max_output_tokens: int = Field(default=2048, description="최대 생성 토큰 상한")
    max_compare_output_tokens: int = Field(default=3072, description="다중 비교 시 최대 생성 토큰")
    tokens_per_target: int = Field(default=3500, description="타겟 제품당 할당 토큰 예산")
    reranked_per_target: int = Field(default=6, description="타겟당 최종 선별 리뷰 개수 (5~8개 in 16K, 10~15개 in 32K)")
    max_history_turns: int = Field(default=15, description="대화 세션 히스토리 보존 턴 수")
    raw_history_turns: int = Field(default=5, description="원문 유지 턴 수 (최근 N턴)")
    summary_history_turns: int = Field(default=10, description="요약 압축 대상 턴 수")
```

---

### 1.2 QualityGradeVerdict & HybridQueryReformulation (Self-RAG 모델)
```python
from typing import List, Optional
from pydantic import BaseModel, Field

class QualityGradeVerdict(BaseModel):
    """1차 검색/리랭킹 품질 검증 판정 결과."""
    status: str = Field(description="PASSED | RETRY_SEARCH | FALLBACK")
    average_score: float = Field(default=0.0, description="상위 선별 리뷰의 평균 리랭킹 점수")
    min_score: float = Field(default=0.0, description="선별 리뷰 최저 점수")
    total_candidates_found: int = Field(default=0, description="수집된 총 후보 문서 수")
    missing_targets: List[str] = Field(default_factory=list, description="검색 결과가 0건인 타겟 목록")
    reason: Optional[str] = Field(default=None, description="재검색 또는 폴백 사유")

class HybridQueryReformulationResult(BaseModel):
    """사전 동의어 확장 + Fast LLM 문맥 재작성 하이브리드 결과."""
    original_query: str
    dictionary_expanded_queries: List[str] = Field(default_factory=list)
    llm_rewritten_query: Optional[str] = None
    merged_queries: List[str] = Field(default_factory=list)
    reformulation_latency_ms: float = 0.0
```

---

### 1.3 MemoryHarness & DeepRecallPayload (계층형 세션 모델)
```python
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class AnaphoraTurnTag(BaseModel):
    """세션 요약에 포함되는 과거 턴 엔티티 메타데이터 태그."""
    turn_index: int = Field(description="턴 번호 (예: 7)")
    entities_mentioned: List[str] = Field(default_factory=list, description="언급된 제품명 (예: ['닥터지 크림'])")
    attributes_discussed: List[str] = Field(default_factory=list, description="논의된 속성 (예: ['보습', '진정', '25000원'])")
    short_summary: str = Field(description="해당 턴의 1문장 요약")

class DeepRecallTurnPayload(BaseModel):
    """Redis L4에서 온디맨드로 복원된 과거 턴의 원본 페이로드."""
    turn_index: int
    user_query: str
    assistant_response: str
    reference_specs: List[Dict[str, Any]] = Field(default_factory=list)
    reference_reviews: List[Dict[str, Any]] = Field(default_factory=list)
    recalled_at: float = Field(description="복원 시각 타임스탬프")
```

---

### 1.4 LivingInspectorEvent (동적 프로세스 시각화 모델)
```python
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class InspectorNodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    BRANCHED = "branched"
    FALLBACK = "fallback"
    ERROR = "error"

class LivingInspectorEvent(BaseModel):
    """UI 타임라인에 동적으로 추가/갱신되는 StateGraph 실행 노드 이벤트."""
    trace_id: str
    event_type: str = "step_update"
    node_id: str = Field(description="노드 고유 식별자 (예: 'QUERY_REFORMULATION')")
    parent_node_id: Optional[str] = Field(default=None, description="부모 노드 ID (분기 렌더링용)")
    title: str = Field(description="노드 제목 (예: '동의어 사전 + Fast LLM 문맥 쿼리 재작성')")
    status: InspectorNodeStatus = Field(default=InspectorNodeStatus.RUNNING)
    is_branch: bool = Field(default=False, description="서브 브랜치 들여쓰기 렌더링 여부")
    elapsed_ms: float = Field(default=0.0, description="노드 실행 누적 소요 시간 (ms)")
    badge_text: Optional[str] = Field(default=None, description="마이크로 뱃지 텍스트 (예: '후보 15건 수집 (+0.4s)')")
    timestamp: float
```

---

### 1.5 RagGraphState (LangGraph 통합 상태 스키마)
```python
from typing import TypedDict, List, Dict, Any, Optional

class RagGraphState(TypedDict, total=False):
    # 식별자 및 세션 메타데이터
    trace_id: str
    session_id: str
    user_id: Optional[str]
    tenant_id: str
    query: str
    normalized_query: str
    
    # 3-Tier 컨텍스트 하네스
    context_harness: ContextHarnessProfile
    
    # 의도 및 지시어 분석
    pattern_type: str
    target_entities: List[Dict[str, Any]]
    is_anaphora_detected: bool
    recalled_turn_payload: Optional[DeepRecallTurnPayload]
    
    # 검색 풀 및 품질 검증
    search_pools: Dict[str, List[Dict[str, Any]]]
    reranked_contexts: Dict[str, List[Dict[str, Any]]]
    quality_verdict: Optional[QualityGradeVerdict]
    retry_count: int
    reformulation_result: Optional[HybridQueryReformulationResult]
    
    # 컨텍스트 조립
    context_text: str
    canary_token: str
    is_fallback: bool
    fallback_reason: Optional[str]
    
    # L5 캐시 및 메트릭
    is_cached: bool
    l5_cache_key: str
    metrics: Dict[str, Any]
    error_log: List[str]
```
