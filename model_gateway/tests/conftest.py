"""Conftest for model_gateway tests."""
from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parents[3]
_aiservice_root = _repo_root / "AISERVICE"
_model_gw_root = _aiservice_root / "model_gateway"

for p in [str(_repo_root), str(_aiservice_root), str(_model_gw_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)
