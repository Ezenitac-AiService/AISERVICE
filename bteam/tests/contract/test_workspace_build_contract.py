import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_exact_uv_members_and_frontend_boundary():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["uv"]["workspace"]["members"] == [
        "packages/core",
        "pipelines",
        "services/dashboard_backend",
        "services/chatbot_a",
        "services/chatbot_b",
    ]
    assert (ROOT / "uv.lock").exists()
    assert (ROOT / "services" / "dashboard_frontend" / "package-lock.json").exists()


def test_dockerignore_excludes_operational_payloads():
    content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (
        "*.sql",
        "*.sqlite3",
        "chroma_db_oliview/",
        "models/",
        "node_modules/",
    ):
        assert pattern in content
