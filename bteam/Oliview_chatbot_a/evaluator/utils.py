import os
import gc
import time
import shutil
import torch

def get_bge_m3_device() -> str:
    """
    가용 하드웨어 가속기(CUDA, MPS)를 감지하여 디바이스 명을 반환합니다.
    단, 저사양 VRAM (2.0GB 이하) 환경에서는 OOM 방지를 위해 CPU 구동으로 강제 폴백합니다.
    """
    if torch.cuda.is_available():
        try:
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            if vram_gb <= 2.0:  # 2GB 이하는 CPU 강제 폴백 (저사양 VRAM 방어)
                return "cpu"
            return "cuda"
        except Exception:
            return "cpu"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def remove_readonly(func, path, excinfo):
    """Windows 파일 권한 해제 헬퍼"""
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)

def safe_remove_directory(dir_path: str, max_retries: int = 5, delay: float = 0.5) -> bool:
    """
    Windows 환경에서 SQLite 파일 잠금 및 권한 문제(PermissionError/OSError 5)를 안전하게 다루기 위해
    가비지 컬렉션을 재실행하고 chmod 해제 핸들러와 함께 리셋을 시도합니다.
    """
    gc.collect()
    for _ in range(max_retries):
        if not os.path.exists(dir_path):
            return True
        try:
            shutil.rmtree(dir_path, onerror=remove_readonly)
            return True
        except (PermissionError, OSError):
            time.sleep(delay)
            gc.collect()
        except Exception:
            pass
    return not os.path.exists(dir_path)
