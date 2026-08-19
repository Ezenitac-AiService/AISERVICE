"""
Unit tests for oliview_core package imports and schema validation.
"""

import sys
import os
import unittest

try:
    import pytest
except ImportError:
    pytest = None

# Ensure bteam is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
bteam_dir = os.path.join(workspace_root, "bteam")
if bteam_dir not in sys.path:
    sys.path.insert(0, bteam_dir)


def test_core_package_import():
    """Verify that oliview_core imports smoothly without importlib dynamic loaders."""
    import oliview_core
    assert hasattr(oliview_core, "__version__")
    assert oliview_core.__version__ == "1.0.0"


def test_schema_models():
    """Verify Pydantic and Dataclass schemas."""
    from oliview_core.types import StepCode, StepEvent, ReferenceReview, RagExecutionMetadata

    event = StepEvent(step=StepCode.INTENT_ANALYSIS, label="의도 분석 중", elapsed_sec=0.05)
    assert event.step == StepCode.INTENT_ANALYSIS
    assert event.elapsed_sec == 0.05

    review = ReferenceReview(
        review_id=123,
        product_name="차앤박 프로폴리스 앰플",
        product_url="https://www.oliveyoung.co.kr",
        clean_text="수분감이 아주 좋습니다.",
    )
    assert review.review_id == 123
    assert review.sentiment == "NEUTRAL"

    meta = RagExecutionMetadata(
        total_latency_sec=0.35,
        selected_review_count=5,
        reference_reviews=[review],
    )
    assert meta.total_latency_sec == 0.35
    assert len(meta.reference_reviews) == 1


def test_config_loader():
    """Verify CoreSettings loads default configuration."""
    from oliview_core.config import get_settings
    settings = get_settings()
    assert settings.main_port == 8081
    assert settings.embed_port == 8090
    assert settings.rerank_port == 8091
    assert "8081/v1" in settings.llm_endpoint


if __name__ == "__main__":
    test_core_package_import()
    test_schema_models()
    test_config_loader()
    print("All oliview_core import unit tests passed successfully!")
