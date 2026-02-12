# ADR DKT-028: Integration Baseline and Compatibility Contracts

- Status: Accepted (DKT-028 baseline)
- Date: 2026-02-12
- Scope: `LangChain + LangGraph + RAG + Codex` integration rollout foundation
- Supersedes: none
- Related: `specs/003-langchain-langgraph-rag-codex-integration/{requirements,design,tasks}.md`, `docs/observer-relay-*.md`

## 1. Context

DAOKit must introduce an integrated runtime path without breaking three frozen public-contract anchors:

1. CLI command and argument surface compatibility.
2. Contract semantics compatibility with `schema_version=1.0.0`.
3. Release evidence anchor compatibility for `v1.0.0-rc1` and `docs/reports/final-run/`.

DKT-028 freezes architecture boundaries and rollout guardrails so downstream tasks (DKT-029+) can implement incrementally with reversible gates.

## 2. Decision

Adopt a dual-engine integration baseline:

1. Keep legacy runtime path available.
2. Add LangGraph runtime path with the same lifecycle contract (`extract -> plan -> dispatch -> verify -> transition`).
3. Add LangChain as orchestration glue for tools/retrieval.
4. Keep RAG advisory-only with source attribution.
5. Keep Codex shim dispatch as the execution bridge for create/resume/rework.

No CLI argument rename/removal, no contract schema fork, and no release evidence tree restructuring are allowed.

## 3. Ownership Boundaries (Frozen)

| Component | Owns | Must Not Own | Primary Evidence |
|---|---|---|---|
| Engine Selector | Choose `legacy` vs `langgraph` runtime via internal config/env gate | New mandatory public CLI arguments | `specs/003-langchain-langgraph-rag-codex-integration/design.md` (Section 5) |
| Legacy Runtime | Existing orchestrator behavior and compatibility fallback | LangGraph-only node orchestration logic | Existing `make test` baseline |
| LangGraph Runtime | Deterministic lifecycle node execution and transition guards | Direct mutation of public CLI surface or contract versions | `specs/003-langchain-langgraph-rag-codex-integration/design.md` (Sections 3.1, 4) |
| LangChain Layer | Tool/retrieval orchestration with correlated traces | Authoritative ledger writes | `specs/003-langchain-langgraph-rag-codex-integration/design.md` (Section 3.2) |
| RAG Bridge | Retrieval for planning/troubleshooting with source attribution | Direct writes to `pipeline_state/events/leases/heartbeat` | `specs/003-langchain-langgraph-rag-codex-integration/requirements.md` (FR-RAG-003) |
| Codex Shim Dispatch | Create/resume/rework execution and dispatch evidence capture | Bypassing acceptance/rework bounds | `specs/003-langchain-langgraph-rag-codex-integration/requirements.md` (FR-CDX-001..003) |
| Ledger Contracts | Source-of-truth state and events (`schema_version=1.0.0`) | Runtime-specific schema forks | `tests/contracts/test_schema_compatibility_guardrails.py` |
| Observer Relay Window | User relay + state visualization + context compaction | Direct step execution, takeover decisions | `docs/observer-relay-persona-and-compaction.md` |

## 4. Compatibility Invariants (Frozen and Test-Linked)

| Invariant ID | Invariant Statement | Verification Command | Evidence Anchor |
|---|---|---|---|
| COMP-CLI-001 | CLI subcommands remain exactly `init/check/run/status/replay/takeover/handoff`. | `PYTHONPATH=src python3 -m unittest discover -s tests/cli -p 'test_parser_compatibility.py' -v` | `tests/cli/test_parser_compatibility.py` |
| COMP-CLI-002 | Existing long option names and destination mapping remain unchanged. | `PYTHONPATH=src python3 -m unittest discover -s tests/cli -p 'test_parser_compatibility.py' -v` | `tests/cli/test_parser_compatibility.py` |
| COMP-SCHEMA-001 | All core contracts pin `schema_version` to constant `1.0.0`. | `PYTHONPATH=src python3 -m unittest discover -s tests/contracts -p 'test_schema_compatibility_guardrails.py' -v` | `tests/contracts/test_schema_compatibility_guardrails.py` |
| COMP-SCHEMA-002 | Critical contract enums (status/event/severity/lease status) remain frozen; enum drift fails validation. | `PYTHONPATH=src python3 -m unittest discover -s tests/contracts -p 'test_schema_compatibility_guardrails.py' -v` | `tests/contracts/test_schema_compatibility_guardrails.py` |
| COMP-RC1-001 | `v1.0.0-rc1` acceptance anchor references and final-run evidence files remain present. | `PYTHONPATH=src python3 -m unittest discover -s tests/contracts -p 'test_release_evidence_anchors.py' -v` | `tests/contracts/test_release_evidence_anchors.py` |
| COMP-RC1-002 | `docs/reports/final-run/` canonical structure remains intact (snapshot/index/manifest/evidence dir). | `PYTHONPATH=src python3 -m unittest discover -s tests/contracts -p 'test_release_evidence_anchors.py' -v` | `tests/contracts/test_release_evidence_anchors.py` |

## 5. Operational Gates (Actionable)

| Gate | Entry Condition | Required Checks | Pass Criteria | Owner |
|---|---|---|---|---|
| G0 Baseline Freeze | Before integration code changes | `make lint && make test` | No baseline regressions | Integration lead |
| G1 Compatibility Lock | Before enabling integrated path in any run | CLI + schema guardrail tests (`COMP-CLI-*`, `COMP-SCHEMA-*`) | All invariant checks pass | Runtime maintainers |
| G2 Release-Anchor Lock | Before acceptance evidence publication | Release anchor guardrail tests (`COMP-RC1-*`) | Required final-run anchors present | Release/evidence owner |
| G3 Rollout Start | Integrated path trial enablement | `check`, `status`, `replay` health and trace sanity on trial run | No takeover storm, no contract drift signals | Operations owner |
| G4 Promote or Rollback | After trial verification | Acceptance matrix + rollback trigger scan | Promote only if zero rollback triggers active | Controller + release owner |

## 6. Rollback Triggers and Criteria

Rollback is mandatory if any trigger below is observed:

1. CLI compatibility break: parser compatibility test fails.
2. Contract compatibility break: schema guardrail test fails.
3. Release anchor break: final-run anchor test fails or expected anchor files disappear.
4. Runtime instability: repeated stale/takeover churn indicates takeover storm.
5. Authority boundary break: relay window performs direct execution or unauthorized decision routing.

Rollback criteria:

1. Switch engine selection to legacy mode (no migration).
2. Re-run `make lint && make test`.
3. Re-run compatibility checks for `COMP-CLI-*`, `COMP-SCHEMA-*`, `COMP-RC1-*`.
4. Confirm `docs/reports/final-run/` structure and anchor references are restored.

Reference procedure: `docs/observer-relay-rollback-runbook.md`.

## 7. Consequences

Positive:

1. Downstream tasks get clear integration ownership and non-breaking guardrails.
2. Compatibility and release anchors are enforceable by concrete tests.
3. Rollback decisions are no longer ad-hoc; they are gate-triggered.

Tradeoff:

1. Strict frozen boundaries reduce short-term implementation freedom.
2. New integration behavior must pass additional compatibility and evidence checks.

## 8. Acceptance Mapping (DKT-028)

| DKT-028 Acceptance Criterion | This ADR Coverage |
|---|---|
| Integration boundaries and ownership are explicit | Section 3 |
| Compatibility invariants are testable and traceable | Section 4 |
| Rollback triggers are actionable and documented | Sections 5 and 6 |
