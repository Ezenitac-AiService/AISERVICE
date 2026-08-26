"""
Main FastAPI server entrypoint delegating to create_app() (FR-001, FR-002, FR-008).
Provides backward compatibility and unified entrypoint binding for uvicorn and test runners.
"""

from src.api.server import create_app, app

__all__ = ["create_app", "app"]

if __name__ == "__main__":
    import uvicorn
    from src.core.config_manager import ConfigManager

    cm = ConfigManager()
    server_cfg = cm.get_server_config()
    port = server_cfg.get("port", 8081)
    host = server_cfg.get("host", "0.0.0.0")
    uvicorn.run("src.api.main:app", host=host, port=port, reload=False)
