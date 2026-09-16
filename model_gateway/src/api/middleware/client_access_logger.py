"""
Client Access & Audit Logging FastAPI Middleware.
Intercepts requests, assigns X-Request-ID, checks API keys, records access & error logs.
"""

import sys
import time
import uuid
import datetime
import traceback
from typing import Callable, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from src.core.client_logger import get_client_logger, AccessLogEntry, ErrorLogEntry
from src.core.api_key_manager import get_api_key_manager


class ClientAccessLogMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware for auditing client requests and assignment of X-Request-ID."""

    def log_error(
        self,
        client_ip: str,
        request_id: str,
        endpoint: str,
        status_code: int,
        detail: str,
        exc: Optional[Exception] = None,
        masked_api_key: Optional[str] = None
    ) -> None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tb_str = None
        if exc is not None:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        elif sys.exc_info()[0] is not None:
            tb_str = traceback.format_exc()

        logger = get_client_logger()
        logger.log_error(ErrorLogEntry(
            timestamp=timestamp,
            request_id=request_id,
            client_ip=client_ip,
            path=endpoint,
            status_code=status_code,
            exception_type=type(exc).__name__ if exc else f"HTTP_{status_code}",
            error_detail=detail,
            masked_api_key=masked_api_key,
            traceback_summary=tb_str
        ))

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        request_id = f"req-{uuid.uuid4().hex[:8]}"
        request.state.request_id = request_id

        # Extract Client IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host
        else:
            client_ip = "unknown"

        user_agent = request.headers.get("User-Agent")
        openai_user = request.headers.get("X-Client-ID") or request.headers.get("X-User-ID")
        model_name = request.query_params.get("model") or request.headers.get("X-Model")

        # Extract Bearer Token or X-API-Key for masked logging
        auth_header = request.headers.get("Authorization", "")
        raw_api_key = None
        if auth_header.startswith("Bearer "):
            raw_api_key = auth_header[7:].strip()
        elif "X-API-Key" in request.headers:
            raw_api_key = request.headers.get("X-API-Key", "").strip()

        # Mask API Key for audit logging (auth enforcement delegated to APIKeyAuthMiddleware)
        key_mgr = get_api_key_manager()
        _, masked_key = key_mgr.verify_key(raw_api_key)
        path = request.url.path

        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            status_code = 500
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            self.log_error(
                client_ip=client_ip,
                request_id=request_id,
                endpoint=path,
                status_code=500,
                detail=str(exc),
                exc=exc,
                masked_api_key=masked_key
            )

            resp = JSONResponse(
                status_code=500,
                content={"detail": f"Internal Server Error: {str(exc)}"}
            )
            resp.headers["X-Request-ID"] = request_id
            return resp

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Attach X-Request-ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log Access
        logger = get_client_logger()
        logger.log_access(AccessLogEntry(
            timestamp=timestamp,
            client_ip=client_ip,
            request_id=request_id,
            method=request.method,
            path=path,
            status_code=status_code,
            latency_ms=latency_ms,
            model=model_name,
            openai_user=openai_user,
            masked_api_key=masked_key,
            user_agent=user_agent
        ))

        # Log Error if 4xx or 5xx
        if status_code >= 400:
            self.log_error(
                client_ip=client_ip,
                request_id=request_id,
                endpoint=path,
                status_code=status_code,
                detail=f"Response status {status_code}",
                masked_api_key=masked_key
            )

        return response

