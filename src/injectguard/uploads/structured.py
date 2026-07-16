from __future__ import annotations

import csv
import io
import json
from typing import Any

from injectguard.types import ContainerType
from injectguard.uploads.builder import SegmentBuilder
from injectguard.uploads.common import decode_text
from injectguard.uploads.errors import UploadScanError
from injectguard.uploads.limits import UploadLimits
from injectguard.uploads.models import ExtractionResult


def extract_json(data: bytes, filename: str, limits: UploadLimits) -> ExtractionResult:
    text = decode_text(data)
    try:
        value = json.loads(text)
    except RecursionError as exc:
        raise UploadScanError(
            "extraction_failed", "The JSON exceeds the configured depth limit."
        ) from exc
    except (TypeError, ValueError) as exc:
        raise UploadScanError("extraction_failed", "The JSON document is malformed.") from exc

    builder = SegmentBuilder(filename, limits)
    _walk_json(value, "$", builder, limits.max_json_depth)
    return ExtractionResult(
        file_type="json",
        detected_mime="application/json",
        segments=builder.segments,
        truncated=builder.truncated,
    )


def _walk_json(
    value: Any,
    path: str,
    builder: SegmentBuilder,
    remaining_depth: int,
) -> None:
    if remaining_depth < 0:
        raise UploadScanError("extraction_failed", "The JSON exceeds the configured depth limit.")
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            _walk_json(child, child_path, builder, remaining_depth - 1)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_json(child, f"{path}[{index}]", builder, remaining_depth - 1)
    elif value is not None:
        builder.add(str(value), ContainerType.JSON, path, section="values")


def extract_csv(data: bytes, filename: str, limits: UploadLimits) -> ExtractionResult:
    text = decode_text(data)
    builder = SegmentBuilder(filename, limits)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    try:
        rows = csv.reader(io.StringIO(text), dialect)
        for row_number, row in enumerate(rows, start=1):
            for column_number, value in enumerate(row, start=1):
                builder.add(
                    value,
                    ContainerType.UNKNOWN,
                    f"row {row_number}, column {column_number}",
                    section=f"row {row_number}",
                )
    except csv.Error as exc:
        raise UploadScanError("extraction_failed", "The CSV document is malformed.") from exc
    return ExtractionResult(
        file_type="csv",
        detected_mime="text/csv",
        segments=builder.segments,
        truncated=builder.truncated,
    )
