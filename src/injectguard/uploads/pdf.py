from __future__ import annotations

from typing import Any

from injectguard.types import ContainerType
from injectguard.uploads.builder import SegmentBuilder
from injectguard.uploads.errors import UploadScanError
from injectguard.uploads.limits import UploadLimits
from injectguard.uploads.models import ExtractionResult


def extract_pdf(data: bytes, filename: str, limits: UploadLimits) -> ExtractionResult:
    if not data.lstrip().startswith(b"%PDF-"):
        raise UploadScanError("unsupported_type", "The uploaded file is not a PDF document.", 415)
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - server extra provides it.
        raise UploadScanError(
            "extraction_failed", "PDF extraction support is not installed."
        ) from exc

    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise UploadScanError("extraction_failed", "The PDF document could not be opened.") from exc

    try:
        if document.needs_pass:
            raise UploadScanError(
                "encrypted_document", "Encrypted or password-protected PDF files are not supported."
            )
        if document.page_count > limits.max_document_pages:
            raise UploadScanError("extraction_failed", "The PDF exceeds the configured page limit.")
        builder = SegmentBuilder(filename, limits)
        warnings: list[str] = []
        useful_text = 0
        image_count = 0

        for page_number, page in enumerate(document, start=1):
            image_count += len(page.get_images(full=True))
            useful_text += _extract_page(page, page_number, builder)
            _extract_annotations(page, page_number, builder)

        _extract_metadata(document, builder)
        _extract_embedded_files(document, builder, limits)

        if useful_text < 20 and image_count and not _extract_ocr(document, builder):
            warnings.append(
                "The PDF appears image-based; OCR was unavailable or produced no useful text."
            )
        if not builder.segments:
            warnings.append("No extractable text was found in the PDF document.")
        return ExtractionResult(
            file_type="pdf",
            detected_mime="application/pdf",
            segments=builder.segments,
            pages=document.page_count,
            warnings=warnings,
            truncated=builder.truncated,
        )
    finally:
        document.close()


def _extract_page(page: Any, page_number: int, builder: SegmentBuilder) -> int:
    try:
        page_dict = page.get_text("dict", sort=True)
    except Exception as exc:
        raise UploadScanError(
            "extraction_failed", f"PDF page {page_number} could not be read."
        ) from exc
    character_count = 0
    span_number = 0
    page_rect = page.rect
    for block in page_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = str(span.get("text", "")).strip()
                if not text:
                    continue
                span_number += 1
                character_count += len(text)
                visibility = _span_visibility(span, page_rect)
                builder.add(
                    text,
                    ContainerType.PDF_TEXT,
                    f"page {page_number}, text span {span_number}",
                    visibility,
                    f"page {page_number}",
                )
    return character_count


def _span_visibility(span: dict[str, Any], page_rect: Any) -> str:
    size = float(span.get("size", 12.0))
    color = int(span.get("color", 0)) & 0xFFFFFF
    red = (color >> 16) & 0xFF
    green = (color >> 8) & 0xFF
    blue = color & 0xFF
    bbox = span.get("bbox", (0.0, 0.0, 0.0, 0.0))
    outside = (
        float(bbox[2]) < float(page_rect.x0)
        or float(bbox[0]) > float(page_rect.x1)
        or float(bbox[3]) < float(page_rect.y0)
        or float(bbox[1]) > float(page_rect.y1)
    )
    if size <= 6.0 or min(red, green, blue) >= 240 or outside:
        return "hidden"
    return "visible"


def _extract_annotations(page: Any, page_number: int, builder: SegmentBuilder) -> None:
    annotation = page.first_annot
    annotation_number = 0
    while annotation is not None:
        annotation_number += 1
        info = annotation.info or {}
        for key in ("content", "title", "subject"):
            value = str(info.get(key, "")).strip()
            builder.add(
                value,
                ContainerType.PDF_TEXT,
                f"page {page_number}, annotation {annotation_number}, {key}",
                "metadata",
                f"page {page_number} annotations",
            )
        annotation = annotation.next


def _extract_metadata(document: Any, builder: SegmentBuilder) -> None:
    for key, value in (document.metadata or {}).items():
        builder.add(
            str(value),
            ContainerType.PDF_TEXT,
            f"document metadata, {key}",
            "metadata",
            "metadata",
        )


def _extract_embedded_files(document: Any, builder: SegmentBuilder, limits: UploadLimits) -> None:
    try:
        names = document.embfile_names()
    except Exception:
        return
    for index, name in enumerate(names, start=1):
        builder.add(
            str(name),
            ContainerType.PDF_TEXT,
            f"embedded file {index}, filename",
            "metadata",
            "embedded files",
        )
        try:
            info = document.embfile_info(name)
            expanded_size = int(info.get("size", info.get("length", 0)))
            if expanded_size > limits.max_upload_bytes:
                continue
            payload = document.embfile_get(name)
        except Exception:
            continue
        if not isinstance(payload, bytes) or len(payload) > limits.max_upload_bytes:
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            continue
        builder.add(
            text,
            ContainerType.UNKNOWN,
            f"embedded file {index}, {name}",
            "hidden",
            "embedded files",
        )


def _extract_ocr(document: Any, builder: SegmentBuilder) -> bool:
    extracted = False
    for page_number, page in enumerate(document, start=1):
        try:
            text_page = page.get_textpage_ocr(flags=0, dpi=150, full=True)
            text = page.get_text("text", textpage=text_page).strip()
        except Exception:
            return extracted
        if text:
            extracted = True
            builder.add(
                text,
                ContainerType.PDF_TEXT,
                f"page {page_number}, OCR text",
                "visible",
                f"page {page_number}",
            )
    return extracted
