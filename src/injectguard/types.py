from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ContainerType(str, Enum):
    ENV_FILE = "ENV_FILE"
    CREDENTIALS = "CREDENTIALS"
    JSON = "JSON"
    YAML = "YAML"
    SOURCE_COMMENT = "SOURCE_COMMENT"
    LOG = "LOG"
    HTML = "HTML"
    MARKDOWN = "MARKDOWN"
    PDF_TEXT = "PDF_TEXT"
    TOOL_RESPONSE = "TOOL_RESPONSE"
    UNKNOWN = "UNKNOWN"


class Verdict(str, Enum):
    CLEAN = "CLEAN"
    SUSPICIOUS = "SUSPICIOUS"
    INJECTION = "INJECTION"


Span = Tuple[int, int]


@dataclass(frozen=True)
class Signal:
    name: str
    weight: float
    span: Optional[Span]
    excerpt: str
    score: float
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["span"] = list(self.span) if self.span else None
        return data


@dataclass(frozen=True)
class ScanResult:
    risk: float
    verdict: Verdict
    signals: List[Signal]
    container: ContainerType
    source: Optional[str] = None

    def explain(self) -> str:
        if not self.signals:
            return (
                f"{self.verdict.value}: no prompt-injection signals were found "
                f"for {self.container.value}."
            )

        top = sorted(
            self.signals,
            key=lambda signal: signal.score * signal.weight,
            reverse=True,
        )[:5]
        parts = [
            f"{self.verdict.value} risk={self.risk:.2f} for {self.container.value}",
            "Top signals:",
        ]
        for signal in top:
            excerpt = f' "{signal.excerpt}"' if signal.excerpt else ""
            detail = f" ({signal.details})" if signal.details else ""
            parts.append(
                f"- {signal.name}: score={signal.score:.2f}, "
                f"weight={signal.weight:.2f}{detail}{excerpt}"
            )
        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk": self.risk,
            "verdict": self.verdict.value,
            "container": self.container.value,
            "source": self.source,
            "signals": [signal.to_dict() for signal in self.signals],
        }

