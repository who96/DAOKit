# DKT-052 Continuity Assertions and Long-Run Soak Harness

## Scope

Implemented DKT-052 strictly inside the allowed paths:

- `src/reliability/`
- `tests/reliability/`
- `tests/e2e/`
- `docs/reports/`

## What Was Added

1. Expanded continuity assertion coverage for takeover/handoff/replay consistency (`CONT-009`..`CONT-011`) and wired signal evaluation into the integrated reliability scenario runner.
2. Added a deterministic long-run soak harness (`run_long_run_soak_harness`) with checkpoint hashing, variance checks, and multi-iteration scenario execution.
3. Added persistent assertion outputs for audit/release gating:
   - machine-readable continuity assertion payload
   - deterministic checkpoint manifest
   - release gate summary
   - human-readable assertion report
4. Extended CLI workflow support with non-breaking additive flags:
   - `--soak`
   - `--soak-root`
   - `--soak-iterations`
5. Added reliability/e2e coverage for the soak harness API and CLI paths.

## Evidence Pointers

- Continuity assertion catalog + fixture mapping:
  - `src/reliability/scenarios/core_rotation_chaos_matrix.py`
- Scenario + matrix + soak runners:
  - `src/reliability/scenarios/integrated_reliability.py`
  - `src/reliability/scenarios/__init__.py`
- New tests:
  - `tests/reliability/test_continuity_soak_harness.py`
  - `tests/e2e/test_integrated_reliability.py`
- Soak evidence outputs:
  - `docs/reports/dkt-052/soak-summary.json`
  - `docs/reports/dkt-052/soak/assertions/continuity-assertions.json`
  - `docs/reports/dkt-052/soak/assertions/deterministic-checkpoints.json`
  - `docs/reports/dkt-052/soak/assertions/continuity-release-gate.json`
  - `docs/reports/dkt-052/soak/assertions/continuity-assertions.md`
- Verification log:
  - `docs/reports/dkt-052/verification.log`
