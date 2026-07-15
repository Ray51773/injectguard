from __future__ import annotations

from injectguard.signals.common import SignalMatch, clamp, density, first_spans, matches
from injectguard.types import ContainerType


MORAL_RE = (
    r"\b(harm|harmful|ethical|ethics|moral|morality|fairness|justice|rights|"
    r"safety|safe|dangerous|danger|victim|abuse|consent|coercion|"
    r"medical|doctor|patient|therapy|self-harm|violence|illegal|lawful)\b"
)
EMOTIONAL_RE = (
    r"\b(urgent|critical|emergency|afraid|fear|panic|distress|trauma|"
    r"vulnerable|desperate|please|beg|important|life[- ]?threatening)\b"
)
SENTIMENT_RE = (
    r"\b(terrible|wonderful|awful|horrific|beautiful|evil|good|bad|"
    r"wrong|right)\b"
)


def score(content: str, container: ContainerType, source: str | None = None) -> SignalMatch:
    spans = (
        matches(MORAL_RE, content)
        + matches(EMOTIONAL_RE, content)
        + matches(SENTIMENT_RE, content)
    )
    raw = len(spans)
    base = density(raw, content, scale=16.0)

    if container in {ContainerType.MARKDOWN, ContainerType.HTML, ContainerType.SOURCE_COMMENT}:
        base *= 0.45
    elif container is ContainerType.UNKNOWN:
        base *= 0.7

    return SignalMatch(
        name="affective_load",
        score=clamp(base),
        spans=first_spans(spans),
        details=f"{raw} affective or moral markers",
    )
