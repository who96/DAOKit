# v1.2 Reliability Guardrail Charter and Acceptance Matrix

## 1. Charter Purpose
This charter freezes v1.2 reliability guardrails for DKT-047 and defines an evidence-first acceptance matrix for Wave 0 and downstream execution assets.

v1.2 rollout and recovery assets are LangGraph-only. No legacy runtime support option is exposed, and parameter-based orchestration switching guidance is disallowed in v1.2 rollout assets.

## 2. DKT-046 Dependency Baseline
DKT-047 inherits the non-breaking baseline proven by DKT-046 artifacts:
- `docs/reports/final-run/v1.1-final-verification-packet.md`
- `docs/reports/final-run/v1.1-release-readiness-summary.md`
- `docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/report.md`
- `docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/verification.log`
- `docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/audit-summary.md`

These anchors define compatibility continuity for CLI contracts, `schema_version=1.0.0`, and final-run evidence topology.

## 3. Scope Lock (v1.2)

### In Scope
- Reliability guardrail charter and acceptance matrix publication.
- LangGraph-only policy hardening in rollout/recovery assets.
- Compatibility and evidence requirements encoding for v1.2 tasks.

### Out of Scope
- Breaking CLI command or argument changes.
- `schema_version=1.0.0` semantic changes.
- `v1.0.0-rc1` anchor semantic changes.
- Evidence topology changes under `docs/reports/final-run/`.

## 4. Guardrail Charter

| Guardrail ID | Constraint | Verification Method | Evidence Anchor |
| --- | --- | --- | --- |
| GR-REL-001 | DKT-047 defines explicit, testable v1.2 reliability guardrails before runtime implementation waves. | Charter/matrix static checks for stable guardrail and acceptance IDs. | `specs/005-v1-2-reliability-operator-experience/guardrail-charter-acceptance-matrix.md` |
| GR-REL-002 | v1.2 rollout assets include explicit acceptance-gate language tied to reliability outputs. | Text checks across roadmap/spec/prompt assets for acceptance wording. | `docs/roadmap.md`, `specs/005-v1-2-reliability-operator-experience/`, `prompts/zhukong-batch/11_V12_RELIABILITY_OPERATOR_PARALLEL_WORKTREE_PROMPT.md` |
| GR-LGO-001 | Runtime and recovery workflows in v1.2 assets are documented and validated as LangGraph-only. | Positive policy scan for LangGraph-only wording in rollout assets. | v1.2 roadmap/spec/prompt assets |
| GR-LGO-002 | Legacy runtime path is absent from v1.2 rollout plan as a supported option. | Negative scan for positive legacy-support wording. | v1.2 roadmap/spec/prompt assets |
| GR-LGO-003 | Parameter-based orchestration switching guidance is disallowed in v1.2 rollout assets. | Prompt/spec policy checks for explicit prohibition language. | `specs/005-v1-2-reliability-operator-experience/requirements.md`, `prompts/zhukong-batch/tasks/DKT-047.md` |
| GR-COMP-001 | Public CLI command and argument names remain unchanged. | API/CLI regression tests plus review for renamed/removed public params. | `src/cli/`, `tests/cli/` |
| GR-COMP-002 | `schema_version=1.0.0` semantic compatibility remains intact. | Contract compatibility tests and schema assertions. | `contracts/`, `tests/contracts/` |
| GR-COMP-003 | `v1.0.0-rc1` release anchor semantics remain intact. | Release anchor continuity checks in release evidence assets. | `docs/reports/final-run/RELEASE_SNAPSHOT.md` |
| GR-COMP-004 | `docs/reports/final-run/` evidence structure remains stable. | Path topology and linkage checks in release-check workflow. | `docs/reports/final-run/` |
| GR-EVID-001 | Verification logs remain machine-parseable for acceptance tooling. | Verification log format checks for command markers. | `verification.log` artifacts |
| GR-EVID-002 | Reliability claims require artifact-backed proof (`report.md`, `verification.log`, `audit-summary.md`). | Audit checks require file pointers for each acceptance claim. | task run directories and final-run evidence mirrors |

## 5. DKT-047 Acceptance Matrix

| Criterion ID | Acceptance Criterion | Required Evidence | Verification Command(s) | Pass Condition |
| --- | --- | --- | --- | --- |
| AC-DKT-047-01 | Reliability guardrails are explicit and testable. | Guardrail table with stable IDs, methods, and anchors. | `rg -n "GR-(REL|LGO|COMP|EVID)-" specs/005-v1-2-reliability-operator-experience/guardrail-charter-acceptance-matrix.md` | Command returns guardrail IDs and rows. |
| AC-DKT-047-02 | LangGraph-only policy is explicit across v1.2 assets. | LangGraph-only wording in roadmap/spec/task assets. | `rg -n "LangGraph-only|LangGraph only|LangGraph Runtime" docs/roadmap.md specs/005-v1-2-reliability-operator-experience/requirements.md specs/005-v1-2-reliability-operator-experience/design.md specs/005-v1-2-reliability-operator-experience/tasks.md specs/005-v1-2-reliability-operator-experience/guardrail-charter-acceptance-matrix.md prompts/zhukong-batch/11_V12_RELIABILITY_OPERATOR_PARALLEL_WORKTREE_PROMPT.md prompts/zhukong-batch/tasks/DKT-047.md` | Policy markers are present in rollout and task assets. |
| AC-DKT-047-03 | Legacy runtime path is absent from v1.2 rollout plan as a supported option. | No positive legacy-support language in rollout assets. | `rg -n "legacy mode still runs|legacy runtime path remains functional|engine can be switched|rollback from LangGraph mode to legacy mode|fallback to legacy runtime" docs/roadmap.md specs/005-v1-2-reliability-operator-experience/requirements.md specs/005-v1-2-reliability-operator-experience/design.md specs/005-v1-2-reliability-operator-experience/tasks.md specs/005-v1-2-reliability-operator-experience/guardrail-charter-acceptance-matrix.md prompts/zhukong-batch/11_V12_RELIABILITY_OPERATOR_PARALLEL_WORKTREE_PROMPT.md prompts/zhukong-batch/tasks/DKT-047.md` | Command returns no matches. |

## 6. Rollout Asset Set (v1.2)
- `docs/roadmap.md`
- `specs/005-v1-2-reliability-operator-experience/requirements.md`
- `specs/005-v1-2-reliability-operator-experience/design.md`
- `specs/005-v1-2-reliability-operator-experience/tasks.md`
- `specs/005-v1-2-reliability-operator-experience/guardrail-charter-acceptance-matrix.md`
- `prompts/zhukong-batch/11_V12_RELIABILITY_OPERATOR_PARALLEL_WORKTREE_PROMPT.md`
- `prompts/zhukong-batch/tasks/DKT-047.md` through `prompts/zhukong-batch/tasks/DKT-055.md`

## 7. Evidence and Non-Breaking Constraints
- Keep `docs/reports/final-run/` anchor structure unchanged.
- Keep compatibility guardrails additive and explicit in downstream v1.2 tasks.
- Require artifact-backed acceptance (`report.md`, `verification.log`, `audit-summary.md`) for reliability claims.
- Preserve DKT-046 evidence continuity as baseline for all v1.2 rollout decisions.

## 8. Change Control
Any update that weakens or removes a guardrail in this charter requires:
1. A replacement guardrail ID with equivalent or stricter protection.
2. Updated evidence mapping in this matrix.
3. Compatibility review against `schema_version=1.0.0`, `v1.0.0-rc1`, and `docs/reports/final-run/` anchors.
