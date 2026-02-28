from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from tools.common.command_runner import run_command
from tools.common.json_schema import JsonSchemaValidationError, validate_json_schema


class FunctionCallingAdapterError(ValueError):
    """Raised when function-calling adapter input is invalid."""


ToolHandler = Callable[[dict[str, Any]], Any]
CommandBuilder = Callable[[dict[str, Any]], Sequence[str]]


@dataclass(frozen=True)
class ToolInvocationResult:
    correlation_id: str
    tool_name: str
    status: str
    request: dict[str, Any]
    result: Any | None
    error: str | None
    timed_out: bool


@dataclass(frozen=True)
class InvocationLogEntry:
    correlation_id: str
    tool_name: str
    request: dict[str, Any]
    result: Any | None
    status: str
    error: str | None
    started_at: str
    finished_at: str


@dataclass(frozen=True)
class _CallableTool:
    args_schema: dict[str, Any]
    handler: ToolHandler


@dataclass(frozen=True)
class _CommandTool:
    args_schema: dict[str, Any]
    build_command: CommandBuilder
    default_timeout_seconds: float | None


class FunctionCallingAdapter:
    """Typed local tool adapter with schema validation and invocation logging."""

    def __init__(self) -> None:
        self._registry: dict[str, _CallableTool | _CommandTool] = {}
        self._invocation_logs: list[InvocationLogEntry] = []

    def register_callable(
        self,
        *,
        name: str,
        args_schema: Mapping[str, Any],
        handler: ToolHandler,
    ) -> None:
        normalized_name = _expect_non_empty_string(name, name="name")
        if not callable(handler):
            raise FunctionCallingAdapterError("handler must be callable")
        if normalized_name in self._registry:
            raise FunctionCallingAdapterError(f"tool '{normalized_name}' is already registered")
        self._registry[normalized_name] = _CallableTool(
            args_schema=_copy_json_schema(args_schema),
            handler=handler,
        )

    def register_command(
        self,
        *,
        name: str,
        args_schema: Mapping[str, Any],
        build_command: CommandBuilder,
        default_timeout_seconds: float | None = None,
    ) -> None:
        normalized_name = _expect_non_empty_string(name, name="name")
        if not callable(build_command):
            raise FunctionCallingAdapterError("build_command must be callable")
        if normalized_name in self._registry:
            raise FunctionCallingAdapterError(f"tool '{normalized_name}' is already registered")

        normalized_timeout = _normalize_timeout(default_timeout_seconds)
        self._registry[normalized_name] = _CommandTool(
            args_schema=_copy_json_schema(args_schema),
            build_command=build_command,
            default_timeout_seconds=normalized_timeout,
        )

    def invoke(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any] | None,
        correlation_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> ToolInvocationResult:
        normalized_name = _expect_non_empty_string(tool_name, name="tool_name")
        normalized_correlation_id = _resolve_correlation_id(correlation_id)
        started_at = _utc_now()

        try:
            request = _normalize_arguments(arguments)
        except FunctionCallingAdapterError as exc:
            finished_at = _utc_now()
            result = ToolInvocationResult(
                correlation_id=normalized_correlation_id,
                tool_name=normalized_name,
                status="validation_error",
                request={},
                result=None,
                error=str(exc),
                timed_out=False,
            )
            self._append_log(result=result, started_at=started_at, finished_at=finished_at)
            return result

        registered = self._registry.get(normalized_name)
        if registered is None:
            finished_at = _utc_now()
            result = ToolInvocationResult(
                correlation_id=normalized_correlation_id,
                tool_name=normalized_name,
                status="error",
                request=request,
                result=None,
                error=f"tool '{normalized_name}' is not registered",
                timed_out=False,
            )
            self._append_log(result=result, started_at=started_at, finished_at=finished_at)
            return result

        try:
            validate_json_schema(schema=registered.args_schema, payload=request)
        except JsonSchemaValidationError as exc:
            finished_at = _utc_now()
            result = ToolInvocationResult(
                correlation_id=normalized_correlation_id,
                tool_name=normalized_name,
                status="validation_error",
                request=request,
                result=None,
                error=str(exc),
                timed_out=False,
            )
            self._append_log(result=result, started_at=started_at, finished_at=finished_at)
            return result

        if isinstance(registered, _CallableTool):
            return self._invoke_callable(
                registered=registered,
                correlation_id=normalized_correlation_id,
                tool_name=normalized_name,
                request=request,
                started_at=started_at,
            )

        return self._invoke_command(
            registered=registered,
            correlation_id=normalized_correlation_id,
            tool_name=normalized_name,
            request=request,
            started_at=started_at,
            timeout_seconds=timeout_seconds,
        )

    def invocation_logs(self) -> tuple[InvocationLogEntry, ...]:
        return tuple(self._invocation_logs)

    def registered_tool_names(self) -> tuple[str, ...]:
        return tuple(self._registry.keys())

    def tool_schema(self, name: str) -> dict[str, Any]:
        normalized_name = _expect_non_empty_string(name, name="name")
        registered = self._registry.get(normalized_name)
        if registered is None:
            raise FunctionCallingAdapterError(f"tool '{normalized_name}' is not registered")
        return _copy_json_schema(registered.args_schema)

    def _invoke_callable(
        self,
        *,
        registered: _CallableTool,
        correlation_id: str,
        tool_name: str,
        request: dict[str, Any],
        started_at: str,
    ) -> ToolInvocationResult:
        try:
            output = registered.handler(_copy_json(request))
            status = "success"
            error = None
            timed_out = False
            result_payload = _copy_json(output)
        except Exception as exc:  # pragma: no cover - defensive runtime path
            status = "error"
            error = f"{exc.__class__.__name__}: {exc}"
            timed_out = False
            result_payload = None

        finished_at = _utc_now()
        result = ToolInvocationResult(
            correlation_id=correlation_id,
            tool_name=tool_name,
            status=status,
            request=request,
            result=result_payload,
            error=error,
            timed_out=timed_out,
        )
        self._append_log(result=result, started_at=started_at, finished_at=finished_at)
        return result

    def _invoke_command(
        self,
        *,
        registered: _CommandTool,
        correlation_id: str,
        tool_name: str,
        request: dict[str, Any],
        started_at: str,
        timeout_seconds: float | None,
    ) -> ToolInvocationResult:
        try:
            command = tuple(registered.build_command(_copy_json(request)))
        except Exception as exc:  # pragma: no cover - defensive runtime path
            finished_at = _utc_now()
            result = ToolInvocationResult(
                correlation_id=correlation_id,
                tool_name=tool_name,
                status="error",
                request=request,
                result=None,
                error=f"{exc.__class__.__name__}: {exc}",
                timed_out=False,
            )
            self._append_log(result=result, started_at=started_at, finished_at=finished_at)
            return result

        normalized_timeout = _normalize_timeout(timeout_seconds)
        effective_timeout = (
            registered.default_timeout_seconds
            if normalized_timeout is None
            else normalized_timeout
        )

        execution = run_command(command=command, timeout_seconds=effective_timeout)
        result_payload = {
            "command": list(execution.command),
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "exit_status": execution.exit_status,
        }
        finished_at = execution.finished_at
        result = ToolInvocationResult(
            correlation_id=correlation_id,
            tool_name=tool_name,
            status=execution.status,
            request=request,
            result=result_payload,
            error=execution.error,
            timed_out=execution.timed_out,
        )
        self._append_log(result=result, started_at=started_at, finished_at=finished_at)
        return result

    def _append_log(
        self,
        *,
        result: ToolInvocationResult,
        started_at: str,
        finished_at: str,
    ) -> None:
        self._invocation_logs.append(
            InvocationLogEntry(
                correlation_id=result.correlation_id,
                tool_name=result.tool_name,
                request=_copy_json(result.request),
                result=_copy_json(result.result),
                status=result.status,
                error=result.error,
                started_at=started_at,
                finished_at=finished_at,
            )
        )


def _copy_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, Mapping):
        raise FunctionCallingAdapterError("args_schema must be an object")
    return _copy_json(dict(schema))


def _normalize_arguments(arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    if arguments is None:
        return {}
    if not isinstance(arguments, Mapping):
        raise FunctionCallingAdapterError("arguments must be an object")
    return _copy_json(dict(arguments))


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise FunctionCallingAdapterError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise FunctionCallingAdapterError(f"{name} must be a non-empty string")
    return normalized


def _resolve_correlation_id(correlation_id: str | None) -> str:
    if correlation_id is None:
        return f"fc-{uuid4().hex[:12]}"
    return _expect_non_empty_string(correlation_id, name="correlation_id")


def _normalize_timeout(timeout_seconds: float | None) -> float | None:
    if timeout_seconds is None:
        return None
    if timeout_seconds <= 0:
        raise FunctionCallingAdapterError("timeout_seconds must be > 0 when provided")
    return float(timeout_seconds)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
