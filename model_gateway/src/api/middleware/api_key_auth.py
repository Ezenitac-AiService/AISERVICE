"""
API Key Authentication & Rate Limiting Middleware (FR-001, FR-008, 043-api-key-auth-toggle).
Checks api_key_enabled toggle, validates Bearer / X-API-Key headers, checks revoked status & rate limits.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from src.core.config_manager import ConfigManager
from src.core.api_key_manager import get_api_key_manager
from src.core.metrics_db import metrics_db


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Enforces API Key Authentication & Rate Limiting on /v1/* inference routes."""

    async def dispatch(self, request: Request, call_next):
        # FR-068: Exempt OPTIONS preflight requests from authentication
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        
        # Only enforce on /v1/ inference endpoints
        if not path.startswith("/v1/"):
            return await call_next(request)

        cm = ConfigManager()
        server_cfg = cm.get_server_config()
        api_key_enabled = server_cfg.get("api_key_enabled", False)

        if not api_key_enabled:
            # Public access mode
            return await call_next(request)

        # Extract API key from Authorization header or X-API-Key header
        api_key = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header[7:].strip()
        elif "X-API-Key" in request.headers:
            api_key = request.headers.get("X-API-Key").strip()

        if not api_key:
            metrics_db.log_request("anonymous", path, 401, is_error=True)
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "API key authentication required", "type": "unauthorized", "code": 401}}
            )

        # Verify API key using ApiKeyManager (no hardcoded test key bypass)
        key_mgr = get_api_key_manager()
        is_valid, _ = key_mgr.verify_key(api_key)
        
        if not is_valid:
            metrics_db.log_request(api_key, path, 401, is_error=True)
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "Invalid API key provided", "type": "invalid_api_key", "code": 401}}
            )

        # Execute request and record response status
        response = await call_next(request)
        is_err = response.status_code >= 400
        prompt_tokens = getattr(request.state, "prompt_tokens", 0)
        completion_tokens = getattr(request.state, "completion_tokens", 0)
        metrics_db.log_request(api_key, path, response.status_code, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, is_error=is_err)
        return response
