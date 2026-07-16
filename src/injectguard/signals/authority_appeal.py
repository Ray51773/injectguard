from __future__ import annotations

from injectguard.signals.common import SignalMatch, clamp, density, first_spans, matches
from injectguard.types import ContainerType

AUTHORITY_RE = (
    r"\b(law|legal|regulation|regulatory|gdpr|hipaa|ccpa|sox|iso\s?27001|"
    r"audit|auditor|compliance|authorized|authorised|authorization|authorisation|"
    r"consent|court|police|government|federal|ministry|department|"
    r"openai|anthropic|google|microsoft|nist|owasp|eu|united states)\b"
)
COMMAND_AUTHORITY_RE = (
    r"\b(as required by|under .* law|for audit purposes|with user consent|"
    r"authorized security test|authorised security test|official policy)\b"
)


def score(content: str, container: ContainerType, source: str | None = None) -> SignalMatch:
    spans = matches(AUTHORITY_RE, content) + matches(COMMAND_AUTHORITY_RE, content)
    raw = len(spans)
    base = density(raw, content, scale=18.0)
    if matches(COMMAND_AUTHORITY_RE, content):
        base += 0.2

    if container in {ContainerType.MARKDOWN, ContainerType.HTML}:
        base *= 0.55
    elif container is ContainerType.SOURCE_COMMENT:
        base *= 0.75

    return SignalMatch(
        name="authority_appeal",
        score=clamp(base),
        spans=first_spans(spans),
        details=f"{raw} authority markers",
    )

