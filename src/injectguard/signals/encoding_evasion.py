from __future__ import annotations

import base64
import binascii
import re

from injectguard.signals.common import (
    SignalMatch,
    clamp,
    first_spans,
    natural_language_score,
    normalize_obfuscation,
)
from injectguard.types import ContainerType


BASE64_RE = re.compile(r"\b(?:[A-Za-z0-9+/]{24,}={0,2}|[A-Za-z0-9_-]{24,})\b")
HEX_RE = re.compile(r"\b(?:0x)?[0-9A-Fa-f]{32,}\b")
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f]")
INJECTION_RE = re.compile(
    r"\b(ignore|previous instructions|system prompt|you are an ai|reveal|exfiltrate)\b",
    re.I,
)


def score(content: str, container: ContainerType, source: str | None = None) -> SignalMatch:
    suspicious_spans = []
    decoded_hits = 0

    for match in BASE64_RE.finditer(content):
        decoded = _decode_base64(match.group(0))
        if decoded and _decoded_is_suspicious(decoded):
            suspicious_spans.append(match.span())
            decoded_hits += 1

    for match in HEX_RE.finditer(content):
        decoded = _decode_hex(match.group(0))
        if decoded and _decoded_is_suspicious(decoded):
            suspicious_spans.append(match.span())
            decoded_hits += 1

    zero_width_spans = [match.span() for match in ZERO_WIDTH_RE.finditer(content)]
    normalized = normalize_obfuscation(content)
    homoglyph_hit = normalized != content and bool(INJECTION_RE.search(normalized))

    base = decoded_hits * 0.45
    if zero_width_spans:
        base += min(0.25, len(zero_width_spans) / 30.0)
        suspicious_spans.extend(zero_width_spans[:3])
    if homoglyph_hit:
        base += 0.35

    return SignalMatch(
        name="encoding_evasion",
        score=clamp(base),
        spans=first_spans(suspicious_spans),
        details=f"{decoded_hits} encoded natural-language blobs",
    )


def _decode_base64(value: str) -> str | None:
    padded = value + "=" * (-len(value) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            decoded = decoder(padded.encode("ascii"), validate=False)
            return decoded.decode("utf-8")
        except Exception:
            continue
    return None


def _decode_hex(value: str) -> str | None:
    cleaned = value[2:] if value.lower().startswith("0x") else value
    try:
        return binascii.unhexlify(cleaned).decode("utf-8")
    except Exception:
        return None


def _decoded_is_suspicious(decoded: str) -> bool:
    return natural_language_score(decoded) > 0.35 and bool(INJECTION_RE.search(decoded))
