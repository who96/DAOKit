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
        self.calls: list[list[dict[str, str]]] = []

    @property
    def config(self) -> LLMConfig:
        return self._config

    def chat_completion(self, *, messages: list[dict[str, str]]) -> LLMCompletionResult:
        self.calls.append(messages)
        return LLMCompletionResult(
            content=self._content,
            model=self._model,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            finish_reason="stop",
            raw_response={"id": "fake"},
        )


class _RaisingLLMClient(_FakeLLMClient):
    def chat_completion(self, *, messages: list[dict[str, str]]) -> LLMCompletionResult:
        self.calls.append(messages)
        raise LLMCallError("llm error")


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

    def _build_adapter(self, *, root: Path, llm_client: _FakeLLMClient) -> LLMDispatchAdapter:
        return LLMDispatchAdapter(
            llm_client=llm_client,
            artifact_store=DispatchArtifactStore(root / "artifacts"),
        )


if __name__ == "__main__":
    unittest.main()
