"""
모델 다운로더 스크립트.
ConfigManager 및 ModelDownloader를 사용하여 Hugging Face 모델을 순차적으로 다운로드합니다.
"""
import os
import sys

# Add the project root to the python path so we can import src.core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.model_downloader import ModelDownloader


def download_models():
    """ConfigManager 명세를 바탕으로 ModelDownloader를 사용하여 모든 지원 모델을 다운로드합니다."""
    downloader = ModelDownloader()
    print(f"Downloading models using ModelDownloader to {downloader.base_dir}...")
    results = downloader.download_all_models()
    for model_id, task in results.items():
        status_str = task.status.value if hasattr(task.status, "value") else str(task.status)
        print(f"  [{model_id}] Status: {status_str} (Progress: {task.download_progress_pct}%)")
        if task.error_message:
            print(f"    Error: {task.error_message}")


if __name__ == "__main__":
    download_models()
