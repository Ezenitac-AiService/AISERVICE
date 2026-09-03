"""Common pytest fixtures for AISERVICE integration and contract tests.

Adheres to SDD specifications and Constitution principles:
- Principle II: TDD & strict contract validation
- Principle IV: Observability & secret masking
- Principle VII: Infrastructure SSOT & Zero hardcoding
"""

from pathlib import Path
import sys
import json
import pytest

_repo_root = Path(__file__).resolve().parent.parent.parent
_aiservice_root = Path(__file__).resolve().parent.parent
for p in [str(_repo_root), str(_aiservice_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the root path of the tunnel repository."""
    return Path(__file__).resolve().parent.parent.parent

@pytest.fixture(scope="session")
def aiservice_root() -> Path:
    """Return the root path of AISERVICE."""
    return Path(__file__).resolve().parent.parent

@pytest.fixture(scope="session")
def specs_dir(repo_root) -> Path:
    """Return the active feature spec directory."""
    return repo_root / "specs" / "001-aiservice-platform-migration"

@pytest.fixture(scope="session")
def contracts_dir(specs_dir) -> Path:
    """Return the contracts directory for the feature."""
    return specs_dir / "contracts"

@pytest.fixture(scope="session")
def dist_client_dir(repo_root) -> Path:
    """Return the dist_client_a directory."""
    return repo_root / "dist_client_a"

@pytest.fixture
def assert_no_secrets():
    """Helper fixture to assert that text content contains no raw secret tokens or private keys."""
    forbidden_tokens = [
        "348a9b698d47c11b5a559616edc22d905b95c4fab59391bb",
        "BEGIN OPENSSH PRIVATE KEY",
        "BEGIN RSA PRIVATE KEY",
        "BEGIN EC PRIVATE KEY",
    ]
    def _checker(text: str):
        if not text:
            return
        for token in forbidden_tokens:
            assert token not in text, f"Security violation: found secret string in content: {token[:10]}..."
    return _checker
