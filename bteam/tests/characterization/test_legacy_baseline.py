from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_legacy_projects_and_blue_compose_are_present():
    expected = {
        "Oliview_Project",
        "Oliview_aspect_sentence_split",
        "Oliview_aspect_sentiment",
        "Oliview_LLM",
        "Oliview_chatbot_a",
        "Oliview_chatbot_b",
        "oliview_core",
    }
    assert expected.issubset({item.name for item in ROOT.iterdir()})
    assert (ROOT / "docker-compose.yml").exists()


def test_blue_routes_remain_characterized():
    nginx = (ROOT.parent / "gateway" / "nginx.conf").read_text(encoding="utf-8")
    for route in (
        "/bteam/oliview/api/",
        "/bteam/oliview/",
        "/bteam/chata/",
        "/bteam/chatb/",
    ):
        assert route in nginx
