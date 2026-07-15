from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar, overload

from injectguard.scanner import scan
from injectguard.types import ContainerType, ScanResult, Verdict

LOGGER = logging.getLogger("injectguard.middleware")
R = TypeVar("R")


@dataclass(frozen=True)
class GuardedToolResponse:
    """A tool response plus its InjectGuard scan result."""

    value: Any
    scan: ScanResult


@overload
def wrap_tool_response(
    fn: Callable[..., Awaitable[R]],
    *,
    container: ContainerType = ContainerType.TOOL_RESPONSE,
    source: str | None = None,
    return_scan: bool = False,
) -> Callable[..., Awaitable[R | GuardedToolResponse]]: ...


@overload
def wrap_tool_response(
    fn: Callable[..., R],
    *,
    container: ContainerType = ContainerType.TOOL_RESPONSE,
    source: str | None = None,
    return_scan: bool = False,
) -> Callable[..., R | GuardedToolResponse]: ...


@overload
def wrap_tool_response(
    fn: None = None,
    *,
    container: ContainerType = ContainerType.TOOL_RESPONSE,
    source: str | None = None,
    return_scan: bool = False,
) -> Callable[[Callable[..., R]], Callable[..., R | GuardedToolResponse]]: ...


def wrap_tool_response(
    fn: Callable[..., Any] | None = None,
    *,
    container: ContainerType = ContainerType.TOOL_RESPONSE,
    source: str | None = None,
    return_scan: bool = False,
) -> Callable[..., Any]:
    """Scan MCP/agent tool responses without changing them by default.

    Set ``return_scan=True`` when the caller wants a ``GuardedToolResponse``
    wrapper containing both the original value and the scan result.
    """

    if fn is None:

        def decorator(inner: Callable[..., Any]) -> Callable[..., Any]:
            return wrap_tool_response(
                inner,
                container=container,
                source=source,
                return_scan=return_scan,
            )

        return decorator

    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            value = await fn(*args, **kwargs)
            result = _scan_value(value, container, source or _source_name(fn))
            _log_result(result)
            if return_scan:
                return GuardedToolResponse(value=value, scan=result)
            return value

        return async_wrapper

    @wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        value = fn(*args, **kwargs)
        result = _scan_value(value, container, source or _source_name(fn))
        _log_result(result)
        if return_scan:
            return GuardedToolResponse(value=value, scan=result)
        return value

    return sync_wrapper


def _scan_value(value: Any, container: ContainerType, source: str) -> ScanResult:
    return scan(_stringify(value), container=container, source=source)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _source_name(fn: Callable[..., Any]) -> str:
    module = getattr(fn, "__module__", "__unknown__")
    name = getattr(fn, "__qualname__", getattr(fn, "__name__", "tool"))
    return f"{module}.{name}"


def _log_result(result: ScanResult) -> None:
    level = logging.INFO
    if result.verdict is Verdict.INJECTION:
        level = logging.ERROR
    elif result.verdict is Verdict.SUSPICIOUS:
        level = logging.WARNING
    LOGGER.log(
        level,
        "tool_response_scanned",
        extra={
            "risk": result.risk,
            "verdict": result.verdict.value,
            "container": result.container.value,
            "source": result.source,
            "signals": [signal.name for signal in result.signals],
        },
    )
