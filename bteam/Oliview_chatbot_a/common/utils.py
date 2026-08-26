"""
공통 유틸리티 함수

- BGE-M3 임베딩 모델 실행 장치 선택
- 폴더 안전 삭제
"""

import os
import shutil
import torch


def get_bge_m3_device() -> str:
    """
    BGE-M3 임베딩 모델이 사용할 장치를 반환합니다.

    Returns
    -------
    str
        "cuda" : NVIDIA GPU 사용
        "cpu"  : CPU 사용
    """

    if torch.cuda.is_available():
        print("[INFO] CUDA GPU 사용")
        return "cuda"

    print("[INFO] CPU 사용")
    return "cpu"


def safe_remove_directory(directory: str) -> bool:
    """
    폴더가 존재하면 안전하게 삭제합니다.

    Parameters
    ----------
    directory : str
        삭제할 폴더 경로

    Returns
    -------
    bool
        True  : 삭제 성공
        False : 폴더가 없거나 삭제 실패
    """

    if not os.path.exists(directory):
        return False

    try:
        shutil.rmtree(directory)
        print(f"[INFO] 기존 폴더 삭제 완료: {directory}")
        return True

    except Exception as e:
        print(f"[ERROR] 폴더 삭제 실패: {e}")
        return False