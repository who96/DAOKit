# v1.4 Scope Guardrail Charter and Acceptance Matrix

## 1. Charter Purpose
This charter freezes v1.4 scope for DKT-064 and defines an evidence-first acceptance matrix for Wave 0.

v1.4 is locked to P2 + P3 only:
- P2: LangGraph conditional edges + checkpoint/resume.
- P3: `StateBackend` abstraction + SQLite backend.

Parallel branches and human-in-the-loop are explicitly excluded from v1.4.

## 2. DKT-063 Dependency Baseline
DKT-064 inherits non-breaking continuity from DKT-063 evidence:
- `docs/reports/dkt-063/report.md`
- `docs/reports/dkt-063/verification.log`
- `docs/reports/dkt-063/audit-summary.md`
- `docs/reports/final-run/v1.3-final-verification-packet.md`
- `docs/reports/final-run/v1.3-release-readiness-summary.md`

These anchors remain the compatibility baseline for CLI surface, `schema_version=1.0.0`, `v1.0.0-rc1`, and `docs/reports/final-run/` evidence topology.

## 3. Scope Lock (v1.4)

### In Scope
- P2 only: LangGraph conditional edges.
- P2 only: LangGraph checkpoint/resume.
- P3 only: `StateBackend` abstraction with FS + SQLite implementations.
- Cross-backend consistency validation between FS and SQLite.
- Scope-freeze documentation and acceptance evidence for DKT-064.

### Out of Scope
- LangGraph parallel branches.
- Human-in-the-loop routing/approval nodes.
- Public CLI command/argument redesign.
- `schema_version=1.0.0` semantic changes.
- `v1.0.0-rc1` anchor semantic changes.
- `docs/reports/final-run/` evidence topology changes.
- Wave-integration sequencing/merge execution in DKT-064.

## 4. Guardrail Charter

| Guardrail ID | Constraint | Verification Method | Evidence Anchor |
| --- | --- | --- | --- |
| GR-SCP-001 | v1.4 scope is fixed to P2 + P3 only. | Scope wording checks across roadmap/spec/planning artifacts. | `docs/roadmap.md`, `v1.3规划.md`, `specs/007-v1-4-deep-integration/` |
| GR-SCP-002 | P2 scope is only conditional edges + checkpoint/resume. | Positive checks for exact P2 scope markers. | `requirements.md`, `design.md`, `tasks.md` |
| GR-SCP-003 | P3 scope is only `StateBackend` + SQLite with FS parity retained. | Positive checks for exact P3 scope markers. | `requirements.md`, `design.md`, `tasks.md` |
| GR-SCP-004 | Parallel branches and human-in-the-loop are excluded from v1.4. | Out-of-scope wording checks for both exclusions. | `requirements.md`, `tasks.md`, `docs/roadmap.md`, `v1.3规划.md` |
| GR-RUN-001 | Runtime default remains LangGraph. | Runtime policy checks across v1.4/v1.3 scope artifacts. | `requirements.md`, `design.md`, `docs/roadmap.md`, `v1.3规划.md` |
| GR-RUN-002 | Legacy runtime remains maintenance-only. | Policy checks for maintenance-only wording. | `requirements.md`, `design.md`, `docs/roadmap.md`, `v1.3规划.md` |
| GR-COMP-001 | Public CLI names/args remain unchanged. | Compatibility guardrail wording checks + baseline verification. | `requirements.md`, `tasks.md`, verification artifacts |
| GR-COMP-002 | `schema_version=1.0.0` semantics remain intact. | Contract guardrail checks + baseline verification. | `requirements.md`, `tasks.md`, verification artifacts |
| GR-COMP-003 | `v1.0.0-rc1` anchor semantics remain intact. | Release-anchor continuity checks in acceptance artifacts. | `requirements.md`, `tasks.md`, `docs/reports/final-run/` |
| GR-COMP-004 | `docs/reports/final-run/` topology remains stable. | Topology existence checks via release-check and path assertions. | `docs/reports/final-run/` |
| GR-EVID-001 | Baseline verification for DKT-064 is evidenced with command outputs. | Check for fresh outputs from `make lint`, `make test`, `make release-check`. | run artifacts for DKT-064 |
| GR-WAVE-001 | DKT-064 Wave 0 is documentation/validation work only. | Task wording checks for explicit no-integration execution rule. | `tasks.md`, `requirements.md`, `v1.3规划.md` |

