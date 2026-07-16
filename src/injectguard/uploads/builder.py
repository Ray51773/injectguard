from __future__ import annotations

from dataclasses import replace

from injectguard.types import ContainerType
from injectguard.uploads.limits import UploadLimits
from injectguard.uploads.models import ExtractedSegment


class SegmentBuilder:
    def __init__(self, filename: str, limits: UploadLimits) -> None:
        self.filename = filename
        self.limits = limits
        self.segments: list[ExtractedSegment] = []
        self.characters = 0
        self.truncated = False

    def add(
        self,
        text: str,
        container: ContainerType,
        location: str,
        visibility: str = "visible",
        section: str = "document",
    ) -> None:
        normalized = text.replace("\x00", "").strip()
        if not normalized or self.truncated:
            return
        remaining = self.limits.max_extracted_characters - self.characters
        if remaining <= 0 or len(self.segments) >= self.limits.max_segments:
            self.truncated = True
            return
        if len(normalized) > remaining:
            normalized = normalized[:remaining]
            self.truncated = True
        segment = ExtractedSegment(
            source_filename=self.filename,
            container=container,
            location=location,
            visibility=visibility,
            text=normalized,
            character_offset=self.characters,
            section=section,
        )
        self.segments.append(segment)
        self.characters += len(normalized) + 1

    def limited_for_response(self) -> list[ExtractedSegment]:
        total = 0
        output: list[ExtractedSegment] = []
        for segment in self.segments:
            remaining = self.limits.response_characters - total
            if remaining <= 0:
                break
            text = segment.text[:remaining]
            output.append(replace(segment, text=text))
            total += len(text)
        return output
