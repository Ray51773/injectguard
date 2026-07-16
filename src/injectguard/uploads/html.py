from __future__ import annotations

import re

from injectguard.types import ContainerType
from injectguard.uploads.builder import SegmentBuilder
from injectguard.uploads.common import decode_text
from injectguard.uploads.errors import UploadScanError
from injectguard.uploads.limits import UploadLimits
from injectguard.uploads.models import ExtractionResult

_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\D|$)|"
    r"font-size\s*:\s*0|width\s*:\s*0|height\s*:\s*0|"
    r"(?:left|top)\s*:\s*-\d{3,}(?:px|rem|em)",
    re.IGNORECASE,
)


def extract_html(data: bytes, filename: str, limits: UploadLimits) -> ExtractionResult:
    try:
        from bs4 import BeautifulSoup, Comment, NavigableString, Tag
    except ImportError as exc:  # pragma: no cover - server extra provides it.
        raise UploadScanError(
            "extraction_failed", "HTML extraction support is not installed."
        ) from exc

    text = decode_text(data)
    if not re.search(r"<!doctype\s+html|<html\b|<body\b|<[A-Za-z][^>]*>", text, re.I):
        raise UploadScanError("unsupported_type", "The uploaded file is not valid HTML.", 415)
    soup = BeautifulSoup(text, "html.parser")
    builder = SegmentBuilder(filename, limits)

    comments = soup.find_all(string=lambda value: isinstance(value, Comment))
    for index, comment in enumerate(comments, 1):
        builder.add(str(comment), ContainerType.HTML, f"HTML comment {index}", "hidden", "comments")

    for index, script in enumerate(soup.find_all(["script", "style"]), 1):
        builder.add(
            script.get_text(" ", strip=True),
            ContainerType.HTML,
            f"{script.name} block {index}",
            "hidden",
            "scripts",
        )

    for element_index, element in enumerate(soup.find_all(True), 1):
        assert isinstance(element, Tag)
        for attribute, value in element.attrs.items():
            if attribute.startswith("data-") or attribute in {"title", "aria-label", "alt", "href"}:
                rendered = " ".join(value) if isinstance(value, list) else str(value)
                builder.add(
                    rendered,
                    ContainerType.HTML,
                    f"<{element.name}> {attribute} attribute {element_index}",
                    "metadata",
                    "attributes",
                )

    text_index = 0
    for node in soup.find_all(string=True):
        if isinstance(node, Comment) or not isinstance(node, NavigableString):
            continue
        parent = node.parent
        if parent is None or parent.name in {"script", "style"}:
            continue
        value = str(node).strip()
        if not value:
            continue
        text_index += 1
        visibility = "hidden" if _is_hidden(parent) else "visible"
        builder.add(
            value,
            ContainerType.HTML,
            f"<{parent.name}> text {text_index}",
            visibility,
            "body",
        )

    return ExtractionResult(
        file_type="html",
        detected_mime="text/html",
        segments=builder.segments,
        truncated=builder.truncated,
    )


def _is_hidden(element: object) -> bool:
    current = element
    while current is not None and hasattr(current, "attrs"):
        attrs = getattr(current, "attrs", {})
        style = str(attrs.get("style", ""))
        classes = " ".join(attrs.get("class", []))
        if (
            "hidden" in attrs
            or str(attrs.get("aria-hidden", "")).lower() == "true"
            or _HIDDEN_STYLE.search(style)
            or re.search(r"(?:^|[-_ ])(?:hidden|sr-only|visually-hidden)(?:$|[-_ ])", classes, re.I)
        ):
            return True
        current = getattr(current, "parent", None)
    return False
