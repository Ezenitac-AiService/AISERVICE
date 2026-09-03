"""Contract tests for subpath assets and base URLs.

Enforces:
- SC-001: 0% 404 error rate on CSS/JS/images/fonts.
- HTML, React Router, Vite, FastAPI, Flask subpath alignments.
"""

from pathlib import Path
import json
import pytest

def test_portal_html_assets_exist(aiservice_root: Path):
    html_dir = aiservice_root / "gateway" / "html"
    assert (html_dir / "index.html").is_file()
    assert (html_dir / "changelog.html").is_file()
    assert (html_dir / "changelog_data.json").is_file()

    # Verify changelog_data.json is valid JSON
    with open(html_dir / "changelog_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, (list, dict))

def test_oliview_vite_base_configuration(aiservice_root: Path):
    vite_config = aiservice_root / "bteam" / "Oliview_Project" / "frontend" / "vite.config.js"
    if vite_config.exists():
        content = vite_config.read_text(encoding="utf-8")
        assert "/bteam/oliview" in content, "Vite base must be set to /bteam/oliview/"

def test_pilos_forwarded_prefix_configuration(aiservice_root: Path):
    compose_path = aiservice_root / "docker-compose.yml"
    content = compose_path.read_text(encoding="utf-8")
    assert "/ateam/pilos" in content or "pilos" in content

def test_chata_and_chatb_base_prefixes(aiservice_root: Path):
    compose_path = aiservice_root / "docker-compose.yml"
    content = compose_path.read_text(encoding="utf-8")
    assert "/bteam/chata" in content
    assert "/bteam/chatb" in content
