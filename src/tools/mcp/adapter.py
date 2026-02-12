from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from tools.common.json_schema import JsonSchemaValidationError, validate_json_schema


class McpAdapterError(ValueError):
    """Raised when MCP adapter configuration is invalid."""


class McpServerClient(Protocol):
    def list_tools(self) -> Sequence[Mapping[str, Any]]:
        """Return tool descriptors available from this MCP server."""

    def call_tool(self, *, name: str, arguments: Mapping[str, Any]) -> Any:
        """Invoke one MCP tool and return response payload."""


@dataclass(frozen=True)
class McpToolCapability:
    server_name: str
    tool_name: str
    qualified_name: str
    description: str | None
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class McpCallTraceEntry:
    attempt: int
    started_at: str
    finished_at: str
    status: str
    request: dict[str, Any]
    response: Any | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True)
class McpInvocationResult:
    correlation_id: str
    server_name: str
    tool_name: str
    status: str
    request: dict[str, Any]
    result: Any | None
    error_code: str | None
    error_message: str | None
    error_action: str | None
    attempt_count: int
    trace: tuple[McpCallTraceEntry, ...]


@dataclass(frozen=True)
class McpInvocationLogEntry:
    correlation_id: str
    server_name: str
    tool_name: str
    status: str
    request: dict[str, Any]
    result: Any | None
    error_code: str | None
    error_message: str | None
    error_action: str | None
    attempt_count: int
    trace: tuple[McpCallTraceEntry, ...]
    started_at: str
    finished_at: str


