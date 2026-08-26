"""
Context Builder Node (Spec 030 / Spec 035 - 3-Tier Context Harness & Deep Recall).
제품 스펙 헤더 번들링, 16K/32K XML 샌드박스 주입, PreFlight 가드 및 On-Demand 회상 컨텍스트 조립기.
"""

import uuid
from typing import Dict, Any, List

from ..config import get_settings, compute_context_harness_profile
from ..graph_state import RagGraphState, RerankedReview, TargetEntity, FALLBACK_LABEL, ContextHarnessProfile
from ..guardrail import escape_review_xml, PreFlightContextGuard
from ..logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.node.context")


def context_builder_node(state: RagGraphState) -> Dict[str, Any]:
    trace_id = state.get("trace_id", get_trace_id())
    reranked_contexts = state.get("reranked_contexts", {})
    target_entities = state.get("target_entities", [])
    is_fallback = state.get("is_fallback", False)
    recalled_turn = state.get("recalled_turn_payload")
    settings = get_settings()

    harness: ContextHarnessProfile = state.get("context_harness") or settings.get_context_harness()

    with StepTimer("CONTEXT_BUILD", trace_id=trace_id):
        canary_token = f"CANARY_{uuid.uuid4().hex[:8].upper()}"
        entity_map = {e["target_id"]: e for e in target_entities}

        context_parts: List[str] = []
        context_parts.append(f'<context canary="{canary_token}" tier="{harness.tier_name}">')

        if recalled_turn:
            context_parts.append(f'  <recalled_context turn="{recalled_turn.turn_index}">')
            context_parts.append(f'    <user_query>{escape_review_xml(recalled_turn.user_query)}</user_query>')
            context_parts.append(f'    <assistant_response>{escape_review_xml(recalled_turn.assistant_response)}</assistant_response>')
            if recalled_turn.reference_specs:
                context_parts.append('    <specs>')
                for s in recalled_turn.reference_specs:
                    context_parts.append(f'      <spec_item>{escape_review_xml(str(s))}</spec_item>')
                context_parts.append('    </specs>')
            context_parts.append('  </recalled_context>')

        for target_id, reviews in reranked_contexts.items():
            entity = entity_map.get(target_id, {})
            target_name = entity.get("target_name", target_id)
            spec_header = entity.get("spec_header") or {}

            context_parts.append(f'  <target id="{target_id}" name="{escape_review_xml(target_name)}">')

            if spec_header:
                context_parts.append("    <spec>")
                if spec_header.get("price"):
                    context_parts.append(f"      <price>{spec_header['price']}원</price>")
                if spec_header.get("volume"):
                    context_parts.append(f"      <volume>{escape_review_xml(spec_header['volume'])}</volume>")
                if spec_header.get("key_ingredients"):
                    context_parts.append(f"      <ingredients>{escape_review_xml(spec_header['key_ingredients'])}</ingredients>")
                if spec_header.get("skin_type"):
                    context_parts.append(f"      <skin_type>{escape_review_xml(spec_header['skin_type'])}</skin_type>")
                context_parts.append("    </spec>")

            context_parts.append("    <reviews>")
            token_budget = harness.tokens_per_target
            used_tokens = 0

            for review in reviews:
                review_text = review.get("review_text", "")
                estimated_tokens = int(len(review_text) * 1.45)

                if used_tokens + estimated_tokens > token_budget:
                    remaining = token_budget - used_tokens
                    char_limit = int(remaining / 1.45)
                    if char_limit > 50:
                        review_text = review_text[:char_limit] + "..."
                    else:
                        break

                escaped_text = escape_review_xml(review_text)
                score = review.get("rerank_score", 0.0)
                rank = review.get("rank", 0)
                context_parts.append(
                    f'      <review rank="{rank}" score="{score:.3f}">'
                    f'{escaped_text}'
                    f'</review>'
                )
                used_tokens += estimated_tokens

            context_parts.append("    </reviews>")
            context_parts.append("  </target>")

        if is_fallback:
            fallback_reason = state.get("fallback_reason", "리랭커 타임아웃")
            context_parts.append(
                f'  <fallback_notice>{FALLBACK_LABEL} ({escape_review_xml(fallback_reason)})</fallback_notice>'
            )

        context_parts.append("</context>")
        raw_context_text = "\n".join(context_parts)

        sanitized_context, was_truncated = PreFlightContextGuard.validate_and_truncate(
            raw_context_text,
            total_n_ctx=harness.total_n_ctx,
            max_output_tokens=harness.max_output_tokens,
        )

        logger.info(
            f"[{trace_id}] 컨텍스트 조립 완료 ({harness.tier_name}): {len(sanitized_context)}자 "
            f"(타겟 {len(reranked_contexts)}개, 잘림={'Y' if was_truncated else 'N'})"
        )

        return {
            "context_text": sanitized_context,
            "canary_token": canary_token,
            "context_harness": harness,
        }
