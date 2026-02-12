# DKT-036 S1 Report: Integrated-mode long-running reliability validation

## Step Identification
- Task ID: `DKT-036`
- Step ID: `S1`
- Run ID: `DKT-036_20260212T093654Z_a62b87a`
- Title: Validate long-running reliability in integrated mode

## Summary of Work
1. Added an integrated reliability scenario runner in allowed scope (`src/reliability/scenarios/integrated_reliability.py`) with deterministic stale forcing, takeover, handoff apply, and replay/status consistency checks.
2. Added e2e coverage (`tests/e2e/test_integrated_reliability.py`) that runs the scenario and asserts all recovery-consistency checks.
3. Added reproducible CLI wrapper (`examples/cli/integrated_reliability_recovery_chain.sh`) for operators.
4. Produced evidence artifacts and markerized command logs for scenario, tests, and baseline verification.

## Acceptance Criteria Results
- Integrated mode recovers from forced stale condition without manual state repair: **PASS** (`checks.recovered_without_manual_state_repair=true`).
- Recovery evidence artifacts are complete and linked under docs/reports: **PASS** (files listed in Artifacts section).
- Replay and status outputs remain consistent after recovery and are test-covered: **PASS** (`checks.status_replay_consistent_after_recovery=true`, e2e tests pass).
- Baseline `make lint && make test` passes with required command markers: **PASS** (COMMAND ENTRY 5 in `verification.log`).

## Key Runtime Evidence
- `runtime_mode`: `integrated`
- `resolved_runtime_engine`: `langgraph`
- `runtime_class`: `LangGraphOrchestratorRuntime`
- `graph_backend`: `fallback`
- `active_status_before_recovery`: `EXECUTE`
- `takeover.takeover_at`: `2026-02-12T09:46:59.687543+00:00`
- `takeover.adopted_step_ids`: `['S1']`
- `takeover.handoff_applied`: `True`
- `event_count`: `10`
- `replay_count`: `10`
- `final_state.status`: `DONE`

## Files Changed
- `src/reliability/scenarios/__init__.py`
- `src/reliability/scenarios/integrated_reliability.py`
- `tests/e2e/test_integrated_reliability.py`
- `examples/cli/integrated_reliability_recovery_chain.sh`

## Artifacts
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/integrated-reliability-summary.json`
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/integrated-reliability-summary-from-script.json`
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/verification.log`
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/audit-summary.md`

