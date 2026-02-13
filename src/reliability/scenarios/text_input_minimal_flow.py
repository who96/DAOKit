from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

from artifacts.dispatch_artifacts import DispatchArtifactStore
from daokit.bootstrap import initialize_repository
from dispatch.shim_adapter import ShimDispatchAdapter
from orchestrator.engine import create_runtime
from state.store import StateStore


REQUIRED_EVIDENCE_PACKET = (
    "report.md",
    "verification.log",
    "audit-summary.md",
    "events.jsonl",
)

EXPECTED_PROCESS_PATH = (
    {"node": "bootstrap", "from_status": None, "to_status": "PLANNING"},
    {"node": "extract", "from_status": "PLANNING", "to_status": "ANALYSIS"},
    {"node": "plan", "from_status": "ANALYSIS", "to_status": "FREEZE"},
    {"node": "dispatch", "from_status": "FREEZE", "to_status": "EXECUTE"},
    {"node": "verify", "from_status": "EXECUTE", "to_status": "ACCEPT"},
    {"node": "transition", "from_status": "ACCEPT", "to_status": "DONE"},
)

REQUIRED_FINAL_RUN_PATHS = (
    "pre_batch_results.tsv",
    "batch_results.tsv",
    "batch_resume_from_dkt003_results.tsv",
    "run_evidence_index.tsv",
    "run_evidence_index.md",
    "evidence_manifest.sha256",
    "evidence",
    "RELEASE_SNAPSHOT.md",
)

