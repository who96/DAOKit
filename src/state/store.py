from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .backend import StateBackend


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _checkpoint_state_hash(state: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        _copy_json(dict(state)),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def _default_process_leases() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "leases": [],
        "updated_at": _utc_now(),
    }


class StateStoreError(RuntimeError):
    """Raised when persisted state cannot be read or written safely."""


class FileSystemStateBackend(StateBackend):
    """File-backed state ledger for orchestrator runtime transitions."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.pipeline_state_path = self.root / "pipeline_state.json"
        self.heartbeat_status_path = self.root / "heartbeat_status.json"
        self.leases_path = self.root / "process_leases.json"
        self.events_path = self.root / "events.jsonl"
        self.snapshots_path = self.root / "snapshots.jsonl"
        self.checkpoints_path = self.root / "checkpoints.jsonl"
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
        if not self.checkpoints_path.exists():
            self.checkpoints_path.write_text("", encoding="utf-8")

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

        checkpoint = {
            "schema_version": "1.0.0",
            "kind": "checkpoint",
            "checkpoint_id": f"ckpt_{uuid4().hex}",
            "timestamp": payload["updated_at"],
            "node": node,
            "from_status": from_status,
            "to_status": to_status,
            "state": payload,
        }
        checkpoint["state_hash"] = _checkpoint_state_hash(checkpoint["state"])
        with self.checkpoints_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(checkpoint, separators=(",", ":")) + "\n")
        return payload

    def save_heartbeat_status(self, status: Mapping[str, Any]) -> dict[str, Any]:
        payload = _copy_json(dict(status))
        payload["updated_at"] = _utc_now()
        self.heartbeat_status_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return payload

    def load_leases(self) -> dict[str, Any]:
        if not self.leases_path.exists():
            return _default_process_leases()
        try:
            payload = json.loads(self.leases_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateStoreError(
                f"process leases are not valid JSON: {self.leases_path}"
            ) from exc
        if not isinstance(payload, dict):
            raise StateStoreError("process leases root must be a JSON object")
        leases = payload.get("leases")
        if not isinstance(leases, list):
            raise StateStoreError("process leases field 'leases' must be a JSON array")
        return payload

    def save_leases(self, leases: Mapping[str, Any]) -> dict[str, Any]:
        payload = _copy_json(dict(leases))
        if "schema_version" not in payload:
            payload["schema_version"] = "1.0.0"
        if payload.get("schema_version") != "1.0.0":
            raise StateStoreError("process leases schema_version must be '1.0.0'")
        if not isinstance(payload.get("leases"), list):
            raise StateStoreError("process leases field 'leases' must be a JSON array")
        payload["updated_at"] = _utc_now()
        self.leases_path.write_text(
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

    def load_latest_valid_checkpoint(self) -> dict[str, Any]:
        lines = self.checkpoints_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return self.load_state()

        diagnostics: list[str] = []
        for reverse_index, raw_line in enumerate(reversed(lines), start=1):
            line_number = len(lines) - reverse_index + 1
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                diagnostics.append(
                    f"line {line_number}: checkpoint entry is not valid JSON"
                )
                continue

            if not isinstance(parsed, dict):
                diagnostics.append(
                    f"line {line_number}: checkpoint entry must be an object"
                )
                continue

            validation_error = self._validate_checkpoint_entry(parsed)
            if validation_error is not None:
                diagnostics.append(f"line {line_number}: {validation_error}")
                continue

            state = _copy_json(dict(parsed["state"]))
            return self._annotate_resume_state(
                state=state,
                checkpoint_id=str(parsed["checkpoint_id"]),
                diagnostics=tuple(reversed(diagnostics)),
            )

        if diagnostics:
            summary = "; ".join(diagnostics[:3])
            if len(diagnostics) > 3:
                summary = f"{summary}; ... {len(diagnostics) - 3} more"
            raise StateStoreError(
                "checkpoint resume failed: "
                f"no valid checkpoint entries in '{self.checkpoints_path}'; {summary}"
            )
        return self.load_state()

    def _validate_checkpoint_entry(self, entry: Mapping[str, Any]) -> str | None:
        schema_version = entry.get("schema_version")
        if schema_version != "1.0.0":
            return "checkpoint schema_version must be '1.0.0'"

        kind = entry.get("kind")
        if kind != "checkpoint":
            return "checkpoint kind must be 'checkpoint'"

        checkpoint_id = entry.get("checkpoint_id")
        if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
            return "checkpoint_id must be a non-empty string"

        timestamp = entry.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp.strip():
            return "timestamp must be a non-empty string"

        state = entry.get("state")
        if not isinstance(state, Mapping):
            return "state must be an object"
        state_schema_version = state.get("schema_version")
        if state_schema_version != "1.0.0":
            return "state.schema_version must be '1.0.0'"

        state_hash = entry.get("state_hash")
        if not isinstance(state_hash, str) or not state_hash.strip():
            return "state_hash must be a non-empty string"
        expected_hash = _checkpoint_state_hash(state)
        if state_hash != expected_hash:
            return "state_hash validation failed"
        return None

    def _annotate_resume_state(
        self,
        *,
        state: dict[str, Any],
        checkpoint_id: str,
        diagnostics: tuple[str, ...],
    ) -> dict[str, Any]:
        role_lifecycle = state.get("role_lifecycle")
        if not isinstance(role_lifecycle, dict):
            role_lifecycle = {"orchestrator": "idle"}
            state["role_lifecycle"] = role_lifecycle
        role_lifecycle["checkpoint_resume_id"] = checkpoint_id
        if diagnostics:
            role_lifecycle["checkpoint_resume_status"] = "recovered_with_warnings"
            role_lifecycle["checkpoint_resume_diagnostics_count"] = str(len(diagnostics))
            role_lifecycle["checkpoint_resume_diagnostics"] = " | ".join(diagnostics[:3])
        else:
            role_lifecycle["checkpoint_resume_status"] = "clean"
            role_lifecycle["checkpoint_resume_diagnostics_count"] = "0"
            role_lifecycle.pop("checkpoint_resume_diagnostics", None)
        return state


class StateStore(FileSystemStateBackend):
    """Backward-compatible alias for the file-system state backend."""
