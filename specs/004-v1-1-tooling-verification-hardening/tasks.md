# v1.1 Tooling and Verification Hardening Tasks

This task pack is LangGraph-only for runtime orchestration. Legacy path is removed from rollout planning.

## Stage A - Baseline and Verification Surface

### Task DKT-038: Freeze v1.1 guardrails and LangGraph-only verification charter
**Goal**
Lock v1.1 scope, compatibility guardrails, and acceptance matrix with explicit LangGraph-only policy.

**Concrete Actions**
1. Publish v1.1 guardrail charter and acceptance matrix draft.
2. Encode non-breaking constraints and evidence anchors.
3. Remove legacy-path references from rollout and acceptance plan.

**Acceptance Criteria**
1. Guardrails are explicit and testable.
2. LangGraph-only policy is explicit in acceptance assets.
3. Legacy runtime path is absent from v1.1 rollout plan.

**Deliverables**
- Guardrail charter + acceptance matrix doc (`specs/004-v1-1-tooling-verification-hardening/guardrail-charter-acceptance-matrix.md`).

**Dependencies**
- DKT-037.

### Task DKT-039: Implement first-class make release-check workflow
**Goal**
Provide deterministic release verification entrypoint and command evidence contract.

**Concrete Actions**
1. Add canonical `make release-check` target.
2. Wire deterministic verification sequence and summary output.
3. Ensure command-evidence logging is preserved.

**Acceptance Criteria**
1. `make release-check` executes expected verification baseline.
2. Output is reproducible on same commit.
3. Command evidence is machine-reviewable.

**Deliverables**
- Release-check workflow + baseline verification logs.

**Dependencies**
- DKT-038.

### Task DKT-040: Implement criterion mapping diagnostics output
**Goal**
Make acceptance diagnostics explicit, criterion-addressable, and evidence-linked.

**Concrete Actions**
1. Define criterion ID registry for release acceptance.
2. Generate Markdown and JSON diagnostics mapping outputs.
3. Add remediation hint and evidence pointer fields.

**Acceptance Criteria**
1. Every criterion has a diagnostic entry.
2. Diagnostics include evidence references and status.
3. Mapping output is stable across repeated runs.

**Deliverables**
- Criteria mapping artifacts + checks.

**Dependencies**
- DKT-038.

## Stage B - Operator UX and Templates

### Task DKT-041: Harden CLI evidence bundle generation and re-verification UX
**Goal**
Make evidence bundle create/review/re-verify flow easy and deterministic without breaking CLI compatibility.

**Concrete Actions**
1. Add additive CLI ergonomics around bundle generation.
2. Add re-verification flow against existing bundles.
3. Keep bundle outputs anchored to existing evidence structure.

**Acceptance Criteria**
1. Bundle generation is reproducible and documented.
2. Re-verification flow works against existing bundles.
3. Existing CLI command/argument contracts remain intact.

**Deliverables**
- CLI UX updates + re-verification tests/docs.

**Dependencies**
- DKT-039, DKT-040.

### Task DKT-042: Stabilize release-check evidence conventions and criteria linkage
**Goal**
Unify report/log/diagnostic linkage so release acceptance is auditable with low ambiguity.

**Concrete Actions**
1. Define evidence pointer conventions across logs/reports/criteria maps.
2. Add consistency checks for missing/broken pointers.
3. Document operator-facing troubleshooting path.

**Acceptance Criteria**
1. Evidence pointers are complete and non-ambiguous.
2. Missing evidence is surfaced as explicit failures.
3. Troubleshooting guidance is actionable.

**Deliverables**
- Evidence linkage spec + consistency checks + troubleshooting docs.

**Dependencies**
- DKT-040, DKT-041.

### Task DKT-043: Add contributor template for tool adapters
**Goal**
Reduce extension variance by shipping a verified tool adapter template.

**Concrete Actions**
1. Provide template scaffold with interface and test placeholders.
2. Add contributor checklist tied to release-check evidence.
3. Document extension compatibility expectations.

**Acceptance Criteria**
1. Template scaffold is usable without ad-hoc edits.
2. Checklist maps to verifiable acceptance points.
3. Extension guidance preserves compatibility constraints.

**Deliverables**
- Tool adapter template + contributor checklist.

**Dependencies**
- DKT-038.

### Task DKT-044: Add contributor template for skill manifests
**Goal**
Provide a standardized skill manifest template with validation-ready guidance.

**Concrete Actions**
1. Provide manifest template with required metadata fields.
2. Add validation checklist and failure examples.
3. Link template usage to release-check verification process.

**Acceptance Criteria**
1. Template clearly states required fields and format.
2. Validation checklist is executable and deterministic.
3. Docs connect manifest quality to release acceptance.

**Deliverables**
- Skill manifest template + validation guide.

**Dependencies**
- DKT-038.

## Stage C - Integration and Final Readiness

### Task DKT-045: Integrate v1.1 hardening gates into CI and operator runbooks
**Goal**
Ensure release-check, diagnostics mapping, and template checks are enforced in one gated flow.

**Concrete Actions**
1. Integrate release-check and diagnostics checks into CI gate sequence.
2. Align operator runbook with gated verification order.
3. Ensure gate outputs are evidence-linked.

**Acceptance Criteria**
1. CI gate executes required hardening checks.
2. Operator runbook is consistent with CI gating.
3. Gate failures map to criterion diagnostics.

**Deliverables**
- CI integration updates + runbook updates.

**Dependencies**
- DKT-042, DKT-043, DKT-044.

### Task DKT-046: Produce v1.1 final verification packet and release readiness summary
**Goal**
Deliver a complete v1.1 evidence packet and go/no-go summary under compatibility constraints.

**Concrete Actions**
1. Generate final report/log/audit artifacts for v1.1.
2. Verify all criteria and guardrails with artifact pointers.
3. Publish release readiness summary with residual risks.

**Acceptance Criteria**
1. Final packet includes required evidence artifacts.
2. Criteria mapping shows complete coverage.
3. Readiness summary is decision-ready and compatibility-safe.

**Deliverables**
- v1.1 final evidence packet + go/no-go summary.

**Dependencies**
- DKT-045.

## Suggested Execution Order (Parallel Waves)
Wave 0: DKT-038
Wave 1 (parallel): DKT-039 + DKT-040
Wave 2 (parallel): DKT-041 + DKT-043 + DKT-044
Wave 3: DKT-042
Wave 4: DKT-045
Wave 5: DKT-046
