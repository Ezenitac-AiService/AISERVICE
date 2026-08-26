"""Unit tests for product series/line resolution and candidate expansion (Spec 038 US1)."""
import pytest
from unittest.mock import MagicMock, patch

from oliview_core.utils.entity_normalizer import HybridEntityNormalizer
from oliview_core.tools.search_tools import tool_search_series_candidates
from oliview_core.models.citation_models import QueryIntentEnum


@pytest.fixture
def mock_retriever_data():
    documents = [
        "헤라 센슈얼 누드 밤 보습감 너무 좋고 각질 안 부각돼요",
        "헤라 센슈얼 누드 글로스 광택감이 예쁘고 촉촉해요",
        "헤라 센슈얼 피팅 글로우 틴트 지속력이 우수합니다",
        "차앤박 프로폴리스 에너지 액티브 앰플 꿀광 피부 만들어줌",
        "차앤박 프로폴리스 에센셜 크림 보습막 형성",
        "롬앤 쥬시 래스팅 틴트 과즙 코팅립",
        "롬앤 쥬시 글래스 틴트 광택",
    ]
    metadatas = [
        {"product_name": "헤라 센슈얼 누드 밤", "brand_name": "헤라", "category": "립케어", "rating": 4.8},
        {"product_name": "헤라 센슈얼 누드 글로스", "brand_name": "헤라", "category": "립메이크업", "rating": 4.7},
        {"product_name": "헤라 센슈얼 피팅 글로우 틴트", "brand_name": "헤라", "category": "립틴트", "rating": 4.6},
        {"product_name": "차앤박 프로폴리스 에너지 액티브 앰플", "brand_name": "차앤박", "category": "앰플/세럼", "rating": 4.9},
        {"product_name": "차앤박 프로폴리스 에센셜 크림", "brand_name": "차앤박", "category": "크림", "rating": 4.7},
        {"product_name": "롬앤 쥬시 래스팅 틴트", "brand_name": "롬앤", "category": "립틴트", "rating": 4.8},
        {"product_name": "롬앤 쥬시 글래스 틴트", "brand_name": "롬앤", "category": "립틴트", "rating": 4.5},
    ]
    return documents, metadatas


def test_tool_search_series_candidates_hera(mock_retriever_data):
    docs, metas = mock_retriever_data
    with patch("oliview_core.tools.search_tools.get_retriever") as mock_get_ret:
        mock_retriever = MagicMock()
        mock_retriever.all_documents = docs
        mock_retriever.all_metadatas = metas
        mock_get_ret.return_value = mock_retriever

        candidates = tool_search_series_candidates(
            series_keyword="센슈얼",
            brand="헤라",
            limit=3,
        )

        assert len(candidates) >= 2
        product_names = [c["product_name"] for c in candidates]
        assert "헤라 센슈얼 누드 밤" in product_names
        assert "헤라 센슈얼 누드 글로스" in product_names


def test_tool_search_series_candidates_cnp(mock_retriever_data):
    docs, metas = mock_retriever_data
    with patch("oliview_core.tools.search_tools.get_retriever") as mock_get_ret:
        mock_retriever = MagicMock()
        mock_retriever.all_documents = docs
        mock_retriever.all_metadatas = metas
        mock_get_ret.return_value = mock_retriever

        candidates = tool_search_series_candidates(
            series_keyword="프로폴리스",
            brand="차앤박",
            limit=3,
        )

        assert len(candidates) >= 2
        product_names = [c["product_name"] for c in candidates]
        assert any("프로폴리스" in name for name in product_names)


def test_hybrid_entity_normalizer_series_query(mock_retriever_data):
    docs, metas = mock_retriever_data
    with patch("oliview_core.tools.search_tools.get_retriever") as mock_get_ret:
        mock_retriever = MagicMock()
        mock_retriever.all_documents = docs
        mock_retriever.all_metadatas = metas
        mock_get_ret.return_value = mock_retriever

        normalizer = HybridEntityNormalizer()
        result = normalizer.normalize("헤라 센슈얼 립 촉촉함과 각질부각 분석해줘")

        assert result.extracted_brand == "헤라"
        assert "촉촉함" in result.extracted_aspects
        assert "각질부각" in result.extracted_aspects
        assert result.is_series_query is True
        assert result.series_keyword == "센슈얼"
        assert len(result.series_candidates) >= 2
