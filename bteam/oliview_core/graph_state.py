"""
LangGraph RAG State & Event Data Models (Spec 035 - Agentic AI & Harness Engineering).
RagGraphState, ContextHarnessProfile, QualityGradeVerdict, LivingInspectorEvent, DeepRecallTurnPayload 데이터 모델 정의.
"""

from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class PatternType(str, Enum):
    """RAG 라우팅 패턴 분류."""
    EXPLICIT_COMPARE = "PATTERN_EXPLICIT_COMPARE"       # 명시적 제품 비교
    FEATURE_DISCOVERY = "PATTERN_FEATURE_DISCOVERY"     # 기능 기반 다자 비교
    ASPECT_PROS_CONS = "PATTERN_ASPECT_PROS_CONS"       # 장단점/다중 속성 분석
    SINGLE_TARGET = "PATTERN_SINGLE_TARGET"             # 단일 제품 질의


class TargetType(str, Enum):
    """분석 대상 엔티티 유형."""
    PRODUCT = "PRODUCT"
    BRAND = "BRAND"
    ATTRIBUTE = "ATTRIBUTE"
    SENTIMENT = "SENTIMENT"


class StepStatus(str, Enum):
    """계층형 서브스텝 진행 상태."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    BRANCHED = "branched"
    FALLBACK = "fallback"
    ERROR = "error"


class SubStepAction(str, Enum):
    """타겟별 서브스텝 세부 액션."""
    START = "START"
    SEARCHING = "SEARCHING"
    SEARCH_DONE = "SEARCH_DONE"
    RERANK_DONE = "RERANK_DONE"
    REFORMULATING = "REFORMULATING"
    RECALLING = "RECALLING"
    ERROR_SKIPPED = "ERROR_SKIPPED"


class ContextHarnessProfile(BaseModel):
    """실시간 게이트웨이 하드웨어 프로파일에 기반한 3-Tier 컨텍스트 예산."""
    total_n_ctx: int = Field(default=16384, description="게이트웨이 유효 컨텍스트 윈도우")
    tier_name: str = Field(default="16K_BASELINE", description="16K_BASELINE | 32K_STANDARD | ULTRA")
    max_input_tokens: int = Field(default=10000, description="입력 컨텍스트 최대 할당 토큰 (85% 안전 마진)")
    max_output_tokens: int = Field(default=2048, description="최대 생성 토큰 상한")
    max_compare_output_tokens: int = Field(default=3072, description="다중 비교 시 최대 생성 토큰")
    tokens_per_target: int = Field(default=3500, description="타겟 제품당 할당 토큰 예산")
    reranked_per_target: int = Field(default=6, description="타겟당 최종 선별 리뷰 개수 (5~8개 in 16K, 10~15개 in 32K)")
    candidates_per_target: int = Field(default=15, description="타겟당 1차 후보 검색 풀 크기")
    max_history_turns: int = Field(default=15, description="대화 세션 히스토리 보존 턴 수")
    raw_history_turns: int = Field(default=5, description="원문 유지 턴 수 (최근 N턴)")
    summary_history_turns: int = Field(default=10, description="요약 압축 대상 턴 수")


class QualityGradeVerdict(BaseModel):
    """1차 검색/리랭킹 품질 검증 판정 결과 (Self-RAG Node)."""
    status: str = Field(default="PASSED", description="PASSED | RETRY_SEARCH | FALLBACK")
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


class AnaphoraTurnTag(BaseModel):
    """세션 요약에 포함되는 과거 턴 엔티티 메타데이터 태그."""
    turn_index: int = Field(description="턴 번호 (예: 7)")
    entities_mentioned: List[str] = Field(default_factory=list, description="언급된 제품명")
    attributes_discussed: List[str] = Field(default_factory=list, description="논의된 속성/가격/성분")
    short_summary: str = Field(description="해당 턴의 1문장 요약")


class DeepRecallTurnPayload(BaseModel):
    """Redis L4에서 온디맨드로 복원된 과거 턴의 원본 페이로드."""
    turn_index: int
    user_query: str
    assistant_response: str
    reference_specs: List[Dict[str, Any]] = Field(default_factory=list)
    reference_reviews: List[Dict[str, Any]] = Field(default_factory=list)
    recalled_at: float = Field(default=0.0, description="복원 시각 타임스탬프")


class LivingInspectorEvent(BaseModel):
    """UI 타임라인에 동적으로 추가/갱신되는 StateGraph 실행 노드 이벤트."""
    trace_id: str
    event_type: str = "step_update"
    node_id: str = Field(description="노드 고유 식별자 (예: 'QUERY_REFORMULATION')")
    parent_node_id: Optional[str] = Field(default=None, description="부모 노드 ID (분기 렌더링용)")
    title: str = Field(description="노드 제목 (예: '동의어 사전 + Fast LLM 문맥 쿼리 재작성')")
    status: StepStatus = Field(default=StepStatus.RUNNING)
    is_branch: bool = Field(default=False, description="서브 브랜치 들여쓰기 렌더링 여부")
    elapsed_ms: float = Field(default=0.0, description="노드 실행 누적 소요 시간 (ms)")
    badge_text: Optional[str] = Field(default=None, description="마이크로 뱃지 텍스트")
    timestamp: float = Field(default=0.0)


class SpecHeader(TypedDict, total=False):
    """제품 스펙 메타데이터 헤더."""
    price: Optional[int]
    volume: Optional[str]
    key_ingredients: Optional[str]
    skin_type: Optional[str]


class TargetEntity(TypedDict):
    """검증된 분석 대상 엔티티."""
    target_id: str
    target_name: str
    brand_name: Optional[str]
    product_name: Optional[str]
    target_type: str
    attribute_query: Optional[str]
    spec_header: Optional[SpecHeader]


class CandidateReview(TypedDict, total=False):
    """1차 검색된 후보 리뷰 (타겟당 최대 15건)."""
    doc_id: str
    review_text: str
    target_id: str
    target_name: str
    product_name: Optional[str]
    clean_product_name: Optional[str]
    brand_name: Optional[str]
    category: Optional[str]
    attribute_name: Optional[str]
    product_url: Optional[str]
    first_stage_score: float
    rating: Optional[float]
    skin_type: Optional[str]


class RerankedReview(TypedDict, total=False):
    """리랭킹 후 쿼터 선별된 최종 리뷰 (타겟당 5~15건)."""
    doc_id: str
    review_text: str
    target_id: str
    target_name: str
    product_name: Optional[str]
    clean_product_name: Optional[str]
    brand_name: Optional[str]
    category: Optional[str]
    attribute_name: Optional[str]
    product_url: Optional[str]
    rerank_score: float
    rank: int
    rating: Optional[float]


class ReviewCitation(TypedDict, total=False):
    """최종 레퍼런스 인용 및 UI 전달용 객체."""
    rank: int
    tag: str
    product_name: str
    clean_product_name: str
    brand_name: str
    category: str
    attribute_name: str
    review_score: float
    clean_text: str
    rerank_score: float
    product_url: str
    oliveyoung_search_url: str


class RagGraphState(TypedDict, total=False):
    """LangGraph StateGraph 전역 상태 스키마 (Spec 035)."""
    trace_id: str
    session_id: str
    user_id: Optional[str]
    tenant_id: str
    query: str
    normalized_query: str
    context_harness: ContextHarnessProfile
    pattern_type: str
    target_entities: List[TargetEntity]
    is_anaphora_detected: bool
    recalled_turn_payload: Optional[DeepRecallTurnPayload]
    search_pools: Dict[str, List[CandidateReview]]
    reranked_contexts: Dict[str, List[RerankedReview]]
    quality_verdict: Optional[QualityGradeVerdict]
    retry_count: int
    reformulation_result: Optional[HybridQueryReformulationResult]
    context_text: str
    canary_token: str
    is_fallback: bool
    fallback_reason: Optional[str]
    target_errors: Dict[str, str]
    is_cached: bool
    l5_cache_key: str
    metrics: Dict[str, Any]
    error_log: List[str]
    # Feature 039: Zero-Search Hard Block & Entity-Aspect RAG
    app_run_mode: str
    is_zero_review_state: bool
    zero_search_verdict: Optional[Dict[str, Any]]
    groundedness_violations: List[str]
    category_candidates: List[Dict[str, Any]]


FALLBACK_LABEL = "⚡ 신속 분석 모드 (실시간 기본 검색)"


class SubStepDetail(TypedDict, total=False):
    target_index: int
    total_targets: int
    target_id: str
    target_name: str
    action: str
    count: int
    message: str


class FallbackInfo(TypedDict, total=False):
    triggered: bool
    label: str
    reason: str


class SubStepEvent(TypedDict, total=False):
    trace_id: str
    event_type: str
    step_id: str
    step_name: str
    sub_step: Optional[SubStepDetail]
    status: str
    fallback_info: Optional[FallbackInfo]
    elapsed_ms: float
    timestamp: float
    badge_text: Optional[str]
    is_branch: bool
    node_id: Optional[str]
    parent_node_id: Optional[str]
