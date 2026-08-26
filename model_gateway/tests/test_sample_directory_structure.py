"""
Unit and integration test for verifying the sample directory structure (091-unify-sample-directories).
Ensures primary physical directory 'sample/' exists with 22 enhanced sample scripts,
and deprecated 'samples' symlink/directory is removed.
"""
import os
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIMARY_SAMPLE_DIR = os.path.join(REPO_ROOT, "sample")
DEPRECATED_SAMPLES_PATH = os.path.join(REPO_ROOT, "samples")


def test_primary_sample_directory_exists():
    """Verify that sample/ exists as a real physical directory."""
    assert os.path.exists(PRIMARY_SAMPLE_DIR), "sample/ physical directory must exist"
    assert os.path.isdir(PRIMARY_SAMPLE_DIR), "sample/ must be a directory"
    assert not os.path.islink(PRIMARY_SAMPLE_DIR), "sample/ must be a physical directory, not a symlink"


def test_deprecated_samples_path_removed():
    """Verify that the deprecated samples symlink/directory is removed."""
    assert not os.path.islink(DEPRECATED_SAMPLES_PATH), "samples symlink must be removed"
    assert not os.path.exists(DEPRECATED_SAMPLES_PATH), "samples path must not exist"


def test_sample_files_completeness():
    """Verify that all 22 sample scripts and required configuration files exist in sample/."""
    expected_files = [
        "common.py",
        "config.json",
        "pyproject.toml",
        "README.md",
    ]
    # 11 sample_XX scripts and 11 openai_XX scripts
    for i in range(1, 12):
        expected_files.append(f"sample_{i:02d}_*.py")
        expected_files.append(f"openai_{i:02d}_*.py")

    files_in_sample = os.listdir(PRIMARY_SAMPLE_DIR)
    
    assert "common.py" in files_in_sample
    assert "config.json" in files_in_sample

    sample_scripts = [f for f in files_in_sample if f.startswith("sample_") and f.endswith(".py")]
    openai_scripts = [f for f in files_in_sample if f.startswith("openai_") and f.endswith(".py")]

    assert len(sample_scripts) == 11, f"Expected 11 sample_XX scripts, found {len(sample_scripts)}"
    assert len(openai_scripts) == 11, f"Expected 11 openai_XX scripts, found {len(openai_scripts)}"
