from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.agent_tools import agent_tools_openai_schema, register_agent_tools
from tools.function_calling.adapter import FunctionCallingAdapter
from tools.workspace import Workspace


class AgentToolsTests(unittest.TestCase):
    def _new_adapter_and_workspace(self) -> tuple[FunctionCallingAdapter, Workspace, Path]:
        root_context = tempfile.TemporaryDirectory()
        self.addCleanup(root_context.cleanup)
        root = Path(root_context.name)
        workspace = Workspace(root=root)
        adapter = FunctionCallingAdapter()
        register_agent_tools(adapter=adapter, workspace=workspace)
        return adapter, workspace, root

    def test_write_file_creates_file(self) -> None:
        adapter, _workspace, root = self._new_adapter_and_workspace()

        result = adapter.invoke(
            tool_name="write_file",
            arguments={"path": "notes/hello.txt", "content": "hello"},
            correlation_id="corr-write",
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result, {"path": "notes/hello.txt", "bytes_written": 5})
        self.assertEqual((root / "notes" / "hello.txt").read_text(encoding="utf-8"), "hello")

    def test_read_file_returns_content(self) -> None:
        adapter, _workspace, root = self._new_adapter_and_workspace()
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "summary.md").write_text("done", encoding="utf-8")

        result = adapter.invoke(
            tool_name="read_file",
            arguments={"path": "docs/summary.md"},
            correlation_id="corr-read",
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result, {"path": "docs/summary.md", "content": "done"})

    def test_execute_command_returns_output(self) -> None:
        adapter, _workspace, _root = self._new_adapter_and_workspace()

        result = adapter.invoke(
            tool_name="execute_command",
            arguments={"command": "printf 'ok'"},
            correlation_id="corr-cmd",
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result["stdout"], "ok")
        self.assertEqual(result.result["stderr"], "")
        self.assertEqual(result.result["exit_status"], 0)

    def test_write_file_escape_blocked(self) -> None:
        adapter, _workspace, _root = self._new_adapter_and_workspace()

        result = adapter.invoke(
            tool_name="write_file",
            arguments={"path": "../outside.txt", "content": "blocked"},
            correlation_id="corr-escape",
        )

        self.assertEqual(result.status, "error")
        self.assertIn("path escapes workspace", result.error or "")

    def test_agent_tools_openai_schema_format(self) -> None:
        adapter, _workspace, _root = self._new_adapter_and_workspace()

        schema = agent_tools_openai_schema(adapter)

        self.assertEqual(len(schema), 3)
        names = {item["function"]["name"] for item in schema}
        self.assertEqual(names, {"write_file", "read_file", "execute_command"})
        for item in schema:
            self.assertEqual(item["type"], "function")
            self.assertIsInstance(item["function"]["parameters"], dict)


if __name__ == "__main__":
    unittest.main()
