from __future__ import annotations


class UploadScanError(Exception):
    """An expected, safely reportable upload failure."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
