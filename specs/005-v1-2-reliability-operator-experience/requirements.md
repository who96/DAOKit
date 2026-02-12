# v1.2 Reliability and Operator Experience Requirements

## 1. Objective
Raise DAOKit day-2 reliability and operator usability by hardening heartbeat/lease/takeover observability, producing actionable recovery reports, and expanding continuity stress validation under LangGraph-only orchestration policy.

## 2. Problem Statement
Post-v1.1 tooling improvements still leave operations gaps:
1. Heartbeat and lease takeover states are not observable enough for fast diagnosis.
2. Operators need stronger recovery dashboards/reports from ledger data.
3. Core-rotation chaos coverage and continuity assertions are not broad enough.
4. Rollout assets must explicitly prohibit legacy orchestration fallback.

## 3. Product Principles
1. Operational truth from ledger/contracts, not ad-hoc console interpretation.
2. Recovery-first ergonomics: operators should identify and act on failure states quickly.
3. LangGraph-only orchestration in rollout and reliability validation assets.
4. Compatibility preservation for CLI contracts, schema semantics, and release evidence anchors.
5. Evidence-backed reliability claims under repeatable scenarios.

## 4. In Scope
- Heartbeat/lease/takeover observability hardening.
- Ledger-derived recovery reports/dashboards for operators.
- Expanded core-rotation chaos scenarios and continuity assertions.
- Reliability gate integration with release verification flow.
- LangGraph-only orchestration wording across v1.2 assets.

## 5. Out of Scope
- Breaking CLI contract changes.
- Breaking schema changes from `1.0.0` semantics.
- Runtime redesign outside reliability/operations hardening scope.
- Evidence directory restructuring under `docs/reports/final-run/`.

## 6. Functional Requirements

### A. Heartbeat/Lease/Takeover Observability
- FR-OBS-001: System must emit explicit heartbeat freshness and lease state diagnostics.
- FR-OBS-002: Takeover events must include reason codes, timing, and correlation IDs.
- FR-OBS-003: Observability outputs must support operator filtering by task/run/step identifiers.

### B. Operator Recovery Reporting
- FR-OPS-001: System must produce recovery reports derived from ledger/events data.
- FR-OPS-002: Recovery report must summarize stale detection, takeover latency, and final continuity status.
- FR-OPS-003: Reports must be available in human-readable and machine-readable forms.

### C. Chaos and Continuity Expansion
- FR-CHAOS-001: System must include expanded core-rotation chaos scenarios.
- FR-CHAOS-002: Continuity assertions must verify no state corruption across takeover/handoff paths.
- FR-CHAOS-003: Reliability scenarios must include repeatable long-run stress execution.

### D. LangGraph-only Orchestration Policy
- FR-LGO-001: v1.2 runtime orchestration and validation workflows must be LangGraph-only.
- FR-LGO-002: Legacy runtime path must be removed from v1.2 rollout plan and acceptance matrix.
- FR-LGO-003: Parameter-based orchestration switching is disallowed in v1.2 rollout assets.

### E. Compatibility Guardrails
- FR-COMP-001: Existing CLI command and argument names must remain intact.
- FR-COMP-002: Contract semantics must remain compatible with `schema_version=1.0.0`.
- FR-COMP-003: `v1.0.0-rc1` anchor semantics and `docs/reports/final-run/` evidence structure must remain unchanged.

## 7. Non-Functional Requirements
- NFR-001 Reliability: stale/takeover diagnosis must be deterministic and reproducible.
- NFR-002 Observability: operators can trace incident timelines without manual data stitching.
- NFR-003 Operability: recovery reports reduce time-to-understand and time-to-action.
- NFR-004 Maintainability: chaos suite and continuity assertions remain extensible.

## 8. Acceptance Gate
1. Heartbeat/lease/takeover observability provides explicit, correlated diagnostics.
2. Operator recovery dashboards/reports are generated from ledger data and actionable.
3. Core-rotation chaos coverage and continuity assertions are expanded and repeatable.
4. v1.2 assets explicitly enforce LangGraph-only orchestration and remove legacy path from rollout plan.
5. Compatibility constraints remain non-breaking.

## 9. Hard Constraints
1. No public CLI argument rename/removal unless approved migration plan exists.
2. No semantic break to `schema_version=1.0.0` contracts.
3. No break to `v1.0.0-rc1` anchor semantics and `docs/reports/final-run/` evidence layout.
4. This iteration outputs research/design/task assets only, not large runtime refactoring.
