from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
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
from reliability.scenarios.core_rotation_chaos_matrix import (
    CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG,
    CORE_ROTATION_MATRIX_VERSION,
    DEFAULT_DETERMINISTIC_CONSTRAINTS,
    CoreRotationChaosScenarioFixture,
    DeterministicExecutionConstraints,
    get_core_rotation_chaos_scenario,
    get_default_core_rotation_chaos_scenario,
    list_core_rotation_chaos_scenarios,
    summarize_core_rotation_chaos_matrix,
)
from reliability.succession import SelfHealingCycleResult, SuccessionManager
from state.store import StateStore


TASK_ID = "DKT-036"
RUN_ID = "RUN-INTEGRATED-RELIABILITY"
STEP_ID = "S1"
SOAK_TASK_ID = "DKT-052"
SOAK_DEFAULT_ITERATIONS = 3
SOAK_VARIANCE_LIMIT = 0
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


def _leases_with_successor(
    *,
    status_payload: dict[str, Any],
    task_id: str,
    run_id: str,
    successor_thread_id: str,
) -> list[dict[str, Any]]:
    leases = status_payload.get("leases")
    if not isinstance(leases, list):
        return []
    return [
        lease
        for lease in leases
        if lease.get("status") == "ACTIVE"
        and lease.get("task_id") == task_id
        and lease.get("run_id") == run_id
        and lease.get("thread_id") == successor_thread_id
    ]


def _resolve_fixture_selection(
    scenario_ids: Sequence[str] | None,
) -> tuple[CoreRotationChaosScenarioFixture, ...]:
    if scenario_ids is None:
        return list_core_rotation_chaos_scenarios()

    selected: list[CoreRotationChaosScenarioFixture] = []
    seen: set[str] = set()
    for scenario_id in scenario_ids:
        normalized = scenario_id.strip()
        if not normalized or normalized in seen:
            continue
        selected.append(get_core_rotation_chaos_scenario(normalized))
        seen.add(normalized)

    if not selected:
        raise ValueError("at least one valid scenario id is required")
    return tuple(selected)


