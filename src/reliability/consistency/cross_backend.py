from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from daokit.bootstrap import initialize_repository
from orchestrator.engine import create_runtime
from reliability.scenarios.integrated_reliability import run_integrated_reliability_scenario
from reliability.scenarios.text_input_minimal_flow import run_text_input_minimal_flow
from state.store import create_state_backend


DEFAULT_BACKENDS = ("filesystem", "sqlite")
DEFAULT_SCENARIOS = (
    "integrated_reliability",
    "text_input_minimal_flow",
    "checkpoint_recovery",
)

VOLATILE_FIELD_TOLERANCE = {
    "ignored_fields": [
        "event_id",
        "checkpoint_id",
        "lease_token",
        "timestamp",
        "updated_at",
        "scenario_root",
        "state_dir",
        "events_log",
        "handoff_package",
        "runtime_settings",
        "operator_recovery_outputs",
        "command_log",
    ],
    "notes": (
        "Equivalence compares backend outputs after canonicalization. Canonicalization keeps only "
        "contract-relevant signals and drops volatile ids/timestamps and absolute filesystem paths."
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    import hashlib

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _reset_scenario_root(scenario_root: Path) -> None:
    if scenario_root.exists():
        shutil.rmtree(scenario_root)
    scenario_root.mkdir(parents=True, exist_ok=True)


def _contract_integrated_reliability(payload: Mapping[str, Any]) -> dict[str, Any]:
    takeover = payload.get("takeover") if isinstance(payload.get("takeover"), Mapping) else {}
    heartbeat = payload.get("heartbeat") if isinstance(payload.get("heartbeat"), Mapping) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), Mapping) else {}
    continuity_results = payload.get("continuity_assertion_results")
    if not isinstance(continuity_results, Mapping):
        continuity_results = {}

    scenario_expectations = payload.get("scenario_expectations")
    expectations_passed = None
    if isinstance(scenario_expectations, Mapping):
        expectations_passed = bool(scenario_expectations.get("passed"))

    final_state = payload.get("final_state") if isinstance(payload.get("final_state"), Mapping) else {}

    first_tick = heartbeat.get("first_tick") if isinstance(heartbeat.get("first_tick"), Mapping) else {}
    second_tick = heartbeat.get("second_tick") if isinstance(heartbeat.get("second_tick"), Mapping) else {}

    return {
        "scenario_id": payload.get("scenario_id"),
        "runtime_mode": payload.get("runtime_mode"),
        "resolved_runtime_engine": payload.get("resolved_runtime_engine"),
        "runtime_class": payload.get("runtime_class"),
        "graph_backend": payload.get("graph_backend"),
        "checks": {key: bool(checks.get(key)) for key in sorted(checks)},
        "scenario_expectations_passed": bool(expectations_passed),
        "continuity_assertion_results": {
            key: bool(continuity_results.get(key)) for key in sorted(continuity_results)
        },
        "takeover": {
            "action": takeover.get("action"),
            "handoff_applied": bool(takeover.get("handoff_applied")),
            "handoff_resume_step_id": takeover.get("handoff_resume_step_id"),
            "adopted_step_ids": list(takeover.get("adopted_step_ids") or []),
            "failed_step_ids": list(takeover.get("failed_step_ids") or []),
            "successor_active_after_recovery": int(takeover.get("successor_active_after_recovery") or 0),
            "successor_active_final": int(takeover.get("successor_active_final") or 0),
        },
        "heartbeat": {
            "first_tick": {
                "status": first_tick.get("status"),
                "reason_code": first_tick.get("reason_code"),
            },
            "second_tick": {
                "status": second_tick.get("status"),
                "reason_code": second_tick.get("reason_code"),
            },
            "stale_event_count": int(heartbeat.get("stale_event_count") or 0),
        },
        "final_state": {
            "status": final_state.get("status"),
            "current_step": final_state.get("current_step"),
        },
        "event_count": int(payload.get("event_count") or 0),
        "replay_count": int(payload.get("replay_count") or 0),
    }


