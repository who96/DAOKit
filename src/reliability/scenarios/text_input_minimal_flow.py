from __future__ import annotations

import argparse
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

    return {
        "task_id": task_id,
        "run_id": run_id,
        "scenario_root": str(scenario_root),
        "state_path": str(state_store.pipeline_state_path),
        "events_path": str(state_store.events_path),
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
