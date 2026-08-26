"""
End-to-End 2-Stage RAG Pipeline Orchestrator for Oliview Core.
"""

import time
from typing import Iterator, Tuple, Optional, List, Dict, Any
from .types import (
    StepCode,
    StepEvent,
    ReferenceReview,
    RagExecutionMetadata,
    IntentAnalysisResult,
)
from .callback import StepCallbackProtocol
from .client import AiGatewayClient
from .retrieval import HybridRetriever
from .rerank import BGEReranker
from .sanitizer import (
    build_oliveyoung_url,
    clean_review_noise,
    detect_brand_and_category,
    normalize_korean_markdown,
)
from .guardrail import PromptInjectionGuardrail, EarlyIntentGuardrail
from .db import fetch_review_metadata

# ────────────────────────────────────────────────────────────────────────────
# Spec 017: 한국어 마크다운 안전 생성 가이드라인 (Korean Markdown Safety Rules)
# ────────────────────────────────────────────────────────────────────────────
KOREAN_MARKDOWN_SAFETY_RULES = """
[한국어 마크다운 작성 필수 규칙]
1. 인용구와 볼드 기호를 절대로 중첩하지 마세요:
   - 금지: **"자극 느껴져요"**라는 피드백
   - 권장: "자극 느껴져요"라는 피드백
   - 권장: **자극성 평가:** "자극 느껴져요"라는 고객 의견
2. 항목별 분석 시 반드시 라벨-콜론-공백 구조를 사용하세요:
   - 권장: - **수분감:** 촉촉하게 흡수되며 당김이 없습니다.
   - 권장: - **발림성:** 부드럽게 펴 발립니다.
3. 볼드 강조 뒤에 한국어 조사를 바로 붙이지 마세요:
   - 금지: **수분감**은 좋습니다
   - 권장: **수분감**은 좋습니다 → 수분감은 좋습니다 (볼드 없이) 또는 **수분감:** 좋습니다 (라벨 구조)
"""

OLIVIEW_SYSTEM_PROMPT = f"""당신은 올리브영 뷰티 리뷰 분석 AI 어시스턴트 '올리뷰'입니다. 실제 고객 리뷰 데이터를 기반으로 객관적이고 유용한 화장품 분석을 제공합니다.
{KOREAN_MARKDOWN_SAFETY_RULES}
[출력 모범 예시]
### 🌿 식물나라 토너: 자극성 및 기능/효과 분석

1. 자극성 관련 분석

- **부정적 반응:** "자극 느껴져요"라는 고객 피드백이 있습니다.
- **중립적/긍정적 반응:** 전반적으로 순한 제품으로 평가받기도 했습니다.

2. 기능 및 효과 분석

- **효과 기대감:** "그냥 일반 토너랑 비슷함"이라고 평했습니다.
- **전반적 평가:** "전반적으로 순해서"라는 긍정적인 평가를 받았습니다.
"""


