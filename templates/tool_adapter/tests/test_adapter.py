from __future__ import annotations

import unittest

from adapter import ToolAdapterTemplate


class ToolAdapterTemplateExampleTests(unittest.TestCase):
    def test_register_and_invoke_success(self) -> None:
        adapter = ToolAdapterTemplate()
        adapter.register_tool(
            name="echo",
            handler=lambda arguments: {"echo": arguments["message"]},
        )

        result = adapter.invoke(tool_name="echo", arguments={"message": "hello"})

        self.assertEqual(result.status, "success")
        self.assertEqual(result.output, {"echo": "hello"})
        self.assertIsNone(result.error)

    def test_unknown_tool_returns_error(self) -> None:
        adapter = ToolAdapterTemplate()

        result = adapter.invoke(tool_name="unknown", arguments={})

        self.assertEqual(result.status, "error")
        self.assertIsNone(result.output)
        self.assertIn("not registered", result.error or "")

    @unittest.skip("Replace this placeholder with adapter-specific validation tests.")
    def test_adapter_specific_validation_rules(self) -> None:
        raise AssertionError("replace with adapter-specific assertions")


if __name__ == "__main__":
    unittest.main()
