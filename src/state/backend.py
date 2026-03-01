from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class StateBackend(Protocol):
    """Persistence abstraction for orchestrator runtime state domains."""

    root: Path
    pipeline_state_path: Path
    heartbeat_status_path: Path
    events_path: Path
    snapshots_path: Path
    checkpoints_path: Path

    def load_state(self) -> dict[str, Any]: ...

    def save_state(
        self,
        state: Mapping[str, Any],
        *,
        node: str | None = None,
        from_status: str | None = None,
        to_status: str | None = None,
    ) -> dict[str, Any]: ...

    def load_heartbeat_status(self) -> dict[str, Any]: ...

    def save_heartbeat_status(self, status: Mapping[str, Any]) -> dict[str, Any]: ...

    def append_event(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str | None,
        event_type: str,
        severity: str,
        payload: Mapping[str, Any],
        dedup_key: str | None = None,
    ) -> dict[str, Any]: ...

    def list_snapshots(self) -> list[dict[str, Any]]: ...

    def load_latest_valid_checkpoint(self) -> dict[str, Any]: ...

    def load_leases(self) -> dict[str, Any]: ...

    def save_leases(self, leases: Mapping[str, Any]) -> dict[str, Any]: ...

    def list_sessions(self) -> list[dict[str, Any]]: ...

    def list_events_by_task(
        self,
        task_id: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...
