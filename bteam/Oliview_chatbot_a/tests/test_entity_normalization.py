"""Unit Tests for Hybrid Cascaded Entity Normalizer (Spec 037 US1)."""
import unittest
import sys
import os

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from oliview_core.utils.entity_normalizer import HybridEntityNormalizer
from oliview_core.models.citation_models import QueryIntentEnum


class TestEntityNormalization(unittest.TestCase):

    def setUp(self):
        self.normalizer = HybridEntityNormalizer()

    def test_single_product_normalization(self):
        res = self.normalizer.normalize("컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘")

        self.assertIsNotNone(res.extracted_product)
        self.assertIn("컬러그램", res.extracted_product)
        self.assertIn("꿀로스", res.extracted_product)
        self.assertIn("발림성", res.extracted_aspects)
        self.assertIn("장단점", res.extracted_aspects)
        self.assertEqual(res.intent, QueryIntentEnum.SINGLE_TARGET)
        self.assertFalse(res.is_discovery)

    def test_attribute_collision_normalization(self):
        res = self.normalizer.normalize("닥터자르트 시카페어 진정 크림의 진정 장단점 알려줘")

        self.assertIsNotNone(res.extracted_product)
        self.assertIn("닥터자르트", res.extracted_product)
        self.assertIn("진정", res.extracted_aspects)
        self.assertEqual(res.intent, QueryIntentEnum.SINGLE_TARGET)

    def test_category_discovery_normalization(self):
        res = self.normalizer.normalize("민감성 피부라 트러블 안나고 순한 쿠션팩트 추천해줘")

        self.assertEqual(res.extracted_category, "쿠션팩트")
        self.assertTrue("트러블" in res.extracted_aspects or "순함" in res.extracted_aspects)
        self.assertTrue(res.is_discovery)
        self.assertEqual(res.intent, QueryIntentEnum.FEATURE_DISCOVERY)

    def test_short_target_name_generation(self):
        res = self.normalizer.normalize("롬앤 쥬시 래스팅 틴트 지속력 어때?")

        self.assertIsNotNone(res.short_target_name)
        self.assertIn("롬앤", res.short_target_name)
        self.assertIn("지속력", res.extracted_aspects)


if __name__ == "__main__":
    unittest.main()
