"""
StreamlitGraphAdapter (Spec 030 FR-017).
LangGraph의 비동기 astream_events를 Streamlit 스레드 안전 동기 제너레이터로 래핑.
"""

import threading
from typing import Generator, Optional, Any, Dict

from oliview_core.graph_orchestrator import MultiTargetGraphOrchestrator
from oliview_core.graph_state import FALLBACK_LABEL
from oliview_core.logger import get_logger

logger = get_logger("oliview.adapter.streamlit")


class StreamlitGraphAdapter:
    """
    Streamlit 메인 스레드에서 LangGraph RAG 파이프라인을 안전하게 실행하는 어댑터.

    Streamlit은 단일 스레드 재실행(rerun) 모델이므로,
    비동기 LangGraph 이벤트를 동기식으로 소비해야 합니다.
    이 어댑터는 stream_rag의 이벤트를 순회하며
    UI 상태 컨테이너를 실시간으로 갱신합니다.
    """

    @staticmethod
    def run_sync_stream(
        orchestrator: MultiTargetGraphOrchestrator,
        query: str,
        session_id: str,
        status_container: Any = None,
        substep_container: Any = None,
        meta_dict: Optional[Dict[str, Any]] = None,
    ) -> Generator[str, None, None]:
        """
        LangGraph RAG 파이프라인을 동기적으로 실행하며 토큰을 yield합니다.

        Args:
            orchestrator: MultiTargetGraphOrchestrator 인스턴스
            query: 사용자 질의
            session_id: 세션 ID
            status_container: st.status() 컨테이너 (실시간 상태 갱신)
            substep_container: st.container() 컨테이너 (서브스텝 렌더링)
            meta_dict: 파이프라인 메타데이터(참조 리뷰, 레이턴시 등)를 저장할 딕셔너리

        Yields:
            str — 생성된 토큰 스트림 (st.write_stream에 전달 가능)
        """
        is_fallback = False
        step_labels = {
            "INTENT": "🔍 1. 의도 분석",
            "SEARCH": "📚 2. 타겟별 하이브리드 검색",
            "RERANK": "🏆 3. 통합 리랭킹",
            "SYNTHESIS": "✍️ 4. 답변 생성",
        }

        def _on_queue_status(status_dict: Dict[str, Any]):
            if status_container:
                try:
                    pos = status_dict.get("queue_position", 0)
                    wait_sec = status_dict.get("estimated_wait_sec", 0)
                    if pos > 0:
                        status_container.update(
                            label=f"⏳ GPU 자원 대기 중 (순번 {pos}번, 약 {wait_sec:.0f}초 예상)",
                            state="running",
                        )
                    else:
                        status_container.update(
                            label="✍️ 4. 답변 생성 중... ⏳",
                            state="running",
                        )
                except Exception:
                    pass

        for event in orchestrator.stream_rag(
            query=query,
            session_id=session_id,
            tenant_id="chata",
            queue_callback=_on_queue_status,
        ):
            event_type = event.get("event_type", "")

            # Spec 031 FR-005: GPU 큐 대기 상태 실시간 렌더링
            if event_type == "queue_waiting":
                if status_container:
                    try:
                        pos = event.get("queue_position", 0)
                        wait_sec = event.get("estimated_wait_sec", 0)
                        status_container.update(
                            label=f"⏳ GPU 대기 중 (순번 {pos}번, 약 {wait_sec:.0f}초 예상)",
                            state="running",
                        )
                    except Exception:
                        pass
                continue

            if event_type == "step_update":
                step_id = event.get("step_id", "")
                step_name = event.get("step_name", "")
                status = event.get("status", "")

                # 상위 스텝 상태 갱신
                if status_container:
                    try:
                        label = step_labels.get(step_id, step_name)
                        if status == "running":
                            status_container.update(label=f"{label} ⏳", state="running")
                        elif status == "complete":
                            status_container.update(label=f"{label} ✅", state="complete")
                    except Exception:
                        pass

                # 서브스텝 렌더링
                sub_step = event.get("sub_step")
                if sub_step and substep_container:
                    try:
                        action = sub_step.get("action", "")
                        target_name = sub_step.get("target_name", "")
                        idx = sub_step.get("target_index", 0)
                        total = sub_step.get("total_targets", 0)
                        count = sub_step.get("count", 0)

                        if action == "SEARCHING":
                            substep_container.write(
                                f"  `[{idx}/{total}]` {target_name} 검색 중... 🔄"
                            )
                        elif action == "SEARCH_DONE":
                            substep_container.write(
                                f"  `[{idx}/{total}]` {target_name} 검색 완료 ({count}건) ✅"
                            )
                        elif action == "ERROR_SKIPPED":
                            substep_container.write(
                                f"  `[{idx}/{total}]` {target_name} ⚠️ (정상 타겟으로 진행)"
                            )
                    except Exception:
                        pass

            elif event_type == "fallback_alert":
                is_fallback = True
                if substep_container:
                    try:
                        fallback_info = event.get("fallback_info", {})
                        label = fallback_info.get("label", FALLBACK_LABEL)
                        substep_container.warning(label)
                    except Exception:
                        pass

            elif event_type == "token":
                token = event.get("token", "")
                if token:
                    yield token

            elif event_type == "complete":
                metrics = event.get("metrics", {})
                total_ms = metrics.get("total_latency_ms", 0)
                ref_reviews = event.get("reference_reviews", [])
                if meta_dict is not None:
                    meta_dict["total_latency_sec"] = total_ms / 1000.0
                    meta_dict["selected_review_count"] = len(ref_reviews)
                    meta_dict["reference_reviews"] = ref_reviews
                    meta_dict["is_fallback"] = event.get("is_fallback", False)

                if status_container:
                    try:
                        cnt_str = f", {len(ref_reviews)}건 선별" if ref_reviews else ""
                        status_container.update(
                            label=f"✅ 분석 완료 ({total_ms/1000:.1f}초{cnt_str})",
                            state="complete",
                            expanded=False,
                        )
                    except Exception:
                        pass
