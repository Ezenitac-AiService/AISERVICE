"""
End-to-End Pipeline Integration Test.
"""

import sys
import os
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
bteam_dir = os.path.join(workspace_root, "bteam")
if bteam_dir not in sys.path:
    sys.path.insert(0, bteam_dir)

from oliview_core.pipeline import prepare_pipeline_stream
from oliview_core.callback import StepCallbackProtocol
from oliview_core.types import StepEvent


class TestCallback:
    def __init__(self):
        self.events = []

    def on_step(self, event: StepEvent):
        self.events.append(event)


def test_pipeline_e2e_execution():
    """Verify 2-stage pipeline execution, callback steps, and metadata."""
    cb = TestCallback()
    question = "차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘"

    t0 = time.time()
    token_gen, meta = prepare_pipeline_stream(question=question, callback=cb)
    retrieval_latency = time.time() - t0

    # 1. Verify 3 callback steps were triggered
    assert len(cb.events) >= 3, f"Expected >= 3 step events, got {len(cb.events)}"
    assert any(e.step.value == "INTENT_ANALYSIS" for e in cb.events)
    assert any(e.step.value == "HYBRID_SEARCH" for e in cb.events)
    assert any(e.step.value == "RERANKING" for e in cb.events)

    # 2. Verify metadata
    assert meta.selected_review_count > 0
    assert len(meta.reference_reviews) > 0
    print(f"[TEST PASS] Retrieval Latency: {retrieval_latency:.3f}s, Selected Reviews: {meta.selected_review_count}")

    # 3. Verify token stream consumption
    first_few_tokens = []
    for i, token in enumerate(token_gen):
        first_few_tokens.append(token)
        if i >= 5:
            break
    assert len(first_few_tokens) > 0
    print(f"[TEST PASS] First Tokens: {''.join(first_few_tokens)}")


if __name__ == "__main__":
    test_pipeline_e2e_execution()
    print("All Pipeline E2E Integration tests passed successfully!")
