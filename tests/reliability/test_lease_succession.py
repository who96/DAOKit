from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from reliability.lease.registry import LeaseRegistry
from reliability.succession.takeover import SuccessionManager
from state.store import StateStore


class _MutableClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def _step_contract(step_id: str, title: str) -> dict[str, object]:
    return {
        "id": step_id,
        "title": title,
        "category": "implementation",
        "goal": f"Execute {step_id}",
        "actions": ["run"],
        "acceptance_criteria": ["done"],
        "expected_outputs": ["report.md"],
        "dependencies": [],
    }


class LeaseSuccessionTests(unittest.TestCase):
    def _new_store(self, root: Path) -> StateStore:
        store = StateStore(root / "state")
        state = store.load_state()
        state["task_id"] = "DKT-014"
        state["run_id"] = "RUN-014"
        state["status"] = "EXECUTE"
        state["current_step"] = "S1"
        state["steps"] = [
            _step_contract("S1", "Lease owner step"),
            _step_contract("S2", "Secondary running step"),
        ]
        store.save_state(state, node="test", from_status="PLANNING", to_status="EXECUTE")
        return store

    def test_lease_register_heartbeat_renew_release_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = _MutableClock(datetime(2026, 2, 11, 15, 30, tzinfo=timezone.utc))
            store = self._new_store(root)
            registry = LeaseRegistry(state_store=store, now_provider=clock.now)

            lease = registry.register(
                lane="default",
                step_id="S1",
                task_id="DKT-014",
                run_id="RUN-014",
                thread_id="thread-main",
                pid=1001,
                ttl_seconds=300,
            )
            self.assertEqual(lease["status"], "ACTIVE")
            self.assertEqual(
                lease["expiry"],
                (clock.now() + timedelta(seconds=300)).isoformat(),
            )

            clock.advance(seconds=30)
            heartbeat = registry.heartbeat(
                lease_token=lease["lease_token"],
                task_id="DKT-014",
                run_id="RUN-014",
                step_id="S1",
            )
            self.assertEqual(heartbeat["last_heartbeat_at"], clock.now().isoformat())

            clock.advance(seconds=30)
            renewed = registry.renew(
                lease_token=lease["lease_token"],
                task_id="DKT-014",
                run_id="RUN-014",
                step_id="S1",
                ttl_seconds=600,
            )
            self.assertEqual(
                renewed["expiry"],
                (clock.now() + timedelta(seconds=600)).isoformat(),
            )

            clock.advance(seconds=15)
            released = registry.release(
                lease_token=lease["lease_token"],
                task_id="DKT-014",
                run_id="RUN-014",
                step_id="S1",
            )
            self.assertEqual(released["status"], "RELEASED")

    def test_expired_leases_cannot_be_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = _MutableClock(datetime(2026, 2, 11, 15, 30, tzinfo=timezone.utc))
            store = self._new_store(root)
            registry = LeaseRegistry(state_store=store, now_provider=clock.now)
            manager = SuccessionManager(
                task_id="DKT-014",
                run_id="RUN-014",
                state_store=store,
                lease_registry=registry,
                now_provider=clock.now,
            )

            lease = registry.register(
                lane="default",
                step_id="S1",
                task_id="DKT-014",
                run_id="RUN-014",
                thread_id="thread-main",
                pid=1001,
                ttl_seconds=120,
            )
            clock.advance(seconds=180)

            result = manager.accept_successor(
                successor_thread_id="thread-successor",
                successor_pid=2002,
            )

            self.assertEqual(result.adopted_step_ids, ())
            self.assertEqual(result.failed_step_ids, ("S1",))
            loaded = registry.list_leases(task_id="DKT-014", run_id="RUN-014")
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["lease_token"], lease["lease_token"])
            self.assertEqual(loaded[0]["status"], "EXPIRED")

    def test_valid_running_leases_transferred_to_successor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = _MutableClock(datetime(2026, 2, 11, 15, 30, tzinfo=timezone.utc))
            store = self._new_store(root)
            registry = LeaseRegistry(state_store=store, now_provider=clock.now)
            manager = SuccessionManager(
                task_id="DKT-014",
                run_id="RUN-014",
                state_store=store,
                lease_registry=registry,
                now_provider=clock.now,
            )

            registry.register(
                lane="default",
                step_id="S1",
                task_id="DKT-014",
                run_id="RUN-014",
                thread_id="thread-main",
                pid=1001,
                ttl_seconds=300,
            )

            result = manager.accept_successor(
                successor_thread_id="thread-successor",
                successor_pid=2002,
            )

            self.assertEqual(result.adopted_step_ids, ("S1",))
            self.assertEqual(result.failed_step_ids, ())

            loaded = registry.list_leases(task_id="DKT-014", run_id="RUN-014")
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["thread_id"], "thread-successor")
            self.assertEqual(loaded[0]["pid"], 2002)
            self.assertEqual(loaded[0]["status"], "ACTIVE")

            state = store.load_state()
            self.assertEqual(state["succession"]["last_takeover_at"], clock.now().isoformat())

    def test_non_adopted_running_steps_marked_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = _MutableClock(datetime(2026, 2, 11, 15, 30, tzinfo=timezone.utc))
            store = self._new_store(root)
            registry = LeaseRegistry(state_store=store, now_provider=clock.now)
            manager = SuccessionManager(
                task_id="DKT-014",
                run_id="RUN-014",
                state_store=store,
                lease_registry=registry,
                now_provider=clock.now,
            )

            registry.register(
                lane="default",
                step_id="S1",
                task_id="DKT-014",
                run_id="RUN-014",
                thread_id="thread-main",
                pid=1001,
                ttl_seconds=300,
            )
            registry.register(
                lane="lane-2",
                step_id="S2",
                task_id="DKT-014",
                run_id="RUN-014",
                thread_id="thread-main",
                pid=1001,
                ttl_seconds=120,
            )
            clock.advance(seconds=180)

            result = manager.accept_successor(
                successor_thread_id="thread-successor",
                successor_pid=2002,
            )

            self.assertEqual(result.adopted_step_ids, ("S1",))
            self.assertEqual(result.failed_step_ids, ("S2",))

            state = store.load_state()
            self.assertEqual(
                state["role_lifecycle"]["step:S2"],
                "failed_non_adopted_lease",
            )

            events = [
                json.loads(line)
                for line in store.events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            step_failed_events = [
                event
                for event in events
                if event["event_type"] == "STEP_FAILED" and event["step_id"] == "S2"
            ]
            self.assertEqual(len(step_failed_events), 1)
            self.assertEqual(
                step_failed_events[0]["payload"]["reason_code"],
                "LEASE_NOT_ADOPTED",
            )


if __name__ == "__main__":
    unittest.main()