## 5. DKT-064 Acceptance Matrix

| Criterion ID | Acceptance Criterion | Required Evidence | Verification Command(s) | Pass Condition |
| --- | --- | --- | --- | --- |
| AC-DKT-064-01 | Scope freeze limits v1.4 to P2/P3 only with explicit P2/P3 boundaries. | Scope lock sections in v1.4 roadmap/spec/planning artifacts and this charter. | `rg -n "P2|P3|Scope Lock|In Scope|Out of Scope|conditional edges|checkpoint/resume|StateBackend|SQLite" docs/roadmap.md v1.3规划.md specs/007-v1-4-deep-integration/requirements.md specs/007-v1-4-deep-integration/design.md specs/007-v1-4-deep-integration/tasks.md specs/007-v1-4-deep-integration/guardrail-charter-acceptance-matrix.md` | Output shows v1.4 scope statements constrained to P2/P3 only. |
| AC-DKT-064-02 | Out-of-scope explicitly excludes parallel branches and human-in-the-loop. | Explicit exclusion wording across authoritative docs. | `rg -n "parallel branches|human-in-the-loop|Out of Scope" docs/roadmap.md v1.3规划.md specs/007-v1-4-deep-integration/requirements.md specs/007-v1-4-deep-integration/tasks.md specs/007-v1-4-deep-integration/guardrail-charter-acceptance-matrix.md` | Output includes both exclusion markers in scope documents. |
| AC-DKT-064-03 | Compatibility/runtime invariants remain explicit, testable, and unchanged. | Guardrail rows and requirement/task constraints for CLI/schema/anchors/runtime policy. | `rg -n "LangGraph|legacy.*maintenance|CLI.*argument|schema_version=1\\.0\\.0|v1\\.0\\.0-rc1|docs/reports/final-run/" docs/roadmap.md v1.3规划.md specs/007-v1-4-deep-integration/requirements.md specs/007-v1-4-deep-integration/design.md specs/007-v1-4-deep-integration/tasks.md specs/007-v1-4-deep-integration/guardrail-charter-acceptance-matrix.md` | Output contains unchanged invariant clauses in all scope assets. |
| AC-DKT-064-04 | Baseline verification commands are executed and evidenced. | Command logs for `make lint`, `make test`, `make release-check`. | `make lint && make test && make release-check` | All commands exit with code `0` and logs are archived under DKT-064 run artifacts. |
| AC-DKT-064-05 | DKT-064 Wave 0 remains scope-freeze only (no wave integration execution). | Explicit no-integration wording in scope documents. | `rg -n "scope-freeze documentation/validation only|no branch-integration execution|Wave 0.*Scope and invariant freeze" specs/007-v1-4-deep-integration/requirements.md specs/007-v1-4-deep-integration/tasks.md specs/007-v1-4-deep-integration/design.md v1.3规划.md` | Output confirms Wave 0 is documentation/validation, not integration execution. |

## 6. Rollout Asset Set (Wave 0)
- `docs/roadmap.md`
- `v1.3规划.md`
- `specs/007-v1-4-deep-integration/requirements.md`
- `specs/007-v1-4-deep-integration/design.md`
- `specs/007-v1-4-deep-integration/tasks.md`
- `specs/007-v1-4-deep-integration/guardrail-charter-acceptance-matrix.md`

## 7. Evidence and Non-Breaking Constraints
- Keep public CLI argument surface unchanged.
- Keep `schema_version=1.0.0` compatibility semantics unchanged.
- Keep `v1.0.0-rc1` anchor semantics and `docs/reports/final-run/` topology unchanged.
- Keep runtime policy unchanged: LangGraph default, legacy runtime maintenance-only.
- DKT-064 acceptance is based on artifacts and verification logs only.

## 8. Change Control
Any update that weakens or removes a guardrail in this charter requires:
1. A replacement guardrail ID with equivalent or stricter protection.
2. Updated acceptance-matrix coverage and verification command mapping.
3. Compatibility review against CLI surface, `schema_version=1.0.0`, `v1.0.0-rc1`, and `docs/reports/final-run/` anchors.
