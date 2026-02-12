from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable


ToolHandler = Callable[[dict[str, Any]], Any]


@runtime_checkable
class ToolAdapter(Protocol):
    """Protocol for DAOKit tool adapters."""

    def register_tool(self, *, name: str, handler: ToolHandler) -> None: ...

    def invoke(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> "ToolInvocationResult": ...


@dataclass(frozen=True)
class ToolInvocationResult:
    status: str
    output: Any | None
    error: str | None


class ToolAdapterTemplate:
    """Copy-ready scaffold for a local tool adapter contribution."""

    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register_tool(self, *, name: str, handler: ToolHandler) -> None:
        normalized_name = _normalize_name(name, field_name="name")
        if not callable(handler):
            raise ValueError("handler must be callable")
        if normalized_name in self._handlers:
            raise ValueError(f"tool '{normalized_name}' is already registered")
        self._handlers[normalized_name] = handler

    def invoke(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> ToolInvocationResult:
        normalized_name = _normalize_name(tool_name, field_name="tool_name")
        request = dict(arguments or {})
        handler = self._handlers.get(normalized_name)
        if handler is None:
            return ToolInvocationResult(
                status="error",
                output=None,
                error=f"tool '{normalized_name}' is not registered",
            )

        try:
            response = handler(request)
        except Exception as exc:  # pragma: no cover - defensive runtime path
            return ToolInvocationResult(
                status="error",
                output=None,
                error=f"{exc.__class__.__name__}: {exc}",
            )

        return ToolInvocationResult(status="success", output=response, error=None)


def _normalize_name(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized
