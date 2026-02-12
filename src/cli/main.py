from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from daokit.bootstrap import RepositoryInitError, initialize_repository
from orchestrator.engine import create_runtime
from reliability.handoff import HandoffPackageError, HandoffPackageStore
from reliability.heartbeat import (
    HeartbeatEvaluatorError,
    HeartbeatThresholds,
    evaluate_heartbeat,
    latest_artifact_mtime,
)
from reliability.lease import LeaseRegistry, LeaseRegistryError
from reliability.succession import SuccessionManager
from state.store import StateStore, StateStoreError

REQUIRED_STATE_FILES = (
    "state/pipeline_state.json",
    "state/heartbeat_status.json",
    "state/process_leases.json",
    "state/events.jsonl",
)

RUN_ACTIVE_STATUSES = {
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
RUNTIME_SETTINGS_FILE = Path("state") / "runtime_settings.json"


@dataclass(frozen=True)
class CliCommandError(Exception):
    code: str
    message: str
    exit_code: int = 1

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daokit-cli",
        description="DAOKit CLI workflow and operator recovery commands",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize repository layout and state files")
    init_parser.add_argument("--root", default=".", help="Repository root path")

    check_parser = subparsers.add_parser("check", help="Validate runtime state and health")
    check_parser.add_argument("--root", default=".", help="Repository root path")
    check_parser.add_argument("--artifact-root", default="artifacts", help="Artifacts directory")
    check_parser.add_argument("--check-interval", type=int, default=300)
    check_parser.add_argument("--warning-after", type=int, default=900)
    check_parser.add_argument("--stale-after", type=int, default=1200)
    check_parser.add_argument("--json", action="store_true", help="Print JSON payload")

    run_parser = subparsers.add_parser("run", help="Run orchestrator workflow")
    run_parser.add_argument("--root", default=".", help="Repository root path")
    run_parser.add_argument("--task-id", required=True)
    run_parser.add_argument("--run-id", help="Run identifier (auto-generated when omitted)")
    run_parser.add_argument("--goal", required=True)
    run_parser.add_argument("--step-id", default="S1")
    run_parser.add_argument("--lane", default="default")
    run_parser.add_argument("--thread-id", help="Lease owner thread id")
    run_parser.add_argument("--lease-ttl", type=int, default=1200)
    run_parser.add_argument(
        "--simulate-interruption",
        action="store_true",
        help="Leave lease active and exit with interruption code",
    )
    run_parser.add_argument(
        "--no-lease",
        action="store_true",
        help="Run workflow without registering process lease",
    )

    status_parser = subparsers.add_parser("status", help="Show ledger, heartbeat, and lease status")
    status_parser.add_argument("--root", default=".", help="Repository root path")
    status_parser.add_argument("--task-id", help="Filter leases by task id")
    status_parser.add_argument("--run-id", help="Filter leases by run id")
    status_parser.add_argument("--json", action="store_true", help="Print JSON payload")

    replay_parser = subparsers.add_parser("replay", help="Replay events or snapshots from state ledger")
    replay_parser.add_argument("--root", default=".", help="Repository root path")
    replay_parser.add_argument(
        "--source",
        choices=("events", "snapshots"),
        default="events",
        help="Replay source",
    )
    replay_parser.add_argument("--limit", type=int, default=20)
    replay_parser.add_argument("--json", action="store_true", help="Print JSON payload")

    takeover_parser = subparsers.add_parser("takeover", help="Adopt running leases after interruption")
    takeover_parser.add_argument("--root", default=".", help="Repository root path")
    takeover_parser.add_argument("--task-id", help="Task id to recover")
    takeover_parser.add_argument("--run-id", help="Run id to recover")
    takeover_parser.add_argument("--successor-thread-id", help="Successor thread id")
    takeover_parser.add_argument("--successor-pid", type=int, default=os.getpid())
    takeover_parser.add_argument("--lease-ttl", type=int, help="Optional TTL override")

    handoff_parser = subparsers.add_parser("handoff", help="Create or apply handoff package")
    handoff_parser.add_argument("--root", default=".", help="Repository root path")
    mode = handoff_parser.add_mutually_exclusive_group()
    mode.add_argument("--create", action="store_true", help="Create handoff package")
    mode.add_argument("--apply", action="store_true", help="Apply handoff package to current ledger")
    handoff_parser.add_argument(
        "--package-path",
        default="state/handoff_package.json",
        help="Handoff package path (relative to root unless absolute)",
    )
    handoff_parser.add_argument(
        "--include-accepted-steps",
        action="store_true",
        help="Include accepted steps in resumable set",
    )
    handoff_parser.add_argument(
        "--evidence-path",
        action="append",
        default=[],
        help="Override evidence output paths (repeatable)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "init": _cmd_init,
        "check": _cmd_check,
        "run": _cmd_run,
        "status": _cmd_status,
        "replay": _cmd_replay,
        "takeover": _cmd_takeover,
        "handoff": _cmd_handoff,
    }

    try:
        return handlers[args.command](args)
    except CliCommandError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("E_INTERRUPTED: interrupted by user", file=sys.stderr)
        return 130


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        result = initialize_repository(root)
    except RepositoryInitError as exc:
        raise CliCommandError("E_INIT_FAILED", str(exc)) from exc

    print(f"Initialized DAOKit skeleton at: {root}")
    if result.created:
        print("Created:")
        for item in result.created:
            print(f"  + {item}")
    if result.skipped:
        print("Unchanged:")
        for item in result.skipped:
            print(f"  = {item}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    _validate_required_state_layout(root)

    pipeline_state = _load_json_file(root / "state" / "pipeline_state.json", code="E_CHECK_STATE_INVALID")
    heartbeat_status = _load_json_file(root / "state" / "heartbeat_status.json", code="E_CHECK_STATE_INVALID")
    leases_payload = _load_json_file(root / "state" / "process_leases.json", code="E_CHECK_STATE_INVALID")

    try:
        thresholds = HeartbeatThresholds(
            check_interval_seconds=args.check_interval,
            warning_after_seconds=args.warning_after,
            stale_after_seconds=args.stale_after,
        )
    except HeartbeatEvaluatorError as exc:
        raise CliCommandError("E_CHECK_HEARTBEAT_INVALID", str(exc)) from exc

    explicit_heartbeat_at = _parse_optional_datetime(
        heartbeat_status.get("last_heartbeat_at"),
        code="E_CHECK_HEARTBEAT_INVALID",
        field_name="heartbeat_status.last_heartbeat_at",
    )
    implicit_output_at = latest_artifact_mtime(root / args.artifact_root)

    status_text = str(pipeline_state.get("status") or "").upper()
    evaluation = evaluate_heartbeat(
        now=datetime.now(timezone.utc),
        execution_active=status_text in RUN_ACTIVE_STATUSES,
        thresholds=thresholds,
        explicit_heartbeat_at=explicit_heartbeat_at,
        implicit_output_at=implicit_output_at,
    )

    payload = {
        "health": "PASS" if evaluation.status != "STALE" else "WARN",
        "pipeline_status": pipeline_state.get("status"),
        "heartbeat": {
            "status": evaluation.status,
            "reason_code": evaluation.reason_code,
            "silence_seconds": evaluation.silence_seconds,
        },
        "lease_count": len(leases_payload.get("leases", []))
        if isinstance(leases_payload.get("leases"), list)
        else 0,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Health check: {payload['health']}")
        print(f"pipeline_status={payload['pipeline_status']}")
        print(
            f"heartbeat={payload['heartbeat']['status']} "
            f"silence_seconds={payload['heartbeat']['silence_seconds']}"
        )
        print(f"lease_count={payload['lease_count']}")

    if evaluation.status == "STALE":
        return 2
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    state_store = StateStore(root / "state")
    runtime_settings = _load_optional_runtime_settings(root)

    run_id = args.run_id or _generate_run_id(args.task_id)
    try:
        runtime = create_runtime(
            task_id=args.task_id,
            run_id=run_id,
            goal=args.goal,
            step_id=args.step_id,
            state_store=state_store,
            env=os.environ,
            config=runtime_settings,
        )
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        raise CliCommandError("E_RUN_FAILED", str(exc)) from exc

    lease_registry: LeaseRegistry | None = None
    lease_record: dict[str, Any] | None = None
    if not args.no_lease:
        try:
            lease_registry = LeaseRegistry(state_store=state_store)
            lease_record = lease_registry.register(
                lane=args.lane,
                step_id=args.step_id,
                task_id=args.task_id,
                run_id=run_id,
                thread_id=args.thread_id or f"cli-{os.getpid()}",
                pid=os.getpid(),
                ttl_seconds=args.lease_ttl,
            )
        except LeaseRegistryError as exc:
            raise CliCommandError("E_RUN_FAILED", f"unable to register lease: {exc}") from exc

    if args.simulate_interruption:
        print(
            "E_RUN_INTERRUPTED: simulated interruption, lease left ACTIVE for takeover",
            file=sys.stderr,
        )
        return 130

    try:
        final_state = runtime.run()
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        raise CliCommandError("E_RUN_FAILED", str(exc)) from exc

    if lease_registry is not None and lease_record is not None:
        try:
            lease_registry.release(
                lease_token=str(lease_record["lease_token"]),
                task_id=args.task_id,
                run_id=run_id,
                step_id=args.step_id,
            )
        except LeaseRegistryError:
            pass

    print(
        " ".join(
            [
                f"task_id={args.task_id}",
                f"run_id={run_id}",
                f"status={final_state.get('status')}",
                f"current_step={final_state.get('current_step')}",
            ]
        )
    )
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    state_store = StateStore(root / "state")

    try:
        pipeline_state = state_store.load_state()
        heartbeat_status = state_store.load_heartbeat_status()
    except StateStoreError as exc:
        raise CliCommandError("E_STATUS_FAILED", str(exc)) from exc

    task_id_filter = args.task_id
    run_id_filter = args.run_id
    if task_id_filter is None:
        task_id_filter = _normalize_optional_text(pipeline_state.get("task_id"))
    if run_id_filter is None:
        run_id_filter = _normalize_optional_text(pipeline_state.get("run_id"))

    try:
        leases = LeaseRegistry(state_store=state_store).list_leases(
            task_id=task_id_filter,
            run_id=run_id_filter,
        )
    except LeaseRegistryError as exc:
        raise CliCommandError("E_STATUS_FAILED", str(exc)) from exc

    handoff_store = HandoffPackageStore(package_path=root / "state" / "handoff_package.json")
    handoff_package = handoff_store.load_package()

    payload = {
        "pipeline_state": pipeline_state,
        "heartbeat_status": heartbeat_status,
        "leases": leases,
        "handoff_package": handoff_package,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            " ".join(
                [
                    f"task_id={pipeline_state.get('task_id')}",
                    f"run_id={pipeline_state.get('run_id')}",
                    f"status={pipeline_state.get('status')}",
                    f"current_step={pipeline_state.get('current_step')}",
                    f"heartbeat={heartbeat_status.get('status')}",
                    f"leases={len(leases)}",
                    f"handoff={'yes' if handoff_package else 'no'}",
                ]
            )
        )
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    limit = max(args.limit, 1)

    if args.source == "events":
        events_path = root / "state" / "events.jsonl"
        entries = _load_json_lines(events_path, code="E_REPLAY_FAILED")
    else:
        state_store = StateStore(root / "state")
        try:
            entries = state_store.list_snapshots()
        except StateStoreError as exc:
            raise CliCommandError("E_REPLAY_FAILED", str(exc)) from exc

    entries = entries[-limit:]

    if args.json:
        print(json.dumps(entries, indent=2))
        return 0

    if not entries:
        print(f"No {args.source} entries recorded.")
        return 0

    for entry in entries:
        if args.source == "events":
            print(
                " ".join(
                    [
                        str(entry.get("timestamp") or "-"),
                        str(entry.get("event_type") or "UNKNOWN"),
                        f"step={entry.get('step_id') or '-'}",
                        f"severity={entry.get('severity') or '-'}",
                    ]
                )
            )
        else:
            print(
                " ".join(
                    [
                        str(entry.get("timestamp") or "-"),
                        str(entry.get("node") or "-"),
                        f"from={entry.get('from_status') or '-'}",
                        f"to={entry.get('to_status') or '-'}",
                    ]
                )
            )
    return 0


def _cmd_takeover(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    state_store = StateStore(root / "state")
    try:
        state = state_store.load_state()
    except StateStoreError as exc:
        raise CliCommandError("E_TAKEOVER_FAILED", str(exc)) from exc

    task_id = args.task_id or _normalize_optional_text(state.get("task_id"))
    run_id = args.run_id or _normalize_optional_text(state.get("run_id"))
    if task_id is None:
        raise CliCommandError("E_TAKEOVER_FAILED", "task id is required for takeover")
    if run_id is None:
        raise CliCommandError("E_TAKEOVER_FAILED", "run id is required for takeover")

    successor_thread_id = args.successor_thread_id or f"takeover-{os.getpid()}"

    try:
        manager = SuccessionManager(
            task_id=task_id,
            run_id=run_id,
            state_store=state_store,
            lease_registry=LeaseRegistry(state_store=state_store),
        )
        result = manager.accept_successor(
            successor_thread_id=successor_thread_id,
            successor_pid=args.successor_pid,
            lease_ttl_seconds=args.lease_ttl,
        )
    except (LeaseRegistryError, ValueError) as exc:
        raise CliCommandError("E_TAKEOVER_FAILED", str(exc)) from exc

    payload = {
        "task_id": result.task_id,
        "run_id": result.run_id,
        "takeover_at": result.takeover_at,
        "adopted_step_ids": list(result.adopted_step_ids),
        "failed_step_ids": list(result.failed_step_ids),
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_handoff(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    package_path = _resolve_path(root, args.package_path)
    state_store = StateStore(root / "state")

    try:
        ledger_state = state_store.load_state()
    except StateStoreError as exc:
        raise CliCommandError("E_HANDOFF_FAILED", str(exc)) from exc

    store = HandoffPackageStore(package_path=package_path)

    if args.apply:
        before_status = str(ledger_state.get("status") or "EXECUTE")
        try:
            resume = store.apply_package(
                ledger_state,
                include_accepted_steps=args.include_accepted_steps,
            )
        except HandoffPackageError as exc:
            raise CliCommandError("E_HANDOFF_FAILED", str(exc)) from exc

        state_store.save_state(
            ledger_state,
            node="cli_handoff_apply",
            from_status=before_status,
            to_status=str(ledger_state.get("status") or before_status),
        )
        print(json.dumps(resume.to_dict(), indent=2))
        return 0

    evidence_paths = args.evidence_path if args.evidence_path else None
    try:
        package = store.write_package(
            ledger_state,
            evidence_paths=evidence_paths,
            include_accepted_steps=args.include_accepted_steps,
        )
    except HandoffPackageError as exc:
        raise CliCommandError("E_HANDOFF_FAILED", str(exc)) from exc

    print(json.dumps(package, indent=2))
    return 0


def _validate_required_state_layout(root: Path) -> None:
    for relative in REQUIRED_STATE_FILES:
        candidate = root / relative
        if not candidate.exists():
            raise CliCommandError(
                "E_CHECK_LAYOUT_MISSING",
                f"missing required file: {relative}",
            )
        if not candidate.is_file():
            raise CliCommandError(
                "E_CHECK_LAYOUT_MISSING",
                f"required path is not a file: {relative}",
            )


def _load_json_file(path: Path, *, code: str) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise CliCommandError(code, f"missing JSON file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliCommandError(code, f"{path}: invalid JSON") from exc

    if not isinstance(payload, dict):
        raise CliCommandError(code, f"{path}: expected JSON object")
    return payload


def _load_optional_runtime_settings(root: Path) -> dict[str, Any] | None:
    settings_path = root / RUNTIME_SETTINGS_FILE
    if not settings_path.exists():
        return None
    if not settings_path.is_file():
        raise CliCommandError("E_RUN_FAILED", f"runtime settings path is not a file: {settings_path}")

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliCommandError("E_RUN_FAILED", f"{settings_path}: invalid JSON") from exc

    if not isinstance(payload, dict):
        raise CliCommandError("E_RUN_FAILED", f"{settings_path}: expected JSON object")
    return payload


def _load_json_lines(path: Path, *, code: str) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        raise CliCommandError(code, f"missing JSONL file: {path}")

    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise CliCommandError(
                code,
                f"{path}:{line_number} contains invalid JSON",
            ) from exc
        if not isinstance(item, dict):
            raise CliCommandError(code, f"{path}:{line_number} expected JSON object")
        entries.append(item)
    return entries


def _parse_optional_datetime(
    value: Any,
    *,
    code: str,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CliCommandError(code, f"{field_name} must be an ISO datetime string")

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CliCommandError(code, f"{field_name} has invalid datetime format") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_path(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (root / candidate).resolve()


def _normalize_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _generate_run_id(task_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{task_id}_{stamp}"
