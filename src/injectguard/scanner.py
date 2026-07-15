from __future__ import annotations

import importlib
from typing import Iterable, List, Optional

from injectguard.config import load_config, thresholds_for, weights_for
from injectguard.signals.common import SignalMatch
from injectguard.types import ContainerType, ScanResult, Signal, Verdict


DETECTORS = [
    "direct_address",
    "instruction_shape",
    "semantic_mismatch",
    "affective_load",
    "authority_appeal",
    "encoding_evasion",
    "role_break",
]


def scan(
    content: str,
    container: ContainerType,
    source: Optional[str] = None,
) -> ScanResult:
    config = load_config()
    weights = weights_for(config, container)
    matches = list(_run_detectors(content, container, source))

    weighted_total = 0.0
    active_weight = 0.0
    signals: List[Signal] = []

    for match in matches:
        weight = weights.get(match.name, 0.0)
        if weight <= 0:
            continue
        active_weight += weight
        weighted_total += weight * match.score
        for span in match.spans[:5] or [None]:
            excerpt = _excerpt(content, span) if span else ""
            signals.append(
                Signal(
                    name=match.name,
                    weight=weight,
                    span=span,
                    excerpt=excerpt,
                    score=match.score,
                    details=match.details,
                )
            )

    risk = weighted_total / active_weight if active_weight else 0.0
    risk = round(max(0.0, min(1.0, risk)), 4)
    thresholds = thresholds_for(config, container)

    if risk >= thresholds["injection"]:
        verdict = Verdict.INJECTION
    elif risk >= thresholds["suspicious"]:
        verdict = Verdict.SUSPICIOUS
    else:
        verdict = Verdict.CLEAN

    signals = [
        signal
        for signal in signals
        if signal.score > 0 or signal.name == "semantic_mismatch"
    ]
    signals.sort(key=lambda signal: signal.score * signal.weight, reverse=True)
    return ScanResult(
        risk=risk,
        verdict=verdict,
        signals=signals,
        container=container,
        source=source,
    )


def _run_detectors(
    content: str,
    container: ContainerType,
    source: Optional[str],
) -> Iterable[SignalMatch]:
    for detector in DETECTORS:
        module = importlib.import_module(f"injectguard.signals.{detector}")
        yield module.score(content, container, source=source)


def _excerpt(content: str, span: tuple[int, int]) -> str:
    start, end = span
    start = max(0, start)
    end = min(len(content), end)
    excerpt = " ".join(content[start:end].split())
    if len(excerpt) > 180:
        return excerpt[:177] + "..."
    return excerpt

