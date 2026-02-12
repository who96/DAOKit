# v1.1 Guardrail Charter and Acceptance Matrix (Draft)

## 1. Charter Purpose
This charter freezes v1.1 guardrails for DKT-038 and defines an evidence-first acceptance matrix for Wave 0+ execution assets.

v1.1 rollout and verification assets are LangGraph-only. Legacy runtime rollout references are removed, and parameter-based orchestration switching is disallowed in v1.1/v1.2 assets.

## 2. Scope Lock (v1.1)

### In Scope
- `make release-check` as deterministic verification entrypoint.
- Criterion-addressable diagnostics with evidence links.
- Evidence bundle ergonomics and re-verification flow improvements.
- Contributor templates for tool adapters and skill manifests.
- LangGraph-only rollout and acceptance assets for v1.1.

### Out of Scope
- Breaking CLI command or argument changes.
- `schema_version=1.0.0` semantic changes.
- `v1.0.0-rc1` anchor semantic changes.
- Evidence topology changes under `docs/reports/final-run/`.

## 3. Compatibility Guardrail Charter

| Guardrail ID | Constraint | Verification Method | Evidence Anchor |
| --- | --- | --- | --- |
| GR-COMP-001 | Public CLI command/argument names remain unchanged. | API/CLI tests + diff review for renamed/removed public params. | `src/cli/`, `tests/cli/` |
| GR-COMP-002 | `schema_version=1.0.0` semantic compatibility remains intact. | Contract compatibility tests and schema assertions. | `contracts/`, `tests/contracts/` |
| GR-COMP-003 | `v1.0.0-rc1` release anchor semantics remain intact. | Evidence anchor checks and release snapshot continuity checks. | `docs/reports/final-run/RELEASE_SNAPSHOT.md` |
| GR-COMP-004 | `docs/reports/final-run/` structure remains stable. | Path existence and topology checks in release-check. | `docs/reports/final-run/` |
| GR-LGO-001 | v1.1 rollout/verification assets are LangGraph-only. | Text policy assertions across v1.1 spec + prompt assets. | `specs/004-v1-1-tooling-verification-hardening/`, `prompts/zhukong-batch/10_V11_TOOLING_VERIFICATION_PARALLEL_WORKTREE_PROMPT.md` |
| GR-LGO-002 | Legacy runtime support references are absent from v1.1 rollout plan language; only retirement wording is allowed. | Negative scan for "legacy supported/switchable" wording in v1.1 rollout assets. | `specs/004-v1-1-tooling-verification-hardening/`, `prompts/zhukong-batch/tasks/DKT-038.md` ... `prompts/zhukong-batch/tasks/DKT-046.md` |
| GR-LGO-003 | Parameter-based orchestration switching is disallowed in v1.1/v1.2 rollout assets. | Prompt/spec wording checks for explicit prohibition. | `specs/004-v1-1-tooling-verification-hardening/requirements.md`, `specs/005-v1-2-reliability-operator-experience/requirements.md` |
| GR-EVID-001 | Verification logs are machine-parseable using `Command:` and/or command-entry markers. | Verification log parser checks and sample log validation. | `verification.log` artifacts |

## 4. DKT-038 Acceptance Matrix

| Criterion ID | Acceptance Criterion | Required Evidence | Verification Command(s) | Pass Condition |
| --- | --- | --- | --- | --- |
| AC-DKT-038-01 | Guardrails are explicit and testable. | This charter with stable guardrail IDs + methods. | `rg -n "GR-COMP|GR-LGO|GR-EVID" specs/004-v1-1-tooling-verification-hardening/guardrail-charter-acceptance-matrix.md` | Guardrail IDs and methods are present. |
| AC-DKT-038-02 | LangGraph-only policy is explicit in acceptance assets. | LangGraph-only wording in specs/tasks/prompts/roadmap assets. | `rg -n "LangGraph-only|LangGraph only" specs/004-v1-1-tooling-verification-hardening docs/roadmap.md prompts/zhukong-batch/10_V11_TOOLING_VERIFICATION_PARALLEL_WORKTREE_PROMPT.md prompts/zhukong-batch/tasks/DKT-03[8-9].md prompts/zhukong-batch/tasks/DKT-04[0-6].md` | All v1.1 acceptance assets include explicit policy wording. |
| AC-DKT-038-03 | Legacy runtime path is absent from v1.1 rollout plan as a supported option. | No positive support language for legacy path in v1.1 rollout assets. | `rg -n "legacy mode still runs|legacy runtime path remains functional|engine can be switched|rollback from LangGraph mode to legacy mode" specs/004-v1-1-tooling-verification-hardening/requirements.md specs/004-v1-1-tooling-verification-hardening/design.md specs/004-v1-1-tooling-verification-hardening/tasks.md docs/roadmap.md prompts/zhukong-batch/10_V11_TOOLING_VERIFICATION_PARALLEL_WORKTREE_PROMPT.md prompts/zhukong-batch/tasks/DKT-03[8-9].md prompts/zhukong-batch/tasks/DKT-04[0-6].md` | Command returns no matches. |

## 5. Rollout Asset Set (v1.1)
- `specs/004-v1-1-tooling-verification-hardening/requirements.md`
- `specs/004-v1-1-tooling-verification-hardening/design.md`
- `specs/004-v1-1-tooling-verification-hardening/tasks.md`
- `prompts/zhukong-batch/10_V11_TOOLING_VERIFICATION_PARALLEL_WORKTREE_PROMPT.md`
- `prompts/zhukong-batch/tasks/DKT-038.md` ... `prompts/zhukong-batch/tasks/DKT-046.md`

## 6. Evidence Anchors and Non-Breaking Constraints
- Keep `docs/reports/final-run/` anchor structure unchanged.
- Keep compatibility guardrails additive and explicit in all downstream v1.1 tasks.
- Require artifact-backed acceptance (`report.md`, `verification.log`, `audit-summary.md`) for release evidence claims.

## 7. Change Control
Any update that weakens or removes a guardrail in this charter requires:
1. A replacement guardrail ID with equivalent or stricter protection.
2. Updated evidence mapping in this matrix.
3. Compatibility review against `schema_version=1.0.0`, `v1.0.0-rc1`, and `docs/reports/final-run/` anchors.
