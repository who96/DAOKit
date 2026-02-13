# DKT-070 Cross-Backend Consistency and Recovery-Path Validation

## Scope

Implemented DKT-070 strictly inside the allowed paths:

- `src/reliability/`
- `tests/verification/`
- `docs/reports/`

No public CLI args/names were changed. `schema_version=1.0.0` semantics and the `v1.0.0-rc1` evidence anchors remain intact.

## What Was Added

1. A cross-backend consistency suite runner (`run_cross_backend_consistency_suite`) that executes the same recovery/takeover-relevant scenarios on both filesystem and sqlite StateBackends and compares canonical contract snapshots within a documented tolerance (volatile ids/timestamps/absolute paths are ignored by construction).
2. Backend selection support for reliability scenario runners while preserving default behavior (`state_backend: str = "filesystem"`).
3. Recovery/takeover parity coverage across three scenarios:
   - `integrated_reliability` (takeover + handoff + replay continuity assertions)
   - `text_input_minimal_flow` (minimal dispatch + evidence packet invariants)
   - `checkpoint_recovery` (inject invalid latest checkpoint entry and assert recovery falls back to the latest valid checkpoint on both backends)
4. Auditable evidence outputs:
   - Per-scenario/per-backend raw summaries and canonical contract snapshots under the agent run directory
   - Structured consistency report outputs (JSON + Markdown)
5. Unit test coverage that runs the suite and asserts equivalence across backends.

## Evidence Pointers

- Validator implementation:
  - `src/reliability/consistency/cross_backend.py`
- Scenario runners updated for backend selection:
  - `src/reliability/scenarios/integrated_reliability.py`
  - `src/reliability/scenarios/text_input_minimal_flow.py`
- Unit tests:
  - `tests/verification/test_cross_backend_consistency.py`
- Consistency report:
  - `docs/reports/dkt-070/consistency-report.json`
  - `docs/reports/dkt-070/consistency-report.md`
- Raw evidence artifacts (per scenario/backend, raw summary + canonical contracts):
  - `.artifacts/agent_runs/DKT-070_20260213T132036Z_7vugm3t/S1/cross-backend/`
- Verification log:
  - `docs/reports/dkt-070/verification.log`

