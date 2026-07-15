from __future__ import annotations

import re

from injectguard.signals.common import SignalMatch, clamp, density, first_spans, matches
from injectguard.types import ContainerType


SECOND_PERSON_RE = r"\b(you|your|yours|yourself|yourselves|reader|assistant|agent|model)\b"
VOCATIVE_RE = r"\b(dear|hello|attention|note to|listen|hey)\s+(assistant|agent|model|reader|ai)\b"
IMPERATIVE_RE = (
    r"(?m)^\s*(ignore|follow|read|write|print|reveal|return|summarize|"
    r"comply|do not|don't|never|always)\b"
)


def score(content: str, container: ContainerType, source: str | None = None) -> SignalMatch:
    pronoun_spans = matches(SECOND_PERSON_RE, content)
    vocative_spans = matches(VOCATIVE_RE, content)
    imperative_spans = matches(IMPERATIVE_RE, content)
    raw_count = len(pronoun_spans) + (2 * len(vocative_spans)) + (2 * len(imperative_spans))

    base = density(raw_count, content, scale=18.0)
    if container in {ContainerType.MARKDOWN, ContainerType.HTML, ContainerType.SOURCE_COMMENT}:
        base *= 0.35
    elif container is ContainerType.UNKNOWN:
        base *= 0.7

    spans = first_spans(vocative_spans + imperative_spans + pronoun_spans)
    return SignalMatch(
        name="direct_address",
        score=clamp(base),
        spans=spans,
        details=f"{raw_count} direct-address markers",
    )