def _hash_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _continuity_assertion_signals(
    *,
    fixture: CoreRotationChaosScenarioFixture,
    cycle: SelfHealingCycleResult,
    first_tick_status: str,
    second_tick_stale_event_emitted: bool,
    status_after_recovery: dict[str, Any],
    status_final: dict[str, Any],
    replay_after_recovery: list[dict[str, Any]],
    replay_final: list[dict[str, Any]],
    events: list[dict[str, Any]],
    scenario_root: Path,
    successor_active_after_recovery: list[dict[str, Any]],
) -> dict[str, bool]:
    takeover_at = cycle.takeover_result.takeover_at if cycle.takeover_result is not None else None
    last_takeover_at = (
        status_after_recovery.get("pipeline_state", {})
        .get("succession", {})
        .get("last_takeover_at")
    )

    if cycle.takeover_result is None:
        actual_adopted_step_ids: tuple[str, ...] = ()
        actual_failed_step_ids: tuple[str, ...] = ()
    else:
        actual_adopted_step_ids = tuple(cycle.takeover_result.adopted_step_ids)
        actual_failed_step_ids = tuple(cycle.takeover_result.failed_step_ids)

    expected_adopted_step_ids = tuple(fixture.expected_adopted_step_ids)
    expected_failed_step_ids = tuple(fixture.expected_failed_step_ids)

    resume_step = cycle.handoff_resume_step_id
    resume_step_recorded = (
        status_after_recovery.get("pipeline_state", {})
        .get("role_lifecycle", {})
        .get("handoff_resume_step")
    )

    if fixture.expected_takeover_action == "TAKEOVER":
        takeover_sync = (
            cycle.action == "TAKEOVER"
            and takeover_at is not None
            and last_takeover_at == takeover_at
        )
    else:
        takeover_sync = cycle.action == fixture.expected_takeover_action and takeover_at is None

    handoff_resume = cycle.handoff_applied == fixture.expected_handoff_applied
    if fixture.expected_handoff_applied:
        handoff_resume = handoff_resume and isinstance(resume_step, str) and resume_step_recorded == resume_step
    else:
        handoff_resume = handoff_resume and resume_step is None

    expected_successor_lease = len(expected_adopted_step_ids) > 0
    if expected_successor_lease:
        lease_ownership = len(successor_active_after_recovery) >= 1
    else:
        lease_ownership = len(successor_active_after_recovery) == 0

    event_ids = tuple(
        event.get("event_id")
        for event in events
        if isinstance(event, dict) and isinstance(event.get("event_id"), str)
    )
    replay_event_ids = tuple(
        replay_entry.get("event_id")
        for replay_entry in replay_final
        if isinstance(replay_entry, dict) and isinstance(replay_entry.get("event_id"), str)
    )
    replay_order_consistent = len(replay_final) == len(events) and replay_event_ids == event_ids
    replay_schema_compatible = all(
        isinstance(replay_entry, dict) and replay_entry.get("schema_version") == "1.0.0"
        for replay_entry in replay_final
    )
    takeover_handoff_replay_consistent = takeover_sync and handoff_resume and replay_order_consistent

    signals = {
        "CONT-001": takeover_sync,
        "CONT-002": handoff_resume,
        "CONT-003": (
            isinstance(replay_after_recovery, list)
            and isinstance(replay_final, list)
            and len(replay_after_recovery) <= len(replay_final)
            and len(replay_final) == len(events)
            and status_final.get("pipeline_state", {}).get("task_id")
            == status_after_recovery.get("pipeline_state", {}).get("task_id")
            and status_final.get("pipeline_state", {}).get("run_id")
            == status_after_recovery.get("pipeline_state", {}).get("run_id")
        ),
        "CONT-004": _json_files_parse_without_repair(scenario_root),
        "CONT-005": cycle.action == "TAKEOVER"
        and cycle.decision_reason_code.startswith("INVALID_LEASE_"),
        "CONT-006": first_tick_status == "STALE" and second_tick_stale_event_emitted is False,
        "CONT-007": (
            actual_adopted_step_ids == expected_adopted_step_ids
            and actual_failed_step_ids == expected_failed_step_ids
        ),
        "CONT-008": lease_ownership,
        "CONT-009": takeover_handoff_replay_consistent,
        "CONT-010": replay_order_consistent,
        "CONT-011": replay_schema_compatible,
    }

    return {assertion_id: bool(signals.get(assertion_id, False)) for assertion_id in fixture.continuity_assertions}


