# v1.1 Tooling and Verification Hardening Requirements

## 1. Objective
Upgrade DAOKit from "integration works" to "release verification is repeatable, diagnosable, and contributor-friendly" while enforcing LangGraph-only runtime orchestration for rollout execution.

## 2. Problem Statement
Wave 6 proved integrated runtime viability, but release operations still have avoidable friction:
1. Release checks are not yet standardized behind one first-class entrypoint.
2. Acceptance diagnostics do not map criteria to evidence with enough precision.
3. CLI evidence bundle generation/re-verification ergonomics are still operator-heavy.
4. Extension contributors lack stable templates for tool adapters and skill manifests.
5. Rollout instructions still need explicit removal of legacy orchestration as an option.

## 3. Product Principles
1. Never break userspace: no public CLI argument rename/removal.
2. Contract continuity first: `schema_version=1.0.0` semantic compatibility is mandatory.
3. Evidence-first acceptance: every criterion must map to verifiable artifacts.
4. LangGraph-only rollout discipline: orchestration path is singular and explicit.
5. Additive hardening: improve tooling and docs without breaking existing release anchors.

## 4. In Scope
- Standardize `make release-check` as the release verification entrypoint.
- Add explicit criterion-to-diagnostic mapping outputs.
- Improve CLI ergonomics for evidence bundle generation and re-verification.
- Provide contributor templates for tool adapters and skill manifests.
- Update verification docs/runbooks for LangGraph-only orchestration.

## 5. Out of Scope
- Large runtime architecture rewrites.
- Breaking CLI argument changes.
- Schema forks or semantic contract changes beyond `1.0.0` compatibility.
- Evidence directory topology changes under `docs/reports/final-run/`.

## 6. Functional Requirements

### A. Release Check Surface
- FR-RC-001: System must provide a first-class `make release-check` target.
- FR-RC-002: `make release-check` must execute a deterministic verification sequence and emit command evidence.
- FR-RC-003: `make release-check` must produce machine-readable summary output for gating.

### B. Acceptance Diagnostics Mapping
- FR-DIAG-001: Each acceptance criterion must map to explicit diagnostic entries.
- FR-DIAG-002: Diagnostic output must include criterion ID, pass/fail status, evidence pointer, and remediation hint.
- FR-DIAG-003: Diagnostics must be available in human-readable and machine-readable forms.

### C. CLI Evidence Bundle Ergonomics
- FR-BUNDLE-001: CLI must support reproducible evidence bundle generation with additive, non-breaking command behavior.
- FR-BUNDLE-002: CLI must support re-verification against an existing evidence bundle.
- FR-BUNDLE-003: Bundle output must stay compatible with `docs/reports/final-run/` anchor structure.

### D. Contributor Templates
- FR-TPL-001: Project must include a tool adapter template with interface, tests, and docs checklist.
- FR-TPL-002: Project must include a skill manifest template with validation checklist.
- FR-TPL-003: Templates must include verification steps coupled to `make release-check`.

### E. LangGraph-only Orchestration Policy
- FR-LGO-001: Runtime orchestration in v1.1 verification workflows must be LangGraph-only.
- FR-LGO-002: Legacy runtime path must be removed from the v1.1 rollout plan and acceptance matrix.
- FR-LGO-003: Orchestration-engine switching via public runtime parameters is not allowed in v1.1/v1.2 rollout assets.

### F. Compatibility Guardrails
- FR-COMP-001: Existing CLI command and argument names must remain intact.
- FR-COMP-002: Contract semantics must remain compatible with `schema_version=1.0.0`.
- FR-COMP-003: `v1.0.0-rc1` release anchor semantics and `docs/reports/final-run/` evidence structure must remain intact.

## 7. Non-Functional Requirements
- NFR-001 Reliability: release checks are reproducible across repeated runs on same commit.
- NFR-002 Observability: failures are diagnosable at criterion level without manual log archaeology.
- NFR-003 Usability: operators can generate and re-verify bundles with minimal command ambiguity.
- NFR-004 Maintainability: templates reduce extension onboarding variance.

## 8. Acceptance Gate
1. `make release-check` is first-class and reproducible.
2. Criterion mapping diagnostics are explicit and artifact-linked.
3. CLI bundle generation and re-verification are documented and operable.
4. Tool adapter and skill manifest templates exist with verification checklists.
5. All rollout assets explicitly enforce LangGraph-only orchestration; legacy path is removed from plan.
6. Compatibility guardrails are verified non-breaking.

## 9. Hard Constraints
1. No public CLI argument rename/removal unless approved migration plan exists.
2. No semantic contract break for `schema_version=1.0.0`.
3. No break to `v1.0.0-rc1` anchor semantics or `docs/reports/final-run/` evidence layout.
4. This iteration focuses on research/design/task assets, not large runtime refactoring.