class McpAdapter:
    """External MCP tool adapter with capability discovery and traceable invocations."""

    def __init__(self, *, max_retries: int = 0) -> None:
        self._servers: dict[str, McpServerClient] = {}
        self._capabilities: dict[str, dict[str, McpToolCapability]] = {}
        self._invocation_logs: list[McpInvocationLogEntry] = []
        self._default_max_retries = _normalize_retry_count(max_retries)

    def register_server(self, *, name: str, client: McpServerClient) -> None:
        normalized_name = _expect_non_empty_string(name, name="name")
        _validate_server_client(client)
        if normalized_name in self._servers:
            raise McpAdapterError(f"server '{normalized_name}' is already registered")
        self._servers[normalized_name] = client
        self._capabilities.pop(normalized_name, None)

    def refresh_capabilities(
        self,
        *,
        server_name: str | None = None,
    ) -> dict[str, tuple[McpToolCapability, ...]]:
        normalized_server_name = _normalize_optional_server_name(server_name)
        target_servers = (
            [normalized_server_name]
            if normalized_server_name is not None
            else sorted(self._servers)
        )

        refreshed: dict[str, tuple[McpToolCapability, ...]] = {}
        for name in target_servers:
            server = self._servers.get(name)
            if server is None:
                raise McpAdapterError(f"server '{name}' is not registered")

            try:
                raw_tools = server.list_tools()
            except Exception as exc:
                raise McpAdapterError(
                    f"failed to discover tools from server '{name}': "
                    f"{exc.__class__.__name__}: {exc}"
                ) from exc

            normalized_tools = _normalize_tool_descriptors(server_name=name, raw_tools=raw_tools)
            self._capabilities[name] = {tool.tool_name: tool for tool in normalized_tools}
            refreshed[name] = tuple(normalized_tools)

        return refreshed

    def list_tools(
        self,
        *,
        server_name: str | None = None,
        refresh: bool = False,
    ) -> tuple[McpToolCapability, ...]:
        normalized_server_name = _normalize_optional_server_name(server_name)

        if refresh:
            self.refresh_capabilities(server_name=normalized_server_name)

        if normalized_server_name is not None:
            self._ensure_capabilities_loaded(server_name=normalized_server_name)
            server_tools = self._capabilities.get(normalized_server_name, {})
            return tuple(sorted(server_tools.values(), key=lambda item: item.qualified_name))

        # Make list deterministic even if discovery was partial earlier.
        for name in sorted(self._servers):
            self._ensure_capabilities_loaded(server_name=name)

        tools = [
            tool
            for server_tools in self._capabilities.values()
            for tool in server_tools.values()
        ]
        return tuple(sorted(tools, key=lambda item: item.qualified_name))

    def capability_map(self) -> dict[str, tuple[McpToolCapability, ...]]:
        mapped: dict[str, tuple[McpToolCapability, ...]] = {}
        for server_name in sorted(self._capabilities):
            mapped[server_name] = tuple(
                sorted(
                    self._capabilities[server_name].values(),
                    key=lambda item: item.qualified_name,
                )
            )
        return mapped

    def invoke(
        self,
        *,
        server_name: str,
        tool_name: str,
        arguments: Mapping[str, Any] | None,
        correlation_id: str | None = None,
        max_retries: int | None = None,
    ) -> McpInvocationResult:
        normalized_server_name = _expect_non_empty_string(server_name, name="server_name")
        normalized_tool_name = _expect_non_empty_string(tool_name, name="tool_name")
        normalized_correlation_id = _resolve_correlation_id(correlation_id)
        normalized_retries = _normalize_retry_count(max_retries)
        if normalized_retries is None:
            normalized_retries = self._default_max_retries

        started_at = _utc_now()

        try:
            request = _normalize_arguments(arguments)
        except McpAdapterError as exc:
            finished_at = _utc_now()
            return self._error_result(
                correlation_id=normalized_correlation_id,
                server_name=normalized_server_name,
                tool_name=normalized_tool_name,
                request={},
                error_code="invalid_arguments",
                error_message=str(exc),
                error_action="provide a JSON object for arguments and retry",
                started_at=started_at,
                finished_at=finished_at,
                trace=(),
            )

        server = self._servers.get(normalized_server_name)
        if server is None:
            finished_at = _utc_now()
            return self._error_result(
                correlation_id=normalized_correlation_id,
                server_name=normalized_server_name,
                tool_name=normalized_tool_name,
                request=request,
                error_code="server_not_found",
                error_message=f"server '{normalized_server_name}' is not registered",
                error_action="register the MCP server before invoking tools",
                started_at=started_at,
                finished_at=finished_at,
                trace=(),
            )

        try:
            self._ensure_capabilities_loaded(server_name=normalized_server_name)
        except McpAdapterError as exc:
            finished_at = _utc_now()
            return self._error_result(
                correlation_id=normalized_correlation_id,
                server_name=normalized_server_name,
                tool_name=normalized_tool_name,
                request=request,
                error_code="discovery_failed",
                error_message=str(exc),
                error_action="check MCP server connectivity, then refresh capabilities",
                started_at=started_at,
                finished_at=finished_at,
                trace=(),
            )

        capability = self._capabilities.get(normalized_server_name, {}).get(normalized_tool_name)
        if capability is None:
            available = sorted(self._capabilities.get(normalized_server_name, {}).keys())
            finished_at = _utc_now()
            return self._error_result(
                correlation_id=normalized_correlation_id,
                server_name=normalized_server_name,
                tool_name=normalized_tool_name,
                request=request,
                error_code="tool_not_found",
                error_message=(
                    f"tool '{normalized_tool_name}' is not available on server "
                    f"'{normalized_server_name}'. Available tools: {available}"
                ),
                error_action="call list_tools() and pick a valid tool name",
                started_at=started_at,
                finished_at=finished_at,
                trace=(),
            )

        try:
            validate_json_schema(schema=capability.input_schema, payload=request)
        except JsonSchemaValidationError as exc:
            finished_at = _utc_now()
            return self._error_result(
                correlation_id=normalized_correlation_id,
                server_name=normalized_server_name,
                tool_name=normalized_tool_name,
                request=request,
                error_code="invalid_arguments",
                error_message=str(exc),
                error_action="fix argument schema mismatch and retry",
                started_at=started_at,
                finished_at=finished_at,
                trace=(),
            )

        trace_entries: list[McpCallTraceEntry] = []
        last_error_message: str | None = None

        total_attempts = normalized_retries + 1
        for attempt in range(1, total_attempts + 1):
            trace_started_at = _utc_now()
            try:
                response = server.call_tool(
                    name=normalized_tool_name,
                    arguments=_copy_json(request),
                )
            except Exception as exc:
                trace_finished_at = _utc_now()
                error_message = (
                    f"attempt {attempt}/{total_attempts} failed: "
                    f"{exc.__class__.__name__}: {exc}"
                )
                last_error_message = error_message
                trace_entries.append(
                    McpCallTraceEntry(
                        attempt=attempt,
                        started_at=trace_started_at,
                        finished_at=trace_finished_at,
                        status="error",
                        request=_copy_json(request),
                        response=None,
                        error_code="remote_call_failed",
                        error_message=error_message,
                    )
                )
                continue

            trace_finished_at = _utc_now()
            copied_response = _copy_json(response)
            trace_entries.append(
                McpCallTraceEntry(
                    attempt=attempt,
                    started_at=trace_started_at,
                    finished_at=trace_finished_at,
                    status="success",
                    request=_copy_json(request),
                    response=copied_response,
                    error_code=None,
                    error_message=None,
                )
            )
            finished_at = _utc_now()
            result = McpInvocationResult(
                correlation_id=normalized_correlation_id,
                server_name=normalized_server_name,
                tool_name=normalized_tool_name,
                status="success",
                request=_copy_json(request),
                result=copied_response,
                error_code=None,
                error_message=None,
                error_action=None,
                attempt_count=len(trace_entries),
                trace=tuple(trace_entries),
            )
            self._append_log(result=result, started_at=started_at, finished_at=finished_at)
            return result

        finished_at = _utc_now()
        final_error = (
            f"{last_error_message}; attempted {total_attempts} time(s). "
            "check MCP server health, credentials, and tool-level parameters"
        )
        return self._error_result(
            correlation_id=normalized_correlation_id,
            server_name=normalized_server_name,
            tool_name=normalized_tool_name,
            request=request,
            error_code="remote_call_failed",
            error_message=final_error,
            error_action="check MCP server health and retry when upstream is stable",
            started_at=started_at,
            finished_at=finished_at,
            trace=tuple(trace_entries),
        )

    def invocation_logs(self) -> tuple[McpInvocationLogEntry, ...]:
        return tuple(self._invocation_logs)

    def _error_result(
        self,
        *,
        correlation_id: str,
        server_name: str,
        tool_name: str,
        request: dict[str, Any],
        error_code: str,
        error_message: str,
        error_action: str,
        started_at: str,
        finished_at: str,
        trace: tuple[McpCallTraceEntry, ...],
    ) -> McpInvocationResult:
        result = McpInvocationResult(
            correlation_id=correlation_id,
            server_name=server_name,
            tool_name=tool_name,
            status="error",
            request=_copy_json(request),
            result=None,
            error_code=error_code,
            error_message=error_message,
            error_action=error_action,
            attempt_count=len(trace),
            trace=trace,
        )
        self._append_log(result=result, started_at=started_at, finished_at=finished_at)
        return result

    def _append_log(
        self,
        *,
        result: McpInvocationResult,
        started_at: str,
        finished_at: str,
    ) -> None:
        self._invocation_logs.append(
            McpInvocationLogEntry(
                correlation_id=result.correlation_id,
                server_name=result.server_name,
                tool_name=result.tool_name,
                status=result.status,
                request=_copy_json(result.request),
                result=_copy_json(result.result),
                error_code=result.error_code,
                error_message=result.error_message,
                error_action=result.error_action,
                attempt_count=result.attempt_count,
                trace=tuple(result.trace),
                started_at=started_at,
                finished_at=finished_at,
            )
        )

    def _ensure_capabilities_loaded(self, *, server_name: str) -> None:
        if server_name not in self._servers:
            raise McpAdapterError(f"server '{server_name}' is not registered")
        if server_name in self._capabilities:
            return
        self.refresh_capabilities(server_name=server_name)


