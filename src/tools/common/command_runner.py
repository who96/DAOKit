from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import subprocess
from typing import Mapping, Sequence


class CommandExecutionError(ValueError):
    """Raised when command execution inputs are invalid."""


@dataclass(frozen=True)
class CommandExecutionResult:
    command: tuple[str, ...]
    status: str
    exit_status: int | None
    stdout: str
    stderr: str
    timed_out: bool
    error: str | None
    started_at: str
    finished_at: str


def run_command(
    *,
    command: Sequence[str],
    timeout_seconds: float | None = None,
    input_text: str | None = None,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> CommandExecutionResult:
    normalized_command = _normalize_command(command)
    normalized_timeout = _normalize_timeout(timeout_seconds)

    started = _utc_now()
    try:
        completed = subprocess.run(
            list(normalized_command),
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=normalized_timeout,
            cwd=cwd,
            env=None if env is None else dict(env),
        )
    except subprocess.TimeoutExpired as exc:
        finished = _utc_now()
        return CommandExecutionResult(
            command=normalized_command,
            status="timeout",
            exit_status=None,
            stdout=_stream_to_text(exc.stdout),
            stderr=_stream_to_text(exc.stderr),
            timed_out=True,
            error=f"command timed out after {normalized_timeout} seconds",
            started_at=started,
            finished_at=finished,
        )
    except OSError as exc:
        finished = _utc_now()
        return CommandExecutionResult(
            command=normalized_command,
            status="error",
            exit_status=None,
            stdout="",
            stderr="",
            timed_out=False,
            error=f"failed to execute command: {exc}",
            started_at=started,
            finished_at=finished,
        )

    finished = _utc_now()
    status = "success" if completed.returncode == 0 else "error"
    error = None if completed.returncode == 0 else f"command exited with status {completed.returncode}"
    return CommandExecutionResult(
        command=normalized_command,
        status=status,
        exit_status=int(completed.returncode),
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        timed_out=False,
        error=error,
        started_at=started,
        finished_at=finished,
    )


def _normalize_command(command: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
        raise CommandExecutionError("command must be a sequence of strings")

    normalized: list[str] = []
    for index, part in enumerate(command):
        if not isinstance(part, str):
            raise CommandExecutionError(f"command[{index}] must be a string")
        value = part.strip()
        if not value:
            raise CommandExecutionError(f"command[{index}] must be a non-empty string")
        normalized.append(value)

    if not normalized:
        raise CommandExecutionError("command must contain at least one part")

    return tuple(normalized)


def _normalize_timeout(timeout_seconds: float | None) -> float | None:
    if timeout_seconds is None:
        return None
    if timeout_seconds <= 0:
        raise CommandExecutionError("timeout_seconds must be > 0 when provided")
    return float(timeout_seconds)


def _stream_to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
