from __future__ import annotations

import unittest
from typing import Any, Callable, Mapping

from tools.mcp.adapter import McpAdapter


class _FakeMcpServer:
    def __init__(
        self,
        *,
        tools: list[dict[str, Any]],
        call_handler: Callable[[str, dict[str, Any]], Any],
    ) -> None:
        self._tools = tools
        self._call_handler = call_handler
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools)

    def call_tool(self, *, name: str, arguments: Mapping[str, Any]) -> Any:
        copied = dict(arguments)
        self.calls.append((name, copied))
        return self._call_handler(name, copied)


class McpAdapterTests(unittest.TestCase):
    def test_tools_can_be_listed_and_invoked(self) -> None:
        adapter = McpAdapter()
        server = _FakeMcpServer(
            tools=[
                {
                    "name": "search_docs",
                    "description": "Search indexed docs",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            ],
            call_handler=lambda name, arguments: {
                "tool": name,
                "query": arguments["query"],
                "count": 2,
            },
        )

        adapter.register_server(name="docs", client=server)
        adapter.refresh_capabilities()
        capabilities = adapter.list_tools()

        self.assertEqual(len(capabilities), 1)
        self.assertEqual(capabilities[0].qualified_name, "docs.search_docs")

        result = adapter.invoke(
            server_name="docs",
            tool_name="search_docs",
            arguments={"query": "MCP"},
            correlation_id="mcp-corr-1",
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result, {"tool": "search_docs", "query": "MCP", "count": 2})
        self.assertEqual(result.attempt_count, 1)
        self.assertEqual(server.calls, [("search_docs", {"query": "MCP"})])

    def test_failed_calls_return_actionable_errors(self) -> None:
        adapter = McpAdapter(max_retries=1)
        server = _FakeMcpServer(
            tools=[
                {
                    "name": "query_db",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "sql": {"type": "string"},
                        },
                        "required": ["sql"],
                        "additionalProperties": False,
                    },
                },
            ],
            call_handler=lambda _name, _arguments: (_ for _ in ()).throw(RuntimeError("database unavailable")),
        )

        adapter.register_server(name="db", client=server)
        adapter.refresh_capabilities()

        result = adapter.invoke(
            server_name="db",
            tool_name="query_db",
            arguments={"sql": "SELECT 1"},
            correlation_id="mcp-corr-2",
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_code, "remote_call_failed")
        self.assertIn("database unavailable", result.error_message or "")
        self.assertIn("attempted 2 time(s)", result.error_message or "")
        self.assertIn("check MCP server health", result.error_action or "")

    def test_trace_is_persisted_for_each_attempt(self) -> None:
        adapter = McpAdapter(max_retries=1)
        attempts = {"count": 0}

        def flaky_call(_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise TimeoutError("upstream timeout")
            return {"ok": True, "input": arguments["value"]}

        server = _FakeMcpServer(
            tools=[
                {
                    "name": "unstable",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "integer"},
                        },
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                },
            ],
            call_handler=flaky_call,
        )

        adapter.register_server(name="unstable-svc", client=server)
        adapter.refresh_capabilities()

        result = adapter.invoke(
            server_name="unstable-svc",
            tool_name="unstable",
            arguments={"value": 7},
            correlation_id="mcp-corr-3",
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.attempt_count, 2)
        self.assertEqual(len(result.trace), 2)
        self.assertEqual(result.trace[0].status, "error")
        self.assertEqual(result.trace[1].status, "success")

        logs = adapter.invocation_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].correlation_id, "mcp-corr-3")
        self.assertEqual(logs[0].status, "success")
        self.assertEqual(len(logs[0].trace), 2)
        self.assertEqual(logs[0].trace[0].error_code, "remote_call_failed")
        self.assertEqual(logs[0].trace[1].response, {"ok": True, "input": 7})


if __name__ == "__main__":
    unittest.main()
