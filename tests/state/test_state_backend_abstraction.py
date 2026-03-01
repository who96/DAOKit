from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any
import unittest
from unittest.mock import patch
from uuid import UUID

from state.backend import StateBackend
from state.store import FileSystemStateBackend, SQLiteStateBackend, StateStore


class StateBackendAbstractionTests(unittest.TestCase):
    def _exercise_backend(self, backend_type: type[FileSystemStateBackend], root: Path) -> dict[str, str]:
        state_root = root / "state"
        with (
            patch("state.store._utc_now", return_value="2026-02-13T13:20:33+00:00"),
            patch("state.store.uuid4", return_value=UUID("00000000-0000-0000-0000-000000000111")),
        ):
            backend = backend_type(state_root)
            state = backend.load_state()
            state["task_id"] = "DKT-068"
            state["run_id"] = "RUN-FS-PARITY"
            state["status"] = "ANALYSIS"
            state["current_step"] = "S1"
            backend.save_state(
                state,
                node="extract",
                from_status="PLANNING",
                to_status="ANALYSIS",
            )
            heartbeat = backend.load_heartbeat_status()
            heartbeat["status"] = "ACTIVE"
            heartbeat["reason_code"] = "parity-check"
            backend.save_heartbeat_status(heartbeat)
            backend.append_event(
                task_id="DKT-068",
                run_id="RUN-FS-PARITY",
                step_id="S1",
                event_type="SYSTEM",
                severity="INFO",
                payload={"check": "parity"},
                dedup_key="dk-068-parity",
            )
            _ = backend.list_snapshots()
            _ = backend.load_latest_valid_checkpoint()

        return {
            "pipeline_state": (state_root / "pipeline_state.json").read_text(encoding="utf-8"),
            "heartbeat_status": (state_root / "heartbeat_status.json").read_text(encoding="utf-8"),
            "events": (state_root / "events.jsonl").read_text(encoding="utf-8"),
            "snapshots": (state_root / "snapshots.jsonl").read_text(encoding="utf-8"),
            "checkpoints": (state_root / "checkpoints.jsonl").read_text(encoding="utf-8"),
        }

    def _exercise_backend_contract(
        self,
        backend_type: type[StateBackend],
        root: Path,
    ) -> dict[str, Any]:
        state_root = root / "state"
        deterministic_uuids = (
            UUID("00000000-0000-0000-0000-000000000111"),
            UUID("00000000-0000-0000-0000-000000000222"),
        )
        with (
            patch("state.store._utc_now", return_value="2026-02-13T13:20:33+00:00"),
            patch("state.store.uuid4", side_effect=deterministic_uuids),
        ):
            backend = backend_type(state_root)
            state = backend.load_state()
            state["task_id"] = "DKT-069"
            state["run_id"] = "RUN-SQLITE-PARITY"
            state["status"] = "ANALYSIS"
            state["current_step"] = "S1"
            saved_state = backend.save_state(
                state,
                node="extract",
                from_status="PLANNING",
                to_status="ANALYSIS",
            )
            heartbeat = backend.load_heartbeat_status()
            heartbeat["status"] = "ACTIVE"
            heartbeat["reason_code"] = "parity-check"
            saved_heartbeat = backend.save_heartbeat_status(heartbeat)
            saved_event = backend.append_event(
                task_id="DKT-069",
                run_id="RUN-SQLITE-PARITY",
                step_id="S1",
                event_type="SYSTEM",
                severity="INFO",
                payload={"check": "sqlite-parity"},
                dedup_key="dk-069-sqlite-parity",
            )
            snapshots = backend.list_snapshots()
            checkpoint_state = backend.load_latest_valid_checkpoint()
            leases = backend.load_leases()
            leases["leases"] = [
                {
                    "lane": "controller",
                    "step_id": "S1",
                    "task_id": "DKT-069",
                    "run_id": "RUN-SQLITE-PARITY",
                    "thread_id": "worker-1",
                    "pid": 12345,
                    "lease_token": "lease-1",
                    "expiry": "2026-02-13T13:30:33+00:00",
                    "status": "ACTIVE",
                    "last_heartbeat_at": "2026-02-13T13:20:33+00:00",
                    "created_at": "2026-02-13T13:20:33+00:00",
                    "updated_at": "2026-02-13T13:20:33+00:00",
                }
            ]
            saved_leases = backend.save_leases(leases)
            reloaded_leases = backend.load_leases()

        return {
            "state": saved_state,
            "heartbeat": saved_heartbeat,
            "event": saved_event,
            "snapshots": snapshots,
            "checkpoint": checkpoint_state,
            "leases": saved_leases,
            "reloaded_leases": reloaded_leases,
        }

    def test_filesystem_backend_implements_state_backend_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fs_backend = FileSystemStateBackend(Path(tmp) / "state")
            alias_backend = StateStore(Path(tmp) / "state-alias")

            self.assertIsInstance(fs_backend, StateBackend)
            self.assertIsInstance(alias_backend, StateBackend)

    def test_state_store_alias_preserves_filesystem_backend_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fs_result = self._exercise_backend(FileSystemStateBackend, root / "fs")
            alias_result = self._exercise_backend(StateStore, root / "alias")
            self.assertEqual(fs_result, alias_result)

    def test_filesystem_backend_layout_remains_contract_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = FileSystemStateBackend(Path(tmp) / "state")
            files = sorted(path.name for path in backend.root.iterdir())
            self.assertEqual(
                files,
                [
                    "checkpoints.jsonl",
                    "events.jsonl",
                    "heartbeat_status.json",
                    "pipeline_state.json",
                    "snapshots.jsonl",
                ],
            )
            pipeline_state = json.loads((backend.root / "pipeline_state.json").read_text(encoding="utf-8"))
            self.assertEqual(pipeline_state["schema_version"], "1.0.0")
            heartbeat_status = json.loads((backend.root / "heartbeat_status.json").read_text(encoding="utf-8"))
            self.assertEqual(heartbeat_status["schema_version"], "1.0.0")

    def test_sqlite_backend_implements_state_backend_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_backend = SQLiteStateBackend(Path(tmp) / "state")
            self.assertIsInstance(sqlite_backend, StateBackend)

    def test_sqlite_backend_preserves_contract_parity_with_filesystem_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fs_result = self._exercise_backend_contract(FileSystemStateBackend, root / "fs")
            sqlite_result = self._exercise_backend_contract(SQLiteStateBackend, root / "sqlite")
            self.assertEqual(sqlite_result, fs_result)

    def test_list_sessions_empty_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = FileSystemStateBackend(Path(tmp) / "state")
            sessions = backend.list_sessions()
            self.assertEqual(sessions, [])

    def test_list_sessions_empty_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = SQLiteStateBackend(Path(tmp) / "state")
            sessions = backend.list_sessions()
            self.assertEqual(sessions, [])

    def test_list_sessions_multiple_tasks_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = FileSystemStateBackend(Path(tmp) / "state")
            backend.append_event(
                task_id="T1",
                run_id="R1",
                step_id=None,
                event_type="HUMAN",
                severity="INFO",
                payload={"message": "goal one", "sender": "human"},
            )
            backend.append_event(
                task_id="T1",
                run_id="R1",
                step_id=None,
                event_type="SYSTEM",
                severity="INFO",
                payload={},
            )
            backend.append_event(
                task_id="T2",
                run_id="R2",
                step_id=None,
                event_type="HUMAN",
                severity="INFO",
                payload={"message": "goal two", "sender": "human"},
            )
            sessions = backend.list_sessions()
            self.assertEqual(len(sessions), 2)
            task_ids = [session["task_id"] for session in sessions]
            self.assertIn("T1", task_ids)
            self.assertIn("T2", task_ids)

    def test_list_sessions_multiple_tasks_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = SQLiteStateBackend(Path(tmp) / "state")
            backend.append_event(
                task_id="T1",
                run_id="R1",
                step_id=None,
                event_type="HUMAN",
                severity="INFO",
                payload={"message": "goal one", "sender": "human"},
            )
            backend.append_event(
                task_id="T1",
                run_id="R1",
                step_id=None,
                event_type="SYSTEM",
                severity="INFO",
                payload={},
            )
            backend.append_event(
                task_id="T2",
                run_id="R2",
                step_id=None,
                event_type="HUMAN",
                severity="INFO",
                payload={"message": "goal two", "sender": "human"},
            )
            sessions = backend.list_sessions()
            self.assertEqual(len(sessions), 2)
            task_ids = [session["task_id"] for session in sessions]
            self.assertIn("T1", task_ids)
            self.assertIn("T2", task_ids)

    def test_list_events_by_task_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = FileSystemStateBackend(Path(tmp) / "state")
            backend.append_event(
                task_id="T1",
                run_id="R1",
                step_id=None,
                event_type="SYSTEM",
                severity="INFO",
                payload={"a": 1},
            )
            backend.append_event(
                task_id="T2",
                run_id="R2",
                step_id=None,
                event_type="SYSTEM",
                severity="INFO",
                payload={"b": 2},
            )
            events = backend.list_events_by_task("T1")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["task_id"], "T1")

    def test_list_events_by_task_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = SQLiteStateBackend(Path(tmp) / "state")
            backend.append_event(
                task_id="T1",
                run_id="R1",
                step_id=None,
                event_type="SYSTEM",
                severity="INFO",
                payload={"a": 1},
            )
            backend.append_event(
                task_id="T2",
                run_id="R2",
                step_id=None,
                event_type="SYSTEM",
                severity="INFO",
                payload={"b": 2},
            )
            events = backend.list_events_by_task("T1")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["task_id"], "T1")

    def test_list_sessions_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for backend_cls in (FileSystemStateBackend, SQLiteStateBackend):
                backend = backend_cls(root / backend_cls.__name__ / "state")
                backend.append_event(
                    task_id="T1",
                    run_id="R1",
                    step_id=None,
                    event_type="HUMAN",
                    severity="INFO",
                    payload={"message": "hi", "sender": "human"},
                )
                sessions = backend.list_sessions()
                self.assertEqual(len(sessions), 1)
                self.assertEqual(sessions[0]["task_id"], "T1")
                self.assertEqual(sessions[0]["goal"], "hi")
                self.assertEqual(sessions[0]["event_count"], 1)


if __name__ == "__main__":
    unittest.main()