def run_integrated_reliability_scenario(
    *,
    repo_root: Path,
    scenario_root: Path,
    task_id: str = TASK_ID,
    run_id: str = RUN_ID,
    step_id: str = STEP_ID,
    scenario_fixture: CoreRotationChaosScenarioFixture | None = None,
    deterministic_constraints: DeterministicExecutionConstraints | None = None,
) -> dict[str, Any]:
    fixture = scenario_fixture or get_default_core_rotation_chaos_scenario()
    constraints = deterministic_constraints or DEFAULT_DETERMINISTIC_CONSTRAINTS

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

    clock = _MutableClock(constraints.resolved_clock_anchor())
    registry = LeaseRegistry(state_store=state_store, now_provider=clock.now)
    _ = registry.register(
        lane="controller",
        step_id=step_id,
        task_id=task_id,
        run_id=run_id,
        thread_id="integrated-controller-thread",
        pid=43210,
        ttl_seconds=fixture.controller_lease_ttl_seconds,
    )

    handoff_store = HandoffPackageStore(package_path=scenario_root / "state" / "handoff_package.json")
    _ = handoff_store.write_package(
        state_store.load_state(),
        include_accepted_steps=fixture.include_accepted_steps_in_handoff,
    )

    signal_at = clock.now() - timedelta(seconds=fixture.heartbeat_silence_seconds)
    heartbeat = HeartbeatDaemon(
        task_id=task_id,
        run_id=run_id,
        step_id=step_id,
        state_store=state_store,
        artifact_root=scenario_root / "artifacts",
        thresholds=HeartbeatThresholds(
            check_interval_seconds=constraints.check_interval_seconds,
            warning_after_seconds=constraints.warning_after_seconds,
            stale_after_seconds=constraints.stale_after_seconds,
        ),
        now_provider=clock.now,
    )
    heartbeat.record_explicit_heartbeat(signal_at)
    _set_mtime(scenario_root / "artifacts" / "integrated" / "heartbeat.log", at=signal_at)

    if fixture.lease_expiry_advance_seconds > 0:
        clock.advance(seconds=fixture.lease_expiry_advance_seconds)

    first_tick = heartbeat.tick()
    clock.advance(seconds=constraints.second_tick_advance_seconds)
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
        include_accepted_steps=fixture.include_accepted_steps_in_handoff,
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
            str(constraints.replay_limit),
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
            str(constraints.replay_limit),
            "--json",
        ),
        expected_codes={0},
    )
    replay_final = json.loads(replay_final_proc.stdout)

    events = _load_events(scenario_root / "state" / "events.jsonl")

    successor_active_after_recovery = _leases_with_successor(
        status_payload=status_after_recovery,
        task_id=task_id,
        run_id=run_id,
        successor_thread_id=successor_thread_id,
    )
    successor_active_final = _leases_with_successor(
        status_payload=status_final,
        task_id=task_id,
        run_id=run_id,
        successor_thread_id=successor_thread_id,
    )

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

    continuity_results = _continuity_assertion_signals(
        fixture=fixture,
        cycle=cycle,
        first_tick_status=first_tick.status,
        second_tick_stale_event_emitted=second_tick.stale_event_emitted,
        status_after_recovery=status_after_recovery,
        status_final=status_final,
        replay_after_recovery=replay_after_recovery,
        replay_final=replay_final,
        events=events,
        scenario_root=scenario_root,
        successor_active_after_recovery=successor_active_after_recovery,
    )
    continuity_details = {
        assertion_id: {
            "description": CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG.get(assertion_id, "unknown assertion"),
            "passed": passed,
        }
        for assertion_id, passed in continuity_results.items()
    }

    if cycle.takeover_result is None:
        adopted_step_ids: tuple[str, ...] = ()
        failed_step_ids: tuple[str, ...] = ()
    else:
        adopted_step_ids = tuple(cycle.takeover_result.adopted_step_ids)
        failed_step_ids = tuple(cycle.takeover_result.failed_step_ids)

    scenario_expectations_checks = {
        "takeover_action_matches_fixture": cycle.action == fixture.expected_takeover_action,
        "heartbeat_status_matches_fixture": first_tick.status == fixture.expected_heartbeat_status,
        "handoff_applied_matches_fixture": cycle.handoff_applied == fixture.expected_handoff_applied,
        "adopted_steps_match_fixture": adopted_step_ids == tuple(fixture.expected_adopted_step_ids),
        "failed_steps_match_fixture": failed_step_ids == tuple(fixture.expected_failed_step_ids),
        "continuity_assertions_met": all(continuity_results.values()) if continuity_results else False,
    }

    expected_successor_lease = len(fixture.expected_adopted_step_ids) > 0
    successor_lease_consistency = (
        len(successor_active_after_recovery) >= 1
        if expected_successor_lease
        else len(successor_active_after_recovery) == 0
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
            and successor_lease_consistency
            and len(takeover_events) >= 1
            and len(handoff_applied_events) >= 1
            and (
                len(stale_events) >= 1 if fixture.expected_heartbeat_status == "STALE" else len(stale_events) >= 0
            )
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
        "heartbeat_condition_matches_fixture": first_tick.status == fixture.expected_heartbeat_status,
        "continuity_assertions_met": all(continuity_results.values()) if continuity_results else False,
    }

    return {
        "task_id": task_id,
        "run_id": run_id,
        "step_id": step_id,
        "scenario_id": fixture.scenario_id,
        "scenario_root": str(scenario_root),
        "matrix_version": CORE_ROTATION_MATRIX_VERSION,
        "scenario_fixture": fixture.to_dict(),
        "deterministic_constraints": constraints.to_dict(),
        "reproducibility": {
            "seed": f"{constraints.seed}:{fixture.scenario_id}",
            "clock_anchor_utc": constraints.to_dict()["clock_anchor_utc"],
            "runtime_mode": _RUNTIME_SETTINGS["runtime"]["mode"],
            "replay_limit": constraints.replay_limit,
            "check_interval_seconds": constraints.check_interval_seconds,
        },
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
            "adopted_step_ids": list(adopted_step_ids),
            "failed_step_ids": list(failed_step_ids),
            "handoff_applied": cycle.handoff_applied,
            "handoff_resume_step_id": cycle.handoff_resume_step_id,
            "successor_active_after_recovery": len(successor_active_after_recovery),
            "successor_active_final": len(successor_active_final),
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
        "scenario_expectations": {
            "checks": scenario_expectations_checks,
            "passed": all(scenario_expectations_checks.values()),
        },
        "continuity_assertions": list(fixture.continuity_assertions),
        "continuity_assertion_results": continuity_results,
        "continuity_assertion_details": continuity_details,
        "evidence_output_points": {
            "scenario_root": str(scenario_root),
            "state_dir": str(scenario_root / "state"),
            "events_log": str(scenario_root / "state" / "events.jsonl"),
            "handoff_package": str(scenario_root / "state" / "handoff_package.json"),
            "runtime_settings": str(settings_path),
        },
        "command_log": [
            {
                "command": f"python -m cli status --root {scenario_root} --task-id {task_id} --run-id {run_id} --json",
                "exit_code": status_after_recovery_proc.returncode,
            },
            {
                "command": (
                    f"python -m cli replay --root {scenario_root} --source events "
                    f"--limit {constraints.replay_limit} --json"
                ),
                "exit_code": replay_after_recovery_proc.returncode,
            },
            {
                "command": f"python -m cli status --root {scenario_root} --task-id {task_id} --run-id {run_id} --json",
                "exit_code": status_final_proc.returncode,
            },
            {
                "command": (
                    f"python -m cli replay --root {scenario_root} --source events "
                    f"--limit {constraints.replay_limit} --json"
                ),
                "exit_code": replay_final_proc.returncode,
            },
        ],
    }