def _contract_text_input_minimal_flow(payload: Mapping[str, Any]) -> dict[str, Any]:
    planner = payload.get("planner") if isinstance(payload.get("planner"), Mapping) else {}
    dispatch = payload.get("dispatch") if isinstance(payload.get("dispatch"), Mapping) else {}
    acceptance = payload.get("acceptance") if isinstance(payload.get("acceptance"), Mapping) else {}
    acceptance_checks = acceptance.get("checks") if isinstance(acceptance.get("checks"), Mapping) else {}
    process_path = acceptance.get("process_path") if isinstance(acceptance.get("process_path"), Mapping) else {}
    artifact_structure = (
        acceptance.get("artifact_structure")
        if isinstance(acceptance.get("artifact_structure"), Mapping)
        else {}
    )
    release_anchor = acceptance.get("release_anchor") if isinstance(acceptance.get("release_anchor"), Mapping) else {}

    final_state = payload.get("final_state") if isinstance(payload.get("final_state"), Mapping) else {}

    return {
        "planner": {
            "step_count": int(planner.get("step_count") or 0),
            "step_ids": list(planner.get("step_ids") or []),
        },
        "dispatch": {
            "call_count": int(dispatch.get("call_count") or 0),
            "llm_invoked": bool(dispatch.get("llm_invoked")),
            "execution_mode": dispatch.get("execution_mode"),
        },
        "acceptance": {
            "checks": {key: bool(acceptance_checks.get(key)) for key in sorted(acceptance_checks)},
            "process_path_signature": process_path.get("signature"),
            "artifact_structure_signature": artifact_structure.get("signature"),
            "release_anchor_compatible": bool(release_anchor.get("compatible")),
        },
        "final_state": {
            "status": final_state.get("status"),
            "current_step": final_state.get("current_step"),
        },
    }


def _contract_checkpoint_recovery(payload: Mapping[str, Any]) -> dict[str, Any]:
    recovered = payload.get("recovered_state") if isinstance(payload.get("recovered_state"), Mapping) else {}
    final_state = payload.get("final_state") if isinstance(payload.get("final_state"), Mapping) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), Mapping) else {}
    return {
        "recovered_status": recovered.get("status"),
        "recovered_step": recovered.get("current_step"),
        "checkpoint_resume_status": recovered.get("checkpoint_resume_status"),
        "checkpoint_resume_diagnostics_present": bool(recovered.get("checkpoint_resume_diagnostics_present")),
        "final_status": final_state.get("status"),
        "checks": {key: bool(checks.get(key)) for key in sorted(checks)},
    }


