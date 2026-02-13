# v1.4 Deep Integration Tasks

## Stage A - Scope Freeze

### Task DKT-064: Freeze v1.4 scope and integration invariants
**Goal**
Freeze P2 + P3 boundaries, runtime policy, and compatibility constraints.

**Concrete Actions**
1. Publish `specs/007-v1-4-deep-integration/guardrail-charter-acceptance-matrix.md` as DKT-064 source of truth.
2. Confirm P2 depth scope is only conditional edges + checkpoint/resume.
3. Confirm P3 backend scope is only `StateBackend` + SQLite (FS parity retained).
4. Align freeze wording across `requirements.md`, `design.md`, `tasks.md`, `docs/roadmap.md`, and `v1.3规划.md`.
5. Run `make lint && make test && make release-check` and archive command evidence for audit.

**Acceptance Criteria**
1. Scope excludes parallel branches and human-in-the-loop.
2. Compatibility invariants are explicit, testable, and unchanged (CLI/schema/anchors/runtime policy).
3. Runtime policy is aligned with maintenance-only legacy mode.
4. Wave 0 acceptance is documentation/validation only (no integration/merge sequencing work).

**Dependencies**
- DKT-063.

## Stage B - P2 LangGraph Depth

### Task DKT-065: Implement conditional-edge policy engine and diagnostics
**Goal**
Enable deterministic dynamic routing with explicit route reasons.

**Concrete Actions**
1. Add conditional route predicates for key lifecycle branches.
2. Emit route-reason diagnostics and guard-failure logs.
3. Add unit tests for route decision determinism.

**Acceptance Criteria**
1. Route decisions are explicit and auditable.
2. Illegal routes fail with actionable diagnostics.
3. Deterministic route behavior is test-covered.

**Dependencies**
- DKT-064.

### Task DKT-066: Integrate conditional routing into orchestrator graph lifecycle
**Goal**
Wire conditional-edge engine into runtime lifecycle transitions.

**Concrete Actions**
1. Apply conditional routes to lifecycle graph nodes.
2. Ensure correlation IDs remain intact across route branches.
3. Add integration tests for route-path coverage.

**Acceptance Criteria**
1. Runtime graph uses conditional routing in production path.
2. Branch traces are artifact-auditable.
3. Integration tests cover expected and failure branches.

**Dependencies**
- DKT-065.

### Task DKT-067: Implement checkpoint manager and resume semantics
**Goal**
Provide checkpoint persistence and reliable resume behavior.

**Concrete Actions**
1. Persist checkpoints at defined lifecycle boundaries.
2. Add checkpoint integrity validation on resume.
3. Add replay/resume tests for interrupted runs.

**Acceptance Criteria**
1. Resume works from latest valid checkpoint.
2. Invalid checkpoints are detected with clear diagnostics.
3. Replay/resume behavior is contract-compatible.

**Dependencies**
- DKT-064.

## Stage C - P3 State Backend Expansion

### Task DKT-068: Introduce StateBackend abstraction and refactor FS backend
**Goal**
Decouple runtime persistence from file-system implementation details.

**Concrete Actions**
1. Define `StateBackend` interface for required state domains.
2. Adapt FS backend to the new interface.
3. Add regression tests proving FS behavior parity.

**Acceptance Criteria**
1. Runtime depends on interface, not FS internals.
2. FS backend remains fully functional.
3. Regression tests preserve current semantics.

**Dependencies**
- DKT-066, DKT-067.

### Task DKT-069: Implement SQLite backend with contract parity
**Goal**
Provide SQLite persistence backend equivalent to FS semantics.

**Concrete Actions**
1. Implement SQLite backend operations for all required state domains.
2. Add transactional safeguards for append and checkpoint operations.
3. Add integration tests for SQLite runtime behavior.

**Acceptance Criteria**
1. SQLite backend passes contract parity checks.
2. Durability and atomicity behaviors are validated.
3. Runtime can execute lifecycle on SQLite backend.

**Dependencies**
- DKT-068.

### Task DKT-070: Add cross-backend consistency and recovery-path validation
**Goal**
Validate FS and SQLite produce equivalent behavior on key scenarios.

**Concrete Actions**
1. Run same scenarios across both backends.
2. Compare contract-relevant state/event outputs.
3. Include recovery-path and takeover-relevant checks.

**Acceptance Criteria**
1. Consistency report shows equivalence within defined tolerance.
2. Recovery-path behavior is consistent across backends.
3. Evidence artifacts are complete and auditable.

**Dependencies**
- DKT-069.

## Stage D - Final Verification

### Task DKT-071: Produce v1.4 final verification packet and release readiness summary
**Goal**
Publish final v1.4 evidence and go/no-go summary.

**Concrete Actions**
1. Execute full v1.4 verification baseline.
2. Aggregate LangGraph-depth and backend-parity evidence.
3. Publish release readiness summary with residual risks.

**Acceptance Criteria**
1. Final packet includes all required evidence artifacts.
2. P2 and P3 acceptance criteria are fully covered.
3. Compatibility invariants remain intact.

**Dependencies**
- DKT-070.

## Suggested Execution Waves
Wave 0: DKT-064
Wave 1: DKT-065 -> DKT-066, and DKT-067 in parallel where feasible
Wave 2: DKT-068 -> DKT-069 -> DKT-070
Wave 3: DKT-071

## DKT-064 Audit Anchors
- `specs/007-v1-4-deep-integration/guardrail-charter-acceptance-matrix.md`
- `docs/roadmap.md`
- `v1.3规划.md`
