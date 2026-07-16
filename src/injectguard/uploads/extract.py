from __future__ import annotations

from injectguard.uploads.common import safe_filename, validated_extension
from injectguard.uploads.docx import extract_docx
from injectguard.uploads.errors import UploadScanError
from injectguard.uploads.html import extract_html
from injectguard.uploads.limits import UploadLimits
from injectguard.uploads.models import ExtractionResult
from injectguard.uploads.pdf import extract_pdf
from injectguard.uploads.structured import extract_csv, extract_json
from injectguard.uploads.text import extract_text


def extract_upload(
    data: bytes,
    filename: str | None,
    limits: UploadLimits,
) -> tuple[str, ExtractionResult]:
    display_name = safe_filename(filename)
    extension = validated_extension(display_name)
    if not data:
        raise UploadScanError("extraction_failed", "The uploaded file is empty.")
    if len(data) > limits.max_upload_bytes:
        raise UploadScanError(
            "file_too_large",
            f"The file exceeds the {limits.max_upload_bytes // (1024 * 1024)} MB upload limit.",
            413,
        )
    _validate_signature(extension, data)

    if extension == ".docx":
        result = extract_docx(data, display_name, limits)
    elif extension == ".pdf":
        result = extract_pdf(data, display_name, limits)
    elif extension in {".html", ".htm"}:
        result = extract_html(data, display_name, limits)
    elif extension == ".json":
        result = extract_json(data, display_name, limits)
    elif extension == ".csv":
        result = extract_csv(data, display_name, limits)
    else:
        result = extract_text(data, display_name, extension, limits)
    return display_name, result


def _validate_signature(extension: str, data: bytes) -> None:
    stripped = data.lstrip()
    is_pdf = stripped.startswith(b"%PDF-")
    is_zip = data.startswith(b"PK\x03\x04")
    if extension == ".pdf" and not is_pdf:
        raise UploadScanError(
            "unsupported_type", "The .pdf extension does not match the file.", 415
        )
    if extension == ".docx" and not is_zip:
        if data.startswith(b"\xd0\xcf\x11\xe0"):
            raise UploadScanError(
                "encrypted_document",
                "Legacy, encrypted, or password-protected Word files are not supported.",
            )
        raise UploadScanError(
            "unsupported_type", "The .docx extension does not match the file.", 415
        )
    if extension not in {".pdf", ".docx"} and (is_pdf or is_zip):
        raise UploadScanError(
            "unsupported_type", "The filename extension does not match the file.", 415
        )
