# DKT-051 Core-Rotation Chaos Matrix Expansion

## Scope

Expanded the core-rotation chaos scenario matrix in allowed scope:

- `src/reliability/scenarios/`
- `tests/reliability/`
- `tests/e2e/`
- `docs/workflows/`
- `docs/reports/`

## What Was Added

1. A dedicated matrix/fixture definition module for DKT-051 with high-risk path coverage tags.
2. Deterministic execution constraints metadata for repeatable scenario execution.
3. Scenario-level continuity assertion tags and result mapping for DKT-052 reuse.
4. Matrix execution output with coverage checks, assertion mapping checks, and reproducibility metadata checks.
5. Workflow documentation for matrix fixtures, constraints, and evidence output points.

## Evidence Pointers

- Matrix/fixture source: `src/reliability/scenarios/core_rotation_chaos_matrix.py`
- Scenario runner + matrix executor: `src/reliability/scenarios/integrated_reliability.py`
- Coverage and metadata tests:
  - `tests/reliability/test_core_rotation_chaos_matrix.py`
  - `tests/e2e/test_integrated_reliability.py`
- Workflow doc: `docs/workflows/core-rotation-chaos-matrix.en.md`
- Verification log: `docs/reports/dkt-051-core-rotation-chaos-matrix/verification.log`
