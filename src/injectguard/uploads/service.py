from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from injectguard.scanner import scan
from injectguard.types import ContainerType, ScanResult, Signal, Verdict
from injectguard.uploads.extract import extract_upload
from injectguard.uploads.limits import UploadLimits
from injectguard.uploads.models import (
    ExtractedSegment,
    FileScanReport,
    Finding,
)


@dataclass(frozen=True)
class _MappedSegment:
    start: int
    end: int
    segment: ExtractedSegment


@dataclass(frozen=True)
class _ScanTarget:
    text: str
    container: ContainerType
    location: str
    visibility: str
    mappings: list[_MappedSegment]


@dataclass(frozen=True)
class _Observation:
    target: _ScanTarget
    result: ScanResult


def scan_uploaded_file(
    data: bytes,
    filename: str | None,
    limits: UploadLimits | None = None,
) -> FileScanReport:
    active_limits = limits or UploadLimits.from_environment()
    scan_identifier = str(uuid4())
    display_name, extraction = extract_upload(data, filename, active_limits)
    targets = _build_targets(extraction.segments, active_limits)
    observations = [
        _Observation(
            target=target,
            result=scan(
                target.text,
                container=target.container,
                source=f"{display_name}: {target.location}",
            ),
        )
        for target in targets
        if target.text.strip()
    ]
    findings = _collect_findings(observations, display_name)
    risk = max((observation.result.risk for observation in observations), default=0.0)
    hidden_finding = any(
        finding.visibility == "hidden" and finding.severity in {"medium", "high"}
        for finding in findings
    )
    high_confidence_finding = any(finding.severity == "high" for finding in findings)
    has_injection = any(
        observation.result.verdict is Verdict.INJECTION for observation in observations
    )
    has_suspicious = any(
        observation.result.verdict is Verdict.SUSPICIOUS for observation in observations
    )
    if hidden_finding or high_confidence_finding:
        risk = max(risk, 0.5)
    if has_injection:
        verdict = "block"
    elif has_suspicious or hidden_finding or high_confidence_finding:
        verdict = "review"
    else:
        verdict = "allow"

    response_segments = _limit_response_segments(
        extraction.segments, active_limits.response_characters
    )
    extraction_summary = {
        "segments": len(extraction.segments),
        "characters": extraction.characters,
        "pages": extraction.pages,
        "hidden_segments": sum(segment.visibility == "hidden" for segment in extraction.segments),
        "metadata_segments": sum(
            segment.visibility == "metadata" for segment in extraction.segments
        ),
        "truncated": extraction.truncated or len(response_segments) < len(extraction.segments),
        "warnings": extraction.warnings,
    }
    return FileScanReport(
        scan_id=scan_identifier,
        filename=display_name,
        file_type=extraction.file_type,
        detected_mime=extraction.detected_mime,
        size_bytes=len(data),
        verdict=verdict,
        risk_score=round(min(1.0, risk), 4),
        extraction=extraction_summary,
        findings=findings[:250],
        extracted_segments=response_segments,
    )


def _build_targets(segments: list[ExtractedSegment], limits: UploadLimits) -> list[_ScanTarget]:
    targets = [
        _ScanTarget(
            text=segment.text,
            container=segment.container,
            location=segment.location,
            visibility=segment.visibility,
            mappings=[_MappedSegment(0, len(segment.text), segment)],
        )
        for segment in segments
    ]

    sections: dict[str, list[ExtractedSegment]] = {}
    for segment in segments:
        sections.setdefault(segment.section, []).append(segment)
    for section, section_segments in sections.items():
        targets.append(_join_segments(section_segments, f"section {section}"))

    if segments:
        combined = _join_segments(segments, "full document")
        targets.append(combined)
        if len(combined.text) > limits.chunk_characters:
            step = max(1, limits.chunk_characters - limits.chunk_overlap)
            for start in range(0, len(combined.text), step):
                end = min(len(combined.text), start + limits.chunk_characters)
                targets.append(_slice_target(combined, start, end))
                if end == len(combined.text):
                    break
    return targets


