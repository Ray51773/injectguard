from __future__ import annotations

from injectguard.signals.common import SignalMatch, clamp, density, first_spans, matches, normalize_obfuscation
from injectguard.types import ContainerType


ROLE_RE = (
    r"(?im)(^|\b)(system|developer|assistant|user)\s*:"
    r"|<\s*/?\s*(system|developer|assistant|user|instructions?|prompt)\b[^>]*>"
    r"|```+\s*(system|developer|assistant|prompt)\b"
)
IGNORE_RE = (
    r"\b(ignore|disregard|forget|override|bypass)\s+"
    r"(all\s+)?(previous|prior|above|earlier)\s+"
    r"(instructions?|prompts?|messages?|rules?)\b"
)
DELIMITER_RE = r"(?m)^\s*(-{3,}|={3,}|#{3,}\s*(system|developer|instructions?)\b|\[/?(INST|SYS)\])"
TAG_INJECTION_RE = r"<\s*(script|iframe|meta|link)\b|<!--\s*(system|prompt|instruction)"


def score(content: str, container: ContainerType, source: str | None = None) -> SignalMatch:
    normalized = normalize_obfuscation(content)
    spans = (
        matches(ROLE_RE, normalized)
        + matches(IGNORE_RE, normalized)
        + matches(DELIMITER_RE, normalized)
        + matches(TAG_INJECTION_RE, normalized)
    )
    ignore_hits = len(matches(IGNORE_RE, normalized))
    role_hits = len(spans)
    base = density(role_hits + ignore_hits * 3, normalized, scale=20.0)
    if ignore_hits:
        base += 0.3
    if container in {ContainerType.MARKDOWN, ContainerType.HTML}:
        base *= 0.75

    return SignalMatch(
        name="role_break",
        score=clamp(base),
        spans=first_spans(spans),
        details=f"{role_hits} role/delimiter markers",
    )