ContractBuilder = Callable[[Mapping[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    contract_builder: ContractBuilder


SCENARIO_DEFINITIONS: dict[str, ScenarioDefinition] = {
    "integrated_reliability": ScenarioDefinition(
        scenario_id="integrated_reliability",
        contract_builder=_contract_integrated_reliability,
    ),
    "text_input_minimal_flow": ScenarioDefinition(
        scenario_id="text_input_minimal_flow",
        contract_builder=_contract_text_input_minimal_flow,
    ),
    "checkpoint_recovery": ScenarioDefinition(
        scenario_id="checkpoint_recovery",
        contract_builder=_contract_checkpoint_recovery,
    ),
}


def _run_checkpoint_recovery(
    *,
    scenario_root: Path,
    task_id: str,
    run_id: str,
    step_id: str,
    state_backend: str,
) -> dict[str, Any]:
    scenario_root.mkdir(parents=True, exist_ok=True)
    initialize_repository(scenario_root)

    runtime_settings = {"runtime": {"mode": "integrated", "state_backend": state_backend}}
    settings_path = scenario_root / "state" / "runtime_settings.json"
    settings_path.write_text(json.dumps(runtime_settings, indent=2) + "\n", encoding="utf-8")

    state_store = create_state_backend(
        scenario_root / "state",
        explicit_backend=state_backend,
        env={},
        config=runtime_settings,
    )
    runtime = create_runtime(
        task_id=task_id,
        run_id=run_id,
        goal="Validate checkpoint recovery resumes from latest valid checkpoint",
        step_id=step_id,
        state_store=state_store,
        config=runtime_settings,
        env={},
    )
    runtime.extract()
    runtime.plan()

    corruption_notes: list[str] = []
    if state_backend == "sqlite" and hasattr(state_store, "db_path"):
        db_path = Path(getattr(state_store, "db_path"))
        conn = sqlite3.connect(db_path.as_posix())
        try:
            with conn:
                conn.execute(
                    "INSERT INTO checkpoints(schema_version,kind,checkpoint_id,timestamp,node,from_status,to_status,state_json,state_hash) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        "1.0.0",
                        "checkpoint",
                        "ckpt_invalid_latest",
                        _utc_now(),
                        None,
                        None,
                        None,
                        "{not-json}",
                        "deadbeef",
                    ),
                )
            corruption_notes.append("sqlite checkpoint table appended invalid latest row")
        finally:
            conn.close()
    else:
        checkpoints_path = Path(getattr(state_store, "checkpoints_path"))
        with checkpoints_path.open("a", encoding="utf-8") as handle:
            handle.write("{not-valid-json}\n")
        corruption_notes.append("filesystem checkpoint log appended invalid json")

    restarted_store = create_state_backend(
        scenario_root / "state",
        explicit_backend=state_backend,
        env={},
        config=runtime_settings,
    )
    resumed_runtime = create_runtime(
        task_id=task_id,
        run_id=run_id,
        goal="Resume after invalid checkpoint entry",
        step_id=step_id,
        state_store=restarted_store,
        config=runtime_settings,
        env={},
    )
    recovered_state = resumed_runtime.recover_state()
    lifecycle = recovered_state.get("role_lifecycle") if isinstance(recovered_state.get("role_lifecycle"), Mapping) else {}

    final_state = resumed_runtime.run()

    recovered_summary = {
        "status": recovered_state.get("status"),
        "current_step": recovered_state.get("current_step"),
        "checkpoint_resume_status": lifecycle.get("checkpoint_resume_status"),
        "checkpoint_resume_diagnostics_present": bool(lifecycle.get("checkpoint_resume_diagnostics")),
        "checkpoint_resume_diagnostics_count": lifecycle.get("checkpoint_resume_diagnostics_count"),
    }

    checks = {
        "recovered_status_is_freeze": recovered_summary.get("status") == "FREEZE",
        "recovered_step_is_s1": recovered_summary.get("current_step") == step_id,
        "checkpoint_resume_warns": recovered_summary.get("checkpoint_resume_status")
        == "recovered_with_warnings",
        "final_status_done": final_state.get("status") == "DONE",
    }

    return {
        "task_id": task_id,
        "run_id": run_id,
        "step_id": step_id,
        "scenario_id": "checkpoint_recovery",
        "state_backend": state_backend,
        "generated_at": _utc_now(),
        "scenario_root": str(scenario_root),
        "runtime_settings_path": str(settings_path),
        "corruption_notes": corruption_notes,
        "recovered_state": recovered_summary,
        "final_state": {
            "status": final_state.get("status"),
            "current_step": final_state.get("current_step"),
        },
        "checks": checks,
    }


def _run_scenario(
    *,
    scenario_id: str,
    repo_root: Path,
    scenario_root: Path,
    state_backend: str,
    task_id: str,
    run_id: str,
    step_id: str,
) -> dict[str, Any]:
    if scenario_id == "integrated_reliability":
        return run_integrated_reliability_scenario(
            repo_root=repo_root,
            scenario_root=scenario_root,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            state_backend=state_backend,
        )
    if scenario_id == "text_input_minimal_flow":
        return run_text_input_minimal_flow(
            repo_root=repo_root,
            scenario_root=scenario_root,
            task_input="Validate cross-backend consistency for minimal text-input flow",
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            env_overrides={"DAOKIT_CODEX_BIN": str(scenario_root / "missing-codex-binary")},
            state_backend=state_backend,
        )
    if scenario_id == "checkpoint_recovery":
        return _run_checkpoint_recovery(
            scenario_root=scenario_root,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            state_backend=state_backend,
        )

    raise ValueError(f"unsupported scenario id: {scenario_id}")


def _render_markdown_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Cross-Backend Consistency Report",
        "",
        f"- Task ID: `{payload.get('task_id')}`",
        f"- Run ID: `{payload.get('run_id')}`",
        f"- Generated At: `{payload.get('generated_at')}`",
        "",
        "## Summary",
        "",
        f"- Backends: `{', '.join(payload.get('backends') or [])}`",
        f"- Scenarios: `{', '.join(payload.get('scenario_ids') or [])}`",
        f"- Overall: `{payload.get('status')}`",
        "",
        "## Tolerance",
        "",
        f"- Notes: {VOLATILE_FIELD_TOLERANCE['notes']}",
        "- Ignored volatile fields:",
    ]
    for field in VOLATILE_FIELD_TOLERANCE["ignored_fields"]:
        lines.append(f"  - `{field}`")

    lines.extend(["", "## Scenario Results", ""])
    for scenario in payload.get("scenarios", []):
        if not isinstance(scenario, Mapping):
            continue
        scenario_id = scenario.get("id")
        comparison = scenario.get("comparison") if isinstance(scenario.get("comparison"), Mapping) else {}
        equivalent = bool(comparison.get("equivalent"))
        lines.append(f"### {scenario_id}")
        lines.append("")
        lines.append(f"- Equivalent: {'PASS' if equivalent else 'FAIL'}")
        if not equivalent:
            diffs = comparison.get("differences")
            if isinstance(diffs, list) and diffs:
                lines.append("- Differences:")
                for item in diffs[:10]:
                    lines.append(f"  - `{item}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def run_cross_backend_consistency_suite(
    *,
    repo_root: Path,
    output_root: Path,
    task_id: str,
    run_id: str,
    step_id: str = "S1",
    backends: Sequence[str] = DEFAULT_BACKENDS,
    scenarios: Sequence[str] = DEFAULT_SCENARIOS,
    report_json: Path | None = None,
    report_markdown: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()

    normalized_backends = [backend.strip().lower() for backend in backends if backend.strip()]
    if normalized_backends != list(DEFAULT_BACKENDS):
        # Keep report stable: only two supported backends for this contract.
        raise ValueError(f"unsupported backend selection: {normalized_backends}")

    selected_scenarios = [scenario.strip() for scenario in scenarios if scenario.strip()]
    if not selected_scenarios:
        raise ValueError("at least one scenario must be selected")
    for scenario_id in selected_scenarios:
        if scenario_id not in SCENARIO_DEFINITIONS:
            raise ValueError(f"unsupported scenario id: {scenario_id}")

    output_root.mkdir(parents=True, exist_ok=True)
    generated_at = _utc_now()

    scenario_reports: list[dict[str, Any]] = []
    all_equivalent = True

    for scenario_id in selected_scenarios:
        definition = SCENARIO_DEFINITIONS[scenario_id]
        backend_outputs: dict[str, dict[str, Any]] = {}

        for backend in normalized_backends:
            backend_root = output_root / scenario_id / backend
            scenario_root = backend_root / "scenario"
            _reset_scenario_root(scenario_root)
            raw_payload = _run_scenario(
                scenario_id=scenario_id,
                repo_root=repo_root,
                scenario_root=scenario_root,
                state_backend=backend,
                task_id=task_id,
                run_id=run_id,
                step_id=step_id,
            )
            contract_snapshot = definition.contract_builder(raw_payload)
            contract_hash = _canonical_hash(contract_snapshot)

            raw_path = backend_root / "raw-summary.json"
            contract_path = backend_root / "contract.json"
            _safe_write_json(raw_path, raw_payload)
            _safe_write_json(contract_path, contract_snapshot)

            backend_outputs[backend] = {
                "backend": backend,
                "scenario_root": str(scenario_root),
                "raw_summary_path": str(raw_path),
                "contract_path": str(contract_path),
                "contract_hash": contract_hash,
                "contract_snapshot": contract_snapshot,
            }

        fs_hash = backend_outputs["filesystem"]["contract_hash"]
        sqlite_hash = backend_outputs["sqlite"]["contract_hash"]
        equivalent = fs_hash == sqlite_hash and backend_outputs["filesystem"]["contract_snapshot"] == backend_outputs["sqlite"]["contract_snapshot"]
        differences: list[str] = []
        if not equivalent:
            all_equivalent = False
            differences.append("contract snapshot mismatch")

        scenario_reports.append(
            {
                "id": scenario_id,
                "contract_hashes": {
                    "filesystem": fs_hash,
                    "sqlite": sqlite_hash,
                },
                "comparison": {
                    "equivalent": equivalent,
                    "differences": differences,
                },
                "outputs": backend_outputs,
            }
        )

    report_payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "workflow": "cross-backend-consistency",
        "task_id": task_id,
        "run_id": run_id,
        "step_id": step_id,
        "generated_at": generated_at,
        "backends": list(normalized_backends),
        "scenario_ids": list(selected_scenarios),
        "tolerance": dict(VOLATILE_FIELD_TOLERANCE),
        "scenarios": scenario_reports,
        "status": "PASS" if all_equivalent else "FAIL",
        "passed": all_equivalent,
        "output_root": str(output_root),
    }

    if report_json is not None:
        _safe_write_json(Path(report_json), report_payload)
    if report_markdown is not None:
        Path(report_markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(report_markdown).write_text(_render_markdown_report(report_payload), encoding="utf-8")

    return report_payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cross-backend-consistency",
        description="Run recovery-path scenarios against filesystem and sqlite backends and compare contract outputs.",
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--task-id", default="DKT-070")
    parser.add_argument("--run-id", default="RUN-CROSS-BACKEND")
    parser.add_argument("--step-id", default="S1")
    parser.add_argument("--report-json", default=None)
    parser.add_argument("--report-markdown", default=None)
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        default=None,
        help=f"Scenario id (default: {', '.join(DEFAULT_SCENARIOS)})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    scenarios = tuple(args.scenarios) if args.scenarios else DEFAULT_SCENARIOS
    payload = run_cross_backend_consistency_suite(
        repo_root=Path(args.repo_root),
        output_root=Path(args.output_root),
        task_id=str(args.task_id),
        run_id=str(args.run_id),
        step_id=str(args.step_id),
        scenarios=scenarios,
        report_json=Path(args.report_json).resolve() if args.report_json else None,
        report_markdown=Path(args.report_markdown).resolve() if args.report_markdown else None,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True))
    return 0 if payload.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
