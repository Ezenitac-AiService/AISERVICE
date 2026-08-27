from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from oliview_core.chat import ChatEngine
from oliview_core.db.connection import create_mysql_engine, session_scope
from sqlalchemy.exc import SQLAlchemyError

from oliview_core.config import Settings

from .report_api import load_report_db, load_report_file

_DATABASE_ENGINE = None
_SEARCH_ENGINE: Any = None


def _get_search_engine() -> ChatEngine:
    global _SEARCH_ENGINE
    if _SEARCH_ENGINE is None:
        _SEARCH_ENGINE = ChatEngine()
    return _SEARCH_ENGINE


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        payload: dict[str, object]
        if path in {"", "/healthz", "/bteam/oliview/api/health"}:
            payload = {
                "status": "ok",
                "service": "dashboard_backend",
                "deployment_stage": os.getenv("DEPLOYMENT_STAGE", "VALIDATION"),
            }
            self.send_response(200)
        elif path.startswith("/bteam/oliview/api/reports/"):
            try:
                report_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                report_id = -1
            loaded = None
            database_error: SQLAlchemyError | None = None
            if report_id > 0 and _DATABASE_ENGINE is not None:
                try:
                    with session_scope(_DATABASE_ENGINE) as session:
                        loaded = load_report_db(session, report_id)
                except SQLAlchemyError as error:  # pragma: no cover
                    database_error = error
            elif report_id > 0:
                loaded = load_report_file(
                    os.getenv("REPORT_DATA_DIR", "reports"), report_id
                )
            if database_error is not None:
                payload = {"error": "report_store_unavailable"}
                self.send_response(503)
                loaded = None
            elif loaded is None:
                payload = {"error": "report_not_found", "report_id": str(report_id)}
                self.send_response(404)
            else:
                payload = {str(key): value for key, value in loaded.items()}
                self.send_response(200)
        else:
            payload = {"error": "not_found"}
            self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        if path != "/bteam/oliview/api/search":
            self._send_json(404, {"error": "not_found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "invalid_content_length"})
            return
        if content_length <= 0 or content_length > 1_048_576:
            self._send_json(413, {"error": "request_body_too_large_or_empty"})
            return
        try:
            raw_payload = json.loads(self.rfile.read(content_length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid_json"})
            return
        if not isinstance(raw_payload, dict):
            self._send_json(400, {"error": "request_body_must_be_object"})
            return
        try:
            payload = _get_search_engine().respond(
                raw_payload, service="dashboard_backend"
            )
        except (TypeError, ValueError):
            self._send_json(400, {"error": "invalid_search_request"})
            return
        except Exception:  # noqa: BLE001 - search must fail closed without internals
            self._send_json(503, {"error": "search_unavailable"})
            return
        self._send_json(200, payload)

    def log_message(self, *_args: object) -> None:
        return


def main() -> None:
    global _DATABASE_ENGINE
    Settings.from_env(dict(os.environ)).validate_data_plane()
    if os.getenv("MYSQL_USER") and os.getenv("MYSQL_PASSWORD"):
        _DATABASE_ENGINE = create_mysql_engine()
    ThreadingHTTPServer(
        ("0.0.0.0", int(os.getenv("PORT", "5050"))), Handler
    ).serve_forever()


if __name__ == "__main__":
    main()
