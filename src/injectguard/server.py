from __future__ import annotations

from typing import Any

from injectguard import ContainerType, detect_container, scan


def create_app() -> Any:
    """Create the optional FastAPI app.

    FastAPI is an optional dependency so importing ``injectguard.server`` does
    not require it. Install with ``pip install injectguard[server]``.
    """

    try:
        from fastapi import FastAPI
        from pydantic import BaseModel, Field
    except Exception as exc:  # pragma: no cover - exercised without server extra.
        raise RuntimeError("Install injectguard[server] to use the FastAPI service.") from exc

    class ScanRequest(BaseModel):
        content: str = Field(..., min_length=0)
        container: ContainerType | None = None
        source: str | None = None

    app = FastAPI(title="injectguard", version="0.1.0")

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