def _join_segments(segments: list[ExtractedSegment], location: str) -> _ScanTarget:
    parts: list[str] = []
    mappings: list[_MappedSegment] = []
    cursor = 0
    for segment in segments:
        if parts:
            parts.append("\n\n")
            cursor += 2
        parts.append(segment.text)
        mappings.append(_MappedSegment(cursor, cursor + len(segment.text), segment))
        cursor += len(segment.text)
    containers = {segment.container for segment in segments}
    container = containers.pop() if len(containers) == 1 else ContainerType.UNKNOWN
    visibilities = {segment.visibility for segment in segments}
    visibility = visibilities.pop() if len(visibilities) == 1 else "mixed"
    return _ScanTarget("".join(parts), container, location, visibility, mappings)


def _slice_target(target: _ScanTarget, start: int, end: int) -> _ScanTarget:
    mappings: list[_MappedSegment] = []
    for mapping in target.mappings:
        overlap_start = max(start, mapping.start)
        overlap_end = min(end, mapping.end)
        if overlap_start < overlap_end:
            mappings.append(
                _MappedSegment(overlap_start - start, overlap_end - start, mapping.segment)
            )
    return _ScanTarget(
        text=target.text[start:end],
        container=target.container,
        location=f"document chunk {start}-{end}",
        visibility=target.visibility,
        mappings=mappings,
    )


def _collect_findings(observations: list[_Observation], filename: str) -> list[Finding]:
    unique: dict[tuple[str, str, str], Finding] = {}
    for observation in observations:
        for signal in observation.result.signals:
            contribution = signal.score * signal.weight
            if signal.name == "semantic_mismatch" and signal.score < 0.5:
                continue
            if contribution < 0.06 and not signal.excerpt:
                continue
            segment = _segment_for_signal(observation.target, signal)
            location = segment.location if segment else observation.target.location
            visibility = segment.visibility if segment else observation.target.visibility
            matched_text = signal.excerpt or _short_excerpt(observation.target.text)
            severity = _severity(contribution, observation.result.verdict, visibility)
            finding = Finding(
                detector=signal.name,
                severity=severity,
                confidence=round(signal.score, 4),
                location=location,
                visibility=visibility,
                matched_text=matched_text,
                explanation=signal.details or "The extracted text does not fit its container.",
                source_filename=filename,
                container=observation.target.container.value,
            )
            key = (finding.detector, finding.location, finding.matched_text)
            previous = unique.get(key)
            if previous is None or finding.confidence > previous.confidence:
                unique[key] = finding
    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        unique.values(),
        key=lambda finding: (severity_order[finding.severity], -finding.confidence),
    )


def _segment_for_signal(target: _ScanTarget, signal: Signal) -> ExtractedSegment | None:
    if signal.span is not None:
        midpoint = (signal.span[0] + signal.span[1]) // 2
        for mapping in target.mappings:
            if mapping.start <= midpoint <= mapping.end:
                return mapping.segment
    if len(target.mappings) == 1:
        return target.mappings[0].segment
    return None


def _severity(contribution: float, verdict: Verdict, visibility: str) -> str:
    if verdict is Verdict.INJECTION or contribution >= 0.35:
        return "high"
    if verdict is Verdict.SUSPICIOUS or contribution >= 0.12 or visibility == "hidden":
        return "medium"
    return "low"


def _short_excerpt(text: str) -> str:
    excerpt = " ".join(text.split())
    return excerpt[:177] + "..." if len(excerpt) > 180 else excerpt


def _limit_response_segments(
    segments: list[ExtractedSegment], max_characters: int
) -> list[ExtractedSegment]:
    output: list[ExtractedSegment] = []
    count = 0
    for segment in segments:
        if count >= max_characters:
            break
        remaining = max_characters - count
        if len(segment.text) <= remaining:
            output.append(segment)
            count += len(segment.text)
        else:
            output.append(
                ExtractedSegment(
                    source_filename=segment.source_filename,
                    container=segment.container,
                    location=segment.location,
                    visibility=segment.visibility,
                    text=segment.text[:remaining],
                    character_offset=segment.character_offset,
                    section=segment.section,
                )
            )
            break
    return output
