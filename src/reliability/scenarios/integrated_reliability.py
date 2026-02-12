from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from daokit.bootstrap import initialize_repository
from orchestrator.engine import create_runtime, resolve_runtime_engine
from reliability.handoff import HandoffPackageStore
from reliability.heartbeat import HeartbeatDaemon, HeartbeatThresholds
from reliability.lease import LeaseRegistry
from reliability.succession import SuccessionManager
from state.store import StateStore


TASK_ID = "DKT-036"
RUN_ID = "RUN-INTEGRATED-RELIABILITY"
STEP_ID = "S1"
_RUNTIME_SETTINGS = {"runtime": {"mode": "integrated"}}
_ACTIVE_STATUSES = {
    "ANALYSIS",
    "FREEZE",
    "EXECUTE",
    "ACCEPT",
    "DRAINING",
    "BLOCKED",
    "RUNNING",
    "WARNING",
    "STALE",
}


@dataclass
class _MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def _set_mtime(path: Path, *, at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("heartbeat artifact\n", encoding="utf-8")
    stamp = at.timestamp()
    os.utime(path, (stamp, stamp))


def _run_cli(
    *,
    repo_root: Path,
    args: Sequence[str],
    expected_codes: set[int],
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    proc = subprocess.run(
        [sys.executable, "-m", "cli", *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in expected_codes:
        cmd = " ".join(["python", "-m", "cli", *args])
        raise RuntimeError(
            f"command failed ({proc.returncode}): {cmd}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = line.strip()
        if not payload:
            continue
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _json_files_parse_without_repair(root: Path) -> bool:
    required = (
        root / "state" / "pipeline_state.json",
        root / "state" / "heartbeat_status.json",
        root / "state" / "process_leases.json",
    )
    try:
        for candidate in required:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return False
        _ = _load_events(root / "state" / "events.jsonl")
    except (OSError, json.JSONDecodeError):
        return False
    return True


def _events_match_run(events: list[dict[str, Any]], *, task_id: str, run_id: str) -> bool:
    if not events:
        return False
    for event in events:
        if event.get("task_id") != task_id:
            return False
        if event.get("run_id") != run_id:
            return False
        if not isinstance(event.get("event_type"), str):
            return False
        if not isinstance(event.get("timestamp"), str):
            return False
    return True


def _reset_scenario_state(root: Path) -> None:
    for relative in ("state", "artifacts"):
        target = root / relative
        if not target.exists():
            continue
        if target.is_file():
            target.unlink()
            continue
        shutil.rmtree(target)


def run_integrated_reliability_scenario(
    *,
    repo_root: Path,
    scenario_root: Path,
    task_id: str = TASK_ID,
    run_id: str = RUN_ID,
    step_id: str = STEP_ID,
) -> dict[str, Any]:
    scenario_root.mkdir(parents=True, exist_ok=True)
    _reset_scenario_state(scenario_root)
    initialize_repository(scenario_root)

    settings_path = scenario_root / "state" / "runtime_settings.json"
    settings_path.write_text(json.dumps(_RUNTIME_SETTINGS, indent=2) + "\n", encoding="utf-8")

    state_store = StateStore(scenario_root / "state")
    resolved_engine = resolve_runtime_engine(config=_RUNTIME_SETTINGS, env={}).value
    runtime = create_runtime(
        task_id=task_id,
        run_id=run_id,
        goal="Validate integrated stale takeover and handoff reliability",
        step_id=step_id,
        state_store=state_store,
        config=_RUNTIME_SETTINGS,
        env={},
    )
    runtime.extract()
    runtime.plan()
    runtime.dispatch()

    state_before_recovery = state_store.load_state()
    active_status = str(state_before_recovery.get("status") or "")

    registry = LeaseRegistry(state_store=state_store)
    _ = registry.register(
        lane="controller",
        step_id=step_id,
        task_id=task_id,
        run_id=run_id,
        thread_id="integrated-controller-thread",
        pid=43210,
        ttl_seconds=1200,
    )

    handoff_store = HandoffPackageStore(package_path=scenario_root / "state" / "handoff_package.json")
    _ = handoff_store.write_package(state_store.load_state(), include_accepted_steps=False)

    now = datetime.now(timezone.utc)
    clock = _MutableClock(now)
    stale_signal_at = now - timedelta(hours=2, minutes=5)
    heartbeat = HeartbeatDaemon(
        task_id=task_id,
        run_id=run_id,
        step_id=step_id,
        state_store=state_store,
        artifact_root=scenario_root / "artifacts",
        thresholds=HeartbeatThresholds(
            check_interval_seconds=60,
            warning_after_seconds=900,
            stale_after_seconds=1200,
        ),
        now_provider=clock.now,
    )
    heartbeat.record_explicit_heartbeat(stale_signal_at)
    _set_mtime(scenario_root / "artifacts" / "integrated" / "heartbeat.log", at=stale_signal_at)
    first_tick = heartbeat.tick()
    clock.advance(seconds=120)
    second_tick = heartbeat.tick()

    successor_thread_id = "integrated-successor-thread"
    manager = SuccessionManager(
        task_id=task_id,
        run_id=run_id,
        state_store=state_store,
        lease_registry=registry,
        now_provider=clock.now,
    )
    cycle = manager.run_self_healing_cycle(
        successor_thread_id=successor_thread_id,
        successor_pid=54321,
        handoff_store=handoff_store,
        include_accepted_steps=False,
        heartbeat_status=first_tick.status,
    )

    status_after_recovery_proc = _run_cli(
        repo_root=repo_root,
        args=(
            "status",
            "--root",
            str(scenario_root),
            "--task-id",
            task_id,
            "--run-id",
            run_id,
            "--json",
        ),
        expected_codes={0},
    )
    status_after_recovery = json.loads(status_after_recovery_proc.stdout)

    replay_after_recovery_proc = _run_cli(
        repo_root=repo_root,
        args=(
            "replay",
            "--root",
            str(scenario_root),
            "--source",
            "events",
            "--limit",
            "500",
            "--json",
        ),
        expected_codes={0},
    )
    replay_after_recovery = json.loads(replay_after_recovery_proc.stdout)

    resumed_runtime = create_runtime(
        task_id=task_id,
        run_id=run_id,
        goal="Complete run after integrated reliability recovery",
        step_id=step_id,
        state_store=state_store,
        config=_RUNTIME_SETTINGS,
        env={},
    )
    final_state = resumed_runtime.run()

    status_final_proc = _run_cli(
        repo_root=repo_root,
        args=(
            "status",
            "--root",
            str(scenario_root),
            "--task-id",
            task_id,
            "--run-id",
            run_id,
            "--json",
        ),
        expected_codes={0},
    )
    status_final = json.loads(status_final_proc.stdout)

    replay_final_proc = _run_cli(
        repo_root=repo_root,
        args=(
            "replay",
            "--root",
            str(scenario_root),
            "--source",
            "events",
            "--limit",
            "500",
            "--json",
        ),
        expected_codes={0},
    )
    replay_final = json.loads(replay_final_proc.stdout)

    events = _load_events(scenario_root / "state" / "events.jsonl")
    leases = status_final.get("leases") if isinstance(status_final.get("leases"), list) else []

    successor_active = [
        lease
        for lease in leases
        if lease.get("status") == "ACTIVE"
        and lease.get("task_id") == task_id
        and lease.get("run_id") == run_id
        and lease.get("thread_id") == successor_thread_id
    ]

    handoff_applied_events = [
        event
        for event in events
        if event.get("event_type") == "SYSTEM"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("operation") == "HANDOFF_APPLIED"
    ]
    takeover_events = [event for event in events if event.get("event_type") == "LEASE_TAKEOVER"]
    stale_events = [event for event in events if event.get("event_type") == "HEARTBEAT_STALE"]

    takeover_at = cycle.takeover_result.takeover_at if cycle.takeover_result is not None else None
    last_takeover_at = (
        status_after_recovery.get("pipeline_state", {})
        .get("succession", {})
        .get("last_takeover_at")
    )

    checks = {
        "forced_stale_condition": (
            first_tick.status == "STALE"
            and first_tick.silence_seconds >= 2 * 3600
            and first_tick.reason_code == "NO_OUTPUT_20M"
            and second_tick.stale_event_emitted is False
        ),
        "takeover_and_handoff_applied_during_active_run": (
            active_status in _ACTIVE_STATUSES
            and cycle.action == "TAKEOVER"
            and cycle.handoff_applied
            and takeover_at is not None
            and last_takeover_at == takeover_at
        ),
        "event_lease_state_consistent": (
            _events_match_run(events, task_id=task_id, run_id=run_id)
            and len(successor_active) >= 1
            and len(takeover_events) >= 1
            and len(handoff_applied_events) >= 1
            and len(stale_events) >= 1
        ),
        "status_replay_consistent_after_recovery": (
            isinstance(replay_after_recovery, list)
            and isinstance(replay_final, list)
            and len(replay_after_recovery) >= len(takeover_events)
            and len(replay_final) == len(events)
            and status_final.get("pipeline_state", {}).get("task_id") == task_id
            and status_final.get("pipeline_state", {}).get("run_id") == run_id
        ),
        "recovered_without_manual_state_repair": _json_files_parse_without_repair(scenario_root),
    }

    return {
        "task_id": task_id,
        "run_id": run_id,
        "step_id": step_id,
        "scenario_root": str(scenario_root),
        "runtime_mode": _RUNTIME_SETTINGS["runtime"]["mode"],
        "resolved_runtime_engine": resolved_engine,
        "runtime_class": runtime.__class__.__name__,
        "graph_backend": getattr(runtime, "graph_backend", "legacy"),
        "active_status_before_recovery": active_status,
        "takeover": {
            "action": cycle.action,
            "decision_reason_code": cycle.decision_reason_code,
            "heartbeat_status": cycle.heartbeat_status,
            "lease_reason_code": cycle.lease_reason_code,
            "takeover_at": takeover_at,
            "adopted_step_ids": list(cycle.takeover_result.adopted_step_ids)
            if cycle.takeover_result is not None
            else [],
            "failed_step_ids": list(cycle.takeover_result.failed_step_ids)
            if cycle.takeover_result is not None
            else [],
            "handoff_applied": cycle.handoff_applied,
            "handoff_resume_step_id": cycle.handoff_resume_step_id,
        },
        "heartbeat": {
            "first_tick": {
                "status": first_tick.status,
                "reason_code": first_tick.reason_code,
                "silence_seconds": first_tick.silence_seconds,
                "stale_event_emitted": first_tick.stale_event_emitted,
            },
            "second_tick": {
                "status": second_tick.status,
                "reason_code": second_tick.reason_code,
                "silence_seconds": second_tick.silence_seconds,
                "stale_event_emitted": second_tick.stale_event_emitted,
            },
            "stale_event_count": len(stale_events),
        },
        "status_after_recovery": status_after_recovery,
        "status_final": status_final,
        "final_state": {
            "status": final_state.get("status"),
            "current_step": final_state.get("current_step"),
            "task_id": final_state.get("task_id"),
            "run_id": final_state.get("run_id"),
        },
        "event_count": len(events),
        "replay_count": len(replay_final),
        "checks": checks,
        "command_log": [
            {
                "command": f"python -m cli status --root {scenario_root} --task-id {task_id} --run-id {run_id} --json",
                "exit_code": status_after_recovery_proc.returncode,
            },
            {
                "command": f"python -m cli replay --root {scenario_root} --source events --limit 500 --json",
                "exit_code": replay_after_recovery_proc.returncode,
            },
            {
                "command": f"python -m cli status --root {scenario_root} --task-id {task_id} --run-id {run_id} --json",
                "exit_code": status_final_proc.returncode,
            },
            {
                "command": f"python -m cli replay --root {scenario_root} --source events --limit 500 --json",
                "exit_code": replay_final_proc.returncode,
            },
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run DKT-036 integrated reliability scenario")
    parser.add_argument("--scenario-root", help="Root directory for scenario state")
    parser.add_argument("--output-json", help="Optional path to write summary JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[3]

    if args.scenario_root:
        scenario_root = Path(args.scenario_root).resolve()
        scenario_root.mkdir(parents=True, exist_ok=True)
    else:
        scenario_root = Path(tempfile.mkdtemp(prefix="daokit_dkt036_integrated_")).resolve()

    payload = run_integrated_reliability_scenario(repo_root=repo_root, scenario_root=scenario_root)
    rendered = json.dumps(payload, indent=2)

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
