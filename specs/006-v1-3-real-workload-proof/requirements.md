# v1.3 Real Workload Proof Requirements

## 1. Objective
Prove DAOKit can complete a real workload end-to-end with auditable evidence, not only run an orchestration skeleton.

## 2. Problem Statement
v1.1 and v1.2 harden tooling and reliability, but two critical gaps remain:
1. No minimal real workload flow demonstrating practical value.
2. RAG production path still depends on toy hash-based embedding behavior.

v1.3 addresses these gaps only (P0 + P1).

## 3. Product Principles
1. Deliver one minimal but real scenario before expanding feature breadth.
2. Keep verification evidence-first and reproducible at process level.
3. Separate production retrieval quality from deterministic test fixtures.
4. Preserve compatibility contracts and release evidence anchors.

## 4. In Scope
- Minimal end-to-end scenario with single coding agent lane.
- Real LLM invocation in runtime path.
- EmbeddingProvider abstraction and at least two candidate embedding backends.
- Small retrieval evaluation harness for default-model decision.
- v1.3 evidence packet and release readiness report.

## 5. Out of Scope
- Multi-agent review/PR automation chain.
- Deep LangGraph capabilities (conditional routing/checkpoint/resume) in this version.
- SQLite state backend introduction.
- Any v1.4 P2/P3 implementation work in v1.3 waves.
- Wave-level integration sequencing and release-tag execution in DKT-056.

## 6. Functional Requirements

### A. Minimal Real E2E Scenario
- FR-E2E-001: System must accept a text task description input (no mandatory GitHub API dependency).
- FR-E2E-002: Planner must generate 2-3 executable steps.
- FR-E2E-003: Dispatch must execute one coding-agent lane with real LLM calls.
- FR-E2E-004: Acceptance must evaluate outputs and produce pass/fail evidence.
- FR-E2E-005: Scenario run must produce generated files plus `report.md`, `verification.log`, and `audit-summary.md`.

### B. Reproducibility and Audit Semantics
- FR-REP-001: Same input must reproduce the same state-transition path.
- FR-REP-002: Same input must reproduce the same tool-call sequence shape.
- FR-REP-003: Artifact structure must remain stable across runs, while LLM content variance is allowed.
- FR-REP-004: `events.jsonl` must provide a complete call-chain audit trail.

### C. Embedding Provider Abstraction
- FR-EMB-001: System must expose an `EmbeddingProvider` interface for pluggable backends.
- FR-EMB-002: Production mode must use real embedding vectors, not hash-derived vectors.
- FR-EMB-003: Test mode must keep deterministic fixture behavior for stable regression tests.
- FR-EMB-004: At least two local model candidates and one optional API candidate must be supported by provider configuration.

### D. Retrieval Evaluation and Default-Model Decision
- FR-EVAL-001: System must provide a small retrieval benchmark set (10-20 representative queries).
- FR-EVAL-002: Evaluation must compute at least top-3 hit quality metrics.
- FR-EVAL-003: Default embedding model selection must be evidence-based from evaluation outputs.
- FR-EVAL-004: Evaluation results must be included in release evidence.

### E. Runtime Policy and Compatibility
- FR-RUN-001: Runtime default remains LangGraph.
- FR-RUN-002: Legacy runtime remains available in maintenance mode (no new feature development).
- FR-COMP-001: Public CLI command/argument names must remain unchanged unless migration is approved.
- FR-COMP-002: Contract semantics must remain compatible with `schema_version=1.0.0`.
- FR-COMP-003: `v1.0.0-rc1` anchor and `docs/reports/final-run/` topology must remain unchanged.

## 7. Non-Functional Requirements
- NFR-001 Reliability: E2E scenario should complete without manual state repair.
- NFR-002 Observability: Each run must be diagnosable from artifacts and logs.
- NFR-003 Reproducibility: Process and artifact structure must be repeatable.
- NFR-004 Maintainability: Provider abstraction should avoid model/vendor lock-in.

## 8. Acceptance Gate
1. Minimal real E2E scenario runs with real LLM invocation and evidence outputs.
2. Process-level reproducibility and structure-level comparability are verified.
3. EmbeddingProvider abstraction is implemented with production/test split.
4. Retrieval evaluation report justifies default model selection.
5. Compatibility and runtime policy constraints are verified non-breaking.
6. Scope freeze guardrails and acceptance matrix remain explicit and auditable.

## 9. Hard Constraints
1. No public CLI argument rename/removal without approved migration.
2. No semantic break to `schema_version=1.0.0` contracts.
3. No break to `v1.0.0-rc1` anchor semantics and `docs/reports/final-run/` structure.
4. v1.3 scope is strictly P0 + P1.
5. DKT-056 scope freeze is documentation/validation work only; no wave integration execution is included.

## 10. Scope Freeze Charter and Evidence Requirements
1. `specs/006-v1-3-real-workload-proof/guardrail-charter-acceptance-matrix.md` is the authoritative DKT-056 scope-freeze artifact.
2. v1.3 scope is fixed to P0 + P1; v1.4 P2/P3 implementation work is explicitly excluded from v1.3 acceptance.
3. Reproducibility checks are process-first:
   - stable state-transition path,
   - stable tool-call sequence shape,
   - stable artifact structure/required fields,
   - LLM text variance allowed.
4. Runtime policy remains LangGraph default with legacy runtime maintenance-only.
5. Compatibility invariants remain unchanged:
   - public CLI names/args,
   - `schema_version=1.0.0` semantics,
   - `v1.0.0-rc1` anchor semantics,
   - `docs/reports/final-run/` evidence topology.
6. Verification command evidence in `verification.log` stays parser-compatible and includes:
   - `Command: <cmd>`
   - `=== COMMAND ENTRY N START/END ===`
7. DKT-055 release-check evidence remains the immediate continuity baseline for DKT-056 compatibility assertions.
