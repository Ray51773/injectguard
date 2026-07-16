from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from injectguard.uploads.errors import UploadScanError
from injectguard.uploads.limits import UploadLimits

SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".html", ".htm", ".docx", ".pdf"}


def safe_filename(filename: str | None) -> str:
    name = Path(filename or "upload").name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return cleaned[:180] or "upload"


def validated_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UploadScanError(
            "unsupported_type",
            f"Unsupported file type. Supported extensions: {supported}.",
            415,
        )
    return extension


def decode_text(data: bytes) -> str:
    if b"\x00" in data:
        raise UploadScanError("unsupported_type", "The file does not contain plain text.", 415)
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            text = data.decode(encoding)
            controls = sum(
                ord(character) < 32 and character not in "\n\r\t\f" for character in text
            )
            if controls / max(1, len(text)) > 0.02:
                raise UploadScanError(
                    "unsupported_type", "The file does not contain plain text.", 415
                )
            return text
        except UnicodeDecodeError:
            continue
    raise UploadScanError("extraction_failed", "The text encoding could not be read.")


def validate_zip(data: bytes, limits: UploadLimits) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        entries = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise UploadScanError("extraction_failed", "The DOCX archive is invalid.") from exc

    if len(entries) > limits.max_archive_entries:
        archive.close()
        raise UploadScanError(
            "extraction_failed", "The document contains too many archive entries."
        )

    expanded = sum(entry.file_size for entry in entries)
    compressed = max(1, sum(entry.compress_size for entry in entries))
    if expanded > limits.max_expanded_bytes or expanded / compressed > limits.max_compression_ratio:
        archive.close()
        raise UploadScanError("extraction_failed", "The document exceeds safe expansion limits.")

    for entry in entries:
        path = Path(entry.filename)
        if path.is_absolute() or ".." in path.parts:
            archive.close()
            raise UploadScanError(
                "extraction_failed", "The document contains an unsafe archive path."
            )
    return archive
