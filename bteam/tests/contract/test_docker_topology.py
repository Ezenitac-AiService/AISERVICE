from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_green_is_parallel_multi_container_topology():
    green = (ROOT / "docker-compose.green.yml").read_text(encoding="utf-8")
    blue = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for service in (
        "pipeline_runner:",
        "dashboard_backend:",
        "dashboard_frontend:",
        "chatbot_a:",
        "chatbot_b:",
    ):
        assert service in green
    assert "name: bteam-green" in green
    assert "container_name:" not in green
    assert "127.0.0.1:15050:5050" in green
    assert "container_name:" in blue


def test_green_does_not_reuse_blue_operational_volume_names():
    green = (ROOT / "docker-compose.green.yml").read_text(encoding="utf-8")
    assert "bteam_mysql_data" not in green
    assert "aiservice-network" not in green