class OliviewPipeline:
    """Standard RAG Pipeline Orchestrator."""

    def __init__(
        self,
        client: Optional[AiGatewayClient] = None,
        retriever: Optional[HybridRetriever] = None,
        reranker: Optional[BGEReranker] = None,
    ):
        self.client = client or AiGatewayClient()
        self.retriever = retriever or HybridRetriever(self.client)
        self.reranker = reranker or BGEReranker(self.client)

    def prepare_pipeline_stream(
        self,
        question: str,
        callback: Optional[StepCallbackProtocol] = None,
        category_hint: Optional[str] = None,
    ) -> Tuple[Iterator[str], RagExecutionMetadata]:
        """
        Executes Guardrailed Synchronous RAG Stages 1~3:
          0. Tier 1 Prompt Injection Guardrail Pre-check
          1. Intent & Attribute Analysis
          2. Hybrid Search (Faiss Dense + BM25)
          3. GPU BGE Reranking
        
        Returns:
          - (token_stream_generator, execution_metadata)
        """
        t0 = time.time()
        # Step 0: Early Intent & Security Gate (Spec 022)
        decision = EarlyIntentGuardrail.evaluate_gate(question)
        if decision.is_blocked:
            metadata = RagExecutionMetadata(
                total_latency_sec=round(decision.latency_ms / 1000.0, 4),
                search_latency_sec=0.0,
                rerank_latency_sec=0.0,
                selected_review_count=0,
                model_name="guardrail-early-blocked",
                fallback_used=True,
                reference_reviews=[],  # 0 references exposed
            )
            def _blocked_stream() -> Iterator[str]:
                yield decision.refusal_message
            return _blocked_stream(), metadata

        # Step 1: Intent Analysis
        if callback:
            callback.on_step(StepEvent(step=StepCode.INTENT_ANALYSIS, label="🔍 질문 의도 및 화장품 속성 분석 중..."))
        brand_hint, detected_cat = detect_brand_and_category(question)
        final_category = category_hint or detected_cat
        time.sleep(0.02)

        # Step 2: Hybrid Search
        t_search_start = time.time()
        if callback:
            callback.on_step(StepEvent(step=StepCode.HYBRID_SEARCH, label="📚 관련 화장품 리뷰 및 성분 하이브리드 검색 중..."))

        candidates = self.retriever.search(
            query=question,
            top_k=25,
            brand_filter=brand_hint,
            category_filter=final_category,
        )
        search_latency = time.time() - t_search_start

        # Step 3: GPU BGE Reranking
        t_rerank_start = time.time()
        if callback:
            callback.on_step(StepEvent(step=StepCode.RERANKING, label="🧠 AI 심층 분석 및 BGE Cross-Encoder 리랭킹 중..."))

        cand_texts = [str(c.get("clean_text") or c.get("review_text") or "") for c in candidates]
        ranked_indices, scores, fallback_used = self.reranker.rerank(
            query=question,
            documents=cand_texts,
            top_k=5,
        )
        rerank_latency = time.time() - t_rerank_start

        # Build Reference Reviews & Context
        selected_candidates = [candidates[i] for i in ranked_indices if i < len(candidates)]
        selected_review_ids = [c.get("review_id") for c in selected_candidates if c.get("review_id")]

        db_meta = fetch_review_metadata([int(i) for i in selected_review_ids if str(i).isdigit()])

        reference_reviews: List[ReferenceReview] = []
        context_blocks: List[str] = []

        for idx, cand in enumerate(selected_candidates):
            r_id = cand.get("review_id", idx)
            db_row = db_meta.get(r_id, {})
            p_name = db_row.get("product_name") or cand.get("product_name") or "올리브영 화장품"
            p_brand = db_row.get("brand") or cand.get("brand") or brand_hint or ""
            p_url = db_row.get("product_url") or cand.get("product_url") or build_oliveyoung_url(p_name, p_brand)
            c_text = clean_review_noise(cand.get("clean_text") or db_row.get("review_clean_text") or cand.get("review_text") or "")
            score = scores[idx] if idx < len(scores) else 0.0

            ref = ReferenceReview(
                review_id=int(r_id) if str(r_id).isdigit() else idx,
                product_name=p_name,
                product_url=p_url,
                clean_text=c_text,
                original_text=cand.get("review_text") or c_text,
                sentiment=cand.get("sentiment") or "NEUTRAL",
                relevance_score=float(score),
                brand=p_brand,
                category=final_category or "",
            )
            reference_reviews.append(ref)
            context_blocks.append(f"[{idx+1}] 상품명: {p_name} (브랜드: {p_brand})\n리뷰 내용: {c_text}")

        total_latency = time.time() - t0

        metadata = RagExecutionMetadata(
            total_latency_sec=total_latency,
            search_latency_sec=search_latency,
            rerank_latency_sec=rerank_latency,
            selected_review_count=len(reference_reviews),
            model_name=self.client.settings.synthesis_llm_model,
            fallback_used=fallback_used,
            reference_reviews=reference_reviews,
        )

        # Spec 021: Tier 2/3 Sandboxed Prompt Generation with Canary Token
        sandboxed_payload = PromptInjectionGuardrail.build_sandboxed_rag_prompt(
            user_query=question,
            reference_blocks=context_blocks,
            base_system_prompt=OLIVIEW_SYSTEM_PROMPT,
        )

        raw_token_stream = self.client.generate_stream(
            prompt=sandboxed_payload.user_content,
            system_prompt=sandboxed_payload.system_prompt,
        )

        # Spec 017 & 021: 스트리밍 정규화 및 Tier 4 카나리아 출력 가드레일 어댑터
        def _guarded_normalized_stream(raw_stream: Iterator[str]) -> Iterator[str]:
            buffer = ""
            for token in raw_stream:
                buffer += token
                # Tier 4: Canary Output Verification
                is_safe, _ = PromptInjectionGuardrail.verify_output_safety(
                    buffer, canary_token=sandboxed_payload.canary_token
                )
                if not is_safe:
                    yield PromptInjectionGuardrail.SAFE_BLOCKED_RESPONSE
                    return

                normalized = normalize_korean_markdown(buffer)
                # 이전까지 이미 yield한 길이만큼 건너뛰고 새로 추가된 부분만 yield
                if len(normalized) > len(buffer) - len(token):
                    yield normalized[len(normalized) - len(token):]
                else:
                    yield token

        return _guarded_normalized_stream(raw_token_stream), metadata


# Global Pipeline Singleton
_global_pipeline: Optional[OliviewPipeline] = None


def get_pipeline() -> OliviewPipeline:
    global _global_pipeline
    if _global_pipeline is None:
        _global_pipeline = OliviewPipeline()
    return _global_pipeline


def prepare_pipeline_stream(
    question: str,
    callback: Optional[StepCallbackProtocol] = None,
    category_hint: Optional[str] = None,
) -> Tuple[Iterator[str], RagExecutionMetadata]:
    """Convenience functional interface for 2-stage stream preparation."""
    return get_pipeline().prepare_pipeline_stream(
        question=question,
        callback=callback,
        category_hint=category_hint,
    )


def generate_pipeline_answer(question: str, callback: Optional[StepCallbackProtocol] = None) -> str:
    """Synchronous complete text generation."""
    stream_gen, _ = prepare_pipeline_stream(question, callback)
    return "".join(list(stream_gen))


def generate_pipeline_answer_stream(question: str, callback: Optional[StepCallbackProtocol] = None) -> Iterator[str]:
    """Generator-only stream interface for legacy compatibility."""
    stream_gen, _ = prepare_pipeline_stream(question, callback)
    return stream_gen
