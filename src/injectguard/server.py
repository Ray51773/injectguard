import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from injectguard import ContainerType, detect_container, scan
from injectguard.uploads import UploadScanError, scan_uploaded_file
from injectguard.uploads.limits import UploadLimits

logger = logging.getLogger("injectguard.server")


def create_app() -> Any:
    """Create the optional FastAPI app.

    FastAPI is an optional dependency so importing ``injectguard.server`` does
    not require it. Install with ``pip install injectguard[server]``.
    """

    try:
        from fastapi import Body, FastAPI, File, HTTPException, UploadFile
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse, JSONResponse, Response
    except Exception as exc:  # pragma: no cover - exercised without server extra.
        raise RuntimeError("Install injectguard[server] to use the FastAPI service.") from exc

    web_root = Path(__file__).with_name("web")
    app = FastAPI(
        title="injectguard",
        version="0.1.0",
        description="Offline prompt-injection detection for machine-shaped containers.",
    )

    allowed_origins = [
        origin.strip()
        for origin in os.environ.get("INJECTGUARD_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    def error_response(error: UploadScanError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
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

    @app.get("/config.js", include_in_schema=False)
    def web_config() -> Response:
        configured_base = os.environ.get("INJECTGUARD_PUBLIC_API_BASE_URL", "")
        body = (
            "window.INJECTGUARD_CONFIG = "
            + json.dumps({"apiBaseUrl": configured_base.rstrip("/")})
            + ";\n"
        )
        return Response(body, media_type="text/javascript")

    @app.get("/healthz", include_in_schema=False)
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/scan")
    def scan_endpoint(
        request: dict[str, Any] = Body(...),  # noqa: B008
    ) -> dict[str, Any]:
        content = request.get("content")
        source = request.get("source")
        requested_container = request.get("container")
        if not isinstance(content, str):
            raise HTTPException(status_code=422, detail="content must be a string")
        if source is not None and not isinstance(source, str):
            raise HTTPException(status_code=422, detail="source must be a string or null")
        try:
            container = (
                ContainerType(requested_container)
                if requested_container
                else detect_container(source, content)
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="container is not supported") from exc
        return scan(
            content,
            container=container,
            source=source,
        ).to_dict()

    @app.post("/api/scan-file")
    async def scan_file_endpoint(
        file: UploadFile = File(...),  # noqa: B008
    ) -> JSONResponse:
        try:
            limits = UploadLimits.from_environment()
            data = bytearray()
            while chunk := await file.read(1024 * 1024):
                data.extend(chunk)
                if len(data) > limits.max_upload_bytes:
                    error = UploadScanError(
                        "file_too_large",
                        "The file exceeds the "
                        f"{limits.max_upload_bytes // (1024 * 1024)} MB upload limit.",
                        413,
                    )
                    return error_response(error)
            try:
                timeout = float(os.environ.get("INJECTGUARD_SCAN_TIMEOUT_SECONDS", "45"))
                report = await asyncio.wait_for(
                    asyncio.to_thread(scan_uploaded_file, bytes(data), file.filename, limits),
                    timeout=timeout,
                )
            except TimeoutError:
                error = UploadScanError(
                    "timeout",
                    "The file scan exceeded the configured processing time.",
                    504,
                )
                logger.warning("file_scan_timeout", extra={"filename": file.filename})
                return error_response(error)
            except UploadScanError as exc:
                logger.info(
                    "file_scan_rejected",
                    extra={"filename": file.filename, "error_code": exc.code},
                )
                return error_response(exc)
            except Exception:
                logger.exception("file_scan_failed", extra={"filename": file.filename})
                error = UploadScanError(
                    "detector_failed", "The scanner could not complete this file.", 500
                )
                return error_response(error)
            logger.info(
                "file_scan_completed",
                extra={
                    "scan_id": report.scan_id,
                    "filename": report.filename,
                    "verdict": report.verdict,
                    "size_bytes": report.size_bytes,
                },
            )
            return JSONResponse(report.to_dict())
        except Exception:
            logger.exception("file_upload_failed", extra={"filename": file.filename})
            error = UploadScanError(
                "detector_failed", "The scanner could not read this upload.", 500
            )
            return error_response(error)
        finally:
            await file.close()

    return app


try:
    app = create_app()
except RuntimeError:
    app = None
