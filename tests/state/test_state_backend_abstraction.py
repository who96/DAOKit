from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from state.backend import StateBackend
from state.store import FileSystemStateBackend, StateStore


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


if __name__ == "__main__":
    unittest.main()