def run_core_rotation_chaos_matrix(
    *,
    repo_root: Path,
    matrix_root: Path,
    deterministic_constraints: DeterministicExecutionConstraints | None = None,
    task_id_prefix: str = "DKT-051",
    run_id_prefix: str = "RUN-CORE-ROTATION",
    step_id: str = STEP_ID,
    scenario_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    constraints = deterministic_constraints or DEFAULT_DETERMINISTIC_CONSTRAINTS
    matrix_root.mkdir(parents=True, exist_ok=True)

    fixtures = _resolve_fixture_selection(scenario_ids)
    matrix_summary = summarize_core_rotation_chaos_matrix()

    scenario_results: list[dict[str, Any]] = []
    for index, fixture in enumerate(fixtures, start=1):
        task_id = f"{task_id_prefix}-{index:02d}"
        run_id = f"{run_id_prefix}-{index:02d}"
        scenario_root = matrix_root / fixture.scenario_id
        result = run_integrated_reliability_scenario(
            repo_root=repo_root,
            scenario_root=scenario_root,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            scenario_fixture=fixture,
            deterministic_constraints=constraints,
        )

        continuity_results = result.get("continuity_assertion_results", {})
        scenario_result = {
            "scenario_id": fixture.scenario_id,
            "task_id": task_id,
            "run_id": run_id,
            "risk_tags": list(fixture.risk_tags),
            "continuity_assertions": list(fixture.continuity_assertions),
            "continuity_assertion_results": continuity_results,
            "continuity_assertion_details": result.get("continuity_assertion_details", {}),
            "scenario_expectations": result.get("scenario_expectations", {}),
            "checks": result.get("checks", {}),
            "takeover": result.get("takeover", {}),
            "event_count": result.get("event_count", 0),
            "replay_count": result.get("replay_count", 0),
            "reproducibility": result.get("reproducibility", {}),
            "deterministic_constraints": result.get("deterministic_constraints", {}),
            "evidence_output_points": result.get("evidence_output_points", {}),
            "command_log": result.get("command_log", []),
        }
        scenario_result["passed"] = bool(
            scenario_result["scenario_expectations"].get("passed")
            and continuity_results
            and all(bool(value) for value in continuity_results.values())
        )
        scenario_results.append(scenario_result)

    assertion_mapping = {
        fixture.scenario_id: list(fixture.continuity_assertions)
        for fixture in fixtures
    }

    reproducibility_metadata_complete = all(
        isinstance(result.get("deterministic_constraints"), dict)
        and bool(result["deterministic_constraints"].get("seed"))
        and bool(result["deterministic_constraints"].get("clock_anchor_utc"))
        and isinstance(result.get("command_log"), list)
        and len(result["command_log"]) >= 4
        and all("exit_code" in item for item in result["command_log"])
        for result in scenario_results
    )

    matrix_checks = {
        "high_risk_paths_covered": bool(matrix_summary.get("checks", {}).get("high_risk_paths_covered")),
        "assertion_mapping_complete": bool(matrix_summary.get("checks", {}).get("assertion_mapping_complete")),
        "reproducibility_metadata_complete": reproducibility_metadata_complete,
        "scenario_expectations_passed": all(result.get("passed", False) for result in scenario_results),
    }

    return {
        "matrix_version": CORE_ROTATION_MATRIX_VERSION,
        "matrix_root": str(matrix_root),
        "deterministic_constraints": constraints.to_dict(),
        "matrix_summary": matrix_summary,
        "assertion_mapping": assertion_mapping,
        "scenario_results": scenario_results,
        "checks": matrix_checks,
    }


def _render_soak_assertion_report(payload: dict[str, Any]) -> str:
    checks = payload.get("checks", {})
    release_gate = payload.get("release_gate", {})
    lines = [
        "# DKT-052 Continuity Assertion Soak Report",
        "",
        f"- Task ID: {payload.get('task_id')}",
        f"- Iterations: {payload.get('iterations')}",
        f"- Scenario IDs: {', '.join(payload.get('scenario_ids', []))}",
        f"- Matrix Version: {payload.get('matrix_version')}",
        f"- Release Gate Status: {release_gate.get('status')}",
        "",
        "## Gate Checks",
        f"- continuity_assertions_all_passed: {checks.get('continuity_assertions_all_passed')}",
        f"- takeover_handoff_replay_consistent: {checks.get('takeover_handoff_replay_consistent')}",
        f"- deterministic_checkpoint_hashes: {checks.get('deterministic_checkpoint_hashes')}",
        f"- bounded_variance: {checks.get('bounded_variance')}",
        "",
        "## Deterministic Checkpoint Hashes",
    ]

    hashes_by_scenario = payload.get("checkpoint_hashes_by_scenario", {})
    for scenario_id, hashes in hashes_by_scenario.items():
        lines.append(f"- {scenario_id}: {', '.join(hashes)}")

    lines.extend(
        [
            "",
            "## Variance",
        ]
    )
    variance_by_scenario = payload.get("variance_by_scenario", {})
    for scenario_id, variance in variance_by_scenario.items():
        lines.append(
            "- "
            f"{scenario_id}: event_count_range={variance.get('event_count_range')} "
            f"replay_count_range={variance.get('replay_count_range')}"
        )
    return "\n".join(lines) + "\n"


def _persist_soak_assertion_outputs(*, soak_root: Path, payload: dict[str, Any]) -> dict[str, str]:
    assertions_root = soak_root / "assertions"
    assertions_root.mkdir(parents=True, exist_ok=True)

    assertions_json_path = assertions_root / "continuity-assertions.json"
    checkpoints_json_path = assertions_root / "deterministic-checkpoints.json"
    release_gate_json_path = assertions_root / "continuity-release-gate.json"
    assertions_markdown_path = assertions_root / "continuity-assertions.md"

    persisted_payload = {
        "task_id": payload["task_id"],
        "matrix_version": payload["matrix_version"],
        "iterations": payload["iterations"],
        "scenario_ids": payload["scenario_ids"],
        "deterministic_constraints": payload["deterministic_constraints"],
        "checks": payload["checks"],
        "release_gate": payload["release_gate"],
        "checkpoint_hashes_by_scenario": payload["checkpoint_hashes_by_scenario"],
        "variance_by_scenario": payload["variance_by_scenario"],
        "checkpoints": payload["checkpoints"],
    }
    assertions_json_path.write_text(json.dumps(persisted_payload, indent=2) + "\n", encoding="utf-8")
    checkpoints_json_path.write_text(json.dumps(payload["checkpoints"], indent=2) + "\n", encoding="utf-8")
    release_gate_json_path.write_text(json.dumps(payload["release_gate"], indent=2) + "\n", encoding="utf-8")
    assertions_markdown_path.write_text(_render_soak_assertion_report(payload), encoding="utf-8")

    return {
        "json": str(assertions_json_path),
        "checkpoints": str(checkpoints_json_path),
        "release_gate": str(release_gate_json_path),
        "markdown": str(assertions_markdown_path),
    }


def run_long_run_soak_harness(
    *,
    repo_root: Path,
    soak_root: Path,
    iterations: int = SOAK_DEFAULT_ITERATIONS,
    deterministic_constraints: DeterministicExecutionConstraints | None = None,
    scenario_ids: Sequence[str] | None = None,
    step_id: str = STEP_ID,
) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    constraints = deterministic_constraints or DEFAULT_DETERMINISTIC_CONSTRAINTS
    fixtures = _resolve_fixture_selection(scenario_ids)
    selected_scenario_ids = [fixture.scenario_id for fixture in fixtures]

    soak_root.mkdir(parents=True, exist_ok=True)
    for existing in soak_root.glob("iteration-*"):
        if existing.is_dir():
            shutil.rmtree(existing)
    assertions_root = soak_root / "assertions"
    if assertions_root.exists():
        shutil.rmtree(assertions_root)

    iteration_results: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    command_log: list[dict[str, Any]] = []
    required_takeover_handoff_replay_assertions = (
        "CONT-001",
        "CONT-002",
        "CONT-003",
        "CONT-009",
        "CONT-010",
        "CONT-011",
    )

    for iteration in range(1, iterations + 1):
        iteration_root = soak_root / f"iteration-{iteration:02d}"
        matrix_payload = run_core_rotation_chaos_matrix(
            repo_root=repo_root,
            matrix_root=iteration_root,
            deterministic_constraints=constraints,
            task_id_prefix=f"{SOAK_TASK_ID}-{iteration:02d}",
            run_id_prefix=f"RUN-LONG-RUN-SOAK-{iteration:02d}",
            step_id=step_id,
            scenario_ids=selected_scenario_ids,
        )

        iteration_checkpoints: list[dict[str, Any]] = []
        for scenario_result in matrix_payload.get("scenario_results", []):
            continuity_assertion_results = {
                key: bool(value)
                for key, value in scenario_result.get("continuity_assertion_results", {}).items()
            }
            takeover = scenario_result.get("takeover", {})
            checkpoint_payload = {
                "scenario_id": scenario_result.get("scenario_id"),
                "takeover_action": takeover.get("action"),
                "decision_reason_code": takeover.get("decision_reason_code"),
                "handoff_applied": takeover.get("handoff_applied"),
                "handoff_resume_step_id": takeover.get("handoff_resume_step_id"),
                "event_count": int(scenario_result.get("event_count", 0)),
                "replay_count": int(scenario_result.get("replay_count", 0)),
                "continuity_assertion_results": continuity_assertion_results,
            }
            checkpoint_hash = _hash_payload(checkpoint_payload)
            takeover_handoff_replay_consistent = all(
                continuity_assertion_results.get(assertion_id, False)
                for assertion_id in required_takeover_handoff_replay_assertions
            )
            checkpoint = {
                "iteration": iteration,
                "matrix_root": str(iteration_root),
                **checkpoint_payload,
                "takeover_handoff_replay_consistent": takeover_handoff_replay_consistent,
                "checkpoint_hash": checkpoint_hash,
            }
            checkpoints.append(checkpoint)
            iteration_checkpoints.append(checkpoint)

            for command in scenario_result.get("command_log", []):
                command_log.append(
                    {
                        "iteration": iteration,
                        "scenario_id": scenario_result.get("scenario_id"),
                        "command": command.get("command"),
                        "exit_code": command.get("exit_code"),
                    }
                )

        iteration_results.append(
            {
                "iteration": iteration,
                "matrix_root": str(iteration_root),
                "scenario_count": len(iteration_checkpoints),
                "checks": matrix_payload.get("checks", {}),
                "checkpoints": iteration_checkpoints,
            }
        )

    checkpoint_hashes_by_scenario: dict[str, list[str]] = {}
    variance_by_scenario: dict[str, dict[str, int | None]] = {}
    for scenario_id in selected_scenario_ids:
        scenario_checkpoints = [checkpoint for checkpoint in checkpoints if checkpoint["scenario_id"] == scenario_id]
        hashes = sorted({checkpoint["checkpoint_hash"] for checkpoint in scenario_checkpoints})
        checkpoint_hashes_by_scenario[scenario_id] = hashes

        event_counts = [int(checkpoint["event_count"]) for checkpoint in scenario_checkpoints]
        replay_counts = [int(checkpoint["replay_count"]) for checkpoint in scenario_checkpoints]
        event_count_range = max(event_counts) - min(event_counts) if event_counts else None
        replay_count_range = max(replay_counts) - min(replay_counts) if replay_counts else None
        variance_by_scenario[scenario_id] = {
            "event_count_range": event_count_range,
            "replay_count_range": replay_count_range,
        }

    checks = {
        "continuity_assertions_all_passed": bool(checkpoints)
        and all(all(result.values()) for result in (checkpoint["continuity_assertion_results"] for checkpoint in checkpoints)),
        "takeover_handoff_replay_consistent": bool(checkpoints)
        and all(checkpoint["takeover_handoff_replay_consistent"] for checkpoint in checkpoints),
        "deterministic_checkpoint_hashes": bool(checkpoint_hashes_by_scenario)
        and all(len(hashes) == 1 for hashes in checkpoint_hashes_by_scenario.values()),
        "bounded_variance": bool(variance_by_scenario)
        and all(
            variance["event_count_range"] is not None
            and variance["replay_count_range"] is not None
            and variance["event_count_range"] <= SOAK_VARIANCE_LIMIT
            and variance["replay_count_range"] <= SOAK_VARIANCE_LIMIT
            for variance in variance_by_scenario.values()
        ),
    }
    release_gate_eligible = all(checks.values())
    release_gate = {
        "task_id": SOAK_TASK_ID,
        "status": "PASS" if release_gate_eligible else "FAIL",
        "eligible": release_gate_eligible,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "criteria": {
            criterion: {
                "required": True,
                "passed": passed,
            }
            for criterion, passed in checks.items()
        },
    }

    payload = {
        "task_id": SOAK_TASK_ID,
        "soak_root": str(soak_root),
        "matrix_version": CORE_ROTATION_MATRIX_VERSION,
        "iterations": iterations,
        "scenario_ids": selected_scenario_ids,
        "deterministic_constraints": constraints.to_dict(),
        "iteration_results": iteration_results,
        "checkpoints": checkpoints,
        "checkpoint_hashes_by_scenario": checkpoint_hashes_by_scenario,
        "variance_by_scenario": variance_by_scenario,
        "checks": checks,
        "release_gate": release_gate,
        "command_log": command_log,
    }
    assertion_outputs = _persist_soak_assertion_outputs(soak_root=soak_root, payload=payload)
    payload["assertion_outputs"] = assertion_outputs
    payload["evidence_output_points"] = {
        "soak_root": str(soak_root),
        "assertions_root": str(soak_root / "assertions"),
        "continuity_assertions_json": assertion_outputs["json"],
        "deterministic_checkpoints_json": assertion_outputs["checkpoints"],
        "continuity_release_gate_json": assertion_outputs["release_gate"],
        "continuity_assertions_markdown": assertion_outputs["markdown"],
    }
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run DKT-036 integrated reliability scenario, DKT-051 core-rotation chaos matrix, "
            "or DKT-052 long-run continuity soak harness"
        )
    )
    parser.add_argument("--scenario-root", help="Root directory for scenario state")
    parser.add_argument("--output-json", help="Optional path to write summary JSON")
    parser.add_argument("--scenario-id", help="Optional matrix fixture id for single-scenario execution")
    parser.add_argument(
        "--matrix",
        action="store_true",
        help="Run the expanded DKT-051 core-rotation chaos scenario matrix",
    )
    parser.add_argument(
        "--matrix-root",
        help="Root directory for matrix execution outputs (defaults to --scenario-root)",
    )
    parser.add_argument(
        "--soak",
        action="store_true",
        help="Run DKT-052 long-run soak harness with deterministic checkpoints",
    )
    parser.add_argument(
        "--soak-root",
        help="Root directory for soak execution outputs (defaults to --scenario-root)",
    )
    parser.add_argument(
        "--soak-iterations",
        type=int,
        default=SOAK_DEFAULT_ITERATIONS,
        help="Number of deterministic soak iterations to execute",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[3]

    if args.soak:
        if args.soak_root:
            soak_root = Path(args.soak_root).resolve()
            soak_root.mkdir(parents=True, exist_ok=True)
        elif args.scenario_root:
            soak_root = Path(args.scenario_root).resolve()
            soak_root.mkdir(parents=True, exist_ok=True)
        else:
            soak_root = Path(tempfile.mkdtemp(prefix="daokit_dkt052_long_run_soak_")).resolve()

        selected_scenario_ids = (args.scenario_id,) if args.scenario_id else None
        payload = run_long_run_soak_harness(
            repo_root=repo_root,
            soak_root=soak_root,
            iterations=args.soak_iterations,
            deterministic_constraints=DEFAULT_DETERMINISTIC_CONSTRAINTS,
            scenario_ids=selected_scenario_ids,
        )
    elif args.matrix:
        if args.matrix_root:
            matrix_root = Path(args.matrix_root).resolve()
            matrix_root.mkdir(parents=True, exist_ok=True)
        elif args.scenario_root:
            matrix_root = Path(args.scenario_root).resolve()
            matrix_root.mkdir(parents=True, exist_ok=True)
        else:
            matrix_root = Path(tempfile.mkdtemp(prefix="daokit_dkt051_core_rotation_matrix_")).resolve()

        payload = run_core_rotation_chaos_matrix(
            repo_root=repo_root,
            matrix_root=matrix_root,
            deterministic_constraints=DEFAULT_DETERMINISTIC_CONSTRAINTS,
        )
    else:
        if args.scenario_root:
            scenario_root = Path(args.scenario_root).resolve()
            scenario_root.mkdir(parents=True, exist_ok=True)
        else:
            scenario_root = Path(tempfile.mkdtemp(prefix="daokit_dkt036_integrated_")).resolve()

        fixture = (
            get_core_rotation_chaos_scenario(args.scenario_id)
            if args.scenario_id
            else get_default_core_rotation_chaos_scenario()
        )
        payload = run_integrated_reliability_scenario(
            repo_root=repo_root,
            scenario_root=scenario_root,
            scenario_fixture=fixture,
            deterministic_constraints=DEFAULT_DETERMINISTIC_CONSTRAINTS,
        )

    rendered = json.dumps(payload, indent=2)

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
