import os
import sys
import importlib.util
import pytest

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
script_file = os.path.join(repo_root, "scripts", "benchmark_quality.py")

spec = importlib.util.spec_from_file_location("benchmark_quality", script_file)
benchmark_quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark_quality)


def test_qwen_benchmark_catalog_integration():
    """T011 / US2: Test benchmark runner catalog integration."""
    catalog = benchmark_quality.get_models_catalog_from_config()
    assert len(catalog) >= 6
    model_ids = [m["model_id"] for m in catalog]
    assert "qwen3.5-4b" in model_ids
    assert "gemma4-e4b" in model_ids
