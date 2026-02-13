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

## v1.3 (Real Workload Proof)

Target themes:

- Freeze scope to P0 + P1 only via DKT-056 guardrail charter and acceptance matrix.
- Prove one minimal real workload lane (`extract -> plan -> dispatch -> acceptance`) with auditable evidence.
- Define reproducibility semantics as process/path consistency + artifact-structure consistency (LLM text variance allowed).
- Upgrade retrieval to provider-based real embeddings with benchmark-backed default-model decision.
- Preserve non-breaking constraints for CLI parameters, `schema_version=1.0.0`, `v1.0.0-rc1`, and `docs/reports/final-run/` evidence topology.
- Keep runtime policy as LangGraph default with legacy runtime maintenance-only.

Expected deliverables:

- Published v1.3 scope freeze artifact: `specs/006-v1-3-real-workload-proof/guardrail-charter-acceptance-matrix.md`.
- v1.3 requirements/design/tasks package under `specs/006-v1-3-real-workload-proof/`.
- Real workload evidence packet and retrieval benchmark evidence in release readiness outputs.

## v1.4 (Deep Integration)

Target themes:

- Freeze v1.4 Wave 0 scope with DKT-064 guardrail charter and acceptance matrix.
- Execute architecture-deepening work deferred from v1.3: P2 (LangGraph conditional routing + checkpoint/resume) and P3 (`StateBackend` + SQLite backend).
- Limit v1.4 scope to P2/P3 only; no P2/P3-adjacent feature expansion in this release line.
- Explicitly exclude parallel branches and human-in-the-loop from v1.4 scope.
- Maintain v1.3 guardrails as compatibility baseline while extending runtime/state capabilities.
- Preserve non-breaking constraints for CLI parameters, `schema_version=1.0.0`, `v1.0.0-rc1`, and `docs/reports/final-run/` evidence topology.
- Keep runtime policy as LangGraph default with legacy runtime maintenance-only.
- Keep v1.4 implementation out of v1.3 waves until v1.3 acceptance is complete.

Expected deliverables:

- Published v1.4 scope freeze artifact: `specs/007-v1-4-deep-integration/guardrail-charter-acceptance-matrix.md`.
- v1.4 requirements/design/tasks package under `specs/007-v1-4-deep-integration/`.
- LangGraph deep integration evidence and backend consistency report.
- Release readiness report for `v1.4.0`.

## Release Notes Discipline

Every roadmap item that ships must include:

1. Changelog entry (`CHANGELOG.md`).
2. Verification evidence (`report.md`, `verification.log`, `audit-summary.md`).
3. Updated operator/contributor docs when behavior changes.
