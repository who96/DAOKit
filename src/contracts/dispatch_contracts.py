from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping


DISPATCH_SCHEMA_VERSION = "1.0.0"
DISPATCH_TARGET_CODEX_WORKER_SHIM = "codex_worker_shim"

_ACTION_TO_SHIM_ACTION = {
    "create": "codex.create",
    "resume": "codex.resume",
    "rework": "codex.rework",
}

_SUCCESS_STATUS_TOKENS = {
    "success",
    "ok",
    "passed",
    "done",
    "completed",
}

_ERROR_STATUS_TOKENS = {
    "error",
    "failed",
    "failure",
    "fatal",
    "timeout",
    "validation_error",
    "cancelled",
    "canceled",
    "rework",
    "needs_rework",
    "retryable_error",
}


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise DispatchContractError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise DispatchContractError(f"{name} must be a non-empty string")
    return normalized


def _normalize_status_token(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _coerce_mapping(value: Any, *, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise DispatchContractError(f"{name} must be an object")
    return dict(value)


def _extract_context_error_message(
    *,
    parsed_output: Mapping[str, Any],
    raw_stderr: str,
) -> str | None:
    for key in ("error", "error_message", "message", "detail", "reason"):
        value = parsed_output.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            return normalized
    normalized_stderr = raw_stderr.strip()
    return normalized_stderr or None


def _assert_context_alignment(
    *,
    context_name: str,
    context: Mapping[str, Any],
    task_id: str,
    run_id: str,
    step_id: str,
    thread_id: str,
) -> None:
    expected_values = {
        "task_id": task_id,
        "run_id": run_id,
        "step_id": step_id,
        "thread_id": thread_id,
    }

    for key, expected in expected_values.items():
        if key not in context:
            continue
        candidate = context[key]
        normalized = _expect_non_empty_string(candidate, name=f"{context_name}.{key}")
        if normalized != expected:
            raise DispatchContractError(f"{context_name}.{key} must match top-level {key}")


class DispatchContractError(ValueError):
    """Raised when Codex dispatch payload violates the integration contract."""


@dataclass(frozen=True)
class CodexShimPayload:
    schema_version: str
    dispatch_target: str
    action: str
    shim_action: str
    task_id: str
    run_id: str
    step_id: str
    thread_id: str
    retry_index: int
    request: dict[str, Any]
    rework_context: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "dispatch_target": self.dispatch_target,
            "action": self.action,
            "shim_action": self.shim_action,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "thread_id": self.thread_id,
            "retry_index": self.retry_index,
            "request": _copy_json(self.request),
        }
        if self.rework_context:
            payload["rework_context"] = _copy_json(self.rework_context)
        return payload


@dataclass(frozen=True)
class DispatchOutcome:
    status: str
    error: str | None


def build_codex_shim_payload(
    *,
    action: str,
    task_id: str,
    run_id: str,
    step_id: str,
    thread_id: str,
    retry_index: int,
    request: Mapping[str, Any] | None,
    rework_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized_action = _expect_non_empty_string(action, name="action").lower()
    if normalized_action not in _ACTION_TO_SHIM_ACTION:
        known_actions = ", ".join(sorted(_ACTION_TO_SHIM_ACTION))
        raise DispatchContractError(f"action must be one of: {known_actions}")

    if retry_index < 0:
        raise DispatchContractError("retry_index must be >= 0")

    normalized_task_id = _expect_non_empty_string(task_id, name="task_id")
    normalized_run_id = _expect_non_empty_string(run_id, name="run_id")
    normalized_step_id = _expect_non_empty_string(step_id, name="step_id")
    normalized_thread_id = _expect_non_empty_string(thread_id, name="thread_id")

    normalized_request = _coerce_mapping(request, name="request")
    _assert_context_alignment(
        context_name="request",
        context=normalized_request,
        task_id=normalized_task_id,
        run_id=normalized_run_id,
        step_id=normalized_step_id,
        thread_id=normalized_thread_id,
    )

    normalized_rework = _coerce_mapping(rework_context, name="rework_context")
    if normalized_rework:
        if normalized_action != "rework":
            raise DispatchContractError("rework_context is only allowed when action is rework")
        _assert_context_alignment(
            context_name="rework_context",
            context=normalized_rework,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            thread_id=normalized_thread_id,
        )

    payload = CodexShimPayload(
        schema_version=DISPATCH_SCHEMA_VERSION,
        dispatch_target=DISPATCH_TARGET_CODEX_WORKER_SHIM,
        action=normalized_action,
        shim_action=_ACTION_TO_SHIM_ACTION[normalized_action],
        task_id=normalized_task_id,
        run_id=normalized_run_id,
        step_id=normalized_step_id,
        thread_id=normalized_thread_id,
        retry_index=retry_index,
        request=_copy_json(normalized_request),
        rework_context=_copy_json(normalized_rework) if normalized_rework else None,
    )
    return payload.to_dict()


def normalize_codex_shim_outcome(
    *,
    return_code: int,
    parsed_output: Mapping[str, Any],
    raw_stderr: str,
) -> DispatchOutcome:
    status_token = _normalize_status_token(parsed_output.get("status"))
    context_error = _extract_context_error_message(
        parsed_output=parsed_output,
        raw_stderr=raw_stderr,
    )

    if return_code != 0:
        message = f"shim exited with status {return_code}"
        if context_error:
            message = f"{message}: {context_error}"
        return DispatchOutcome(status="error", error=message)

    if status_token in _ERROR_STATUS_TOKENS:
        return DispatchOutcome(
            status="error",
            error=context_error or f"shim reported failure status '{status_token}'",
        )

    if status_token is None or status_token in _SUCCESS_STATUS_TOKENS:
        return DispatchOutcome(status="success", error=None)

    # Unknown status values remain success to preserve backward compatibility
    # for zero-exit shims while still keeping normalization deterministic.
    return DispatchOutcome(status="success", error=None)
