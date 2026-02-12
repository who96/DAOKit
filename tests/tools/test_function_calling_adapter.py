from __future__ import annotations

import sys
import unittest

from tools.function_calling.adapter import FunctionCallingAdapter


class FunctionCallingAdapterTests(unittest.TestCase):
    def test_invalid_args_rejected_before_execution(self) -> None:
        adapter = FunctionCallingAdapter()
        executed: list[dict[str, object]] = []

        def handler(arguments: dict[str, object]) -> dict[str, object]:
            executed.append(arguments)
            return {"echo": arguments["message"]}

        adapter.register_callable(
            name="echo",
            args_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            handler=handler,
        )

        result = adapter.invoke(
            tool_name="echo",
            arguments={"message": 123},
            correlation_id="corr-invalid",
        )

        self.assertEqual(result.status, "validation_error")
        self.assertEqual(executed, [])
        self.assertIn("must be of type 'string'", result.error or "")

        logs = adapter.invocation_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].correlation_id, "corr-invalid")
        self.assertEqual(logs[0].status, "validation_error")
        self.assertEqual(logs[0].request, {"message": 123})
        self.assertIsNone(logs[0].result)

    def test_timeout_is_handled_and_recorded(self) -> None:
        adapter = FunctionCallingAdapter()

        adapter.register_command(
            name="sleepy",
            args_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            build_command=lambda _arguments: [
                sys.executable,
                "-c",
                "import time; time.sleep(0.25)",
            ],
            default_timeout_seconds=0.05,
        )

        result = adapter.invoke(
            tool_name="sleepy",
            arguments={},
            correlation_id="corr-timeout",
        )

        self.assertEqual(result.status, "timeout")
        self.assertTrue(result.timed_out)
        self.assertIsNotNone(result.error)

        logs = adapter.invocation_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].correlation_id, "corr-timeout")
        self.assertEqual(logs[0].status, "timeout")
        self.assertEqual(logs[0].request, {})
        self.assertIn("timed out", logs[0].error or "")

    def test_invocation_logs_include_request_result_and_status(self) -> None:
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

        result = adapter.invoke(
            tool_name="sum",
            arguments={"left": 2, "right": 5},
            correlation_id="corr-success",
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result, {"sum": 7})
        self.assertFalse(result.timed_out)

        logs = adapter.invocation_logs()
        self.assertEqual(len(logs), 1)
        entry = logs[0]
        self.assertEqual(entry.correlation_id, "corr-success")
        self.assertEqual(entry.request, {"left": 2, "right": 5})
        self.assertEqual(entry.result, {"sum": 7})
        self.assertEqual(entry.status, "success")


if __name__ == "__main__":
    unittest.main()
