from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from reliability.handoff.package import HandoffPackageStore
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

    def test_register_maps_default_lane_to_controller_and_updates_lifecycle(self) -> None:
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
            self.assertEqual(lease["lane"], "controller")

            lifecycle = store.load_state()["role_lifecycle"]
            self.assertEqual(lifecycle["controller_lane"], "controller")
            self.assertEqual(lifecycle["controller_ownership"], "controller:S1")
            self.assertEqual(lifecycle["lane:controller"], "active_step:S1")
            self.assertEqual(lifecycle["step:S1"], "owned_by_lane:controller")

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

    def test_self_healing_warning_is_observe_only(self) -> None:
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
                ttl_seconds=300,
            )
            store.save_heartbeat_status(
                {
                    "schema_version": "1.0.0",
                    "status": "WARNING",
                    "last_heartbeat_at": (clock.now() - timedelta(seconds=901)).isoformat(),
                    "reason_code": "NO_OUTPUT_15M",
                    "warning_after_seconds": 900,
                    "stale_after_seconds": 1200,
                    "last_escalation_at": None,
                }
            )

            result = manager.run_self_healing_cycle(
                successor_thread_id="thread-successor",
                successor_pid=2002,
            )

            self.assertEqual(result.action, "OBSERVE")
            self.assertEqual(result.takeover_result, None)
            self.assertEqual(result.handoff_applied, False)

            loaded = registry.list_leases(task_id="DKT-014", run_id="RUN-014")
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["lease_token"], lease["lease_token"])
            self.assertEqual(loaded[0]["thread_id"], "thread-main")
            self.assertEqual(loaded[0]["pid"], 1001)

            state = store.load_state()
            self.assertEqual(state["succession"]["last_takeover_at"], None)

            events = [
                json.loads(line)
                for line in store.events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(
                [event["event_type"] for event in events if event["event_type"] == "LEASE_TAKEOVER"],
                [],
            )
            self.assertEqual(
                [event["event_type"] for event in events if event["event_type"] == "HEARTBEAT_WARNING"],
                ["HEARTBEAT_WARNING"],
            )

    def test_self_healing_stale_triggers_takeover_and_handoff_apply(self) -> None:
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

            state = store.load_state()
            state["current_step"] = "S2"
            state["role_lifecycle"]["step:S1"] = "accepted"
            state["role_lifecycle"]["step:S2"] = "pending"
            store.save_state(state, node="test_seed_handoff", from_status="EXECUTE", to_status="EXECUTE")

            handoff_store = HandoffPackageStore(
                package_path=root / "state" / "handoff_package.json",
                now_provider=clock.now,
            )
            handoff_store.write_package(state)

            state = store.load_state()
            state["current_step"] = "S1"
            state["role_lifecycle"]["step:S1"] = "owned_by_lane:controller"
            state["role_lifecycle"]["step:S2"] = "pending"
            store.save_state(state, node="test_restore_runtime", from_status="EXECUTE", to_status="EXECUTE")

            registry.register(
                lane="default",
                step_id="S1",
                task_id="DKT-014",
                run_id="RUN-014",
                thread_id="thread-main",
                pid=1001,
                ttl_seconds=300,
            )
            store.save_heartbeat_status(
                {
                    "schema_version": "1.0.0",
                    "status": "STALE",
                    "last_heartbeat_at": (clock.now() - timedelta(seconds=1400)).isoformat(),
                    "reason_code": "NO_OUTPUT_20M",
                    "warning_after_seconds": 900,
                    "stale_after_seconds": 1200,
                    "last_escalation_at": clock.now().isoformat(),
                }
            )

            result = manager.run_self_healing_cycle(
                successor_thread_id="thread-successor",
                successor_pid=2002,
                handoff_store=handoff_store,
            )

            self.assertEqual(result.action, "TAKEOVER")
            self.assertIsNotNone(result.takeover_result)
            assert result.takeover_result is not None
            self.assertEqual(result.takeover_result.adopted_step_ids, ("S1",))
            self.assertEqual(result.handoff_applied, True)
            self.assertEqual(result.handoff_resume_step_id, "S1")

            loaded = registry.list_leases(task_id="DKT-014", run_id="RUN-014")
            self.assertEqual(loaded[0]["thread_id"], "thread-successor")
            self.assertEqual(loaded[0]["pid"], 2002)

            latest_state = store.load_state()
            self.assertEqual(latest_state["succession"]["last_takeover_at"], clock.now().isoformat())
            self.assertEqual(latest_state["current_step"], "S1")
            self.assertEqual(latest_state["role_lifecycle"]["handoff_resume_step"], "S1")

            events = [
                json.loads(line)
                for line in store.events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            allowed_event_types = {
                "STEP_STARTED",
                "STEP_COMPLETED",
                "STEP_FAILED",
                "ACCEPTANCE_PASSED",
                "ACCEPTANCE_FAILED",
                "HEARTBEAT_WARNING",
                "HEARTBEAT_STALE",
                "LEASE_TAKEOVER",
                "SYSTEM",
            }
            self.assertTrue(
                all(event["event_type"] in allowed_event_types for event in events)
            )
            self.assertIn("LEASE_TAKEOVER", [event["event_type"] for event in events])
            self.assertIn("SYSTEM", [event["event_type"] for event in events])

    def test_self_healing_invalid_lease_forces_takeover_even_on_warning(self) -> None:
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
                ttl_seconds=120,
            )
            clock.advance(seconds=180)
            store.save_heartbeat_status(
                {
                    "schema_version": "1.0.0",
                    "status": "WARNING",
                    "last_heartbeat_at": (clock.now() - timedelta(seconds=901)).isoformat(),
                    "reason_code": "NO_OUTPUT_15M",
                    "warning_after_seconds": 900,
                    "stale_after_seconds": 1200,
                    "last_escalation_at": None,
                }
            )

            result = manager.run_self_healing_cycle(
                successor_thread_id="thread-successor",
                successor_pid=2002,
            )

            self.assertEqual(result.action, "TAKEOVER")
            self.assertTrue(result.decision_reason_code.startswith("INVALID_LEASE_"))
            self.assertIsNotNone(result.takeover_result)
            assert result.takeover_result is not None
            self.assertEqual(result.takeover_result.adopted_step_ids, ())
            self.assertEqual(result.takeover_result.failed_step_ids, ("S1",))

            state = store.load_state()
            self.assertEqual(state["succession"]["last_takeover_at"], clock.now().isoformat())


if __name__ == "__main__":
    unittest.main()
