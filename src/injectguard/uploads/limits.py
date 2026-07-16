from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UploadLimits:
    max_upload_bytes: int = 20 * 1024 * 1024
    max_archive_entries: int = 2_000
    max_expanded_bytes: int = 80 * 1024 * 1024
    max_compression_ratio: int = 150
    max_document_pages: int = 2_000
    max_json_depth: int = 100
    max_segments: int = 50_000
    max_extracted_characters: int = 8_000_000
    chunk_characters: int = 16_000
    chunk_overlap: int = 2_000
    response_characters: int = 750_000

    @classmethod
    def from_environment(cls) -> UploadLimits:
        return cls(
            max_upload_bytes=_integer_env("INJECTGUARD_MAX_UPLOAD_BYTES", cls.max_upload_bytes),
            max_archive_entries=_integer_env(
                "INJECTGUARD_MAX_ARCHIVE_ENTRIES", cls.max_archive_entries
            ),
            max_expanded_bytes=_integer_env(
                "INJECTGUARD_MAX_EXPANDED_BYTES", cls.max_expanded_bytes
            ),
            max_compression_ratio=_integer_env(
                "INJECTGUARD_MAX_COMPRESSION_RATIO", cls.max_compression_ratio
            ),
            max_document_pages=_integer_env(
                "INJECTGUARD_MAX_DOCUMENT_PAGES", cls.max_document_pages
            ),
            max_json_depth=_integer_env("INJECTGUARD_MAX_JSON_DEPTH", cls.max_json_depth),
            max_segments=_integer_env("INJECTGUARD_MAX_SEGMENTS", cls.max_segments),
            max_extracted_characters=_integer_env(
                "INJECTGUARD_MAX_EXTRACTED_CHARACTERS", cls.max_extracted_characters
            ),
            chunk_characters=_integer_env("INJECTGUARD_CHUNK_CHARACTERS", cls.chunk_characters),
            chunk_overlap=_integer_env("INJECTGUARD_CHUNK_OVERLAP", cls.chunk_overlap),
            response_characters=_integer_env(
                "INJECTGUARD_RESPONSE_CHARACTERS", cls.response_characters
            ),
        )


def _integer_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
