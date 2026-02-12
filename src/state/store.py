from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _default_pipeline_state() -> dict[str, Any]:
    return {
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


def _default_heartbeat_status() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "IDLE",
        "last_heartbeat_at": None,
        "reason_code": None,
        "updated_at": _utc_now(),
    }


class StateStoreError(RuntimeError):
    """Raised when persisted state cannot be read or written safely."""


class StateStore:
    """File-backed state ledger for orchestrator runtime transitions."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.pipeline_state_path = self.root / "pipeline_state.json"
        self.heartbeat_status_path = self.root / "heartbeat_status.json"
        self.events_path = self.root / "events.jsonl"
        self.snapshots_path = self.root / "snapshots.jsonl"
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.pipeline_state_path.exists():
            self.pipeline_state_path.write_text(
                json.dumps(_default_pipeline_state(), indent=2) + "\n",
                encoding="utf-8",
            )
        if not self.heartbeat_status_path.exists():
            self.heartbeat_status_path.write_text(
                json.dumps(_default_heartbeat_status(), indent=2) + "\n",
                encoding="utf-8",
            )
        if not self.events_path.exists():
            self.events_path.write_text("", encoding="utf-8")
        if not self.snapshots_path.exists():
            self.snapshots_path.write_text("", encoding="utf-8")

    def load_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.pipeline_state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateStoreError(
                f"pipeline state is not valid JSON: {self.pipeline_state_path}"
            ) from exc
        if not isinstance(payload, dict):
            raise StateStoreError("pipeline state root must be a JSON object")
        return payload

    def load_heartbeat_status(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.heartbeat_status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateStoreError(
                f"heartbeat status is not valid JSON: {self.heartbeat_status_path}"
            ) from exc
        if not isinstance(payload, dict):
            raise StateStoreError("heartbeat status root must be a JSON object")
        return payload

    def save_state(
        self,
        state: Mapping[str, Any],
        *,
        node: str | None = None,
        from_status: str | None = None,
        to_status: str | None = None,
    ) -> dict[str, Any]:
        payload = _copy_json(dict(state))
        payload["updated_at"] = _utc_now()
        self.pipeline_state_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

        snapshot = {
            "timestamp": payload["updated_at"],
            "node": node,
            "from_status": from_status,
            "to_status": to_status,
            "state": payload,
        }
        with self.snapshots_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, separators=(",", ":")) + "\n")
        return payload

    def save_heartbeat_status(self, status: Mapping[str, Any]) -> dict[str, Any]:
        payload = _copy_json(dict(status))
        payload["updated_at"] = _utc_now()
        self.heartbeat_status_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return payload

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
    ) -> dict[str, Any]:
        event = {
            "schema_version": "1.0.0",
            "event_id": f"evt_{uuid4().hex}",
            "task_id": task_id,
            "run_id": run_id,
            "step_id": step_id,
            "event_type": event_type,
            "severity": severity,
            "timestamp": _utc_now(),
            "payload": _copy_json(dict(payload)),
            "dedup_key": dedup_key,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        return event

    def list_snapshots(self) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for line in self.snapshots_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise StateStoreError("snapshot log contains invalid JSON line") from exc
            if not isinstance(parsed, dict):
                raise StateStoreError("snapshot log entries must be objects")
            snapshots.append(parsed)
        return snapshots
