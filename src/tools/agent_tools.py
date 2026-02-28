from __future__ import annotations

from typing import Any

from tools.common.command_runner import run_command
from tools.function_calling.adapter import FunctionCallingAdapter
from tools.workspace import Workspace


WRITE_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "minLength": 1},
        "content": {"type": "string"},
    },
    "required": ["path", "content"],
    "additionalProperties": False,
}

READ_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "minLength": 1},
    },
    "required": ["path"],
    "additionalProperties": False,
}

EXECUTE_COMMAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "minLength": 1},
        "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
    },
    "required": ["command"],
    "additionalProperties": False,
}


def register_agent_tools(adapter: FunctionCallingAdapter, workspace: Workspace) -> None:
    def _write_file(arguments: dict[str, Any]) -> dict[str, Any]:
        path = str(arguments["path"])
        content = str(arguments["content"])
        resolved = workspace.resolve(path)
        workspace.ensure_parent(resolved)
        resolved.write_text(content, encoding="utf-8")
        return {
            "path": path,
            "bytes_written": len(content.encode("utf-8")),
        }

    def _read_file(arguments: dict[str, Any]) -> dict[str, Any]:
        path = str(arguments["path"])
        resolved = workspace.resolve(path)
        text = resolved.read_text(encoding="utf-8")
        return {
            "path": path,
            "content": text,
        }

    def _execute_command(arguments: dict[str, Any]) -> dict[str, Any]:
        timeout_raw = arguments.get("timeout_seconds", 30)
        timeout_seconds = float(timeout_raw)
        execution = run_command(
            command=["/bin/sh", "-c", str(arguments["command"])],
            cwd=str(workspace.root),
            timeout_seconds=timeout_seconds,
        )
        return {
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "exit_status": execution.exit_status,
        }

    adapter.register_callable(
        name="write_file",
        args_schema=WRITE_FILE_SCHEMA,
        handler=_write_file,
    )
    adapter.register_callable(
        name="read_file",
        args_schema=READ_FILE_SCHEMA,
        handler=_read_file,
    )
    adapter.register_callable(
        name="execute_command",
        args_schema=EXECUTE_COMMAND_SCHEMA,
        handler=_execute_command,
    )


def agent_tools_openai_schema(adapter: FunctionCallingAdapter) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "parameters": adapter.tool_schema(name),
            },
        }
        for name in adapter.registered_tool_names()
    ]


__all__ = [
    "agent_tools_openai_schema",
    "register_agent_tools",
]
