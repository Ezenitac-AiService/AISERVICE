from __future__ import annotations

import os
from http.server import ThreadingHTTPServer

from oliview_core.http_compat import build_handler

from oliview_core.config import Settings

Handler = build_handler("chatbot_b")


def main() -> None:
    Settings.from_env(dict(os.environ)).validate_data_plane()
    ThreadingHTTPServer(
        ("0.0.0.0", int(os.getenv("PORT", "8002"))), Handler
    ).serve_forever()


if __name__ == "__main__":
    main()
