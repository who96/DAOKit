# v1.4 Deep Integration Requirements

## 1. Objective
Deepen orchestration and state-layer architecture after v1.3 workload proof by implementing high-value LangGraph capabilities and a pluggable SQLite state backend.

## 2. Problem Statement
After v1.3, DAOKit proves real workload execution but still needs deeper architecture proof:
1. LangGraph capability usage is still shallow for dynamic recovery-oriented routing.
2. State persistence remains file-system only.

v1.4 addresses these two areas only (P2 + P3).

## 3. Product Principles
1. Favor depth over breadth: do fewer integrations, but complete them fully.
2. Keep orchestration deterministic and auditable.
3. Preserve compatibility while expanding runtime internals.
4. Maintain legacy runtime stability without adding new features to it.

## 4. In Scope
- P2 scope only: LangGraph conditional edges for dynamic route control.
- P2 scope only: LangGraph checkpoint/resume capability integrated into runtime lifecycle.
- P3 scope only: `StateBackend` abstraction with file-system and SQLite implementations.
- Cross-backend consistency validation and reliability evidence.

## 5. Out of Scope
- LangGraph parallel branches.
- Human-in-the-loop flows.
- Any P2/P3-adjacent feature expansion outside conditional edges + checkpoint/resume + StateBackend + SQLite.
- Presentation/demo packaging as release-critical scope.
- Public CLI contract redesign.

## 6. Functional Requirements

### A. LangGraph Conditional Routing
- FR-LG-001: Runtime must support conditional edge routing based on verified state and node outputs.
- FR-LG-002: Route decisions must be logged with deterministic reason metadata.
- FR-LG-003: Illegal/undefined route transitions must fail with explicit diagnostics.

### B. LangGraph Checkpoint/Resume
- FR-CKPT-001: Runtime must persist checkpoints at defined lifecycle boundaries.
- FR-CKPT-002: Runtime must resume from latest valid checkpoint without manual state repair.
- FR-CKPT-003: Checkpoint replay path must preserve contract-compatible state semantics.

### C. StateBackend Abstraction
- FR-SB-001: Runtime must use a `StateBackend` interface for state, events, leases, and heartbeat data.
- FR-SB-002: Existing file-system backend must remain fully supported.
- FR-SB-003: SQLite backend must implement equivalent semantics and durability guarantees.
- FR-SB-004: Backend selection must remain internal (env/config), with no breaking CLI parameter changes.

### D. Cross-Backend Consistency
- FR-CONS-001: Same scenario inputs must produce equivalent state/event outcomes across FS and SQLite backends.
- FR-CONS-002: Consistency tests must include takeover/recovery relevant paths.
- FR-CONS-003: Consistency evidence must be part of final release packet.

### E. Runtime Policy and Compatibility
- FR-RUN-001: LangGraph remains default runtime.
- FR-RUN-002: Legacy runtime remains maintenance-only (no new features).
- FR-COMP-001: Public CLI command/argument names must remain unchanged unless approved migration exists.
- FR-COMP-002: Contract semantics must remain compatible with `schema_version=1.0.0`.
- FR-COMP-003: `v1.0.0-rc1` anchor and `docs/reports/final-run/` evidence topology must remain unchanged.

## 7. Non-Functional Requirements
- NFR-001 Reliability: checkpoint/resume should reduce recovery interruption risk.
- NFR-002 Determinism: conditional-routing outcomes must be explainable and repeatable.
- NFR-003 Operability: backend differences must remain transparent to operators.
- NFR-004 Maintainability: backend abstraction should isolate persistence concerns cleanly.

## 8. Acceptance Gate
1. DKT-064 scope freeze artifact is published and explicitly limits v1.4 to P2/P3 only.
2. Conditional routing is implemented with deterministic diagnostics.
3. Checkpoint/resume works in runtime lifecycle with auditable evidence.
4. StateBackend abstraction is implemented with FS + SQLite parity.
5. Cross-backend consistency tests pass for required scenarios.
6. Compatibility and runtime-policy constraints are verified non-breaking.

## 9. Hard Constraints
1. No public CLI argument rename/removal without approved migration.
2. No semantic break to `schema_version=1.0.0` contracts.
3. No break to `v1.0.0-rc1` anchor semantics and final-run evidence structure.
4. v1.4 scope is strictly P2 + P3.
5. DKT-064 Wave 0 is scope-freeze documentation/validation only; no branch-integration execution work is included.

## 10. Scope Freeze Charter and Evidence Requirements
1. `specs/007-v1-4-deep-integration/guardrail-charter-acceptance-matrix.md` is the authoritative DKT-064 freeze artifact.
2. v1.4 scope is fixed to:
   - P2: conditional edges + checkpoint/resume only.
   - P3: `StateBackend` abstraction + SQLite backend only.
3. v1.4 explicitly excludes:
   - parallel branches,
   - human-in-the-loop,
   - and any public CLI contract redesign.
4. Runtime policy remains unchanged:
   - LangGraph default runtime,
   - legacy runtime maintenance-only.
5. Compatibility invariants remain unchanged:
   - public CLI names/args,
   - `schema_version=1.0.0` semantics,
   - `v1.0.0-rc1` anchor semantics,
   - `docs/reports/final-run/` evidence topology.
6. Baseline verification evidence for DKT-064 must include fresh outputs from:
   - `make lint`
   - `make test`
   - `make release-check`
