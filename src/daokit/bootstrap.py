from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

REQUIRED_DIRECTORIES = (
    "src",
    "contracts",
    "state",
    "artifacts",
    "docs",
    "tests",
    "examples",
)


@dataclass
class InitResult:
    created: list[str]
    skipped: list[str]


class RepositoryInitError(RuntimeError):
    """Raised when initialization cannot satisfy the required repository shape."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state_documents() -> dict[str, str]:
    pipeline_state = {
        "schema_version": "1.0.0",
        "task_id": None,
        "run_id": None,
        "goal": "",
        "status": "PLANNING",
        "current_step": None,
        "steps": [],
        "role_lifecycle": {"orchestrator": "idle"},
        "succession": {
            "enabled": True,
            "last_takeover_at": None,
        },
        "updated_at": _utc_now(),
    }
    heartbeat_status = {
        "schema_version": "1.0.0",
        "status": "IDLE",
        "last_heartbeat_at": None,
        "reason_code": None,
        "updated_at": _utc_now(),
    }
    process_leases = {
        "schema_version": "1.0.0",
        "leases": [],
        "updated_at": _utc_now(),
    }
    return {
        "state/pipeline_state.json": json.dumps(pipeline_state, indent=2) + "\n",
        "state/heartbeat_status.json": json.dumps(heartbeat_status, indent=2) + "\n",
        "state/process_leases.json": json.dumps(process_leases, indent=2) + "\n",
        "state/events.jsonl": "",
    }


def _record(result: InitResult, rel_path: str, was_created: bool) -> None:
    if was_created:
        result.created.append(rel_path)
    else:
        result.skipped.append(rel_path)


def _write_if_missing(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        return True
    except FileExistsError:
        return False


def _ensure_directory(path: Path) -> bool:
    if path.exists():
        if not path.is_dir():
            raise RepositoryInitError(f"expected directory at '{path}', found non-directory entry")
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def _ensure_file_target(path: Path) -> None:
    if path.exists() and not path.is_file():
        raise RepositoryInitError(f"expected file at '{path}', found non-file entry")


def initialize_repository(root: Path) -> InitResult:
    root = root.resolve()
    if root.exists() and not root.is_dir():
        raise RepositoryInitError(f"target root '{root}' is not a directory")

    result = InitResult(created=[], skipped=[])

    for relative in REQUIRED_DIRECTORIES:
        directory = root / relative
        _record(result, relative, _ensure_directory(directory))

    for relative, content in _default_state_documents().items():
        file_path = root / relative
        _ensure_file_target(file_path)
        _record(result, relative, _write_if_missing(file_path, content))

    return result
