from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
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


class SQLiteStateBackend(StateBackend):
    """SQLite-backed state ledger with FS-compatible read/write semantics."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.db_path = self.root / "state.sqlite3"
        self.pipeline_state_path = self.root / "pipeline_state.json"
        self.heartbeat_status_path = self.root / "heartbeat_status.json"
        self.leases_path = self.root / "process_leases.json"
        self.events_path = self.root / "events.jsonl"
        self.snapshots_path = self.root / "snapshots.jsonl"
        self.checkpoints_path = self.root / "checkpoints.jsonl"
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for path in (
            self.events_path,
            self.snapshots_path,
            self.checkpoints_path,
        ):
            if not path.exists():
                path.write_text("", encoding="utf-8")

        with self._connect() as conn:
            self._ensure_schema(conn)
            self._seed_defaults(conn)

        # Keep baseline JSON docs present for operator tooling that expects them on disk.
        if not self.pipeline_state_path.exists():
            self.pipeline_state_path.write_text(
                json.dumps(self.load_state(), indent=2) + "\n",
                encoding="utf-8",
            )
        if not self.heartbeat_status_path.exists():
            self.heartbeat_status_path.write_text(
                json.dumps(self.load_heartbeat_status(), indent=2) + "\n",
                encoding="utf-8",
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Durability-oriented defaults; WAL improves concurrent reader behavior.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                state_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS heartbeat_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                status_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS process_leases (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                leases_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                node TEXT,
                from_status TEXT,
                to_status TEXT,
                state_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                schema_version TEXT NOT NULL,
                kind TEXT NOT NULL,
                checkpoint_id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                node TEXT,
                from_status TEXT,
                to_status TEXT,
                state_json TEXT NOT NULL,
                state_hash TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                schema_version TEXT NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                step_id TEXT,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                dedup_key TEXT
            )
            """
        )

    def _seed_defaults(self, conn: sqlite3.Connection) -> None:
        if self._row_missing(conn, "pipeline_state"):
            seeded = self._load_seed_from_file(self.pipeline_state_path) or _default_pipeline_state()
            conn.execute(
                "INSERT INTO pipeline_state(id, state_json) VALUES (1, ?)",
                (json.dumps(seeded, separators=(",", ":")),),
            )
        if self._row_missing(conn, "heartbeat_status"):
            seeded = self._load_seed_from_file(self.heartbeat_status_path) or _default_heartbeat_status()
            conn.execute(
                "INSERT INTO heartbeat_status(id, status_json) VALUES (1, ?)",
                (json.dumps(seeded, separators=(",", ":")),),
            )
        if self._row_missing(conn, "process_leases"):
            seeded = self._load_seed_from_file(self.leases_path) or _default_process_leases()
            conn.execute(
                "INSERT INTO process_leases(id, leases_json) VALUES (1, ?)",
                (json.dumps(seeded, separators=(",", ":")),),
            )

    def _row_missing(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(f"SELECT 1 FROM {table} WHERE id = 1").fetchone()
        return row is None

    def _load_seed_from_file(self, path: Path) -> dict[str, Any] | None:
        if not path.exists() or not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def load_state(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT state_json FROM pipeline_state WHERE id = 1").fetchone()
        if row is None:
            return _default_pipeline_state()
        try:
            payload = json.loads(str(row["state_json"]))
        except json.JSONDecodeError as exc:
            raise StateStoreError("pipeline state is not valid JSON in sqlite store") from exc
        if not isinstance(payload, dict):
            raise StateStoreError("pipeline state root must be a JSON object")
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

        snapshot = {
            "timestamp": payload["updated_at"],
            "node": node,
            "from_status": from_status,
            "to_status": to_status,
            "state": payload,
        }
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

        try:
            with self._connect() as conn:
                with conn:
                    conn.execute(
                        "UPDATE pipeline_state SET state_json = ? WHERE id = 1",
                        (json.dumps(payload, separators=(",", ":")),),
                    )
                    conn.execute(
                        "INSERT INTO snapshots(timestamp,node,from_status,to_status,state_json) VALUES (?,?,?,?,?)",
                        (
                            snapshot["timestamp"],
                            snapshot["node"],
                            snapshot["from_status"],
                            snapshot["to_status"],
                            json.dumps(payload, separators=(",", ":")),
                        ),
                    )
                    conn.execute(
                        "INSERT INTO checkpoints(schema_version,kind,checkpoint_id,timestamp,node,from_status,to_status,state_json,state_hash) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            checkpoint["schema_version"],
                            checkpoint["kind"],
                            checkpoint["checkpoint_id"],
                            checkpoint["timestamp"],
                            checkpoint["node"],
                            checkpoint["from_status"],
                            checkpoint["to_status"],
                            json.dumps(payload, separators=(",", ":")),
                            checkpoint["state_hash"],
                        ),
                    )
        except Exception as exc:
            raise StateStoreError(f"sqlite save_state failed: {exc}") from exc

        self.pipeline_state_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.snapshots_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, separators=(",", ":")) + "\n")
        with self.checkpoints_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(checkpoint, separators=(",", ":")) + "\n")
        return payload

    def load_heartbeat_status(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status_json FROM heartbeat_status WHERE id = 1"
            ).fetchone()
        if row is None:
            return _default_heartbeat_status()
        try:
            payload = json.loads(str(row["status_json"]))
        except json.JSONDecodeError as exc:
            raise StateStoreError("heartbeat status is not valid JSON in sqlite store") from exc
        if not isinstance(payload, dict):
            raise StateStoreError("heartbeat status root must be a JSON object")
        return payload

    def save_heartbeat_status(self, status: Mapping[str, Any]) -> dict[str, Any]:
        payload = _copy_json(dict(status))
        payload["updated_at"] = _utc_now()
        try:
            with self._connect() as conn:
                with conn:
                    conn.execute(
                        "UPDATE heartbeat_status SET status_json = ? WHERE id = 1",
                        (json.dumps(payload, separators=(",", ":")),),
                    )
        except Exception as exc:
            raise StateStoreError(f"sqlite save_heartbeat_status failed: {exc}") from exc

        self.heartbeat_status_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return payload

    def load_leases(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT leases_json FROM process_leases WHERE id = 1"
            ).fetchone()
        if row is None:
            return _default_process_leases()
        try:
            payload = json.loads(str(row["leases_json"]))
        except json.JSONDecodeError as exc:
            raise StateStoreError("process leases are not valid JSON in sqlite store") from exc
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

        try:
            with self._connect() as conn:
                with conn:
                    conn.execute(
                        "UPDATE process_leases SET leases_json = ? WHERE id = 1",
                        (json.dumps(payload, separators=(",", ":")),),
                    )
        except Exception as exc:
            raise StateStoreError(f"sqlite save_leases failed: {exc}") from exc

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

        try:
            with self._connect() as conn:
                with conn:
                    conn.execute(
                        "INSERT INTO events(schema_version,event_id,task_id,run_id,step_id,event_type,severity,timestamp,payload_json,dedup_key) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            event["schema_version"],
                            event["event_id"],
                            event["task_id"],
                            event["run_id"],
                            event["step_id"],
                            event["event_type"],
                            event["severity"],
                            event["timestamp"],
                            json.dumps(event["payload"], separators=(",", ":")),
                            event["dedup_key"],
                        ),
                    )
        except Exception as exc:
            raise StateStoreError(f"sqlite append_event failed: {exc}") from exc

        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        return event

    def list_snapshots(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT timestamp,node,from_status,to_status,state_json FROM snapshots ORDER BY seq ASC"
            ).fetchall()
        if not rows:
            return self._list_snapshots_from_file()

        snapshots: list[dict[str, Any]] = []
        for row in rows:
            try:
                state = json.loads(str(row["state_json"]))
            except json.JSONDecodeError as exc:
                raise StateStoreError("snapshot entry is not valid JSON in sqlite store") from exc
            if not isinstance(state, dict):
                raise StateStoreError("snapshot state must be a JSON object")
            snapshots.append(
                {
                    "timestamp": str(row["timestamp"]),
                    "node": row["node"],
                    "from_status": row["from_status"],
                    "to_status": row["to_status"],
                    "state": state,
                }
            )
        return snapshots

    def _list_snapshots_from_file(self) -> list[dict[str, Any]]:
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
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT schema_version,kind,checkpoint_id,timestamp,node,from_status,to_status,state_json,state_hash "
                "FROM checkpoints ORDER BY seq DESC"
            ).fetchall()

        if not rows:
            return self._load_latest_valid_checkpoint_from_file()

        diagnostics: list[str] = []
        for idx, row in enumerate(rows, start=1):
            entry: dict[str, Any] = {
                "schema_version": row["schema_version"],
                "kind": row["kind"],
                "checkpoint_id": row["checkpoint_id"],
                "timestamp": row["timestamp"],
                "node": row["node"],
                "from_status": row["from_status"],
                "to_status": row["to_status"],
                "state_hash": row["state_hash"],
            }
            try:
                state = json.loads(str(row["state_json"]))
            except json.JSONDecodeError:
                diagnostics.append(f"row {idx}: checkpoint state is not valid JSON")
                continue
            if not isinstance(state, dict):
                diagnostics.append(f"row {idx}: checkpoint state must be an object")
                continue
            entry["state"] = state

            validation_error = self._validate_checkpoint_entry(entry)
            if validation_error is not None:
                diagnostics.append(f"row {idx}: {validation_error}")
                continue

            recovered = _copy_json(dict(state))
            return self._annotate_resume_state(
                state=recovered,
                checkpoint_id=str(entry["checkpoint_id"]),
                diagnostics=tuple(reversed(diagnostics)),
            )

        if diagnostics:
            summary = "; ".join(diagnostics[:3])
            if len(diagnostics) > 3:
                summary = f"{summary}; ... {len(diagnostics) - 3} more"
            raise StateStoreError(
                "checkpoint resume failed: no valid checkpoint entries in sqlite store; "
                f"{summary}"
            )
        return self.load_state()

    def _load_latest_valid_checkpoint_from_file(self) -> dict[str, Any]:
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


