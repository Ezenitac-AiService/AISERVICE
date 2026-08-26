"""
On-Demand Deep Recall Node (Spec 035 FR-006 / T019).
비명시적 대명사 질의 시 Redis L4 세션 스토어에서 과거 특정 턴의 원본 페이로드를 온디맨드로 역조회합니다.
"""

import time
import logging
from typing import Optional
from ..graph_state import RagGraphState, DeepRecallTurnPayload
from ..session import session_store

logger = logging.getLogger("oliview.rag.deep_recall")


async def deep_recall_node(state: RagGraphState) -> RagGraphState:
    trace_id = state.get("trace_id", "unknown")
    session_id = state.get("session_id", "")
    is_anaphora = state.get("is_anaphora_detected", False)
    recalled_payload: Optional[DeepRecallTurnPayload] = None

    if is_anaphora and session_id:
        t0 = time.time()
        for turn_idx in range(30, 0, -1):
            payload = session_store.get_turn_payload(session_id, turn_idx)
            if payload:
                recalled_payload = payload
                elapsed_ms = (time.time() - t0) * 1000.0
                logger.info(
                    f"[{trace_id}] [DeepRecallNode] Successfully recalled Turn {turn_idx} from Redis L4 in {elapsed_ms:.2f}ms"
                )
                break

    return {
        **state,
        "recalled_turn_payload": recalled_payload,
    }
