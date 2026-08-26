import unittest

from pilos.service.knowledge_cache import (
    SERVICE_KNOWLEDGE_CACHE,
    get_cached_service_knowledge,
    is_cached_service_block,
)


class KnowledgeCacheTest(unittest.TestCase):
    def test_all_15_service_blocks_are_cached(self):
        expected_blocks = {
            "service_overview",
            "service_research_target",
            "service_models",
            "service_positive_model",
            "service_negative_model",
            "service_model_difference",
            "service_score_calculation",
            "service_interpretation",
            "service_columns",
            "service_cautions",
            "column_model_date",
            "column_text_score",
            "column_comment_count",
            "column_supply_index",
            "column_buy_volume",
            "column_sell_volume",
        }

        self.assertEqual(
            expected_blocks.issubset(set(SERVICE_KNOWLEDGE_CACHE.keys())),
            True,
            f"누락된 캐시 블록: {expected_blocks - set(SERVICE_KNOWLEDGE_CACHE.keys())}",
        )

    def test_cached_entry_has_valid_structure(self):
        for block_key in (
            "service_overview",
            "service_interpretation",
            "service_models",
            "column_supply_index",
        ):
            with self.subTest(block_key=block_key):
                entry = get_cached_service_knowledge(block_key)
                self.assertIsNotNone(entry)
                self.assertEqual(entry["status"], "ready")
                self.assertEqual(entry["route"], "service_knowledge")
                self.assertTrue(len(entry["answer"].strip()) > 0)
                self.assertTrue(len(entry["sources"]) >= 1)
                self.assertEqual(entry["sources"][0]["type"], "service_document")
                self.assertEqual(entry["sources"][0]["label"], "PILOS 서비스 문서")
                self.assertEqual(entry["sources"][0]["version"], "1.0")

    def test_is_cached_service_block_helper(self):
        self.assertTrue(is_cached_service_block("service_overview"))
        self.assertTrue(is_cached_service_block("column_buy_volume"))
        self.assertFalse(is_cached_service_block("stock_summary"))
        self.assertFalse(is_cached_service_block("unknown_key"))


if __name__ == "__main__":
    unittest.main()