ENV_STATE_BACKEND = "DAOKIT_STATE_BACKEND"
CONFIG_STATE_BACKEND_PATHS = (
    ("state", "backend"),
    ("runtime", "state_backend"),
)


class StateBackendKind(str, Enum):
    FILESYSTEM = "filesystem"
    SQLITE = "sqlite"


class StateBackendSelectionError(ValueError):
    """Raised when state backend selection is invalid."""


def resolve_state_backend(
    *,
    explicit_backend: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> StateBackendKind:
    source = explicit_backend
    if source is None and env is not None:
        source = env.get(ENV_STATE_BACKEND)
    if source is None:
        source = _read_config_string(config, path_candidates=CONFIG_STATE_BACKEND_PATHS)
    normalized = StateBackendKind.FILESYSTEM.value if source is None else source.strip().lower()

    if normalized in {"fs", "filesystem", "file", "file-system", "file_system"}:
        return StateBackendKind.FILESYSTEM
    if normalized in {"sqlite", "sqlite3"}:
        return StateBackendKind.SQLITE

    raise StateBackendSelectionError(
        "unsupported state backend "
        f"'{normalized}'. Supported values: filesystem, sqlite."
    )


def create_state_backend(
    root: Path,
    *,
    explicit_backend: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> StateBackend:
    selected = resolve_state_backend(
        explicit_backend=explicit_backend,
        env=env,
        config=config,
    )
    if selected == StateBackendKind.SQLITE:
        return SQLiteStateBackend(root)
    return StateStore(root)


def _read_config_string(
    config: Mapping[str, Any] | None,
    *,
    path_candidates: tuple[tuple[str, ...], ...],
) -> str | None:
    for path in path_candidates:
        value = _get_nested_config_value(config, path=path)
        if value is not None:
            return value
    return None


def _get_nested_config_value(
    config: Mapping[str, Any] | None,
    *,
    path: tuple[str, ...],
) -> str | None:
    node: Any = config
    for token in path:
        if not isinstance(node, dict):
            return None
        if token not in node:
            return None
        node = node[token]
    if isinstance(node, str):
        return node
    return None
