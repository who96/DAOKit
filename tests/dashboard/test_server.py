from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from starlette.testclient import TestClient

from dashboard.server import create_app


class DashboardServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.state_root = self.root / "state"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._write_default_state_files()
        self.client = TestClient(create_app(self.state_root))

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write_default_state_files(self) -> None:
        pipeline_state = {
            "schema_version": "1.0.0",
            "task_id": "DKT-9000",
            "run_id": "RUN-9000",
            "goal": "Test dashboard API wiring",
            "status": "PLANNING",
            "current_step": "S1",
            "steps": [],
            "role_lifecycle": {"orchestrator": "idle"},
            "succession": {"enabled": True, "last_takeover_at": None},
            "updated_at": "2026-02-28T00:00:00+00:00",
        }
        heartbeat_status = {
            "schema_version": "1.0.0",
            "status": "IDLE",
            "last_heartbeat_at": None,
            "reason_code": None,
            "updated_at": "2026-02-28T00:00:00+00:00",
        }
        process_leases = {
            "schema_version": "1.0.0",
            "leases": [],
            "updated_at": "2026-02-28T00:00:00+00:00",
        }
        (self.state_root / "pipeline_state.json").write_text(
            json.dumps(pipeline_state, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.state_root / "heartbeat_status.json").write_text(
            json.dumps(heartbeat_status, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.state_root / "process_leases.json").write_text(
            json.dumps(process_leases, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.state_root / "events.jsonl").write_text("", encoding="utf-8")
        (self.state_root / "snapshots.jsonl").write_text("", encoding="utf-8")
        (self.state_root / "checkpoints.jsonl").write_text("", encoding="utf-8")

    def test_get_state(self) -> None:
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "1.0.0")
        self.assertEqual(payload["status"], "PLANNING")

    def test_get_heartbeat(self) -> None:
        response = self.client.get("/api/heartbeat")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "1.0.0")
        self.assertEqual(payload["status"], "IDLE")

    def test_get_leases(self) -> None:
        response = self.client.get("/api/leases")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("leases", payload)
        self.assertEqual(payload["leases"], [])

    def test_get_events_empty(self) -> None:
        response = self.client.get("/api/events")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_events_with_data(self) -> None:
        events_path = self.state_root / "events.jsonl"
        events_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "event_id": "evt_1",
                            "timestamp": "2026-02-28T00:00:01+00:00",
                            "event_type": "SYSTEM",
                        }
                    ),
                    json.dumps(
                        {
                            "event_id": "evt_2",
                            "timestamp": "2026-02-28T00:00:02+00:00",
                            "event_type": "SYSTEM",
                        }
                    ),
                    json.dumps(
                        {
                            "event_id": "evt_3",
                            "timestamp": "2026-02-28T00:00:03+00:00",
                            "event_type": "SYSTEM",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        response = self.client.get("/api/events?limit=2")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["event_id"], "evt_3")
        self.assertEqual(payload[1]["event_id"], "evt_2")

    def test_get_events_limit(self) -> None:
        lines = []
        for idx in range(1, 6):
            lines.append(
                json.dumps(
                    {
                        "event_id": f"evt_{idx}",
                        "timestamp": f"2026-02-28T00:00:0{idx}+00:00",
                        "event_type": "SYSTEM",
                    }
                )
            )
        (self.state_root / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

        response = self.client.get("/api/events?limit=3")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 3)
        self.assertEqual([item["event_id"] for item in payload], ["evt_5", "evt_4", "evt_3"])

    def test_get_sessions_empty(self) -> None:
        response = self.client.get("/api/sessions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_sessions_groups_by_task_id(self) -> None:
        events = [
            {
                "schema_version": "1.0.0",
                "event_id": "evt_a1",
                "task_id": "TASK-A",
                "run_id": "RUN-A",
                "step_id": None,
                "event_type": "HUMAN",
                "severity": "INFO",
                "timestamp": "2026-03-01T00:00:01+00:00",
                "payload": {"message": "hello A", "sender": "human"},
                "dedup_key": None,
            },
            {
                "schema_version": "1.0.0",
                "event_id": "evt_a2",
                "task_id": "TASK-A",
                "run_id": "RUN-A",
                "step_id": None,
                "event_type": "SYSTEM",
                "severity": "INFO",
                "timestamp": "2026-03-01T00:00:02+00:00",
                "payload": {},
                "dedup_key": None,
            },
            {
                "schema_version": "1.0.0",
                "event_id": "evt_b1",
                "task_id": "TASK-B",
                "run_id": "RUN-B",
                "step_id": None,
                "event_type": "HUMAN",
                "severity": "INFO",
                "timestamp": "2026-03-01T00:00:03+00:00",
                "payload": {"message": "hello B", "sender": "human"},
                "dedup_key": None,
            },
        ]
        lines = [json.dumps(event, separators=(",", ":")) for event in events]
        (self.state_root / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

        response = self.client.get("/api/sessions")
        self.assertEqual(response.status_code, 200)
        sessions = response.json()
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]["task_id"], "TASK-B")
        self.assertEqual(sessions[1]["task_id"], "TASK-A")
        self.assertEqual(sessions[1]["event_count"], 2)
        self.assertEqual(sessions[0]["goal"], "hello B")

    def test_get_events_filter_by_task_id(self) -> None:
        events = [
            {
                "schema_version": "1.0.0",
                "event_id": "evt_x1",
                "task_id": "TASK-X",
                "run_id": "RUN-X",
                "step_id": None,
                "event_type": "SYSTEM",
                "severity": "INFO",
                "timestamp": "2026-03-01T00:00:01+00:00",
                "payload": {},
                "dedup_key": None,
            },
            {
                "schema_version": "1.0.0",
                "event_id": "evt_y1",
                "task_id": "TASK-Y",
                "run_id": "RUN-Y",
                "step_id": None,
                "event_type": "SYSTEM",
                "severity": "INFO",
                "timestamp": "2026-03-01T00:00:02+00:00",
                "payload": {},
                "dedup_key": None,
            },
        ]
        lines = [json.dumps(event, separators=(",", ":")) for event in events]
        (self.state_root / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

        response = self.client.get("/api/events?task_id=TASK-X")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["task_id"], "TASK-X")

    def test_get_events_no_task_id_returns_all(self) -> None:
        events = [
            {
                "schema_version": "1.0.0",
                "event_id": "evt_p1",
                "task_id": "TASK-P",
                "run_id": "RUN-P",
                "step_id": None,
                "event_type": "SYSTEM",
                "severity": "INFO",
                "timestamp": "2026-03-01T00:00:01+00:00",
                "payload": {},
                "dedup_key": None,
            },
            {
                "schema_version": "1.0.0",
                "event_id": "evt_q1",
                "task_id": "TASK-Q",
                "run_id": "RUN-Q",
                "step_id": None,
                "event_type": "SYSTEM",
                "severity": "INFO",
                "timestamp": "2026-03-01T00:00:02+00:00",
                "payload": {},
                "dedup_key": None,
            },
        ]
        lines = [json.dumps(event, separators=(",", ":")) for event in events]
        (self.state_root / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

        response = self.client.get("/api/events")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)

    def test_get_snapshots_empty(self) -> None:
        response = self.client.get("/api/snapshots")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_index(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_post_message(self) -> None:
        response = self.client.post("/api/message", json={"message": "hello"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["event_type"], "HUMAN")
        self.assertIn("event_id", payload)
        self.assertEqual(payload["payload"]["message"], "hello")
        self.assertEqual(payload["payload"]["sender"], "human")

    def test_post_message_empty(self) -> None:
        response = self.client.post("/api/message", json={"message": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_post_message_with_step_id(self) -> None:
        response = self.client.post(
            "/api/message", json={"message": "check S1", "step_id": "S1"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["step_id"], "S1")

    def test_post_message_persisted_in_events(self) -> None:
        self.client.post("/api/message", json={"message": "test msg"})
        events_response = self.client.get("/api/events")
        events = events_response.json()
        self.assertTrue(any(e["event_type"] == "HUMAN" for e in events))

    def test_post_run_empty_goal(self) -> None:
        response = self.client.post("/api/run", json={"goal": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_post_run_returns_started(self) -> None:
        response = self.client.post("/api/run", json={"goal": "test orchestration"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("task_id", payload)
        self.assertTrue(payload["task_id"].startswith("DKT-DASH-"))
        self.assertEqual(payload["status"], "started")

    def test_state_error_handling(self) -> None:
        (self.state_root / "pipeline_state.json").write_text("{invalid json}\n", encoding="utf-8")

        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
