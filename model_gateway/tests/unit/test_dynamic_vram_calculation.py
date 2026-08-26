import pytest
import os
from src.core.process_manager import ProcessManager, poll_server_health

def test_calculate_dynamic_base_vram_mb(tmp_path):
    dummy_gguf = tmp_path / "test_model.gguf"
    # Create 2GB dummy file
    size_2gb = 2 * 1024 * 1024 * 1024
    dummy_gguf.write_bytes(b"\x00" * 1000)
    
    # Calculate base VRAM with 2.0GB size
    base_vram = ProcessManager.calculate_base_vram_mb(str(dummy_gguf), file_size_bytes=size_2gb)
    # Expected: 2048 MB * 1.15 = 2355.2 -> 2355 MB
    assert base_vram == 2355

def test_calculate_dynamic_polling_timeout():
    # 500MB model -> 15s (min bound)
    t1 = ProcessManager.calculate_polling_timeout(500)
    assert t1 == 15.0

    # 5000MB model -> 10 + 5000/500 = 20.0s
    t2 = ProcessManager.calculate_polling_timeout(5000)
    assert t2 == 20.0

    # 15000MB model -> 30s (max bound)
    t3 = ProcessManager.calculate_polling_timeout(15000)
    assert t3 == 30.0
