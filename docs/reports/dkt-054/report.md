# DKT-054 Reliability Gate Integration

## Scope

Integrate reliability diagnostics and continuity validation into the release-gate flow under `v1.2` reliability objectives.

## What Was Added

1. Added deterministic `make gate-reliability-readiness` command to `Makefile`.
2. Added reliability gate runner `src/verification/reliability_gate.py` with markerized command evidence output and JSON summary output.
3. Expanded release criteria with `RC-REL-001` and `RC-REL-002` in `src/verification/criteria_registry.py`.
4. Updated `.github/workflows/v11-hardening-gate.yml` to run reliability readiness gate in order between `gate-release-check` and `gate-criteria-linkage`.
5. Updated evidence runbook and orchestration contract docs for sequence/evidence mappings.
6. Tightened CI contract tests for gate target discovery and evidence-path wiring.
7. Restored compatibility path in `src/reliability/diagnostics.py` so `operator_recovery` and integrated reliability flows can emit diagnostics from state-store data.

## Verification Mapping

- Command evidence: `docs/reports/dkt-054/verification.log`
- Gate evidence: `.artifacts/reliability-gate/verification.log`, `.artifacts/reliability-gate/summary.json`
- Release-check evidence summary: `docs/reports/dkt-054/release-check-summary.json`

## Files Changed

- `Makefile`
- `.github/workflows/v11-hardening-gate.yml`
- `src/verification/criteria_registry.py`
- `src/verification/reliability_gate.py`
- `src/reliability/diagnostics.py`
- `tests/ci/test_v11_hardening_gate_contract.py`
- `tests/verification/test_criteria_registry.py`
- `docs/workflows/release-check-evidence-troubleshooting.en.md`
- `docs/workflows/codex-integration-runbook.en.md`
- `docs/workflows/codex-integration-runbook.zh-CN.md`
- `docs/reports/dkt-054/verification.log`
- `docs/reports/dkt-054/release-check-summary.json`
- `docs/reports/dkt-054/audit-summary.md`

## Status

DKT-054 has been integrated with deterministic command evidence and is ready for wave merge.
