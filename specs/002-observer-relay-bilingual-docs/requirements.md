# Observer Relay and Bilingual Experience Requirements

## 1. Objective
Implement an observer-relay operating model for the external main window while preserving DAOKit public compatibility, and add bilingual documentation assets for English and Chinese users.

## 2. Problem Statement
Current DAOKit execution and docs have three gaps for the next iteration:
1. The external main window is not explicitly constrained as relay-only in implementation-level behavior.
2. The controller-as-subagent and self-healing closed loop need production-ready execution tasks.
3. Repository-facing docs are not language-separated (pure English + pure Chinese), and there is no bilingual multi-agent collaboration workflow example covering end-of-turn health checks and handoff recovery.

## 3. Product Principles for This Iteration
1. Observer purity: external window forwards and visualizes only; it does not execute worker actions.
2. Controller ownership: task routing and data destination decisions are made by controller agent in subagent chain.
3. Self-healing first: detect, decide, takeover, recover must be explicit and auditable.
4. Backward-safe delivery: no breaking changes to CLI argument names, schema version semantics, or release evidence layout.
5. Bilingual usability: English and Chinese users must have first-class, cross-linked entry docs.

## 4. In Scope
- Observer-relay role boundary implementation and tests.
- Controller-in-subagent routing integration and ownership persistence.
- Self-healing loop based on heartbeat + lease + takeover + handoff.
- Relay context compaction policy (keep/drop strategy) with stale-noise pruning.
- Compatibility guardrails and rollback runbook for non-breaking migration.
- Pure English README and pure Chinese README with two-way language links.
- Bilingual multi-agent collaboration workflow example (including health-check -> handoff -> clear -> restore flow).

## 5. Out of Scope
- CLI surface redesign or command rename.
- Contract schema version upgrade beyond `1.0.0`.
- Re-layout of `docs/reports/final-run/` evidence structure.
- New SaaS/dashboard products.

## 6. Functional Requirements

### A. Observer Relay Runtime
- FR-OR-001: External main window must support relay-only behavior (forward + observe + visualize).
- FR-OR-002: External main window must reject direct execution-role actions in relay mode.
- FR-OR-003: Relay context must preserve: user goal, constraints, latest instruction, current blockers, controller route summary.

### B. Controller-in-Subagent Chain
- FR-OR-004: Controller agent must be represented as a subagent execution lane.
- FR-OR-005: Controller routing ownership must be reflected in lease and lifecycle records without changing existing schema semantics.
- FR-OR-006: External relay may present state summaries but cannot become execution authority.

### C. Self-Healing Closed Loop
- FR-OR-007: System must support deterministic detect/decide/takeover/recover cycle.
- FR-OR-008: Detection must use heartbeat status + lease validity signals.
- FR-OR-009: Recovery must reuse existing `takeover` and `handoff` paths.
- FR-OR-010: Event emission must stay within current `events` schema enum constraints.

### D. Compaction and Context Hygiene
- FR-OR-011: Compaction must remove stale execution logs, duplicate status reports, historical failure noise, and irrelevant API error dumps.
- FR-OR-012: Compaction must be idempotent and keep required relay context fields intact.

### E. Compatibility and Safety
- FR-OR-013: CLI command names and argument names must remain unchanged.
- FR-OR-014: `schema_version=1.0.0` contract semantics must remain backward-compatible.
- FR-OR-015: `v1.0.0-rc1` anchor meaning and `docs/reports/final-run/` evidence structure must remain intact.
- FR-OR-016: A rollback runbook must define how to revert observer-relay changes without data loss.

### F. Bilingual Documentation
- FR-OR-017: `README.md` must be pure English narrative.
- FR-OR-018: A Chinese counterpart readme (for example `README.zh-CN.md`) must be pure Chinese narrative.
- FR-OR-019: English and Chinese readmes must include explicit two-way language navigation links.
- FR-OR-020: Repository must include bilingual multi-agent collaboration workflow examples with aligned structure and content parity.

## 7. Non-Functional Requirements
- NFR-OR-001 Reliability: self-healing logic must avoid false-positive takeover storms.
- NFR-OR-002 Determinism: same state + same signals produce same recovery decision.
- NFR-OR-003 Observability: each key recovery decision must be traceable through events and status outputs.
- NFR-OR-004 Performance: relay compaction should reduce context noise without introducing significant latency.
- NFR-OR-005 Maintainability: role boundaries and compaction policy must be testable with unit or CLI-level tests.

## 8. Acceptance Gate for This Iteration
1. Observer relay role boundary is enforced and tested.
2. Controller subagent routing + self-healing loop is runnable and auditable.
3. CLI/schema/release-evidence compatibility constraints are verified non-breaking.
4. Bilingual readmes and bilingual collaboration workflow docs are complete, cross-linked, and navigation-ready.

## 9. Constraints to Reconfirm During Execution
1. Do not rename CLI args.
2. Do not break `schema_version=1.0.0` parsing expectations.
3. Do not restructure `docs/reports/final-run/`.
4. Keep evidence and verification log discipline for each implementation task.
