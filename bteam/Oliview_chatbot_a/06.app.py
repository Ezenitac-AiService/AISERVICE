"""
Backward-compatibility Shim for Legacy 06.app.py Entrypoint (Spec 016 / Spec 039).
Delegates execution directly to app.py.
"""
import runpy
from pathlib import Path

_APP_PATH = Path(__file__).resolve().parent / "app.py"
runpy.run_path(str(_APP_PATH), run_name="__main__")
