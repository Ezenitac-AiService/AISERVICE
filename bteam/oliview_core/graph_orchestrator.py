"""
LangGraph StateGraph Multi-Target RAG Orchestrator (Spec 035 - Agentic AI & Living Process Inspector).
선언적 StateGraph 컴파일, Self-RAG 품질 검증 조건부 분기, 계층형 메모리 온디맨드 심층 회상,
실시간 동적 Living Inspector SSE 이벤트 스트리밍.
"""

import time
import json
import urllib.parse
from typing import Dict, Any, Iterator, AsyncGenerator, Optional, List

try:
    from langgraph.graph import StateGraph, END
except ImportError:
    StateGraph = None
    END = "__end__"

from .config import get_settings
from .graph_state import (
    RagGraphState, TargetEntity, PatternType,
    SubStepEvent, StepStatus, SubStepAction, SubStepDetail,
    FALLBACK_LABEL, ContextHarnessProfile,
    QualityGradeVerdict, HybridQueryReformulationResult,
    LivingInspectorEvent,
)
from .nodes.router_node import intent_router_node
from .nodes.search_node import search_single_target
from .nodes.rerank_node import reranker_node
from .nodes.quality_grade_node import evaluate_search_quality, quality_grade_node
from .nodes.reformulation_node import hybrid_reformulate_query, reformulation_node
from .nodes.deep_recall_node import deep_recall_node
from .nodes.context_node import context_builder_node
from .nodes.synthesis_node import synthesis_stream_node, get_token_stream
from .nodes.abstention_node import zero_search_abstention_node, should_abstain_zero_search
from .guardrail import ZERO_SEARCH_TEMPLATE, GroundednessSanitizer
from .anaphora_resolver import AnaphoraResolver
from .session import session_store
from .logger import get_logger, generate_trace_id, set_trace_id, get_trace_id, StepTimer

logger = get_logger("oliview.orchestrator")


