from __future__ import annotations

import types
import unittest

from orchestrator.engine import (
    ToolOrchestrationEngine,
    create_tool_orchestration_layer,
    resolve_tool_orchestration_engine,
)
from tools.function_calling.adapter import FunctionCallingAdapter
from tools.mcp.adapter import McpAdapter


class ToolOrchestrationModeTests(unittest.TestCase):
    def _new_function_adapter(self) -> FunctionCallingAdapter:
        adapter = FunctionCallingAdapter()
        adapter.register_callable(
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
        return adapter

    def test_tool_orchestration_defaults_to_legacy_mode(self) -> None:
        selected = resolve_tool_orchestration_engine(explicit_mode=None, env={})
        self.assertEqual(selected, ToolOrchestrationEngine.LEGACY)

    def test_invalid_tool_orchestration_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_tool_orchestration_engine(explicit_mode="experimental", env={})

        self.assertIn("unsupported tool orchestration engine", str(ctx.exception))
        self.assertIn("legacy", str(ctx.exception))
        self.assertIn("langchain", str(ctx.exception))

    def test_factory_produces_langchain_mode_when_dependency_available(self) -> None:
        layer = create_tool_orchestration_layer(
            function_calling_adapter=self._new_function_adapter(),
            mcp_adapter=McpAdapter(),
            explicit_mode="langchain",
            import_module=lambda _name: types.SimpleNamespace(__name__="langchain"),
        )

        status = layer.mode_status()
        self.assertEqual(status.requested_mode, ToolOrchestrationEngine.LANGCHAIN.value)
        self.assertEqual(status.active_mode, ToolOrchestrationEngine.LANGCHAIN.value)
        self.assertIsNone(status.fallback_reason)

    def test_factory_falls_back_to_legacy_when_langchain_unavailable(self) -> None:
        layer = create_tool_orchestration_layer(
            function_calling_adapter=self._new_function_adapter(),
            mcp_adapter=McpAdapter(),
            explicit_mode="langchain",
            import_module=lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)),
        )

        status = layer.mode_status()
        self.assertEqual(status.requested_mode, ToolOrchestrationEngine.LANGCHAIN.value)
        self.assertEqual(status.active_mode, ToolOrchestrationEngine.LEGACY.value)
        self.assertIn("requires optional dependency", status.fallback_reason or "")

        result = layer.invoke_function_tool(
            task_id="DKT-032",
            run_id="RUN-FALLBACK",
            step_id="S1",
            tool_name="sum",
            arguments={"left": 1, "right": 2},
        )
        self.assertEqual(result.status, "success")


if __name__ == "__main__":
    unittest.main()
