from __future__ import annotations

import json
from pathlib import Path
import tempfile
import types
import unittest
from typing import Any, Callable, Mapping

from hooks.runtime import HookRuntime
from skills.loader import SkillLoader
from tools.function_calling.adapter import FunctionCallingAdapter
from tools.langchain.orchestration import ToolOrchestrationLayer, ToolOrchestrationMode
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

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools)

    def call_tool(self, *, name: str, arguments: Mapping[str, Any]) -> Any:
        return self._call_handler(name, dict(arguments))


def _write_skill_with_hook(root: Path) -> None:
    skill_dir = root / "audit-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "hook_impl.py").write_text(
        (
            "def before_dispatch(ledger_state, context):\n"
            "    ledger_state['skill_hook_ran'] = True\n"
            "    ledger_state['skill_context'] = context.get('flag')\n"
        ),
        encoding="utf-8",
    )
    (skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "name": "audit-skill",
                "version": "0.1.0",
                "hooks": [
                    {
                        "event": "pre-dispatch",
                        "handler": "hook_impl.py:before_dispatch",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class LangChainToolOrchestrationTests(unittest.TestCase):
    def test_langchain_mode_traces_preserve_task_run_step_correlation(self) -> None:
        function_adapter = FunctionCallingAdapter()
        function_adapter.register_callable(
            name="sum",
            args_schema={
                "type": "object",
                "properties": {
                    "left": {"type": "integer"},
                    "right": {"type": "integer"},
                },
                "required": ["left", "right"],
                "additionalProperties": False,
            },
            handler=lambda arguments: {
                "sum": int(arguments["left"]) + int(arguments["right"]),
            },
        )

        mcp_adapter = McpAdapter()
        mcp_adapter.register_server(
            name="docs",
            client=_FakeMcpServer(
                tools=[
                    {
                        "name": "lookup",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                            "additionalProperties": False,
                        },
                    }
                ],
                call_handler=lambda _name, arguments: {"hits": [arguments["query"]]},
            ),
        )
        mcp_adapter.refresh_capabilities()

        layer = ToolOrchestrationLayer(
            function_calling_adapter=function_adapter,
            mcp_adapter=mcp_adapter,
            requested_mode=ToolOrchestrationMode.LANGCHAIN.value,
            import_module=lambda _name: types.SimpleNamespace(__name__="langchain"),
        )

        fc_result = layer.invoke_function_tool(
            task_id="DKT-032",
            run_id="RUN-1",
            step_id="S1",
            tool_name="sum",
            arguments={"left": 2, "right": 3},
        )
        self.assertEqual(fc_result.status, "success")

        mcp_result = layer.invoke_mcp_tool(
            task_id="DKT-032",
            run_id="RUN-1",
            step_id="S1",
            server_name="docs",
            tool_name="lookup",
            arguments={"query": "langchain"},
        )
        self.assertEqual(mcp_result.status, "success")

        traces = layer.trace_logs()
        self.assertEqual(len(traces), 2)
        for entry in traces:
            self.assertEqual(entry.task_id, "DKT-032")
            self.assertEqual(entry.run_id, "RUN-1")
            self.assertEqual(entry.step_id, "S1")
            self.assertEqual(entry.orchestration_mode, ToolOrchestrationMode.LANGCHAIN.value)
            self.assertTrue(entry.correlation_id)

    def test_reuses_existing_function_mcp_skill_and_hook_contracts(self) -> None:
        function_adapter = FunctionCallingAdapter()
        function_adapter.register_callable(
            name="echo",
            args_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
                "additionalProperties": False,
            },
            handler=lambda arguments: {"echo": arguments["message"]},
        )

        mcp_adapter = McpAdapter()
        mcp_adapter.register_server(
            name="svc",
            client=_FakeMcpServer(
                tools=[
                    {
                        "name": "ping",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    }
                ],
                call_handler=lambda _name, _arguments: {"pong": True},
            ),
        )
        mcp_adapter.refresh_capabilities()

        hook_runtime = HookRuntime()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_skill_with_hook(root)
            skill_loader = SkillLoader(search_paths=[root])

            layer = ToolOrchestrationLayer(
                function_calling_adapter=function_adapter,
                mcp_adapter=mcp_adapter,
                hook_runtime=hook_runtime,
                skill_loader=skill_loader,
                requested_mode=ToolOrchestrationMode.LANGCHAIN.value,
                import_module=lambda _name: types.SimpleNamespace(__name__="langchain"),
            )

            self.assertIs(layer.adapters.function_calling, function_adapter)
            self.assertIs(layer.adapters.mcp, mcp_adapter)
            self.assertIs(layer.adapters.hooks, hook_runtime)
            self.assertIs(layer.adapters.skills, skill_loader)

            loaded = layer.load_skill(
                task_id="DKT-032",
                run_id="RUN-2",
                step_id="S1",
                skill_name="audit-skill",
            )
            self.assertEqual(loaded.manifest.name, "audit-skill")

            hook_result = layer.run_hook(
                task_id="DKT-032",
                run_id="RUN-2",
                step_id="S1",
                hook_point="pre-dispatch",
                ledger_state={},
                context={"flag": "ok"},
            )
            self.assertEqual(hook_result.status, "success")
            self.assertTrue(hook_result.ledger_state["skill_hook_ran"])
            self.assertEqual(hook_result.ledger_state["skill_context"], "ok")

            fc_result = layer.invoke_function_tool(
                task_id="DKT-032",
                run_id="RUN-2",
                step_id="S1",
                tool_name="echo",
                arguments={"message": "hello"},
            )
            self.assertEqual(fc_result.result, {"echo": "hello"})

            mcp_result = layer.invoke_mcp_tool(
                task_id="DKT-032",
                run_id="RUN-2",
                step_id="S1",
                server_name="svc",
                tool_name="ping",
                arguments={},
            )
            self.assertEqual(mcp_result.result, {"pong": True})

    def test_missing_langchain_dependency_falls_back_to_legacy_mode(self) -> None:
        function_adapter = FunctionCallingAdapter()
        function_adapter.register_callable(
            name="sum",
            args_schema={
                "type": "object",
                "properties": {
                    "left": {"type": "integer"},
                    "right": {"type": "integer"},
                },
                "required": ["left", "right"],
                "additionalProperties": False,
            },
            handler=lambda arguments: {
                "sum": int(arguments["left"]) + int(arguments["right"]),
            },
        )

        layer = ToolOrchestrationLayer(
            function_calling_adapter=function_adapter,
            mcp_adapter=McpAdapter(),
            requested_mode=ToolOrchestrationMode.LANGCHAIN.value,
            import_module=lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)),
        )

        status = layer.mode_status()
        self.assertEqual(status.requested_mode, ToolOrchestrationMode.LANGCHAIN.value)
        self.assertEqual(status.active_mode, ToolOrchestrationMode.LEGACY.value)
        self.assertIn("requires optional dependency", status.fallback_reason or "")

        result = layer.invoke_function_tool(
            task_id="DKT-032",
            run_id="RUN-3",
            step_id="S1",
            tool_name="sum",
            arguments={"left": 4, "right": 6},
        )
        self.assertEqual(result.status, "success")

        trace = layer.trace_logs()[0]
        self.assertEqual(trace.orchestration_mode, ToolOrchestrationMode.LEGACY.value)


if __name__ == "__main__":
    unittest.main()
