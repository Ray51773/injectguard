from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from injectguard import detect_container, scan
from injectguard.types import ContainerType, ScanResult


@runtime_checkable
class DocumentLike(Protocol):
    page_content: str
    metadata: dict[str, Any]


@dataclass
class ScannedDocument:
    page_content: str
    metadata: dict[str, Any]


class InjectGuardTransformer:
    """LangChain-compatible document transformer.

    The class intentionally avoids importing LangChain at module import time.
    It works with LangChain ``Document`` objects or any object with
    ``page_content`` and ``metadata`` attributes.
    """

    def __init__(self, container: ContainerType | None = None) -> None:
        self.container = container

    def transform_documents(
        self,
        documents: list[DocumentLike],
        **_: Any,
    ) -> list[DocumentLike | ScannedDocument]:
        return [self._scan_document(document) for document in documents]

    async def atransform_documents(
        self,
        documents: list[DocumentLike],
        **kwargs: Any,
    ) -> list[DocumentLike | ScannedDocument]:
        return self.transform_documents(documents, **kwargs)

    def _scan_document(self, document: DocumentLike) -> DocumentLike | ScannedDocument:
        metadata = dict(getattr(document, "metadata", {}) or {})
        source = _source_from_metadata(metadata)
        container = self.container or detect_container(source, document.page_content)
        result = scan(document.page_content, container=container, source=source)
        metadata["injectguard"] = result.to_dict()

        try:
            document.metadata = metadata
            return document
        except Exception:
            return ScannedDocument(
                page_content=document.page_content,
                metadata=metadata,
            )


def scan_document(
    document: DocumentLike,
    *,
    container: ContainerType | None = None,
) -> tuple[DocumentLike | ScannedDocument, ScanResult]:
    metadata = dict(getattr(document, "metadata", {}) or {})
    source = _source_from_metadata(metadata)
    resolved_container = container or detect_container(source, document.page_content)
    result = scan(document.page_content, container=resolved_container, source=source)
    metadata["injectguard"] = result.to_dict()
    try:
        document.metadata = metadata
        return document, result
    except Exception:
        scanned = ScannedDocument(page_content=document.page_content, metadata=metadata)
        return scanned, result


def _source_from_metadata(metadata: dict[str, Any]) -> str | None:
    for key in ("source", "file_path", "path", "url"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None

