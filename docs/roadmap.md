# DAOKit Roadmap

This roadmap captures post-`v1.0.0` release direction.

## v1.1 (Tooling and Verification Hardening)

Target themes:

- Add a first-class `make release-check` target.
- Expand acceptance gate diagnostics with explicit criterion mapping output.
- Improve CLI ergonomics for reproducible release verification bundles.
- Add contributor templates for new tool adapters and skill manifests.
- Freeze v1.1 guardrail charter and acceptance matrix as rollout baseline.
- Keep v1.1 rollout assets LangGraph-only (no orchestration-engine switching surface).

Expected deliverables:

- Release verification command surface standardized.
- Stronger docs/test coupling for extension contributions.
- Published guardrail charter and acceptance matrix for v1.1 waves.

## v1.2 (Reliability and Operator Experience)

Target themes:

- Strengthen stale heartbeat and lease takeover observability.
- Add clearer operator recovery dashboards/reports from ledger data.
- Expand core-rotation stress scenarios and continuity assertions.
- Freeze a v1.2 reliability guardrail charter and acceptance matrix.
- Keep v1.2 rollout and recovery assets LangGraph-only (no orchestration-engine switching surface).
- Preserve non-breaking constraints for CLI parameters, `schema_version=1.0.0`, `v1.0.0-rc1`, and `docs/reports/final-run/` evidence topology.

Expected deliverables:

- More robust succession recovery under chaos scenarios.
- Better day-2 operations for long-running agent workflows.
- Published `specs/005-v1-2-reliability-operator-experience/guardrail-charter-acceptance-matrix.md`.

## Release Notes Discipline

Every roadmap item that ships must include:

1. Changelog entry (`CHANGELOG.md`).
2. Verification evidence (`report.md`, `verification.log`, `audit-summary.md`).
3. Updated operator/contributor docs when behavior changes.