class MultiTargetGraphOrchestrator:
    def __init__(self):
        self.settings = get_settings()
        self.anaphora_resolver = AnaphoraResolver()
        self.graph = self._build_and_compile_graph()

    def _build_and_compile_graph(self):
        if StateGraph is None:
            logger.warning("[MultiTargetGraphOrchestrator] LangGraph not installed; running in fallback mode.")
            return None

        workflow = StateGraph(RagGraphState)

        workflow.add_node("intent_router", intent_router_node)
        workflow.add_node("search_per_target", self._search_node_wrapper)
        workflow.add_node("reranker", reranker_node)
        workflow.add_node("quality_grade", quality_grade_node)
        workflow.add_node("reformulation", reformulation_node)
        workflow.add_node("deep_recall", deep_recall_node)
        workflow.add_node("context_builder", context_builder_node)
        workflow.add_node("synthesis_stream", synthesis_stream_node)

        workflow.set_entry_point("intent_router")
        workflow.add_edge("intent_router", "search_per_target")
        workflow.add_edge("search_per_target", "reranker")
        workflow.add_edge("reranker", "quality_grade")

        workflow.add_conditional_edges(
            "quality_grade",
            self.should_retry_search,
            {
                "RETRY_SEARCH": "reformulation",
                "PROCEED_TO_SYNTHESIS": "deep_recall",
                "FALLBACK": "deep_recall",
            }
        )

        workflow.add_edge("reformulation", "search_per_target")
        workflow.add_edge("deep_recall", "context_builder")
        workflow.add_edge("context_builder", "synthesis_stream")
        workflow.add_edge("synthesis_stream", END)

        try:
            return workflow.compile()
        except Exception as e:
            logger.error(f"Failed to compile LangGraph StateGraph: {e}")
            return None

    def _search_node_wrapper(self, state: RagGraphState) -> Dict[str, Any]:
        target_entities = state.get("target_entities", [])
        merged_pools = dict(state.get("search_pools", {}))
        merged_errors = dict(state.get("target_errors", {}))
        reformulation = state.get("reformulation_result")

        for idx, target in enumerate(target_entities):
            target_id = target.get("target_id", f"target_{idx}")
            query_to_use = state.get("query", "")
            if reformulation and reformulation.merged_queries:
                query_to_use = reformulation.merged_queries[min(idx + 1, len(reformulation.merged_queries) - 1)]

            search_state = {
                "trace_id": state.get("trace_id", "unknown"),
                "query": query_to_use,
                "normalized_query": state.get("normalized_query", ""),
                "current_target": target,
            }
            res = search_single_target(search_state)
            for tid, candidates in res.get("search_pools", {}).items():
                if tid not in merged_pools:
                    merged_pools[tid] = []
                existing_ids = {c["doc_id"] for c in merged_pools[tid]}
                for c in candidates:
                    if c["doc_id"] not in existing_ids:
                        merged_pools[tid].append(c)

        return {
            "search_pools": merged_pools,
            "target_errors": merged_errors,
        }

    def should_retry_search(self, state: RagGraphState) -> str:
        retry_count = state.get("retry_count", 0)
        verdict: Optional[QualityGradeVerdict] = state.get("quality_verdict")

        if retry_count < 1 and verdict and verdict.status == "RETRY_SEARCH":
            return "RETRY_SEARCH"
        return "PROCEED_TO_SYNTHESIS"

    def stream_rag(
        self,
        query: str,
        session_id: str = "",
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        tenant_id: str = "chata",
        queue_callback=None,
    ) -> Iterator[Dict[str, Any]]:
        trace_id = trace_id or generate_trace_id()
        set_trace_id(trace_id)
        pipeline_start = time.perf_counter()

        harness = self.settings.get_context_harness()
        is_anaphora = self.anaphora_resolver.is_anaphora_query(query)

        state: RagGraphState = {
            "trace_id": trace_id,
            "session_id": session_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "query": query,
            "normalized_query": "",
            "context_harness": harness,
            "pattern_type": "",
            "target_entities": [],
            "is_anaphora_detected": is_anaphora,
            "recalled_turn_payload": None,
            "search_pools": {},
            "reranked_contexts": {},
            "quality_verdict": None,
            "retry_count": 0,
            "reformulation_result": None,
            "context_text": "",
            "canary_token": "",
            "is_fallback": False,
            "fallback_reason": None,
            "target_errors": {},
            "is_cached": False,
            "l5_cache_key": "",
            "metrics": {},
            "error_log": [],
        }

        t_node = time.perf_counter()
        yield _make_living_step_event(
            trace_id, "INTENT_ANALYSIS", "1. 의도 및 대화 맥락 분석 중...",
            StepStatus.RUNNING, badge_text=f"{harness.tier_name} 모드 가동"
        )

        router_result = intent_router_node(state)
        state.update(router_result)

        target_entities = state.get("target_entities", [])
        elapsed_intent = (time.perf_counter() - t_node) * 1000.0

        yield _make_living_step_event(
            trace_id, "INTENT_ANALYSIS", f"1. 의도 분석 완료 ({len(target_entities)}개 제품)",
            StepStatus.COMPLETE, elapsed_ms=elapsed_intent,
            badge_text=f"타겟 {len(target_entities)}건 식별 (+{elapsed_intent/1000.0:.2f}s)"
        )

        t_node = time.perf_counter()
        yield _make_living_step_event(
            trace_id, "HYBRID_SEARCH", "2. 타겟별 하이브리드 검색 중...", StepStatus.RUNNING
        )

        merged_pools: Dict[str, list] = {}
        merged_errors: Dict[str, str] = {}

        for idx, target in enumerate(target_entities):
            target_name = target.get("target_name", "unknown")
            target_id = target.get("target_id", f"target_{idx}")

            search_state = {
                "trace_id": trace_id,
                "query": state.get("query", ""),
                "normalized_query": state.get("normalized_query", ""),
                "current_target": target,
            }
            search_result = search_single_target(search_state)
            for tid, candidates in search_result.get("search_pools", {}).items():
                merged_pools[tid] = candidates
            for tid, err in search_result.get("target_errors", {}).items():
                merged_errors[tid] = err

        state["search_pools"] = merged_pools
        state["target_errors"] = merged_errors
        total_found = sum(len(v) for v in merged_pools.values())
        elapsed_search = (time.perf_counter() - t_node) * 1000.0

        yield _make_living_step_event(
            trace_id, "HYBRID_SEARCH", f"2. 1차 검색 완료 (총 {total_found}건 수집)",
            StepStatus.COMPLETE, elapsed_ms=elapsed_search,
            badge_text=f"{total_found}건 후보 확보 (+{elapsed_search/1000.0:.2f}s)"
        )

        t_node = time.perf_counter()
        yield _make_living_step_event(
            trace_id, "RERANKING", "3. 타겟별 통합 리랭킹 중...", StepStatus.RUNNING
        )

        rerank_result = reranker_node(state)
        state.update(rerank_result)

        if state.get("is_fallback"):
            yield _make_fallback_event(trace_id, state.get("fallback_reason", ""))

        elapsed_rerank = (time.perf_counter() - t_node) * 1000.0
        total_selected = sum(len(v) for v in state.get("reranked_contexts", {}).values())

        yield _make_living_step_event(
            trace_id, "RERANKING", f"3. 통합 리랭킹 완료 ({total_selected}건 선별)",
            StepStatus.COMPLETE, elapsed_ms=elapsed_rerank,
            badge_text=f"쿼터 {total_selected}건 선별 (+{elapsed_rerank/1000.0:.2f}s)"
        )

        verdict = evaluate_search_quality(state.get("reranked_contexts", {}), min_threshold=0.35)
        state["quality_verdict"] = verdict

        if self.should_retry_search(state) == "RETRY_SEARCH":
            t_branch = time.perf_counter()
            yield _make_living_step_event(
                trace_id, "QUERY_REFORMULATION", "↳ 🔄 하이브리드 재검색 중 (사전 동의어 + Fast LLM 문맥 쿼리)",
                StepStatus.RUNNING, is_branch=True, parent_node_id="RERANKING",
                badge_text=f"품질 보완 (평균 {verdict.average_score:.2f} 미달)"
            )

            reform_res = hybrid_reformulate_query(query, [t.get("target_name", "") for t in target_entities])
            state["retry_count"] = 1
            state["reformulation_result"] = reform_res

            search_update = self._search_node_wrapper(state)
            state.update(search_update)
            rerank_update = reranker_node(state)
            state.update(rerank_update)

            elapsed_branch = (time.perf_counter() - t_branch) * 1000.0
            new_total = sum(len(v) for v in state.get("reranked_contexts", {}).values())

            yield _make_living_step_event(
                trace_id, "QUERY_REFORMULATION", f"↳ ✓ 2차 보량 검색 완료 (총 {new_total}건 확보)",
                StepStatus.COMPLETE, is_branch=True, parent_node_id="RERANKING",
                elapsed_ms=elapsed_branch, badge_text=f"재검색 성공 (+{elapsed_branch/1000.0:.2f}s)"
            )

        if is_anaphora and session_id:
            t_recall = time.perf_counter()
            yield _make_living_step_event(
                trace_id, "DEEP_RECALL", "↳ 🧠 과거 대화 심층 회상 중 (Redis L4 원본 복원)",
                StepStatus.RUNNING, is_branch=True, parent_node_id="INTENT_ANALYSIS"
            )

            for turn_idx in range(30, 0, -1):
                payload = session_store.get_turn_payload(session_id, turn_idx)
                if payload:
                    state["recalled_turn_payload"] = payload
                    elapsed_recall = (time.perf_counter() - t_recall) * 1000.0
                    yield _make_living_step_event(
                        trace_id, "DEEP_RECALL", f"↳ ✓ 과거 대화 심층 회상 완료 (Turn {turn_idx} 원본 복원)",
                        StepStatus.COMPLETE, is_branch=True, parent_node_id="INTENT_ANALYSIS",
                        elapsed_ms=elapsed_recall, badge_text=f"Turn {turn_idx} 복원 (+{elapsed_recall:.1f}ms)"
                    )
                    break

        # Feature 039 / Spec 039: 2026 CRAG Fast-Path Zero-Search Hard Block
        final_selected = sum(len(v) for v in state.get("reranked_contexts", {}).values())
        if final_selected == 0:
            abstain_update = zero_search_abstention_node(state)
            state.update(abstain_update)

            total_ms = (time.perf_counter() - pipeline_start) * 1000
            total_sec = round(total_ms / 1000.0, 2)

            yield _make_living_step_event(
                trace_id, "ABSTENTION", "4. 검색 결과 0건 즉시 안내 (Fast Abstention)", StepStatus.COMPLETE,
                elapsed_ms=total_ms, badge_text=f"0건 부재 고지 (+{total_sec}s)"
            )

            for line in ZERO_SEARCH_TEMPLATE.split("\n"):
                yield {
                    "trace_id": trace_id,
                    "event_type": "token",
                    "token": line + "\n",
                    "timestamp": time.time(),
                }

            yield {
                "trace_id": trace_id,
                "event_type": "complete",
                "metrics": state.get("metrics", {}),
                "total_latency_sec": total_sec,
                "is_cached": False,
                "context_tier": harness.tier_name,
                "l5_cache_key": "",
                "selected_review_count": 0,
                "reference_reviews": [],
                "is_fallback": False,
                "target_count": len(target_entities),
                "retry_count": state.get("retry_count", 0),
                "suggested_chips": state.get("zero_search_verdict", {}).get("suggested_chips", ["스킨케어", "쿠션", "인기 앰플"]),
                "timestamp": time.time(),
            }
            return

        context_result = context_builder_node(state)
        state.update(context_result)

        yield _make_living_step_event(
            trace_id, "LLM_SYNTHESIS", "4. 실시간 마크다운 답변 생성 중...", StepStatus.RUNNING,
            badge_text=f"토큰 스트리밍 (16K/32K {harness.tier_name})"
        )

        for token in get_token_stream(state, queue_callback=queue_callback):
            yield {
                "trace_id": trace_id,
                "event_type": "token",
                "token": token,
                "timestamp": time.time(),
            }

        ref_reviews = []
        for target_id, reviews in state.get("reranked_contexts", {}).items():
            for idx, r in enumerate(reviews, start=1):
                p_name = r.get("product_name") or r.get("target_name") or target_id
                b_name = r.get("brand_name") or (p_name.split()[0] if p_name else "")
                c_name = r.get("category") or "화장품"
                attr_name = r.get("attribute_name") or ""
                r_text = r.get("review_text", "")
                clean_t = r_text
                if clean_t.startswith("[") and "]" in clean_t:
                    clean_t = clean_t.split("]", 1)[1].strip()
                p_url = r.get("product_url") or f"https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query={urllib.parse.quote(p_name)}"

                ref_reviews.append({
                    "rank": len(ref_reviews) + 1,
                    "product_name": p_name,
                    "brand_name": b_name,
                    "category": c_name,
                    "attribute_name": attr_name,
                    "review_score": r.get("rating", 5.0),
                    "separated_sentence": clean_t,
                    "clean_text": clean_t,
                    "rerank_score": round(r.get("rerank_score", 0.0), 4),
                    "clean_product_name": p_name,
                    "product_url": p_url,
                    "oliveyoung_search_url": p_url,
                })

        total_ms = (time.perf_counter() - pipeline_start) * 1000
        total_sec = round(total_ms / 1000.0, 2)
        is_cached = state.get("is_cached", False)
        state["metrics"]["total_latency_ms"] = total_ms
        state["metrics"]["is_cached"] = is_cached

        synthesis_label = "4. 답변 생성 완료 (L5 캐시 ⚡)" if is_cached else "4. 답변 생성 완료"
        yield _make_living_step_event(
            trace_id, "LLM_SYNTHESIS", synthesis_label, StepStatus.COMPLETE,
            elapsed_ms=total_ms, badge_text=f"총 {total_sec}s 완료"
        )

        yield {
            "trace_id": trace_id,
            "event_type": "complete",
            "metrics": state.get("metrics", {}),
            "total_latency_sec": total_sec,
            "is_cached": is_cached,
            "context_tier": harness.tier_name,
            "l5_cache_key": state.get("l5_cache_key", ""),
            "selected_review_count": len(ref_reviews),
            "reference_reviews": ref_reviews,
            "is_fallback": state.get("is_fallback", False),
            "target_count": len(target_entities),
            "retry_count": state.get("retry_count", 0),
            "timestamp": time.time(),
        }

    async def astream_rag(
        self,
        query: str,
        session_id: str = "",
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        tenant_id: str = "chata",
        queue_callback=None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        for event in self.stream_rag(query, session_id, user_id, trace_id, tenant_id, queue_callback):
            yield event


def _make_living_step_event(
    trace_id: str,
    node_id: str,
    title: str,
    status: StepStatus,
    elapsed_ms: float = 0.0,
    badge_text: Optional[str] = None,
    is_branch: bool = False,
    parent_node_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "trace_id": trace_id,
        "event_type": "step_update",
        "step_id": node_id,
        "step_name": title,
        "node_id": node_id,
        "parent_node_id": parent_node_id,
        "title": title,
        "status": status.value if isinstance(status, StepStatus) else status,
        "is_branch": is_branch,
        "elapsed_ms": round(elapsed_ms, 1),
        "badge_text": badge_text,
        "timestamp": time.time(),
    }


def _make_fallback_event(trace_id: str, reason: str) -> Dict[str, Any]:
    return {
        "trace_id": trace_id,
        "event_type": "fallback_alert",
        "step_id": "RERANKING",
        "fallback_info": {
            "triggered": True,
            "label": FALLBACK_LABEL,
            "reason": reason,
        },
        "timestamp": time.time(),
    }


graph_orchestrator = MultiTargetGraphOrchestrator()