REQUIRED_INDEX_COLUMNS = (
    "task_id",
    "run_id",
    "ledger_source",
    "execution_track",
    "evidence_complete",
    "final_assessment",
    "report_md",
    "verification_log",
    "audit_summary",
)


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _load_snapshots(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    snapshots: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            snapshots.append(parsed)
    return snapshots


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _stable_signature(value: Any) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return digest


def _normalize_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _observed_process_path(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    for snapshot in snapshots:
        node = _normalize_optional_string(snapshot.get("node"))
        if node is None:
            continue
        observed.append(
            {
                "node": node,
                "from_status": _normalize_optional_string(snapshot.get("from_status")),
                "to_status": _normalize_optional_string(snapshot.get("to_status")),
            }
        )
    return observed


def _dispatch_actions(call_entries: list[Any]) -> list[str]:
    actions: list[str] = []
    for entry in call_entries:
        if not isinstance(entry, Mapping):
            continue
        action = _normalize_optional_string(entry.get("action"))
        if action is None:
            continue
        actions.append(action)
    return actions


def _dispatch_shape_consistent(actions: list[str]) -> bool:
    if not actions:
        return False
    if actions[0] != "create":
        return False
    in_rework_phase = False
    for action in actions[1:]:
        if action == "resume":
            if in_rework_phase:
                return False
            continue
        if action == "rework":
            in_rework_phase = True
            continue
        return False
    return True


def _build_process_path_acceptance(
    *,
    snapshots: list[dict[str, Any]],
    call_entries: list[Any],
) -> dict[str, Any]:
    observed = _observed_process_path(snapshots)
    dispatch_actions = _dispatch_actions(call_entries)
    dispatch_shape_ok = _dispatch_shape_consistent(dispatch_actions)
    observed_signature = _stable_signature(
        {
            "transitions": observed,
            "dispatch_shape": (
                "create,resume*,rework*" if dispatch_shape_ok else ",".join(dispatch_actions)
            ),
        }
    )
    expected_signature = _stable_signature(
        {
            "transitions": EXPECTED_PROCESS_PATH,
            "dispatch_shape": "create,resume*,rework*",
        }
    )
    transition_path_matches = observed == list(EXPECTED_PROCESS_PATH)
    return {
        "expected": list(EXPECTED_PROCESS_PATH),
        "observed": observed,
        "dispatch_actions": dispatch_actions,
        "dispatch_shape_consistent": dispatch_shape_ok,
        "transition_path_matches": transition_path_matches,
        "signature": observed_signature,
        "expected_signature": expected_signature,
        "consistent": transition_path_matches and dispatch_shape_ok,
    }


def _events_schema_compatible(events: list[dict[str, Any]], *, task_id: str, run_id: str) -> bool:
    if not events:
        return False
    for event in events:
        if event.get("schema_version") != "1.0.0":
            return False
        if event.get("task_id") != task_id:
            return False
        if event.get("run_id") != run_id:
            return False
        if not isinstance(event.get("event_type"), str):
            return False
        if not isinstance(event.get("timestamp"), str):
            return False
        if not isinstance(event.get("payload"), Mapping):
            return False
    return True


def _release_anchor_compatibility(repo_root: Path) -> dict[str, Any]:
    final_run_root = repo_root / "docs" / "reports" / "final-run"
    missing_paths = [
        (final_run_root / relative).as_posix()
        for relative in REQUIRED_FINAL_RUN_PATHS
        if not (final_run_root / relative).exists()
    ]

    index_header: list[str] = []
    index_path = final_run_root / "run_evidence_index.tsv"
    if index_path.exists():
        lines = index_path.read_text(encoding="utf-8").splitlines()
        if lines:
            index_header = lines[0].split("\t")
    header_matches = tuple(index_header) == REQUIRED_INDEX_COLUMNS

    return {
        "final_run_root": final_run_root.as_posix(),
        "required_paths_missing": missing_paths,
        "run_evidence_index_header": index_header,
        "run_evidence_index_header_matches": header_matches,
        "compatible": not missing_paths and header_matches,
    }


def _build_evidence_paths(*, evidence_root: Path) -> dict[str, Path]:
    return {
        "report.md": evidence_root / "report.md",
        "verification.log": evidence_root / "verification.log",
        "audit-summary.md": evidence_root / "audit-summary.md",
        "events.jsonl": evidence_root / "events.jsonl",
    }


def _artifact_structure_acceptance(
    *,
    evidence_paths: Mapping[str, Path],
    scenario_root: Path,
    task_id: str,
    run_id: str,
) -> dict[str, Any]:
    missing_files = [
        file_name
        for file_name in REQUIRED_EVIDENCE_PACKET
        if not evidence_paths[file_name].is_file()
    ]
    present_files = [
        file_name
        for file_name in REQUIRED_EVIDENCE_PACKET
        if evidence_paths[file_name].is_file()
    ]

    verification_has_markers = False
    verification_path = evidence_paths["verification.log"]
    if verification_path.is_file():
        verification_text = verification_path.read_text(encoding="utf-8")
        verification_has_markers = (
            "Command:" in verification_text and "=== COMMAND ENTRY" in verification_text
        )

    events = _load_events(evidence_paths["events.jsonl"])
    events_schema_ok = _events_schema_compatible(events, task_id=task_id, run_id=run_id)

    relative_paths: dict[str, str] = {}
    for file_name, path in evidence_paths.items():
        try:
            relative_paths[file_name] = path.relative_to(scenario_root).as_posix()
        except ValueError:
            relative_paths[file_name] = path.as_posix()

    signature = _stable_signature(
        {
            "required_files": list(REQUIRED_EVIDENCE_PACKET),
            "relative_paths": relative_paths,
        }
    )

    consistent = not missing_files and verification_has_markers and events_schema_ok
    return {
        "required_files": list(REQUIRED_EVIDENCE_PACKET),
        "present_files": present_files,
        "missing_files": missing_files,
        "relative_paths": relative_paths,
        "verification_has_command_markers": verification_has_markers,
        "events_schema_compatible": events_schema_ok,
        "signature": signature,
        "consistent": consistent,
    }


def _render_report_markdown(
    *,
    task_id: str,
    run_id: str,
    step_id: str,
    process_path: Mapping[str, Any],
    artifact_structure: Mapping[str, Any],
    release_anchor: Mapping[str, Any],
) -> str:
    lines = [
        "# Text Input Minimal Flow Report",
        "",
        f"- Task: `{task_id}`",
        f"- Run: `{run_id}`",
        f"- Step: `{step_id}`",
        "",
        "## Acceptance Checks",
        "",
        f"- Process-path consistency: {'PASS' if process_path.get('consistent') else 'FAIL'}",
        f"- Artifact-structure consistency: {'PASS' if artifact_structure.get('consistent') else 'FAIL'}",
        f"- Release-anchor compatibility: {'PASS' if release_anchor.get('compatible') else 'FAIL'}",
        "",
        "## Signatures",
        "",
        f"- Process path: `{process_path.get('signature')}`",
        f"- Artifact structure: `{artifact_structure.get('signature')}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def _render_verification_log(
    *,
    scenario_root: Path,
    task_id: str,
    run_id: str,
    step_id: str,
    process_path: Mapping[str, Any],
    artifact_structure: Mapping[str, Any],
    release_anchor: Mapping[str, Any],
) -> str:
    lines = [
        "=== COMMAND ENTRY 1 START ===",
        (
            "Command: python -m reliability.scenarios.text_input_minimal_flow "
            f"--scenario-root {scenario_root} --task-id {task_id} --run-id {run_id} --step-id {step_id}"
        ),
        f"Working Directory: {scenario_root}",
        "--- OUTPUT START ---",
        f"process_path_signature={process_path.get('signature')}",
        f"process_path_expected_signature={process_path.get('expected_signature')}",
        f"process_path_consistent={process_path.get('consistent')}",
        f"artifact_structure_signature={artifact_structure.get('signature')}",
        f"artifact_structure_consistent={artifact_structure.get('consistent')}",
        f"release_anchor_compatible={release_anchor.get('compatible')}",
        "--- OUTPUT END ---",
        "Exit Code: 0",
        "=== COMMAND ENTRY 1 END ===",
        "",
    ]
    return "\n".join(lines)


def _render_audit_summary(
    *,
    process_path: Mapping[str, Any],
    artifact_structure: Mapping[str, Any],
    release_anchor: Mapping[str, Any],
    evidence_paths: Mapping[str, Path],
) -> str:
    lines = [
        "# Audit Summary",
        "",
        f"- [ {'PASS' if process_path.get('consistent') else 'FAIL'} ] process-path consistency",
        f"- [ {'PASS' if artifact_structure.get('consistent') else 'FAIL'} ] artifact-structure consistency",
        f"- [ {'PASS' if release_anchor.get('compatible') else 'FAIL'} ] release-anchor compatibility",
        "",
        "Required evidence files:",
    ]
    for file_name in REQUIRED_EVIDENCE_PACKET:
        lines.append(f"- `{file_name}` -> `{evidence_paths[file_name].as_posix()}`")
    lines.append("")
    return "\n".join(lines)


def _build_dispatch_runner(
    *,
    repo_root: Path,
    scenario_root: Path,
    env_overrides: Mapping[str, str] | None = None,
):
    env = os.environ.copy()
    repo_src = (repo_root / "src").resolve().as_posix()
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    if existing_pythonpath:
        env["PYTHONPATH"] = f"{repo_src}{os.pathsep}{existing_pythonpath}"
    else:
        env["PYTHONPATH"] = repo_src
    if env_overrides:
        for key, value in env_overrides.items():
            env[str(key)] = str(value)

    def _runner(command: Sequence[str], payload: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(scenario_root),
            env=env,
        )

    return _runner


def _latest_dispatch_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    dispatch_events = [
        event
        for event in events
        if isinstance(event.get("dedup_key"), str)
        and str(event["dedup_key"]).startswith("dispatch-invocation:")
        and isinstance(event.get("payload"), Mapping)
    ]
    if not dispatch_events:
        return None
    return dispatch_events[-1]


def run_text_input_minimal_flow(
    *,
    repo_root: Path,
    scenario_root: Path,
    task_input: str,
    task_id: str = "DKT-057",
    run_id: str = "RUN-TEXT-INPUT-MINIMAL",
    step_id: str = "S1",
    env_overrides: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    scenario_root.mkdir(parents=True, exist_ok=True)
    initialize_repository(scenario_root)

    state_store = StateStore(scenario_root / "state")
    dispatch_adapter = ShimDispatchAdapter(
        shim_path="codex-worker-shim",
        shim_command_prefix=(sys.executable, "-m", "dispatch.codex_worker_shim"),
        artifact_store=DispatchArtifactStore(scenario_root / "artifacts" / "dispatch"),
        command_runner=_build_dispatch_runner(
            repo_root=repo_root,
            scenario_root=scenario_root,
            env_overrides=env_overrides,
        ),
    )

    runtime = create_runtime(
        task_id=task_id,
        run_id=run_id,
        goal=task_input,
        step_id=step_id,
        state_store=state_store,
        dispatch_adapter=dispatch_adapter,
        explicit_engine="langgraph",
        env={},
        config={},
    )
    final_state = runtime.run()

    steps = final_state.get("steps")
    planner_steps = [step for step in (steps if isinstance(steps, list) else []) if isinstance(step, Mapping)]
    events = _load_events(state_store.events_path)
    dispatch_event = _latest_dispatch_event(events)
    dispatch_payload = dispatch_event.get("payload") if isinstance(dispatch_event, Mapping) else {}
    calls = dispatch_payload.get("calls") if isinstance(dispatch_payload, Mapping) else []
    call_entries = list(calls) if isinstance(calls, list) else []
    snapshots = _load_snapshots(state_store.snapshots_path)

    process_path = _build_process_path_acceptance(
        snapshots=snapshots,
        call_entries=call_entries,
    )
    release_anchor = _release_anchor_compatibility(repo_root)

    llm_invoked = any(
        isinstance(entry, Mapping) and bool(entry.get("llm_invoked"))
        for entry in call_entries
    )
    execution_mode = "unknown"
    for entry in call_entries:
        if isinstance(entry, Mapping):
            mode = entry.get("execution_mode")
            if isinstance(mode, str) and mode.strip():
                execution_mode = mode.strip()

    evidence_root = scenario_root / "artifacts" / "reports" / step_id
    evidence_root.mkdir(parents=True, exist_ok=True)
    evidence_paths = _build_evidence_paths(evidence_root=evidence_root)
    evidence_paths["events.jsonl"].write_text(
        state_store.events_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    placeholder_artifact_structure = {
        "required_files": list(REQUIRED_EVIDENCE_PACKET),
        "present_files": ["events.jsonl"],
        "missing_files": ["report.md", "verification.log", "audit-summary.md"],
        "relative_paths": {},
        "verification_has_command_markers": False,
        "events_schema_compatible": False,
        "signature": "pending",
        "consistent": False,
    }
    evidence_paths["report.md"].write_text(
        _render_report_markdown(
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            process_path=process_path,
            artifact_structure=placeholder_artifact_structure,
            release_anchor=release_anchor,
        ),
        encoding="utf-8",
    )
    evidence_paths["verification.log"].write_text(
        _render_verification_log(
            scenario_root=scenario_root,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            process_path=process_path,
            artifact_structure=placeholder_artifact_structure,
            release_anchor=release_anchor,
        ),
        encoding="utf-8",
    )
    evidence_paths["audit-summary.md"].write_text(
        _render_audit_summary(
            process_path=process_path,
            artifact_structure=placeholder_artifact_structure,
            release_anchor=release_anchor,
            evidence_paths=evidence_paths,
        ),
        encoding="utf-8",
    )
    artifact_structure = _artifact_structure_acceptance(
        evidence_paths=evidence_paths,
        scenario_root=scenario_root,
        task_id=task_id,
        run_id=run_id,
    )
    evidence_paths["report.md"].write_text(
        _render_report_markdown(
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            process_path=process_path,
            artifact_structure=artifact_structure,
            release_anchor=release_anchor,
        ),
        encoding="utf-8",
    )
    evidence_paths["verification.log"].write_text(
        _render_verification_log(
            scenario_root=scenario_root,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            process_path=process_path,
            artifact_structure=artifact_structure,
            release_anchor=release_anchor,
        ),
        encoding="utf-8",
    )
    evidence_paths["audit-summary.md"].write_text(
        _render_audit_summary(
            process_path=process_path,
            artifact_structure=artifact_structure,
            release_anchor=release_anchor,
            evidence_paths=evidence_paths,
        ),
        encoding="utf-8",
    )

    checks = {
        "process_path_consistent": bool(process_path.get("consistent")),
        "artifact_structure_consistent": bool(artifact_structure.get("consistent")),
        "release_anchor_compatible": bool(release_anchor.get("compatible")),
    }

    return {
        "task_id": task_id,
        "run_id": run_id,
        "scenario_root": str(scenario_root),
        "state_path": str(state_store.pipeline_state_path),
        "events_path": str(state_store.events_path),
        "snapshots_path": str(state_store.snapshots_path),
        "final_state": final_state,
        "planner": {
            "step_count": len(planner_steps),
            "step_ids": [str(step.get("id")) for step in planner_steps],
        },
        "dispatch": {
            "event_found": dispatch_event is not None,
            "call_count": len(call_entries),
            "llm_invoked": llm_invoked,
            "execution_mode": execution_mode,
            "calls": call_entries,
        },
        "evidence": {
            "root": str(evidence_root),
            "required_files": list(REQUIRED_EVIDENCE_PACKET),
            "paths": {name: path.as_posix() for name, path in evidence_paths.items()},
        },
        "acceptance": {
            "checks": checks,
            "process_path": process_path,
            "artifact_structure": artifact_structure,
            "release_anchor": release_anchor,
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="text-input-minimal-flow",
        description="Run DKT-057 minimal text-input extract-plan-dispatch-acceptance scenario",
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--scenario-root", required=True)
    parser.add_argument("--task-input", required=True)
    parser.add_argument("--task-id", default="DKT-057")
    parser.add_argument("--run-id", default="RUN-TEXT-INPUT-MINIMAL")
    parser.add_argument("--step-id", default="S1")
    parser.add_argument("--codex-bin", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    env_overrides = None
    if args.codex_bin:
        env_overrides = {"DAOKIT_CODEX_BIN": str(args.codex_bin)}

    payload = run_text_input_minimal_flow(
        repo_root=Path(args.repo_root).resolve(),
        scenario_root=Path(args.scenario_root).resolve(),
        task_input=str(args.task_input),
        task_id=str(args.task_id),
        run_id=str(args.run_id),
        step_id=str(args.step_id),
        env_overrides=env_overrides,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
