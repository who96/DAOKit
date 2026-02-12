from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from artifacts.dispatch_artifacts import DispatchArtifactStore, DispatchCallArtifacts


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise DispatchError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise DispatchError(f"{name} must be a non-empty string")
    return normalized


def _coerce_mapping(value: Any, *, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise DispatchError(f"{name} must be an object")
    return dict(value)


def _stable_thread_id(*, task_id: str, run_id: str, step_id: str) -> str:
    canonical = f"{task_id}|{run_id}|{step_id}"
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"thread-{digest}"


def _parse_output(raw_stdout: str) -> dict[str, Any]:
    text = raw_stdout.strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, Mapping):
        return dict(parsed)

    key_values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            key_values[key] = value
    if key_values:
        return key_values

    return {"message": text}


@dataclass(frozen=True)
class DispatchCallResult:
    action: str
    status: str
    task_id: str
    run_id: str
    step_id: str
    thread_id: str
    retry_index: int
    command: tuple[str, ...]
    parsed_output: dict[str, Any]
    artifacts: DispatchCallArtifacts


class DispatchError(RuntimeError):
    """Raised when dispatch request cannot be executed or normalized safely."""


CompletedProcess = subprocess.CompletedProcess[str]
CommandRunner = Callable[[Sequence[str], str], CompletedProcess]


class ShimDispatchAdapter:
    """Shim wrapper that supports create/resume/rework with mandatory artifact capture."""

    def __init__(
        self,
        *,
        shim_path: str | Path,
        artifact_store: DispatchArtifactStore,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.shim_path = str(shim_path)
        self.artifact_store = artifact_store
        self.command_runner = command_runner or self._default_command_runner

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

        normalized_request = _coerce_mapping(request, name="request")
        normalized_rework = _coerce_mapping(rework_context, name="rework_context")

        command = self._build_command(
            action=action,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            thread_id=normalized_thread_id,
            dry_run=dry_run,
        )
        payload = {
            "action": action,
            "task_id": normalized_task_id,
            "run_id": normalized_run_id,
            "step_id": normalized_step_id,
            "thread_id": normalized_thread_id,
            "retry_index": retry_index,
            "request": _copy_json(normalized_request),
        }
        if normalized_rework:
            payload["rework_context"] = _copy_json(normalized_rework)

        if dry_run:
            shim_output = {
                "status": "success",
                "action": action,
                "task_id": normalized_task_id,
                "run_id": normalized_run_id,
                "step_id": normalized_step_id,
                "thread_id": normalized_thread_id,
                "retry_index": retry_index,
            }
            raw_stdout = json.dumps(shim_output, sort_keys=True)
            raw_stderr = ""
            return_code = 0
        else:
            completed = self.command_runner(
                command,
                json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")),
            )
            raw_stdout = completed.stdout or ""
            raw_stderr = completed.stderr or ""
            return_code = int(completed.returncode)

        parsed_output = _parse_output(raw_stdout)
        status = "success" if return_code == 0 else "error"
        error_message = None if return_code == 0 else f"shim exited with status {return_code}"
        if return_code == 0 and isinstance(parsed_output.get("status"), str):
            status = str(parsed_output["status"]).strip() or status

        artifacts = self.artifact_store.write_call_artifacts(
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            thread_id=normalized_thread_id,
            action=action,
            retry_index=retry_index,
            command=command,
            request_payload=payload,
            status=status,
            raw_stdout=raw_stdout,
            parsed_output=parsed_output,
            raw_stderr=raw_stderr,
            error=error_message,
        )
        return DispatchCallResult(
            action=action,
            status=status,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            thread_id=normalized_thread_id,
            retry_index=retry_index,
            command=tuple(command),
            parsed_output=parsed_output,
            artifacts=artifacts,
        )

    def _build_command(
        self,
        *,
        action: str,
        task_id: str,
        run_id: str,
        step_id: str,
        thread_id: str,
        dry_run: bool,
    ) -> list[str]:
        command = [
            self.shim_path,
            action,
            "--task-id",
            task_id,
            "--run-id",
            run_id,
            "--step-id",
            step_id,
            "--thread-id",
            thread_id,
        ]
        if dry_run:
            command.append("--dry-run")
        return command

    @staticmethod
    def _default_command_runner(command: Sequence[str], payload: str) -> CompletedProcess:
        return subprocess.run(
            list(command),
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )
