"""Unit tests for pure-python binary scanner scripts/verify_wheel_binary.py."""

import os
import sys
import tempfile
import zipfile
import pytest

from scripts.verify_wheel_binary import verify_wheel, scan_so_with_python_bytes


def create_mock_wheel(tmp_path, so_contents: bytes, has_cuda_so: bool = True) -> str:
    """Creates a temporary .whl file containing mock .so files."""
    wheel_path = os.path.join(str(tmp_path), "test_package-0.1.0-py3-none-linux_x86_64.whl")
    with zipfile.ZipFile(wheel_path, "w") as z:
        z.writestr("test_pkg/libggml-cpu.so", so_contents)
        if has_cuda_so:
            z.writestr("test_pkg/libggml-cuda.so", b"dummy cuda content without avx")
    return wheel_path


def test_verify_wheel_non_existent():
    is_valid, counts, cuda_enabled, msg = verify_wheel("/path/does/not/exist.whl")
    assert not is_valid
    assert not cuda_enabled
    assert "not found" in msg.lower()


def test_verify_wheel_valid(tmp_path):
    # Pure SSE4.2 / x86-64 code without VEX prefix bytes (0xC5 / 0xC4)
    safe_so_content = b"\x48\x89\xe5\x48\x83\xec\x10\xb8\x01\x00\x00\x00\xc3"
    whl_path = create_mock_wheel(tmp_path, safe_so_content, has_cuda_so=True)
    is_valid, counts, cuda_enabled, msg = verify_wheel(whl_path)
    assert is_valid
    assert cuda_enabled
    assert "verified valid" in msg.lower()


def test_verify_wheel_invalid_avx(tmp_path):
    # Simulated VEX prefix bytes (0xC5, 0xC4) in .so
    avx_so_content = b"\x48\x89\xe5\xc5\xf8\x10\x05\x00\xc4\xe2\x7d\x18\xc3"
    whl_path = create_mock_wheel(tmp_path, avx_so_content, has_cuda_so=True)
    is_valid, counts, cuda_enabled, msg = verify_wheel(whl_path)
    assert not is_valid
    assert "invalid" in msg.lower()


def test_scan_so_with_python_bytes():
    # Content with 2 VEX opcodes
    data = b"\x90\xc5\xf8\x10\x05\x90\xc4\xe2\x7d\x18\x90"
    with tempfile.NamedTemporaryFile("wb", delete=False) as f:
        f.write(data)
        temp_file = f.name

    try:
        count = scan_so_with_python_bytes(temp_file)
        assert count >= 1
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)


# --- Edge case tests (T011) ---


def test_verify_wheel_corrupted_zip(tmp_path):
    """Corrupted ZIP file should return invalid with descriptive error."""
    corrupted_whl = os.path.join(str(tmp_path), "corrupted-0.1.0-py3-none-linux_x86_64.whl")
    with open(corrupted_whl, "wb") as f:
        f.write(b"this is not a zip file at all")
    is_valid, counts, cuda_enabled, msg = verify_wheel(corrupted_whl)
    assert not is_valid
    assert not cuda_enabled
    assert "failed" in msg.lower() or "not found" in msg.lower()


def test_verify_wheel_no_so_files(tmp_path):
    """Wheel with no .so files should return invalid."""
    whl_path = os.path.join(str(tmp_path), "noso-0.1.0-py3-none-linux_x86_64.whl")
    with zipfile.ZipFile(whl_path, "w") as z:
        z.writestr("pkg/__init__.py", "# empty package")
    is_valid, counts, cuda_enabled, msg = verify_wheel(whl_path)
    assert not is_valid
    assert "no shared libraries" in msg.lower()


def test_verify_wheel_missing_cuda_so(tmp_path):
    """Wheel with .so files but no cuda .so should return invalid (cuda_enabled=False)."""
    safe_content = b"\x48\x89\xe5\x48\x83\xec\x10\xb8\x01\x00\x00\x00\xc3"
    whl_path = create_mock_wheel(tmp_path, safe_content, has_cuda_so=False)
    is_valid, counts, cuda_enabled, msg = verify_wheel(whl_path)
    assert not is_valid
    assert not cuda_enabled


def test_verify_wheel_empty_so(tmp_path):
    """Wheel with an empty .so file should still complete scan without error."""
    whl_path = os.path.join(str(tmp_path), "emptyso-0.1.0-py3-none-linux_x86_64.whl")
    with zipfile.ZipFile(whl_path, "w") as z:
        z.writestr("pkg/libggml-cpu.so", b"")
        z.writestr("pkg/libggml-cuda.so", b"")
    is_valid, counts, cuda_enabled, msg = verify_wheel(whl_path)
    # Empty .so files have 0 AVX instructions and cuda detected by name
    assert is_valid
    assert cuda_enabled