def _validate_server_client(client: McpServerClient) -> None:
    list_tools = getattr(client, "list_tools", None)
    call_tool = getattr(client, "call_tool", None)
    if not callable(list_tools) or not callable(call_tool):
        raise McpAdapterError(
            "client must expose callable list_tools() and call_tool(name=..., arguments=...)"
        )


def _normalize_tool_descriptors(
    *,
    server_name: str,
    raw_tools: Sequence[Mapping[str, Any]],
) -> list[McpToolCapability]:
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, (str, bytes)):
        raise McpAdapterError(
            f"server '{server_name}' returned invalid tools payload; expected a sequence"
        )

    normalized: list[McpToolCapability] = []
    seen_names: set[str] = set()

    for index, raw_item in enumerate(raw_tools):
        if not isinstance(raw_item, Mapping):
            raise McpAdapterError(
                f"server '{server_name}' returned invalid tool descriptor at index {index}"
            )

        item = dict(raw_item)
        tool_name = _expect_non_empty_string(item.get("name"), name=f"tools[{index}].name")
        if tool_name in seen_names:
            raise McpAdapterError(
                f"server '{server_name}' returned duplicate tool name '{tool_name}'"
            )
        seen_names.add(tool_name)

        description_raw = item.get("description")
        description = None if description_raw is None else _expect_non_empty_string(
            description_raw,
            name=f"tools[{index}].description",
        )

        schema_raw = item.get("inputSchema", item.get("input_schema", {}))
        if schema_raw is None:
            schema_raw = {}
        if not isinstance(schema_raw, Mapping):
            raise McpAdapterError(
                f"server '{server_name}' returned invalid schema for tool '{tool_name}'"
            )

        schema = _copy_json(dict(schema_raw))
        if not schema:
            schema = {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }

        normalized.append(
            McpToolCapability(
                server_name=server_name,
                tool_name=tool_name,
                qualified_name=f"{server_name}.{tool_name}",
                description=description,
                input_schema=schema,
            )
        )

    return normalized


def _normalize_optional_server_name(server_name: str | None) -> str | None:
    if server_name is None:
        return None
    return _expect_non_empty_string(server_name, name="server_name")


def _normalize_arguments(arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    if arguments is None:
        return {}
    if not isinstance(arguments, Mapping):
        raise McpAdapterError("arguments must be an object")
    return _copy_json(dict(arguments))


def _resolve_correlation_id(correlation_id: str | None) -> str:
    if correlation_id is None:
        return f"mcp-{uuid4().hex[:12]}"
    return _expect_non_empty_string(correlation_id, name="correlation_id")


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise McpAdapterError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise McpAdapterError(f"{name} must be a non-empty string")
    return normalized


def _normalize_retry_count(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise McpAdapterError("max_retries must be an integer >= 0")
    if value < 0:
        raise McpAdapterError("max_retries must be >= 0")
    return value


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def _json_default(value: Any) -> Any:
    return {
        "__type__": value.__class__.__name__,
        "__repr__": repr(value),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
