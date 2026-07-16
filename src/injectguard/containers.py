from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from injectguard.types import ContainerType

try:
    import yaml as yaml_module
except Exception:  # pragma: no cover - PyYAML is a runtime dependency.
    yaml: Any = None
else:
    yaml = yaml_module


_CREDENTIAL_NAME_RE = re.compile(
    r"(credential|secret|token|private[_-]?key|id_rsa|id_dsa|id_ed25519|\.pem$|\.key$)",
    re.IGNORECASE,
)
_SOURCE_EXTS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
_MARKDOWN_EXTS = {".md", ".markdown", ".mdx", ".rst"}
_LOG_EXTS = {".log", ".out", ".err"}


def detect_container(filename: str | None, content: str) -> ContainerType:
    """Infer a container type from filename and content."""

    path = Path(filename or "")
    name = path.name.lower()
    suffix = path.suffix.lower()
    stripped = content.lstrip()

    if name in {".env", ".env.local", ".envrc"} or suffix == ".env":
        return ContainerType.ENV_FILE
    if _CREDENTIAL_NAME_RE.search(name):
        return ContainerType.CREDENTIALS
    if suffix == ".json" or _looks_like_json(stripped):
        return ContainerType.JSON
    if suffix in {".yml", ".yaml"} or _looks_like_yaml(stripped):
        return ContainerType.YAML
    if suffix in {".html", ".htm"} or re.search(r"<html\b|<!doctype html|<body\b", stripped, re.I):
        return ContainerType.HTML
    if suffix in _MARKDOWN_EXTS or _looks_like_markdown(stripped):
        return ContainerType.MARKDOWN
    if suffix == ".pdf" or name.endswith(".pdf.txt"):
        return ContainerType.PDF_TEXT
    if suffix in _LOG_EXTS or _looks_like_log(stripped):
        return ContainerType.LOG
    if suffix in _SOURCE_EXTS and _comment_ratio(content) > 0.35:
        return ContainerType.SOURCE_COMMENT
    return ContainerType.UNKNOWN


def _looks_like_json(content: str) -> bool:
    if not content or content[0] not in "[{":
        return False
    try:
        json.loads(content)
    except Exception:
        return False
    return True


def _looks_like_yaml(content: str) -> bool:
    if yaml is None or not content:
        return False
    if not re.search(r"^[A-Za-z0-9_.-]+\s*:", content, re.M):
        return False
    try:
        parsed = yaml.safe_load(content)
    except Exception:
        return False
    return isinstance(parsed, (dict, list))


def _looks_like_markdown(content: str) -> bool:
    return bool(
        re.search(r"^#{1,6}\s+\S+", content, re.M)
        or re.search(r"\[[^\]]+\]\([^)]+\)", content)
        or re.search(r"^[-*]\s+\S+", content, re.M)
    )


def _looks_like_log(content: str) -> bool:
    sample = "\n".join(content.splitlines()[:12])
    return bool(
        re.search(r"\b(INFO|WARN|WARNING|ERROR|DEBUG|TRACE)\b", sample)
        or re.search(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", sample, re.M)
    )


def _comment_ratio(content: str) -> float:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return 0.0
    comment_lines = [line for line in lines if line.startswith(("#", "//", "/*", "*", "<!--"))]
    return len(comment_lines) / len(lines)
