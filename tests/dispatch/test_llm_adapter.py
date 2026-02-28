from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from artifacts.dispatch_artifacts import DispatchArtifactStore
from dispatch.llm_adapter import LLMDispatchAdapter
from llm.client import LLMCallError, LLMCompletionResult, LLMConfig


class _FakeLLMClient:
    """Deterministic LLMClient test double."""

    def __init__(
        self,
        *,
        content: str = "implementation complete",
        model: str = "test-model",
        config: LLMConfig | None = None,
    ) -> None:
        self._content = content
        self._model = model
        self._config = config or LLMConfig(api_key="test-key", model=model)
        self.calls: list[list[dict[str, object]]] = []
        self.tools_calls: list[list[dict[str, object]] | None] = []

    @property
    def config(self) -> LLMConfig:
        return self._config

    def chat_completion(
        self,
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> LLMCompletionResult:
        self.calls.append(messages)
        self.tools_calls.append(tools)
        return LLMCompletionResult(
            content=self._content,
            model=self._model,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            finish_reason="stop",
            raw_response={"id": "fake"},
        )


class _RaisingLLMClient(_FakeLLMClient):
    def chat_completion(
        self,
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> LLMCompletionResult:
        self.calls.append(messages)
        self.tools_calls.append(tools)
        raise LLMCallError("llm error")


class _SequenceLLMClient(_FakeLLMClient):
    def __init__(
        self,
        *,
        completions: list[LLMCompletionResult],
        config: LLMConfig | None = None,
    ) -> None:
        model = completions[0].model if completions else "test-model"
        super().__init__(content="", model=model, config=config)
        self._completions = list(completions)

    def chat_completion(
        self,
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> LLMCompletionResult:
        self.calls.append(messages)
        self.tools_calls.append(tools)
        if not self._completions:
            raise AssertionError("no scripted completion left")
        return self._completions.pop(0)


class _ToolInvocationResult:
    def __init__(self, *, result: dict[str, object]) -> None:
        self.result = result


class _FakeToolOrchestrationLayer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def invoke_function_tool(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        tool_name: str,
        arguments: dict[str, object] | None,
        correlation_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> _ToolInvocationResult:
        self.calls.append(
            {
                "task_id": task_id,
                "run_id": run_id,
                "step_id": step_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "correlation_id": correlation_id,
                "timeout_seconds": timeout_seconds,
            }
        )
        return _ToolInvocationResult(result={"ok": True, "tool_name": tool_name, "arguments": arguments or {}})


class LLMDispatchAdapterTests(unittest.TestCase):
    def test_create_dry_run_does_not_call_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _FakeLLMClient()
            adapter = self._build_adapter(root=Path(tmp), llm_client=llm_client)

            result = adapter.create(
                task_id="DKT-200",
                run_id="DKT-200_RUN",
                step_id="S1",
                request={"step_title": "do thing"},
                dry_run=True,
            )

            self.assertEqual(result.status, "success")
            self.assertEqual(result.parsed_output.get("execution_mode"), "dry_run")
            self.assertEqual(result.parsed_output.get("llm_invoked"), False)
            self.assertEqual(llm_client.calls, [])

    def test_create_calls_llm_and_returns_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _FakeLLMClient(content="done")
            adapter = self._build_adapter(root=Path(tmp), llm_client=llm_client)

            result = adapter.create(
                task_id="DKT-201",
                run_id="DKT-201_RUN",
                step_id="S1",
                request={"step_title": "Implement adapter"},
                dry_run=False,
            )

            self.assertEqual(result.status, "success")
            self.assertEqual(result.parsed_output.get("execution_mode"), "llm_direct")
            self.assertEqual(result.parsed_output.get("llm_invoked"), True)
            self.assertEqual(result.parsed_output.get("message"), "done")
            self.assertEqual(len(llm_client.calls), 1)

    def test_every_call_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _FakeLLMClient()
            adapter = self._build_adapter(root=Path(tmp), llm_client=llm_client)

            create_result = adapter.create(
                task_id="DKT-202",
                run_id="DKT-202_RUN",
                step_id="S1",
                request={"step_title": "Create"},
            )
            resume_result = adapter.resume(
                task_id="DKT-202",
                run_id="DKT-202_RUN",
                step_id="S1",
                request={"step_title": "Resume"},
            )
            rework_result = adapter.rework(
                task_id="DKT-202",
                run_id="DKT-202_RUN",
                step_id="S1",
                request={"step_title": "Rework"},
                rework_context={"failed_calls": [{"action": "create", "status": "error"}]},
            )

            for result in (create_result, resume_result, rework_result):
                self.assertTrue(result.artifacts.request_path.is_file())
                self.assertTrue(result.artifacts.output_path.is_file())
                self.assertTrue(result.artifacts.error_path.is_file())

    def test_thread_id_stable_across_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = self._build_adapter(root=Path(tmp), llm_client=_FakeLLMClient())

            create_result = adapter.create(task_id="DKT-203", run_id="RUN-1", step_id="S1")
            resume_result = adapter.resume(task_id="DKT-203", run_id="RUN-1", step_id="S1")

            self.assertEqual(create_result.thread_id, resume_result.thread_id)

    def test_correlation_id_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = self._build_adapter(root=Path(tmp), llm_client=_FakeLLMClient())

            create_result = adapter.create(task_id="DKT-204", run_id="RUN-1", step_id="S1")
            resume_result = adapter.resume(task_id="DKT-204", run_id="RUN-1", step_id="S1")

            self.assertEqual(create_result.correlation_id, resume_result.correlation_id)

    def test_create_messages_contain_step_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _FakeLLMClient()
            adapter = self._build_adapter(root=Path(tmp), llm_client=llm_client)

            adapter.create(
                task_id="DKT-205",
                run_id="RUN-1",
                step_id="S1",
                request={
                    "task_id": "DKT-205",
                    "run_id": "RUN-1",
                    "step_id": "S1",
                    "step_title": "Implement LLM adapter",
                    "goal": "Replace shim with direct LLM",
                    "acceptance_criteria": [
                        "Call LLM client directly",
                        "Write artifacts for all calls",
                    ],
                },
            )

            self.assertEqual(len(llm_client.calls), 1)
            messages = llm_client.calls[0]
            user_text = "\n".join(message["content"] for message in messages if message["role"] == "user")
            self.assertIn("Step Title: Implement LLM adapter", user_text)
            self.assertIn("Goal: Replace shim with direct LLM", user_text)
            self.assertIn("Acceptance Criteria:", user_text)
            self.assertIn("- Call LLM client directly", user_text)

    def test_rework_includes_context_in_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _FakeLLMClient()
            adapter = self._build_adapter(root=Path(tmp), llm_client=llm_client)

            adapter.rework(
                task_id="DKT-206",
                run_id="RUN-1",
                step_id="S2",
                request={"step_title": "Fix failing test"},
                rework_context={
                    "failed_calls": [
                        {
                            "action": "create",
                            "status": "error",
                            "parsed_output": {"message": "acceptance criteria not met"},
                        }
                    ]
                },
            )

            self.assertEqual(len(llm_client.calls), 1)
            messages = llm_client.calls[0]
            user_text = "\n".join(message["content"] for message in messages if message["role"] == "user")
            self.assertIn("Previous attempts failed:", user_text)
            self.assertIn("Attempt (create): error", user_text)
            self.assertIn("acceptance criteria not met", user_text)

    def test_llm_error_returns_error_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = self._build_adapter(root=Path(tmp), llm_client=_RaisingLLMClient())

            result = adapter.create(task_id="DKT-207", run_id="RUN-1", step_id="S1")

            self.assertEqual(result.status, "error")
            self.assertEqual(result.parsed_output.get("status"), "error")
            self.assertIn("llm error", str(result.parsed_output.get("message")))

    def test_parsed_output_contains_llm_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = self._build_adapter(root=Path(tmp), llm_client=_FakeLLMClient())

            result = adapter.create(task_id="DKT-208", run_id="RUN-1", step_id="S1")

            self.assertEqual(result.parsed_output.get("model"), "test-model")
            usage = result.parsed_output.get("usage")
            self.assertIsInstance(usage, dict)
            self.assertEqual(usage.get("total_tokens"), 30)
            self.assertEqual(result.parsed_output.get("finish_reason"), "stop")

    def test_resume_action_in_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _FakeLLMClient()
            adapter = self._build_adapter(root=Path(tmp), llm_client=llm_client)

            adapter.resume(
                task_id="DKT-209",
                run_id="RUN-1",
                step_id="S1",
                request={"step_title": "Resume task"},
            )

            self.assertEqual(len(llm_client.calls), 1)
            messages = llm_client.calls[0]
            user_payload = next(
                (message["content"] for message in messages if message["role"] == "user"),
                "",
            )
            self.assertIn("Action: resume", user_payload)

    def test_artifact_request_payload_records_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = self._build_adapter(root=Path(tmp), llm_client=_FakeLLMClient())

            result = adapter.create(task_id="DKT-210", run_id="RUN-1", step_id="S1")
            request_doc = json.loads(result.artifacts.request_path.read_text(encoding="utf-8"))

            request_payload = request_doc["request"]
            self.assertIn("messages", request_payload)
            self.assertIsInstance(request_payload["messages"], list)

    def test_agent_loop_iterates_with_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _SequenceLLMClient(
                completions=[
                    LLMCompletionResult(
                        content="",
                        model="agent-model",
                        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                        finish_reason="tool_calls",
                        raw_response={"id": "c1"},
                        tool_calls=(
                            {
                                "id": "call-1",
                                "function_name": "write_file",
                                "arguments": {"path": "out.txt", "content": "hello"},
                            },
                        ),
                    ),
                    LLMCompletionResult(
                        content="done",
                        model="agent-model",
                        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                        finish_reason="stop",
                        raw_response={"id": "c2"},
                    ),
                ],
            )
            tool_layer = _FakeToolOrchestrationLayer()
            tools_schema = [
                {
                    "type": "function",
                    "function": {"name": "write_file", "parameters": {"type": "object"}},
                }
            ]
            adapter = LLMDispatchAdapter(
                llm_client=llm_client,
                artifact_store=DispatchArtifactStore(Path(tmp) / "artifacts"),
                tool_orchestration_layer=tool_layer,
                tools_schema=tools_schema,
            )

            result = adapter.create(task_id="DKT-211", run_id="RUN-1", step_id="S1")

            self.assertEqual(result.status, "success")
            self.assertEqual(result.parsed_output.get("message"), "done")
            self.assertEqual(len(llm_client.calls), 2)
            self.assertEqual(len(tool_layer.calls), 1)
            self.assertEqual(tool_layer.calls[0]["tool_name"], "write_file")
            self.assertEqual(llm_client.tools_calls[0], tools_schema)

    def test_agent_loop_max_iterations_breaker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _SequenceLLMClient(
                completions=[
                    LLMCompletionResult(
                        content="still running",
                        model="agent-model",
                        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                        finish_reason="tool_calls",
                        raw_response={"id": "c1"},
                        tool_calls=(
                            {
                                "id": "call-1",
                                "function_name": "read_file",
                                "arguments": {"path": "in.txt"},
                            },
                        ),
                    )
                ],
            )
            tool_layer = _FakeToolOrchestrationLayer()
            adapter = LLMDispatchAdapter(
                llm_client=llm_client,
                artifact_store=DispatchArtifactStore(Path(tmp) / "artifacts"),
                tool_orchestration_layer=tool_layer,
                tools_schema=[{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}],
                max_agent_iterations=1,
            )

            result = adapter.create(task_id="DKT-212", run_id="RUN-1", step_id="S1")

            self.assertEqual(result.status, "success")
            self.assertEqual(result.parsed_output.get("iterations"), 1)
            self.assertEqual(len(llm_client.calls), 1)
            self.assertEqual(len(tool_layer.calls), 1)

    def test_agent_loop_records_tool_call_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _SequenceLLMClient(
                completions=[
                    LLMCompletionResult(
                        content="",
                        model="agent-model",
                        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                        finish_reason="tool_calls",
                        raw_response={"id": "c1"},
                        tool_calls=(
                            {
                                "id": "call-1",
                                "function_name": "execute_command",
                                "arguments": {"command": "echo ok"},
                            },
                        ),
                    ),
                    LLMCompletionResult(
                        content="ok",
                        model="agent-model",
                        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                        finish_reason="stop",
                        raw_response={"id": "c2"},
                    ),
                ],
            )
            tool_layer = _FakeToolOrchestrationLayer()
            adapter = LLMDispatchAdapter(
                llm_client=llm_client,
                artifact_store=DispatchArtifactStore(Path(tmp) / "artifacts"),
                tool_orchestration_layer=tool_layer,
                tools_schema=[{"type": "function", "function": {"name": "execute_command", "parameters": {"type": "object"}}}],
            )

            result = adapter.create(task_id="DKT-213", run_id="RUN-1", step_id="S1")

            tool_call_log = result.parsed_output.get("tool_call_log")
            self.assertIsInstance(tool_call_log, list)
            self.assertEqual(len(tool_call_log), 1)
            self.assertEqual(tool_call_log[0]["tool_name"], "execute_command")
            self.assertEqual(tool_call_log[0]["tool_call_id"], "call-1")

    def test_no_tool_layer_keeps_existing_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm_client = _FakeLLMClient(content="plain response")
            adapter = self._build_adapter(root=Path(tmp), llm_client=llm_client)

            result = adapter.create(task_id="DKT-214", run_id="RUN-1", step_id="S1")

            self.assertEqual(result.status, "success")
            self.assertEqual(result.parsed_output.get("execution_mode"), "llm_direct")
            self.assertNotIn("tool_call_log", result.parsed_output)
            self.assertNotIn("iterations", result.parsed_output)
            self.assertEqual(llm_client.tools_calls, [None])

    def _build_adapter(self, *, root: Path, llm_client: _FakeLLMClient) -> LLMDispatchAdapter:
        return LLMDispatchAdapter(
            llm_client=llm_client,
            artifact_store=DispatchArtifactStore(root / "artifacts"),
        )


if __name__ == "__main__":
    unittest.main()
