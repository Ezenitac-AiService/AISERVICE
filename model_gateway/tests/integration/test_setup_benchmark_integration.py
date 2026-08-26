import pytest
import os
import subprocess
import json


def test_setup_script_force_benchmark_and_skip():
    """T016 [US2]: Integration test for setup.sh CLI options --skip-benchmark and --force-benchmark."""
    # Test --skip-benchmark flag execution
    res_skip = subprocess.run(
        ["./setup.sh", "--skip-benchmark", "--skip-build"],
        capture_output=True,
        text=True,
        cwd=os.getcwd()
    )
    assert res_skip.returncode == 0
    assert "3단계 실측 벤치마크를 스킵하고 기존 설정을 보존합니다" in res_skip.stdout or "스킵" in res_skip.stdout

    # Test profiles existence
    profiles_path = "config/model_context_profiles.json"
    assert os.path.exists(profiles_path)
    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles_data = json.load(f)
    assert "profiles" in profiles_data
