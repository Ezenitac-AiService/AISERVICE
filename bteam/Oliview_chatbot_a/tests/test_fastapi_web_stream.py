"""Integration tests for FastAPI SSE streaming endpoint and health checks (Spec 038 US3)."""
import pytest
import json
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from main import app


@pytest.mark.asyncio
async def test_health_check():
    """FastAPI 서버 헬스 체크 엔드포인트 검증."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "Oliview ChatA" in data["app"]


@pytest.mark.asyncio
async def test_root_index_html():
    """메인 HTML 서빙 검증."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_chat_stream_sse_endpoint():
    """FastAPI SSE 스트리밍 엔드포인트 이벤트 수신 검증."""
    mock_events = [
        {"event_type": "step_update", "step_id": "INTENT", "step_name": "🔍 1. 의도 분석", "status": "running"},
        {"event_type": "token", "token": "헤라 "},
        {"event_type": "token", "token": "센슈얼 "},
        {"event_type": "complete", "total_latency_sec": 1.2, "selected_review_count": 2, "reference_reviews": []},
    ]

    with patch("main.orchestrator.stream_rag", return_value=iter(mock_events)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "query": "헤라 센슈얼 립 촉촉함 분석해줘",
                "session_id": "test_sess_001",
                "category_hint": "립",
                "bypass_cache": True,
            }
            response = await ac.post("/api/v1/chat/stream", json=payload)
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            content = response.text
            assert "event: step_update" in content
            assert "event: token" in content
            assert "event: complete" in content
            assert "헤라 " in content


@pytest.mark.asyncio
async def test_chat_history_endpoint():
    """FastAPI Redis 세션 이력 조회 엔드포인트 검증."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/chat/history/test_sess_001")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test_sess_001"
        assert isinstance(data["messages"], list)


@pytest.mark.asyncio
async def test_chat_stream_error_handling():
    """FastAPI SSE 스트리밍 도중 예외 발생 시 error 이벤트 전송 검증."""
    with patch("main.orchestrator.stream_rag", side_effect=RuntimeError("GPU Reranker Offline")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "query": "오류 발생 테스트",
                "session_id": "test_err_sess",
            }
            response = await ac.post("/api/v1/chat/stream", json=payload)
            assert response.status_code == 200
            assert "event: error" in response.text
            assert "GPU Reranker Offline" in response.text

