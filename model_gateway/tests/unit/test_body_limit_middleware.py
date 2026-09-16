import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Request
from src.api.middleware.body_limit import RequestBodyLimitMiddleware

@pytest.mark.asyncio
async def test_body_limit_content_length_exceeded():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=100)

    @app.post("/test")
    async def post_test(request: Request):
        data = await request.body()
        return {"size": len(data)}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Under limit -> 200
        resp_ok = await client.post("/test", content=b"a" * 50)
        assert resp_ok.status_code == 200

        # 2. Over limit via Content-Length -> 413
        resp_413 = await client.post("/test", content=b"a" * 150)
        assert resp_413.status_code == 413
        assert resp_413.json()["error"]["code"] == "request_body_too_large"
