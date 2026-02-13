# v1.3 Real Workload Proof Tasks

## Stage A - Scope Freeze

### Task DKT-056: Freeze v1.3 scope and reproducibility semantics
**Goal**
Freeze P0 + P1 boundaries, reproducibility definitions, and compatibility invariants.

**Concrete Actions**
1. Publish `guardrail-charter-acceptance-matrix.md` as the v1.3 scope-freeze source of truth.
2. Encode process-level reproducibility checks (path stability, tool-call sequence shape stability, artifact-structure consistency, LLM text-variance allowance).
3. Confirm runtime policy: LangGraph default, legacy maintenance-only.
4. Confirm compatibility invariants remain unchanged and auditable (`schema_version=1.0.0`, CLI public args, `v1.0.0-rc1`, `docs/reports/final-run/` topology).
5. Run baseline verification commands and retain parser-compatible `verification.log` command evidence.

**Acceptance Criteria**
1. Scope freezes v1.3 as P0 + P1 and explicitly excludes v1.4 P2/P3 implementation work, with a clear acceptance matrix.
2. Reproducibility semantics are explicit and testable: process path and tool-call sequence shape are stable, LLM text variance is allowed, and artifact structure consistency is enforced.
3. Compatibility/runtime constraints are unchanged and auditable: CLI public args unchanged, `schema_version=1.0.0` semantics preserved, `v1.0.0-rc1` and `docs/reports/final-run/` topology preserved, LangGraph default + legacy maintenance-only.
4. Wave integration/merge operations are not executed in this task.

**Deliverables**
- `specs/006-v1-3-real-workload-proof/guardrail-charter-acceptance-matrix.md`
- Updates to `requirements.md`, `design.md`, `tasks.md`, and `v1.3规划.md`
- Baseline verification evidence (`make lint`, `make test`, `make release-check`) with command entries in `verification.log`

**Task-Level Validation Commands**
1. `make lint`
2. `make test`
3. `make release-check`
4. `rg -n "AC-DKT-056|GR-(SCP|REP|RUN|COMP|EVID)" specs/006-v1-3-real-workload-proof/guardrail-charter-acceptance-matrix.md`

**Dependencies**
- DKT-055.

## Stage B - P0 Minimal Real E2E Scenario

### Task DKT-057: Implement minimal text-input E2E scenario flow
**Goal**
Implement extract-plan-dispatch-acceptance flow for a single coding-agent lane.

**Concrete Actions**
1. Add minimal scenario input path using text task description.
2. Enforce planner output to 2-3 executable steps.
3. Run dispatch via real LLM path with bounded scope.

**Acceptance Criteria**
1. Scenario executes end-to-end without mandatory external API dependency.
2. Planner emits bounded actionable steps.
3. Dispatch lane uses real LLM invocation.

**Dependencies**
- DKT-056.

### Task DKT-058: Add scenario evidence packet and acceptance verification
**Goal**
Guarantee E2E scenario run emits complete and auditable evidence outputs.

**Concrete Actions**
1. Emit `report.md`, `verification.log`, `audit-summary.md`, and `events.jsonl`.
2. Add acceptance checks for process-path and artifact-structure consistency.
3. Add regression tests for evidence completeness.

**Acceptance Criteria**
1. Required evidence files are generated per run.
2. Acceptance verifies path/structure consistency.
3. Evidence remains compatible with existing release anchors.

**Dependencies**
- DKT-057.

## Stage C - P1 Embedding Upgrade

### Task DKT-059: Introduce EmbeddingProvider abstraction
**Goal**
Create a pluggable embedding interface that decouples retrieval from fixed model implementation.

**Concrete Actions**
1. Define provider interface and integration contract.
2. Add production/test mode separation.
3. Add unit tests for provider behavior and fallback handling.

**Acceptance Criteria**
1. Retrieval path depends on provider abstraction, not hard-coded implementation.
2. Test mode remains deterministic.
3. Interface supports multiple backend candidates.

**Dependencies**
- DKT-056.

### Task DKT-060: Replace hash embedding in production path
**Goal**
Move production retrieval off toy hash vectors while preserving deterministic test fixtures.

**Concrete Actions**
1. Wire real embedding backend(s) into production path.
2. Keep deterministic fixture path for regression tests.
3. Add migration-safe compatibility checks.

**Acceptance Criteria**
1. Production retrieval uses real embeddings.
2. Deterministic tests continue to pass.
3. Existing contracts remain non-breaking.

**Dependencies**
- DKT-059.

### Task DKT-061: Build retrieval evaluation harness and dataset
**Goal**
Provide benchmark evidence for default embedding selection.

**Concrete Actions**
1. Create 10-20 query evaluation set.
2. Implement top-k retrieval quality measurements.
3. Produce benchmark report artifacts.

**Acceptance Criteria**
1. Benchmark harness is reproducible.
2. Metrics are generated per candidate model.
3. Report artifacts are evidence-linked.

**Dependencies**
- DKT-060.

### Task DKT-062: Decide default embedding model based on benchmark evidence
**Goal**
Select and document default embedding model through measured results.

**Concrete Actions**
1. Compare candidate model metrics and operational tradeoffs.
2. Select default model and update runtime config/docs.
3. Record rationale in release evidence.

**Acceptance Criteria**
1. Model selection is benchmark-backed.
2. Configuration and docs are aligned.
3. Selection rationale is auditable.

**Selection Record (implemented)**
- Default backend: `local/token-signature`.
- Benchmark evidence:
  - `docs/reports/dkt-061/benchmark/retrieval-benchmark-metrics.json`
  - `docs/reports/dkt-061/benchmark/retrieval-benchmark-report.md`
- Tradeoff note: `local/char-trigram` has stronger `hit_rate_at_1`, but `local/token-signature` wins on the primary ranking key (`ndcg_at_3`) and `hit_rate_at_3`, matching the default `top_k=3` retrieval policy focus.

**Dependencies**
- DKT-061.

## Stage D - Final Verification

### Task DKT-063: Produce v1.3 final verification packet and release readiness summary
**Goal**
Publish final v1.3 evidence and go/no-go summary.

**Concrete Actions**
1. Run full v1.3 verification baseline.
2. Aggregate scenario and retrieval benchmark evidence.
3. Publish readiness summary with residual risks.

**Acceptance Criteria**
1. Final packet includes all required evidence artifacts.
2. P0 and P1 acceptance criteria are fully covered.
3. Compatibility invariants remain intact.

**Dependencies**
- DKT-058, DKT-062.

## Suggested Execution Waves
Wave 0: DKT-056
Wave 1: DKT-057 -> DKT-058
Wave 2: DKT-059 -> DKT-060 -> DKT-061 -> DKT-062
Wave 3: DKT-063
