from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from injectguard.types import ContainerType

Visibility = str


@dataclass(frozen=True)
class ExtractedSegment:
    source_filename: str
    container: ContainerType
    location: str
    visibility: Visibility
    text: str
    character_offset: int = 0
    section: str = "document"

    def to_dict(self, include_text: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source_filename": self.source_filename,
            "container": self.container.value,
            "location": self.location,
            "visibility": self.visibility,
            "character_offset": self.character_offset,
            "section": self.section,
        }
        if include_text:
            data["text"] = self.text
        return data


@dataclass
class ExtractionResult:
    file_type: str
    detected_mime: str
    segments: list[ExtractedSegment] = field(default_factory=list)
    pages: int = 0
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def characters(self) -> int:
        return sum(len(segment.text) for segment in self.segments)


@dataclass(frozen=True)
class Finding:
    detector: str
    severity: str
    confidence: float
    location: str
    visibility: Visibility
    matched_text: str
    explanation: str
    source_filename: str
    container: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FileScanReport:
    scan_id: str
    filename: str
    file_type: str
    detected_mime: str
    size_bytes: int
    verdict: str
    risk_score: float
    extraction: dict[str, Any]
    findings: list[Finding]
    extracted_segments: list[ExtractedSegment]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "detected_mime": self.detected_mime,
            "size_bytes": self.size_bytes,
            "verdict": self.verdict,
            "risk_score": self.risk_score,
            "extraction": self.extraction,
            "findings": [finding.to_dict() for finding in self.findings],
            "extracted_segments": [segment.to_dict() for segment in self.extracted_segments],
        }
