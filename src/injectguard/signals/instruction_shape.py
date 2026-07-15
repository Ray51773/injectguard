from __future__ import annotations

import re

from injectguard.signals.common import (
    SignalMatch,
    clamp,
    density,
    first_spans,
    get_spacy_nlp,
    matches,
)
from injectguard.types import ContainerType


COMPLIANCE_RE = (
    r"\b(if you are (an? )?(ai|assistant|agent|language model)|"
    r"before proceeding|from now on|you must|you should|must not|do not|"
    r"under no circumstances|regardless of|comply with|follow these instructions)\b"
)
PROHIBITION_RE = (
    r"\b(never|do not|don't|must not|cannot|forbidden|prohibited|"
    r"under no circumstances)\b"
)
LEXICAL_IMPERATIVE_RE = (
    r"(?m)^\s*(ignore|disregard|forget|reveal|print|return|send|"
    r"exfiltrate|summarize|classify|answer|translate|execute|decode)\b"
)


def score(content: str, container: ContainerType, source: str | None = None) -> SignalMatch:
    spans = (
        matches(COMPLIANCE_RE, content)
        + matches(PROHIBITION_RE, content)
        + matches(LEXICAL_IMPERATIVE_RE, content)
    )
    compliance_count = len(spans)
    imperative_count = _imperative_count(content)
    raw = compliance_count * 2 + imperative_count
    base = density(raw, content, scale=22.0)

    if container in {ContainerType.MARKDOWN, ContainerType.HTML}:
        base *= 0.55
    elif container is ContainerType.SOURCE_COMMENT:
        base *= 0.7

    return SignalMatch(
        name="instruction_shape",
        score=clamp(base),
        spans=first_spans(spans),
        details=f"{imperative_count} imperative-like clauses, {compliance_count} compliance frames",
    )


def _imperative_count(content: str) -> int:
    nlp = get_spacy_nlp()
    if nlp is None:
        return len(matches(LEXICAL_IMPERATIVE_RE, content))

    doc = nlp(content[:20000])
    count = 0
    for sent in doc.sents:
        tokens = [token for token in sent if not token.is_space and not token.is_punct]
        if not tokens:
            continue
        first = tokens[0]
        if first.tag_ == "VB" or first.pos_ == "VERB" and first.dep_ in {"ROOT", ""}:
            count += 1
            continue
        if (
            len(tokens) > 1
            and tokens[0].lower_ in {"please", "kindly"}
            and tokens[1].pos_ == "VERB"
        ):
            count += 1
    if count:
        return count
    return len(matches(LEXICAL_IMPERATIVE_RE, content))
