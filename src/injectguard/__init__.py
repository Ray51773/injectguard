"""Offline prompt-injection detection for machine-shaped containers."""

from injectguard.containers import detect_container
from injectguard.scanner import scan
from injectguard.types import ContainerType, ScanResult, Signal, Verdict

__all__ = [
    "ContainerType",
    "ScanResult",
    "Signal",
    "Verdict",
    "detect_container",
    "scan",
]

