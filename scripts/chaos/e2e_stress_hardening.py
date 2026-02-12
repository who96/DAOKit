from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from acceptance.engine import AcceptanceEngine
from reliability.heartbeat.daemon import HeartbeatDaemon
from reliability.heartbeat.evaluator import HeartbeatThresholds
from reliability.lease.registry import LeaseRegistry
from state.store import StateStore


TASK_ID = "DKT-017"
RUN_ID = "RUN-E2E-STRESS"
STEP_ID = "S1"


@dataclass
class _MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def _set_mtime(path: Path, at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stale heartbeat signal\n", encoding="utf-8")
    ts = at.timestamp()
    os.utime(path, (ts, ts))


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
        joined = " ".join(["python", "-m", "cli", *args])
        raise RuntimeError(
            f"command failed ({proc.returncode}): {joined}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _no_manual_json_repair_needed(root: Path) -> bool:
    required_json_files = (
        root / "state" / "pipeline_state.json",
        root / "state" / "heartbeat_status.json",
        root / "state" / "process_leases.json",
    )
    for candidate in required_json_files:
        parsed = json.loads(candidate.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            return False
    _ = _load_events(root / "state" / "events.jsonl")
    return True


def _release_active_leases(store: StateStore) -> None:
    registry = LeaseRegistry(state_store=store)
    leases = registry.list_leases(task_id=TASK_ID, run_id=RUN_ID)
    for lease in leases:
        if lease.get("status") != "ACTIVE":
            continue
        registry.release(
            lease_token=str(lease["lease_token"]),
            task_id=TASK_ID,
            run_id=RUN_ID,
            step_id=str(lease["step_id"]),
        )


def _event_log_consistent(events: list[dict[str, Any]], final_state: dict[str, Any]) -> bool:
    if not events:
        return False
    expected_task_id = final_state.get("task_id")
    expected_run_id = final_state.get("run_id")
    if expected_task_id != TASK_ID or expected_run_id != RUN_ID:
        return False
    for event in events:
        if event.get("task_id") != expected_task_id:
            return False
        if event.get("run_id") != expected_run_id:
            return False
        if not isinstance(event.get("event_type"), str):
            return False
        if not isinstance(event.get("timestamp"), str):
            return False
    return True


def run_stress_scenario(*, repo_root: Path, scenario_root: Path) -> dict[str, Any]:
    scenario_root.mkdir(parents=True, exist_ok=True)
    command_log: list[dict[str, Any]] = []

    init_proc = _run_cli(
        repo_root=repo_root,
        args=("init", "--root", str(scenario_root)),
        expected_codes={0},
    )
    command_log.append(
        {
            "command": f"python -m cli init --root {scenario_root}",
            "exit_code": init_proc.returncode,
        }
    )

    interrupted_proc = _run_cli(
        repo_root=repo_root,
        args=(
            "run",
            "--root",
            str(scenario_root),
            "--task-id",
            TASK_ID,
            "--run-id",
            RUN_ID,
            "--goal",
            "End-to-end stress hardening run",
            "--step-id",
            STEP_ID,
            "--simulate-interruption",
        ),
        expected_codes={130},
    )
    command_log.append(
        {
            "command": (
                "python -m cli run --root "
                f"{scenario_root} --task-id {TASK_ID} --run-id {RUN_ID} "
                "--goal 'End-to-end stress hardening run' --step-id S1 --simulate-interruption"
            ),
            "exit_code": interrupted_proc.returncode,
        }
    )

    store = StateStore(scenario_root / "state")
    clock = _MutableClock(datetime(2026, 2, 11, 16, 15, tzinfo=timezone.utc))
    daemon = HeartbeatDaemon(
        task_id=TASK_ID,
        run_id=RUN_ID,
        step_id=STEP_ID,
        state_store=store,
        artifact_root=scenario_root / "artifacts",
        thresholds=HeartbeatThresholds(
            check_interval_seconds=60,
            warning_after_seconds=900,
            stale_after_seconds=1200,
        ),
        now_provider=clock.now,
    )
    stale_signal_at = clock.now() - timedelta(hours=2, minutes=5)
    daemon.record_explicit_heartbeat(stale_signal_at)
    _set_mtime(scenario_root / "artifacts" / "stress" / "heartbeat.log", stale_signal_at)
    first_tick = daemon.tick()
    clock.advance(seconds=300)
    second_tick = daemon.tick()

    takeover_proc = _run_cli(
        repo_root=repo_root,
        args=(
            "takeover",
            "--root",
            str(scenario_root),
            "--task-id",
            TASK_ID,
            "--run-id",
            RUN_ID,
            "--successor-thread-id",
            "stress-successor-thread",
        ),
        expected_codes={0},
    )
    command_log.append(
        {
            "command": (
                "python -m cli takeover --root "
                f"{scenario_root} --task-id {TASK_ID} --run-id {RUN_ID} "
                "--successor-thread-id stress-successor-thread"
            ),
            "exit_code": takeover_proc.returncode,
        }
    )
    takeover_payload = json.loads(takeover_proc.stdout)

    evidence_root = scenario_root / "artifacts" / "reports" / STEP_ID
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "report.md").write_text(
        "# Stress Step Report\n\nGenerated by chaos stress scenario.\n",
        encoding="utf-8",
    )
    (evidence_root / "audit-summary.md").write_text(
        "# Audit Summary\n\nScope check passed for stress scenario evidence.\n",
        encoding="utf-8",
    )
    (evidence_root / "verification.log").write_text(
        "first attempt without command markers\n",
        encoding="utf-8",
    )

    criteria = [
        "System recovers without manual JSON repair",
        "Every completed step links valid evidence artifacts",
        "Final state and event log consistent and replayable",
    ]
    engine = AcceptanceEngine()
    failed_decision = engine.evaluate_step(
        task_id=TASK_ID,
        run_id=RUN_ID,
        step_id=STEP_ID,
        acceptance_criteria=criteria,
        expected_outputs=["report.md", "verification.log", "audit-summary.md"],
        evidence_root=evidence_root,
    ).to_dict()
    if failed_decision["status"] != "failed":
        raise RuntimeError("expected first acceptance attempt to fail and produce rework payload")

    store.append_event(
        task_id=TASK_ID,
        run_id=RUN_ID,
        step_id=STEP_ID,
        event_type="STEP_REWORK_REQUESTED",
        severity="WARN",
        payload={
            "reason_codes": failed_decision["rework"]["failed_criteria"][0]["reason_codes"],
            "source": "stress_scenario",
        },
    )

    (evidence_root / "verification.log").write_text(
        "=== COMMAND ENTRY 1 START ===\n"
        "Command: PYTHONPATH=src python -m unittest discover -s tests/e2e -p 'test_*.py' -v\n"
        "Exit Code: 0\n"
        "=== COMMAND ENTRY 1 END ===\n",
        encoding="utf-8",
    )

    passed_decision = engine.evaluate_step(
        task_id=TASK_ID,
        run_id=RUN_ID,
        step_id=STEP_ID,
        acceptance_criteria=criteria,
        expected_outputs=["report.md", "verification.log", "audit-summary.md"],
        evidence_root=evidence_root,
    ).to_dict()
    if passed_decision["status"] != "passed":
        raise RuntimeError("expected second acceptance attempt to pass after rework")

    state_before_accept = store.load_state()
    prev_status = str(state_before_accept.get("status") or "EXECUTE")
    role_lifecycle = state_before_accept.get("role_lifecycle")
    if not isinstance(role_lifecycle, dict):
        role_lifecycle = {}
        state_before_accept["role_lifecycle"] = role_lifecycle
    role_lifecycle[f"step:{STEP_ID}"] = "accepted"
    state_before_accept.setdefault("step_evidence", {})
    if isinstance(state_before_accept["step_evidence"], dict):
        state_before_accept["step_evidence"][STEP_ID] = [
            "artifacts/reports/S1/report.md",
            "artifacts/reports/S1/verification.log",
            "artifacts/reports/S1/audit-summary.md",
        ]
    store.save_state(
        state_before_accept,
        node="stress_acceptance",
        from_status=prev_status,
        to_status=prev_status,
    )
    store.append_event(
        task_id=TASK_ID,
        run_id=RUN_ID,
        step_id=STEP_ID,
        event_type="STEP_ACCEPTED",
        severity="INFO",
        payload={
            "proof_id": passed_decision["proof"]["proof_id"],
            "evidence_paths": [
                "artifacts/reports/S1/report.md",
                "artifacts/reports/S1/verification.log",
                "artifacts/reports/S1/audit-summary.md",
            ],
        },
    )

    complete_proc = _run_cli(
        repo_root=repo_root,
        args=(
            "run",
            "--root",
            str(scenario_root),
            "--task-id",
            TASK_ID,
            "--run-id",
            RUN_ID,
            "--goal",
            "Finalize stress run after takeover and rework",
            "--step-id",
            STEP_ID,
            "--no-lease",
        ),
        expected_codes={0},
    )
    command_log.append(
        {
            "command": (
                "python -m cli run --root "
                f"{scenario_root} --task-id {TASK_ID} --run-id {RUN_ID} "
                "--goal 'Finalize stress run after takeover and rework' --step-id S1 --no-lease"
            ),
            "exit_code": complete_proc.returncode,
        }
    )

    _release_active_leases(store)

    replay_proc = _run_cli(
        repo_root=repo_root,
        args=(
            "replay",
            "--root",
            str(scenario_root),
            "--source",
            "events",
            "--limit",
            "200",
            "--json",
        ),
        expected_codes={0},
    )
    command_log.append(
        {
            "command": f"python -m cli replay --root {scenario_root} --source events --limit 200 --json",
            "exit_code": replay_proc.returncode,
        }
    )
    replay_payload = json.loads(replay_proc.stdout)

    final_state = store.load_state()
    events = _load_events(scenario_root / "state" / "events.jsonl")

    step_evidence = final_state.get("step_evidence")
    evidence_paths: list[str] = []
    if isinstance(step_evidence, dict):
        raw_paths = step_evidence.get(STEP_ID)
        if isinstance(raw_paths, list):
            evidence_paths = [str(item) for item in raw_paths if isinstance(item, str)]

    linked_evidence_valid = bool(evidence_paths)
    for rel in evidence_paths:
        if not (scenario_root / rel).is_file():
            linked_evidence_valid = False
            break

    stale_events = [event for event in events if event.get("event_type") == "HEARTBEAT_STALE"]

    checks = {
        "recovered_without_manual_json_repair": _no_manual_json_repair_needed(scenario_root),
        "rework_loop_executed": failed_decision["status"] == "failed" and passed_decision["status"] == "passed",
        "succession_takeover_executed": len(takeover_payload.get("adopted_step_ids", [])) >= 1,
        "forced_stale_interval_2h_plus": (
            first_tick.status == "STALE"
            and first_tick.silence_seconds >= 2 * 3600
            and first_tick.reason_code == "NO_OUTPUT_20M"
        ),
        "deduplicated_stale_event": len(stale_events) == 1 and second_tick.stale_event_emitted is False,
        "completed_step_links_valid_evidence": linked_evidence_valid,
        "final_state_event_log_consistent_replayable": (
            _event_log_consistent(events, final_state)
            and isinstance(replay_payload, list)
            and len(replay_payload) == len(events)
            and str(final_state.get("status")) == "DONE"
        ),
    }

    return {
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "scenario_root": str(scenario_root),
        "command_log": command_log,
        "takeover": takeover_payload,
        "rework": {
            "first_status": failed_decision["status"],
            "second_status": passed_decision["status"],
            "proof_id": passed_decision["proof"]["proof_id"],
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
        "final_state": {
            "status": final_state.get("status"),
            "current_step": final_state.get("current_step"),
            "task_id": final_state.get("task_id"),
            "run_id": final_state.get("run_id"),
        },
        "event_count": len(events),
        "replay_count": len(replay_payload),
        "evidence_paths": evidence_paths,
        "checks": checks,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run DKT-017 end-to-end stress scenario.")
    parser.add_argument("--scenario-root", help="Root directory used for stress scenario state")
    parser.add_argument("--output-json", help="Write scenario summary JSON to this path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]

    if args.scenario_root:
        scenario_root = Path(args.scenario_root).resolve()
        scenario_root.mkdir(parents=True, exist_ok=True)
    else:
        scenario_root = Path(
            tempfile.mkdtemp(prefix="daokit_dkt017_stress_")
        ).resolve()

    result = run_stress_scenario(repo_root=repo_root, scenario_root=scenario_root)
    output = json.dumps(result, indent=2)

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
