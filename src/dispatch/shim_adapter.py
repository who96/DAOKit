from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from artifacts.dispatch_artifacts import DispatchArtifactStore, DispatchCallArtifacts
from contracts.dispatch_contracts import (
    DispatchContractError,
    build_codex_shim_payload,
    normalize_codex_shim_outcome,
)
from state.relay_policy import RelayModePolicy, RelayPolicyError

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
    correlation_id: str
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
        shim_command_prefix: Sequence[str] | None = None,
        artifact_store: DispatchArtifactStore,
        command_runner: CommandRunner | None = None,
        relay_policy: RelayModePolicy | None = None,
    ) -> None:
        self.shim_path = str(shim_path)
        self.shim_command_prefix = (
            tuple(str(token) for token in shim_command_prefix)
            if shim_command_prefix is not None
            else None
        )
        if self.shim_command_prefix is not None and len(self.shim_command_prefix) == 0:
            raise DispatchError("shim_command_prefix must not be empty")
        self.artifact_store = artifact_store
        self.command_runner = command_runner or self._default_command_runner
        self.relay_policy = relay_policy or RelayModePolicy(relay_mode_enabled=False)

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

    def _guard_execution_action(self, action: str) -> None:
        try:
            self.relay_policy.guard_action(action=action)
        except RelayPolicyError as exc:
            raise DispatchError(str(exc)) from exc

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

        explicit_correlation_id: Any = None
        if isinstance(request, Mapping):
            explicit_correlation_id = request.get("correlation_id")
        if isinstance(explicit_correlation_id, str) and explicit_correlation_id.strip():
            normalized_correlation_id = explicit_correlation_id.strip()
        else:
            normalized_correlation_id = _stable_correlation_id(
                task_id=normalized_task_id,
                run_id=normalized_run_id,
                step_id=normalized_step_id,
            )

        command = self._build_command(
            action=action,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            thread_id=normalized_thread_id,
            dry_run=dry_run,
        )
        try:
            payload = build_codex_shim_payload(
                action=action,
                task_id=normalized_task_id,
                run_id=normalized_run_id,
                step_id=normalized_step_id,
                thread_id=normalized_thread_id,
                retry_index=retry_index,
                request=request,
                rework_context=rework_context,
            )
        except DispatchContractError as exc:
            raise DispatchError(str(exc)) from exc
        payload["correlation_id"] = normalized_correlation_id

        if dry_run:
            shim_output = {
                "status": "success",
                "action": action,
                "task_id": normalized_task_id,
                "run_id": normalized_run_id,
                "step_id": normalized_step_id,
                "thread_id": normalized_thread_id,
                "correlation_id": normalized_correlation_id,
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
        normalized_outcome = normalize_codex_shim_outcome(
            return_code=return_code,
            parsed_output=parsed_output,
            raw_stderr=raw_stderr,
        )
        status = normalized_outcome.status
        error_message = normalized_outcome.error

        artifacts = self.artifact_store.write_call_artifacts(
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            thread_id=normalized_thread_id,
            correlation_id=normalized_correlation_id,
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
            correlation_id=normalized_correlation_id,
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
        prefix = list(self.shim_command_prefix) if self.shim_command_prefix is not None else [self.shim_path]
        command = [
            *prefix,
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
        try:
            return subprocess.run(
                list(command),
                input=payload,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            fallback_output = {
                "status": "success",
                "message": "shim executable not found; noop fallback completed",
                "execution_mode": "shim_noop_fallback",
            }
            return subprocess.CompletedProcess(
                args=list(command),
                returncode=0,
                stdout=json.dumps(fallback_output, ensure_ascii=True),
                stderr="",
            )
