# DKT-050 Recovery Report and Dashboard Outputs

## Scope

Implemented operator recovery reporting in `src/reports/operator_recovery.py` and wired it into the integrated reliability runner in `src/reliability/scenarios/integrated_reliability.py`.

## What Was Added

1. Added deterministic operator recovery payload generation from authoritative state store data via `build_operator_recovery_payload`.
2. Added dual-format persistence (`JSON` + `Markdown`) for operator dashboards.
3. Emitted report pointers in integrated scenario output for `operator_recovery_outputs`.
4. Added continuity-derived sections for stale detection and takeover latency in report content.
5. Added report-level tests for payload schema, evidence persistence, and pointer mapping (`tests/reports/test_operator_recovery_report.py`).

## Evidence Pointers

- Recovery report generator:
  - `src/reports/__init__.py`
  - `src/reports/operator_recovery.py`
- Scenario wiring:
  - `src/reliability/scenarios/integrated_reliability.py`
- Unit coverage:
  - `tests/reports/test_operator_recovery_report.py`
- Command evidence:
  - `docs/reports/dkt-050/verification.log`
  - `docs/reports/dkt-050/release-check-summary.json`
