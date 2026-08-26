"""FastAPI Web Server for Oliview ChatA (Spec 038).

Supports Server-Sent Events (SSE) streaming (/api/v1/chat/stream),
Static HTML/CSS/JS frontend serving, and direct integration with MultiTargetGraphOrchestrator.
"""
import os
import json
import logging
from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from oliview_core.models.series_models import ChatStreamRequest, ChatStreamEvent
from oliview_core.graph_orchestrator import MultiTargetGraphOrchestrator
from oliview_core.logger import get_logger, generate_trace_id

logger = get_logger("oliview.fastapi")

app = FastAPI(
    title="Oliview ChatA FastAPI Web Service",
    description="Olive Young Beauty Review Analysis Agent with LangGraph & SSE Streaming",
    version="2.0.0",
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 경로 설정
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)

# 정적 파일 서빙 마운트
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 오케스트레이터 인스턴스
orchestrator = MultiTargetGraphOrchestrator()


@app.get("/", response_class=HTMLResponse)
async def read_index():
    """데스크탑/모바일 반응형 웹 메인 페이지 서빙."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Oliview ChatA FastAPI Web Service</h1><p>Static UI initializing...</p>")


@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트."""
    return {"status": "ok", "app": "Oliview ChatA FastAPI", "version": "2.0.0"}


async def sse_event_generator(req: ChatStreamRequest, trace_id: str) -> AsyncGenerator[str, None]:
    """LangGraph 파이프라인 출력을 표준 SSE 포맷으로 스트리밍 변환."""
    try:
        query = req.query.strip()
        session_id = req.session_id or f"sess_{trace_id}"

        # 1. 의도 분석 시작 이벤트
        init_event = {
            "event_type": "step_update",
            "step_id": "INTENT",
            "step_name": "🔍 1. 의도 분석 및 라인명 매칭",
            "status": "running",
            "trace_id": trace_id,
        }
        yield f"event: step_update\ndata: {json.dumps(init_event, ensure_ascii=False)}\n\n"

        # 2. 오케스트레이터 스트림 실행
        for event in orchestrator.stream_rag(
            query=query,
            session_id=session_id,
            trace_id=trace_id,
            tenant_id="chata",
        ):
            event_type = event.get("event_type", "step_update")
            event_data_json = json.dumps(event, ensure_ascii=False)
            yield f"event: {event_type}\ndata: {event_data_json}\n\n"

    except Exception as e:
        logger.error(f"[{trace_id}] SSE stream generation error: {e}", exc_info=True)
        error_event = {
            "event_type": "error",
            "error_message": str(e),
            "trace_id": trace_id,
        }
        yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"


@app.post("/api/v1/chat/stream")
async def stream_chat(req: ChatStreamRequest, request: Request):
    """FastAPI SSE 실시간 채팅 스트리밍 엔드포인트."""
    trace_id = generate_trace_id()
    logger.info(f"[{trace_id}] /api/v1/chat/stream incoming query: {req.query}")

    return StreamingResponse(
        sse_event_generator(req, trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Trace-Id": trace_id,
        },
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8501))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
