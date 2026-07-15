from __future__ import annotations

from pathlib import Path
from typing import Any

from injectguard import ContainerType, detect_container, scan


def create_app() -> Any:
    """Create the optional FastAPI app.

    FastAPI is an optional dependency so importing ``injectguard.server`` does
    not require it. Install with ``pip install injectguard[server]``.
    """

    try:
        from fastapi import FastAPI
        from fastapi.responses import FileResponse
        from pydantic import BaseModel, Field
    except Exception as exc:  # pragma: no cover - exercised without server extra.
        raise RuntimeError("Install injectguard[server] to use the FastAPI service.") from exc

    class ScanRequest(BaseModel):
        content: str = Field(..., min_length=0)
        container: ContainerType | None = None
        source: str | None = None

    web_root = Path(__file__).with_name("web")
    app = FastAPI(
        title="injectguard",
        version="0.1.0",
        description="Offline prompt-injection detection for machine-shaped containers.",
    )
    @app.get("/", include_in_schema=False)
    def web_interface() -> FileResponse:
        return FileResponse(web_root / "index.html")

    @app.get("/styles.css", include_in_schema=False)
    def web_styles() -> FileResponse:
        return FileResponse(web_root / "styles.css", media_type="text/css")

    @app.get("/app.js", include_in_schema=False)
    def web_script() -> FileResponse:
        return FileResponse(web_root / "app.js", media_type="text/javascript")

    @app.post("/scan")
    def scan_endpoint(request: ScanRequest) -> dict[str, Any]:
        container = request.container or detect_container(request.source, request.content)
        return scan(
            request.content,
            container=container,
            source=request.source,
        ).to_dict()

    return app


try:
    app = create_app()
except RuntimeError:
    app = None
