from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from state.store import SQLiteStateBackend, StateStoreError


class SQLiteBackendAtomicityTests(unittest.TestCase):
    def test_save_state_is_atomic_across_snapshot_and_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = SQLiteStateBackend(Path(tmp) / "state")

            state = backend.load_state()
            state["task_id"] = "DKT-069"
            state["run_id"] = "RUN-ATOMICITY"
            state["status"] = "ANALYSIS"
            state["current_step"] = "S1"

            class _AbortAfterSnapshotConnection(sqlite3.Connection):
                def __init__(self, *args: object, **kwargs: object) -> None:
                    super().__init__(*args, **kwargs)
                    self._snapshot_seen = False

                def execute(self, sql: str, parameters: object = ()) -> sqlite3.Cursor:  # type: ignore[override]
                    if "insert into snapshots" in sql.lower():
                        self._snapshot_seen = True
                    elif self._snapshot_seen and "insert into checkpoints" in sql.lower():
                        raise RuntimeError("simulated crash before checkpoint insert")
                    return super().execute(sql, parameters)  # type: ignore[arg-type]

            real_connect = sqlite3.connect
            with (
                patch("state.store._utc_now", return_value="2026-02-13T13:20:33+00:00"),
                patch("state.store.uuid4", return_value=UUID("00000000-0000-0000-0000-000000000111")),
                patch(
                    "state.store.sqlite3.connect",
                    side_effect=lambda *a, **k: real_connect(
                        *a, **k, factory=_AbortAfterSnapshotConnection
                    ),
                ),
            ):
                with self.assertRaises(StateStoreError):
                    backend.save_state(
                        state,
                        node="extract",
                        from_status="PLANNING",
                        to_status="ANALYSIS",
                    )

            # The failed transaction must not partially persist any state transition artifacts.
            self.assertEqual(backend.list_snapshots(), [])
            resumed = backend.load_latest_valid_checkpoint()
            self.assertIsInstance(resumed, dict)
            self.assertIsNone(resumed.get("task_id"))

    def test_append_event_is_atomic_per_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = SQLiteStateBackend(Path(tmp) / "state")

            class _AbortEventInsertConnection(sqlite3.Connection):
                def execute(self, sql: str, parameters: object = ()) -> sqlite3.Cursor:  # type: ignore[override]
                    if "insert into events" in sql.lower():
                        raise RuntimeError("simulated crash during event append")
                    return super().execute(sql, parameters)  # type: ignore[arg-type]

            real_connect = sqlite3.connect
            with (
                patch("state.store._utc_now", return_value="2026-02-13T13:20:33+00:00"),
                patch("state.store.uuid4", return_value=UUID("00000000-0000-0000-0000-000000000111")),
                patch(
                    "state.store.sqlite3.connect",
                    side_effect=lambda *a, **k: real_connect(
                        *a, **k, factory=_AbortEventInsertConnection
                    ),
                ),
            ):
                with self.assertRaises(StateStoreError):
                    backend.append_event(
                        task_id="DKT-069",
                        run_id="RUN-ATOMICITY",
                        step_id="S1",
                        event_type="SYSTEM",
                        severity="INFO",
                        payload={"hello": "world"},
                        dedup_key="atomic-event",
                    )

            # No event row should exist after the aborted append.
            events_path = backend.events_path
            self.assertTrue(events_path.exists(), "compat events.jsonl is required for operator tooling")
            self.assertEqual(events_path.read_text(encoding="utf-8"), "")

    def test_sqlite_backend_persists_state_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "state"
            backend = SQLiteStateBackend(state_root)

            state = backend.load_state()
            state["task_id"] = "DKT-069"
            state["run_id"] = "RUN-DURABLE"
            state["status"] = "ANALYSIS"
            state["current_step"] = "S1"
            backend.save_state(
                state,
                node="extract",
                from_status="PLANNING",
                to_status="ANALYSIS",
            )
            backend.append_event(
                task_id="DKT-069",
                run_id="RUN-DURABLE",
                step_id="S1",
                event_type="SYSTEM",
                severity="INFO",
                payload={"durability": "check"},
                dedup_key="durable-event",
            )

            restarted = SQLiteStateBackend(state_root)
            reloaded = restarted.load_state()
            self.assertEqual(reloaded.get("task_id"), "DKT-069")
            self.assertEqual(reloaded.get("run_id"), "RUN-DURABLE")
            self.assertGreaterEqual(len(restarted.list_snapshots()), 1)
            checkpoint = restarted.load_latest_valid_checkpoint()
            self.assertEqual(checkpoint.get("task_id"), "DKT-069")
            self.assertTrue((state_root / "state.sqlite3").is_file())
            self.assertTrue(restarted.events_path.is_file())
            self.assertNotEqual(restarted.events_path.read_text(encoding="utf-8").strip(), "")


if __name__ == "__main__":
    unittest.main()
