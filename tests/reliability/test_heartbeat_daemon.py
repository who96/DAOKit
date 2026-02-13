from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from reliability.heartbeat.daemon import HeartbeatDaemon
from reliability.heartbeat.evaluator import HeartbeatThresholds
from state.store import StateStore, create_state_backend


class _MutableClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def _set_mtime(path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    path.touch(exist_ok=True)
    path.write_text("heartbeat\n", encoding="utf-8")
    os.utime(path, (ts, ts))


class HeartbeatDaemonTests(unittest.TestCase):
    def _new_daemon(self, *, root: Path, clock: _MutableClock, artifact_root: Path) -> HeartbeatDaemon:
        store = create_state_backend(root / "state")
        return HeartbeatDaemon(
            task_id="DKT-013",
            run_id="RUN-013",
            step_id="S1",
            state_store=store,
            artifact_root=artifact_root,
            thresholds=HeartbeatThresholds(
                check_interval_seconds=60,
                warning_after_seconds=900,
                stale_after_seconds=1200,
            ),
            now_provider=clock.now,
        )

    def test_execution_with_output_remains_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            clock = _MutableClock(datetime(2026, 2, 11, 15, 30, tzinfo=timezone.utc))
            daemon = self._new_daemon(root=root, clock=clock, artifact_root=artifacts)

            daemon.record_explicit_heartbeat(
                clock.now() - timedelta(seconds=1800)
            )
            _set_mtime(artifacts / "latest.log", clock.now() - timedelta(seconds=30))

            result = daemon.tick()
            heartbeat = daemon.state_store.load_heartbeat_status()

            self.assertEqual(result.status, "ACTIVE")
            self.assertEqual(result.reason_code, None)
            self.assertEqual(heartbeat["status"], "RUNNING")
            self.assertEqual(heartbeat["reason_code"], None)
            self.assertEqual(daemon.state_store.events_path.read_text(encoding="utf-8"), "")

    def test_silence_crossing_threshold_becomes_stale_with_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            clock = _MutableClock(datetime(2026, 2, 11, 15, 30, tzinfo=timezone.utc))
            daemon = self._new_daemon(root=root, clock=clock, artifact_root=artifacts)

            stale_signal_at = clock.now() - timedelta(seconds=1201)
            daemon.record_explicit_heartbeat(stale_signal_at)
            _set_mtime(artifacts / "latest.log", stale_signal_at)

            result = daemon.tick()
            heartbeat = daemon.state_store.load_heartbeat_status()
            events = [
                json.loads(line)
                for line in daemon.state_store.events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertEqual(result.status, "STALE")
            self.assertEqual(result.reason_code, "NO_OUTPUT_20M")
            self.assertEqual(heartbeat["status"], "STALE")
            self.assertEqual(heartbeat["reason_code"], "NO_OUTPUT_20M")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "HEARTBEAT_STALE")
            self.assertEqual(events[0]["payload"]["reason_code"], "NO_OUTPUT_20M")

    def test_duplicate_stale_alerts_are_suppressed_in_same_streak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            clock = _MutableClock(datetime(2026, 2, 11, 15, 30, tzinfo=timezone.utc))
            daemon = self._new_daemon(root=root, clock=clock, artifact_root=artifacts)

            stale_signal_at = clock.now() - timedelta(seconds=1400)
            daemon.record_explicit_heartbeat(stale_signal_at)
            _set_mtime(artifacts / "latest.log", stale_signal_at)

            first = daemon.tick()
            clock.advance(seconds=120)
            second = daemon.tick()

            events = [
                json.loads(line)
                for line in daemon.state_store.events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertEqual(first.status, "STALE")
            self.assertEqual(second.status, "STALE")
            self.assertEqual(
                [event["event_type"] for event in events if event["event_type"] == "HEARTBEAT_STALE"],
                ["HEARTBEAT_STALE"],
            )


if __name__ == "__main__":
    unittest.main()
