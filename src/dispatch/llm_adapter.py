from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Mapping

from artifacts.dispatch_artifacts import DispatchArtifactStore
from dispatch.shim_adapter import DispatchCallResult, DispatchError
from state.relay_policy import RelayModePolicy, RelayPolicyError

if TYPE_CHECKING:
    from llm.client import LLMCallError, LLMClient, LLMCompletionResult


DEFAULT_SYSTEM_PROMPT = (
    "You are a coding agent executing a single step in an orchestrated pipeline. "
    "Return a concise implementation status and next action. Keep output short and actionable."
)


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise DispatchError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise DispatchError(f"{name} must be a non-empty string")
    return normalized


def _stable_thread_id(*, task_id: str, run_id: str, step_id: str) -> str:
    canonical = f"{task_id}|{run_id}|{step_id}"
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"thread-{digest}"


def _stable_correlation_id(*, task_id: str, run_id: str, step_id: str) -> str:
    canonical = f"{task_id}|{run_id}|{step_id}|dispatch"
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"corr-{digest}"


def _as_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


class LLMDispatchAdapter:
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        artifact_store: DispatchArtifactStore,
        relay_policy: RelayModePolicy | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._artifact_store = artifact_store
        self._relay_policy = relay_policy or RelayModePolicy(relay_mode_enabled=False)
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    def create(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        request: Mapping[str, Any] | None = None,
        thread_id: str | None = None,
        retry_index: int = 0,
        dry_run: bool = False,
    ) -> DispatchCallResult:
        self._guard_execution_action("dispatch.create")
        return self._dispatch(
            action="create",
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            request=request,
            thread_id=thread_id,
            retry_index=retry_index,
            dry_run=dry_run,
            rework_context=None,
        )

    def resume(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        request: Mapping[str, Any] | None = None,
        thread_id: str | None = None,
        retry_index: int = 0,
        dry_run: bool = False,
    ) -> DispatchCallResult:
        self._guard_execution_action("dispatch.resume")
        return self._dispatch(
            action="resume",
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            request=request,
            thread_id=thread_id,
            retry_index=retry_index,
            dry_run=dry_run,
            rework_context=None,
        )

    def rework(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        request: Mapping[str, Any] | None = None,
        thread_id: str | None = None,
        retry_index: int = 0,
        dry_run: bool = False,
        rework_context: Mapping[str, Any] | None = None,
    ) -> DispatchCallResult:
        self._guard_execution_action("dispatch.rework")
        return self._dispatch(
            action="rework",
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            request=request,
            thread_id=thread_id,
            retry_index=retry_index,
            dry_run=dry_run,
            rework_context=rework_context,
        )

    def _dispatch(
        self,
        *,
        action: str,
        task_id: str,
        run_id: str,
        step_id: str,
        request: Mapping[str, Any] | None,
        thread_id: str | None,
        retry_index: int,
        dry_run: bool,
        rework_context: Mapping[str, Any] | None,
    ) -> DispatchCallResult:
        normalized_task_id = _expect_non_empty_string(task_id, name="task_id")
        normalized_run_id = _expect_non_empty_string(run_id, name="run_id")
        normalized_step_id = _expect_non_empty_string(step_id, name="step_id")
        normalized_thread_id = (
            _expect_non_empty_string(thread_id, name="thread_id")
            if thread_id is not None
            else _stable_thread_id(
                task_id=normalized_task_id,
                run_id=normalized_run_id,
                step_id=normalized_step_id,
            )
        )

        if retry_index < 0:
            raise DispatchError("retry_index must be >= 0")

        request_mapping = _as_mapping(request)
        explicit_correlation_id = request_mapping.get("correlation_id")
        if isinstance(explicit_correlation_id, str) and explicit_correlation_id.strip():
            normalized_correlation_id = explicit_correlation_id.strip()
        else:
            normalized_correlation_id = _stable_correlation_id(
                task_id=normalized_task_id,
                run_id=normalized_run_id,
                step_id=normalized_step_id,
            )

        command = (
            "llm",
            self._llm_client.config.base_url,
            self._llm_client.config.model,
            action,
        )
        messages = self._build_messages(
            action=action,
            request=request_mapping,
            rework_context=_as_mapping(rework_context),
        )

        if dry_run:
            parsed_output: dict[str, Any] = {
                "status": "success",
                "action": action,
                "task_id": normalized_task_id,
                "run_id": normalized_run_id,
                "step_id": normalized_step_id,
                "thread_id": normalized_thread_id,
                "correlation_id": normalized_correlation_id,
                "retry_index": retry_index,
                "execution_mode": "dry_run",
                "llm_invoked": False,
                "message": "dry-run dispatch execution",
            }
            status = "success"
            error_message = None
        else:
            from llm.client import LLMCallError as _LLMCallError

            try:
                completion = self._llm_client.chat_completion(messages=messages)
                parsed_output = self._build_success_output(action=action, completion=completion)
                status = "success"
                error_message = None
            except _LLMCallError as exc:
                error_message = str(exc)
                parsed_output = {
                    "status": "error",
                    "action": action,
                    "execution_mode": "llm_direct",
                    "llm_invoked": False,
                    "message": error_message,
                }
                status = "error"

        request_payload = {
            "task_id": normalized_task_id,
            "run_id": normalized_run_id,
            "step_id": normalized_step_id,
            "action": action,
            "messages": messages,
        }
        artifacts = self._artifact_store.write_call_artifacts(
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            thread_id=normalized_thread_id,
            correlation_id=normalized_correlation_id,
            action=action,
            retry_index=retry_index,
            command=list(command),
            request_payload=request_payload,
            status=status,
            raw_stdout=str(parsed_output.get("message", "")),
            parsed_output=parsed_output,
            raw_stderr="",
            error=error_message,
        )

        return DispatchCallResult(
            action=action,
            status=status,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            thread_id=normalized_thread_id,
            correlation_id=normalized_correlation_id,
            retry_index=retry_index,
            command=tuple(command),
            parsed_output=parsed_output,
            artifacts=artifacts,
        )

    def _build_messages(
        self,
        *,
        action: str,
        request: Mapping[str, Any] | None,
        rework_context: Mapping[str, Any] | None,
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": self._system_prompt}]

        req = _as_mapping(request)
        title = str(req.get("step_title") or "Complete the assigned step").strip()
        goal = str(req.get("goal") or "").strip()
        acceptance = req.get("acceptance_criteria")
        criteria: list[str] = []
        if isinstance(acceptance, list):
            criteria = [
                str(item).strip() for item in acceptance if isinstance(item, str) and item.strip()
            ]

        lines = [
            f"Action: {action}",
            f"Task ID: {req.get('task_id') or 'unknown'}",
            f"Run ID: {req.get('run_id') or 'unknown'}",
            f"Step ID: {req.get('step_id') or 'unknown'}",
            f"Step Title: {title}",
        ]
        if goal:
            lines.append(f"Goal: {goal}")
        if criteria:
            lines.append("Acceptance Criteria:")
            lines.extend(f"- {item}" for item in criteria[:5])
        lines.append("Return a concise implementation status and next action.")

        messages.append({"role": "user", "content": "\n".join(lines)})

        context = _as_mapping(rework_context)
        if action == "rework" and context:
            rework_lines = ["Previous attempts failed:"]
            failed_calls = context.get("failed_calls")
            if isinstance(failed_calls, list):
                for call in failed_calls:
                    if not isinstance(call, Mapping):
                        continue
                    call_action = call.get("action", "unknown")
                    call_status = call.get("status", "unknown")
                    message = ""
                    output = call.get("parsed_output")
                    if isinstance(output, Mapping):
                        message = str(output.get("message", ""))[:200]
                    base_line = f"- Attempt ({call_action}): {call_status}"
                    if message:
                        base_line = f"{base_line} - {message}"
                    rework_lines.append(base_line)
            rework_lines.append("Please address these failures and provide a corrected implementation.")
            messages.append({"role": "user", "content": "\n".join(rework_lines)})

        return messages

    def _guard_execution_action(self, action: str) -> None:
        try:
            self._relay_policy.guard_action(action=action)
        except RelayPolicyError as exc:
            raise DispatchError(str(exc)) from exc

    @staticmethod
    def _build_success_output(*, action: str, completion: LLMCompletionResult) -> dict[str, Any]:
        return {
            "status": "success",
            "action": action,
            "execution_mode": "llm_direct",
            "llm_invoked": True,
            "message": completion.content,
            "model": completion.model,
            "usage": completion.usage,
            "finish_reason": completion.finish_reason,
        }
