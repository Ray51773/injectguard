from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from injectguard.types import ContainerType, Span


@dataclass(frozen=True)
class SignalMatch:
    name: str
    score: float
    spans: list[Span]
    details: str = ""


INERT_CONTAINERS = {
    ContainerType.ENV_FILE,
    ContainerType.CREDENTIALS,
    ContainerType.JSON,
    ContainerType.YAML,
    ContainerType.LOG,
    ContainerType.PDF_TEXT,
    ContainerType.TOOL_RESPONSE,
}


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def matches(pattern: str, content: str, flags: int = re.IGNORECASE) -> list[Span]:
    return [match.span() for match in re.finditer(pattern, content, flags)]


def density(count: int, content: str, scale: float) -> float:
    words = max(1, len(re.findall(r"\b[\w'-]+\b", content)))
    return clamp((count / words) * scale)


def natural_language_score(text: str) -> float:
    words = re.findall(r"[A-Za-z]{2,}", text)
    if len(words) < 4:
        return 0.0
    stop = {
        "the",
        "and",
        "you",
        "your",
        "are",
        "this",
        "that",
        "with",
        "not",
        "for",
        "before",
        "ignore",
        "instructions",
        "previous",
        "system",
        "must",
        "should",
    }
    stop_hits = sum(1 for word in words if word.lower() in stop)
    alpha_ratio = sum(ch.isalpha() or ch.isspace() for ch in text) / max(1, len(text))
    word_component = (len(words) / 20.0) * 0.45
    stop_component = (stop_hits / max(1, len(words))) * 0.35
    return clamp(word_component + stop_component + alpha_ratio * 0.2)


def normalize_obfuscation(text: str) -> str:
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    normalized = unicodedata.normalize("NFKC", cleaned)
    table = str.maketrans(
        {
            "\u0430": "a",
            "\u0435": "e",
            "\u043e": "o",
            "\u0440": "p",
            "\u0441": "c",
            "\u0443": "y",
            "\u0445": "x",
            "\u0391": "A",
            "\u0392": "B",
            "\u0395": "E",
            "\u0397": "H",
            "\u0399": "I",
            "\u039a": "K",
            "\u039c": "M",
            "\u039d": "N",
            "\u039f": "O",
            "\u03a1": "P",
            "\u03a4": "T",
            "\u03a7": "X",
        }
    )
    return normalized.translate(table)


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


@lru_cache(maxsize=1)
def get_spacy_nlp() -> Any | None:
    try:
        import spacy
    except Exception:
        return None

    for model in ("en_core_web_sm", "en_core_web_md"):
        try:
            return spacy.load(model, disable=["ner"])
        except Exception:
            continue
    try:
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
        return nlp
    except Exception:
        return None


def first_spans(spans: Iterable[Span], limit: int = 5) -> list[Span]:
    unique = []
    seen = set()
    for span in spans:
        if span in seen:
            continue
        seen.add(span)
        unique.append(span)
        if len(unique) >= limit:
            break
    return unique
