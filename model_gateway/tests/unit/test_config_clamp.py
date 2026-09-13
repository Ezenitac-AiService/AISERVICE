import json
import unittest
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
MODEL_CONFIG_FILE = CONFIG_DIR / "model_config.json"
SERVER_CONFIG_FILE = CONFIG_DIR / "server_config.json"


class TestConfigClamp(unittest.TestCase):
    def test_model_config_context_clamp_and_presets(self):
        """Assert current_n_ctx is clamped <= 16384 and 9B/12B presets are removed."""
        self.assertTrue(MODEL_CONFIG_FILE.exists(), f"Missing {MODEL_CONFIG_FILE}")
        with open(MODEL_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Context clamp
        self.assertLessEqual(
            data.get("current_n_ctx", 0),
            16384,
            f"model_config.json current_n_ctx {data.get('current_n_ctx')} exceeds 16384",
        )

        # Presets clamp
        presets = data.get("available_presets", [])
        self.assertNotIn("gemma4-12b", presets, "gemma4-12b preset must be removed")
        self.assertNotIn("qwen3.5-9b", presets, "qwen3.5-9b preset must be removed")

    def test_server_config_hardware_tier_and_vram_limit(self):
        """Assert server_config.json enforces ampere_sm86 and vram_limit_mb == 10240."""
        self.assertTrue(SERVER_CONFIG_FILE.exists(), f"Missing {SERVER_CONFIG_FILE}")
        with open(SERVER_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(
            data.get("vram_limit_mb"),
            10240,
            f"vram_limit_mb must be 10240 for RTX 3060 12GB (got {data.get('vram_limit_mb')})",
        )

        tier = data.get("hardware_profiling", {}).get("fallback_hardware_tier")
        self.assertEqual(
            tier,
            "ampere_sm86",
            f"fallback_hardware_tier must be ampere_sm86 (got {tier})",
        )

        self.assertLessEqual(
            data.get("current_n_ctx", 0),
            16384,
            f"server_config.json current_n_ctx {data.get('current_n_ctx')} exceeds 16384",
        )


if __name__ == "__main__":
    unittest.main()
