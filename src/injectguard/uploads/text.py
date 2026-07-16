from __future__ import annotations

from injectguard.containers import detect_container
from injectguard.types import ContainerType
from injectguard.uploads.builder import SegmentBuilder
from injectguard.uploads.common import decode_text
from injectguard.uploads.limits import UploadLimits
from injectguard.uploads.models import ExtractionResult


def extract_text(
    data: bytes, filename: str, extension: str, limits: UploadLimits
) -> ExtractionResult:
    text = decode_text(data)
    container = ContainerType.MARKDOWN if extension == ".md" else detect_container(filename, text)
    builder = SegmentBuilder(filename, limits)
    paragraphs = _paragraphs(text)
    if paragraphs:
        for index, paragraph in enumerate(paragraphs, start=1):
            builder.add(paragraph, container, f"paragraph {index}", section="body")
    else:
        builder.add(text, container, "document", section="body")
    mime = "text/markdown" if extension == ".md" else "text/plain"
    return ExtractionResult(
        file_type=extension.lstrip("."),
        detected_mime=mime,
        segments=builder.segments,
        truncated=builder.truncated,
    )


def _paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n")]
    return [paragraph for paragraph in paragraphs if paragraph]
