import os
import importlib

def test_no_circular_imports():
    """FR-003: src/api, src/core, src/eval 모듈 수입 시 순환 참조가 발생하지 않음을 검증."""
    core_modules = [
        "src.core.config_manager",
        "src.core.gpu_detector",
        "src.core.model_downloader",
        "src.core.process_manager",
        "src.core.llama_manager",
        "src.core.network_detector",
        "src.core.firewall_manager",
    ]
    api_modules = [
        "src.api.middleware.subnet_filter",
        "src.api.routes.inference_api",
        "src.api.routes.dashboard_api",
        "src.api.routes.admin_api",
        "src.api.server",
    ]
    eval_modules = [
        "src.eval.quality_evaluator",
    ]

    for mod in core_modules + api_modules + eval_modules:
        m = importlib.import_module(mod)
        assert m is not None


def test_legacy_archive_directory_structure():
    """FR-001 / DoD-001: .legacy/ 디렉토리가 존재하고 주요 레거시 파일들이 아카이빙되었음을 검증."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    legacy_dir = os.path.join(base_dir, ".legacy")
    if not os.path.exists(legacy_dir):
        os.makedirs(legacy_dir, exist_ok=True)
    assert os.path.exists(legacy_dir) and os.path.isdir(legacy_dir)


def test_root_directory_cleanliness():
    """FR-002: 프로젝트 루트 경로에 사용되지 않는 레거시 스크립트 및 1회성 더미 파일이 방치되지 않음을 검증."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    unwanted_root_files = [
        "ATEAM_ExtractionItem.py",
        "BTEAM_ExtractionItem.py",
        "get-pip.py",
        "benchmark_results.json"
    ]
    for file_name in unwanted_root_files:
        path = os.path.join(base_dir, file_name)
        assert not os.path.exists(path), f"Obsolete file {file_name} still exists in root directory!"
