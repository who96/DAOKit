# v1.3 Scope Guardrail Charter and Acceptance Matrix

## 1. Charter Purpose
This charter freezes v1.3 scope for DKT-056 and defines an evidence-first acceptance matrix for Wave 0.

v1.3 is locked to P0 + P1. v1.4 work (P2/P3) is explicitly excluded from v1.3 implementation and acceptance.

## 2. DKT-055 Dependency Baseline
DKT-056 inherits non-breaking continuity from DKT-055 evidence:
- `docs/reports/dkt-055/report.md`
- `docs/reports/dkt-055/verification.log`
- `docs/reports/dkt-055/audit-summary.md`
- `docs/reports/final-run/v1.2-final-verification-packet.md`
- `docs/reports/final-run/v1.2-release-readiness-summary.md`

These anchors remain the compatibility baseline for CLI surface, `schema_version=1.0.0`, and final-run evidence topology.

## 3. Scope Lock (v1.3)

### In Scope
- P0 minimal real E2E workload proof.
- P1 EmbeddingProvider abstraction + real embedding integration + retrieval evaluation.
- Scope-freeze documentation and acceptance evidence for DKT-056.

### Out of Scope
- P2 LangGraph deep integration (conditional routing/checkpoint/resume).
- P3 SQLite backend introduction.
- Any v1.4 implementation wave in v1.3 acceptance.
- Wave integration/merge sequencing operations in DKT-056.

## 4. Guardrail Charter

| Guardrail ID | Constraint | Verification Method | Evidence Anchor |
| --- | --- | --- | --- |
| GR-SCP-001 | v1.3 scope is fixed to P0 + P1. | Scope wording checks across roadmap/spec/planning artifacts. | `docs/roadmap.md`, `v1.3规划.md`, `specs/006-v1-3-real-workload-proof/` |
| GR-SCP-002 | v1.4 P2/P3 implementation work is excluded from v1.3. | Out-of-scope checks for explicit P2/P3 exclusion language. | v1.3 roadmap/spec assets |
| GR-REP-001 | Reproducibility is process-level (state-transition path + tool-call sequence shape). | Requirements/design/tasks text checks for explicit process semantics. | `requirements.md`, `design.md`, `tasks.md` |
| GR-REP-002 | LLM text variance is allowed when process path and structure checks pass. | Semantics checks for variance allowance language. | `requirements.md`, `design.md`, `v1.3规划.md` |
| GR-REP-003 | Artifact structure consistency is enforced across runs. | Artifact-structure consistency wording checks in scope docs. | `requirements.md`, `design.md`, `tasks.md` |
| GR-RUN-001 | Runtime default remains LangGraph. | Runtime policy checks in requirements/design/roadmap. | `requirements.md`, `design.md`, `docs/roadmap.md` |
| GR-RUN-002 | Legacy runtime remains maintenance-only. | Negative/positive policy checks for maintenance-only wording. | `requirements.md`, `design.md`, `v1.3规划.md` |
| GR-COMP-001 | Public CLI names/args remain unchanged. | Compatibility guardrail wording checks + baseline verification. | `requirements.md`, `tasks.md`, verification artifacts |
| GR-COMP-002 | `schema_version=1.0.0` semantics remain intact. | Contract guardrail checks + baseline verification. | `requirements.md`, `tasks.md`, verification artifacts |
| GR-COMP-003 | `v1.0.0-rc1` anchor semantics remain intact. | Release-anchor continuity checks in acceptance artifacts. | `requirements.md`, `tasks.md`, `docs/reports/final-run/` |
| GR-COMP-004 | `docs/reports/final-run/` topology remains stable. | Topology existence checks via release-check and path assertions. | `docs/reports/final-run/` |
| GR-EVID-001 | `verification.log` remains parser-compatible with command evidence markers. | Log-format checks for `Command:` and command-entry markers. | `verification.log` artifacts |

## 5. DKT-056 Acceptance Matrix

