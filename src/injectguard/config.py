from __future__ import annotations

import copy
import os
from importlib import resources
from typing import Any, Dict, Mapping, MutableMapping

try:
    import yaml
except Exception:  # pragma: no cover - exercised only in minimal environments.
    yaml = None

from injectguard.types import ContainerType


DEFAULT_CONFIG_RESOURCE = "default_config.yml"


def load_config() -> Dict[str, Any]:
    with resources.files("injectguard.data").joinpath(DEFAULT_CONFIG_RESOURCE).open(
        "r",
        encoding="utf-8",
    ) as handle:
        config = _load_yaml(handle.read())

    override_path = os.environ.get("INJECTGUARD_CONFIG")
    if override_path:
        with open(override_path, "r", encoding="utf-8") as handle:
            override = _load_yaml(handle.read())
        config = _deep_merge(config, override)
    return config


def weights_for(config: Mapping[str, Any], container: ContainerType) -> Dict[str, float]:
    weights = copy.deepcopy(config.get("weights", {}).get("UNKNOWN", {}))
    weights.update(config.get("weights", {}).get(container.value, {}))
    return {str(name): float(weight) for name, weight in weights.items()}


def thresholds_for(config: Mapping[str, Any], container: ContainerType) -> Dict[str, float]:
    thresholds = copy.deepcopy(config.get("thresholds", {}).get("UNKNOWN", {}))
    thresholds.update(config.get("thresholds", {}).get(container.value, {}))
    return {
        "suspicious": float(thresholds.get("suspicious", 0.35)),
        "injection": float(thresholds.get("injection", 0.65)),
    }


def enabled_detectors(config: Mapping[str, Any]) -> set[str]:
    configured = config.get("detectors", {})
    if not isinstance(configured, Mapping):
        return set()
    return {
        str(name)
        for name, enabled in configured.items()
        if bool(enabled)
    }


def _deep_merge(
    base: MutableMapping[str, Any],
    override: Mapping[str, Any],
) -> MutableMapping[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, Mapping)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _load_yaml(text: str) -> Dict[str, Any]:
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return _simple_yaml(text)


def _simple_yaml(text: str) -> Dict[str, Any]:
    """Parse the small mapping-only config shape used by the bundled defaults."""

    root: Dict[str, Any] = {}
    stack: list[tuple[int, Dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, _, raw_value = raw_line.strip().partition(":")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value = raw_value.strip()
        if value == "":
            child: Dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            lower_value = value.lower()
            if lower_value in {"true", "false"}:
                parent[key] = lower_value == "true"
            else:
                try:
                    parent[key] = float(value)
                except ValueError:
                    parent[key] = value.strip('"').strip("'")
    return root
