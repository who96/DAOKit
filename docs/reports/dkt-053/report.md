# DKT-053 Operator Recovery Runbook and Drill Templates

## Scope

Deliver Day-2 operator readiness documentation for stale heartbeat and lease takeover incidents.

- Runbook: `docs/workflows/operator-recovery-runbook.en.md`
- Drill templates: `docs/workflows/operator-recovery-drill-templates.en.md`

This task depends on DKT-050 and DKT-052 and is aligned to the same dashboard and continuity outputs.

## What Was Added

1. Refined actionable operator recovery runbook with explicit evidence checkpoints.
2. Added three drill templates:
   - `T-053-DRILL-01` stale heartbeat drill
   - `T-053-DRILL-02` takeover escalation drill
   - `T-053-DRILL-03` readiness evidence checklist
3. Linked runbook and drill outputs to DKT-050 operator reports and DKT-052 continuity checks.

## Acceptance Mapping

- Actionable recovery guidance: Runbook covers stale heartbeat triage and takeover branches.
- Reproducible drills: Templates include concrete command sequences and deterministic artifact names.
- Evidence alignment: Evidence checklists are required to reference operator report outputs and state/event files.

## Evidence Pointers

- `docs/workflows/operator-recovery-runbook.en.md`
- `docs/workflows/operator-recovery-drill-templates.en.md`
- `docs/reports/dkt-053/verification.log`
- `docs/reports/dkt-053/release-check-summary.json`
- `src/reports/operator_recovery.py` (source dependency, unchanged in this task)
- `docs/workflows/codex-integration-runbook.en.md` (existing cross-link context)