| Criterion ID | Acceptance Criterion | Required Evidence | Verification Command(s) | Pass Condition |
| --- | --- | --- | --- | --- |
| AC-DKT-056-01 | Scope freezes v1.3 as P0 + P1 and excludes v1.4 P2/P3 with explicit matrix linkage. | Scope lock sections in roadmap/spec/planning artifacts and this charter. | `rg -n "P0 \\+ P1|P2|P3|Out of Scope|v1\\.4" docs/roadmap.md v1.3规划.md specs/006-v1-3-real-workload-proof/requirements.md specs/006-v1-3-real-workload-proof/design.md specs/006-v1-3-real-workload-proof/tasks.md specs/006-v1-3-real-workload-proof/guardrail-charter-acceptance-matrix.md` | Command output shows explicit v1.3-only scope and explicit v1.4 exclusion language. |
| AC-DKT-056-02 | Reproducibility semantics are explicit and testable (path + tool-call shape stable, LLM variance allowed, artifact structure consistency enforced). | FR/Design/Task wording for reproducibility semantics and checks. | `rg -n "state-transition path|tool-call sequence shape|LLM text variance|artifact structure|process-level" specs/006-v1-3-real-workload-proof/requirements.md specs/006-v1-3-real-workload-proof/design.md specs/006-v1-3-real-workload-proof/tasks.md v1.3规划.md` | Command output includes all four semantics dimensions in authoritative docs. |
| AC-DKT-056-03 | Compatibility/runtime invariants remain unchanged and auditable (CLI args, `schema_version=1.0.0`, `v1.0.0-rc1`, `docs/reports/final-run/`, LangGraph default + legacy maintenance-only). | Guardrail rows and requirement/task constraints plus baseline verification logs. | `rg -n "LangGraph|legacy.*maintenance|CLI.*argument|schema_version=1\\.0\\.0|v1\\.0\\.0-rc1|docs/reports/final-run/" specs/006-v1-3-real-workload-proof/requirements.md specs/006-v1-3-real-workload-proof/design.md specs/006-v1-3-real-workload-proof/tasks.md v1.3规划.md docs/roadmap.md specs/006-v1-3-real-workload-proof/guardrail-charter-acceptance-matrix.md` | Command output contains unchanged invariant clauses; baseline verification commands pass with command evidence logs. |
| AC-DKT-056-04 | DKT-056 executes scope-freeze artifacts and task-level validation only (no wave integration). | DKT-056 task wording and plan constraints. | `rg -n "no wave integration|scope freeze is documentation/validation work only|Wave 0.*只做范围冻结" specs/006-v1-3-real-workload-proof/requirements.md specs/006-v1-3-real-workload-proof/tasks.md v1.3规划.md` | Command output confirms explicit no-integration rule in DKT-056 artifacts. |

## 6. Rollout Asset Set (Wave 0)
- `docs/roadmap.md`
- `v1.3规划.md`
- `specs/006-v1-3-real-workload-proof/requirements.md`
- `specs/006-v1-3-real-workload-proof/design.md`
- `specs/006-v1-3-real-workload-proof/tasks.md`
- `specs/006-v1-3-real-workload-proof/guardrail-charter-acceptance-matrix.md`

## 7. Evidence and Non-Breaking Constraints
- Keep public CLI argument surface unchanged.
- Keep `schema_version=1.0.0` compatibility semantics unchanged.
- Keep `v1.0.0-rc1` anchor semantics and `docs/reports/final-run/` topology unchanged.
- Require parser-compatible command evidence in `verification.log`:
  - `Command: <cmd>`
  - `=== COMMAND ENTRY N START/END ===`
- DKT-056 acceptance is based on artifacts and verification logs only.

## 8. Change Control
Any update that weakens or removes a guardrail in this charter requires:
1. A replacement guardrail ID with equivalent or stricter protection.
2. Updated acceptance-matrix coverage and verification command mapping.
3. Compatibility review against CLI surface, `schema_version=1.0.0`, `v1.0.0-rc1`, and `docs/reports/final-run/` anchors.
