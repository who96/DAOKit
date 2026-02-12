from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _normalize_path(value: Path) -> str:
    return value.resolve().as_posix()


@dataclass(frozen=True)
class DispatchCallArtifacts:
    request_path: Path
    output_path: Path
    error_path: Path

    def normalized_paths(self) -> dict[str, str]:
        return {
            "request": _normalize_path(self.request_path),
            "output": _normalize_path(self.output_path),
            "error": _normalize_path(self.error_path),
        }


class DispatchArtifactStore:
    """Persists request/output/error artifacts for every shim dispatch call."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_call_artifacts(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        thread_id: str,
        action: str,
        retry_index: int,
        command: Sequence[str],
        request_payload: Mapping[str, Any],
        status: str,
        raw_stdout: str,
        parsed_output: Mapping[str, Any],
        raw_stderr: str,
        error: str | None,
        correlation_id: str | None = None,
    ) -> DispatchCallArtifacts:
        call_id = f"call-{retry_index:03d}-{uuid4().hex[:8]}"
        call_dir = (
            self.root
            / task_id
            / run_id
            / step_id
            / thread_id
            / action
            / call_id
        )
        call_dir.mkdir(parents=True, exist_ok=True)

        artifacts = DispatchCallArtifacts(
            request_path=call_dir / "request.json",
            output_path=call_dir / "output.json",
            error_path=call_dir / "error.json",
        )
        normalized_paths = artifacts.normalized_paths()

        request_doc = {
            "task_id": task_id,
            "run_id": run_id,
            "step_id": step_id,
            "thread_id": thread_id,
            "correlation_id": correlation_id,
            "action": action,
            "retry_index": retry_index,
            "command": list(command),
            "request": _copy_json(dict(request_payload)),
        }
        output_doc = {
            "task_id": task_id,
            "run_id": run_id,
            "step_id": step_id,
            "thread_id": thread_id,
            "correlation_id": correlation_id,
            "action": action,
            "status": status,
            "raw_stdout": raw_stdout,
            "parsed_output": _copy_json(dict(parsed_output)),
            "normalized_output_paths": normalized_paths,
        }
        error_doc = {
            "task_id": task_id,
            "run_id": run_id,
            "step_id": step_id,
            "thread_id": thread_id,
            "correlation_id": correlation_id,
            "action": action,
            "error": error,
            "raw_stderr": raw_stderr,
            "normalized_output_paths": normalized_paths,
        }

        artifacts.request_path.write_text(
            json.dumps(request_doc, indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts.output_path.write_text(
            json.dumps(output_doc, indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts.error_path.write_text(
            json.dumps(error_doc, indent=2) + "\n",
            encoding="utf-8",
        )
        return artifacts
