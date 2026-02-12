# LangChain + LangGraph + RAG Cooperation (Portfolio Narrative)

Language: **English** | [中文](langchain-langgraph-rag-cooperation.zh-CN.md)

## 1. Why this document exists

DAOKit uses LangGraph, LangChain, and RAG together in one production-oriented runtime path.
This note explains the runtime role split, how those layers cooperate in each lifecycle stage,
and where Codex worker dispatch fits for real execution.

## 2. Runtime role split

| Runtime Layer | Primary Role | What It Must Not Do |
| --- | --- | --- |
| LangGraph runtime (`src/orchestrator/`) | Deterministic lifecycle execution: `extract -> plan -> dispatch -> verify -> transition` | Bypass ledger writes or skip transition guards |
| LangChain orchestration (`src/tools/langchain/`) | Orchestrate tool and retriever calls with step/task/run correlation | Become source of truth for state |
| RAG retriever (`src/rag/`) | Supply advisory context with source attribution and relevance hints | Mutate authoritative state directly |
| Codex shim dispatch (`src/dispatch/`) | Execute create/resume/rework actions and emit request/output/error artifacts | Change CLI external argument contracts |
| Ledger contracts (`state/` + `contracts/`) | Persist authoritative state, events, lease, heartbeat, and succession | Accept schema-breaking writes |

## 3. Cooperation by lifecycle stage

1. `extract`
- LangGraph normalizes task/run context and preserves guardrails.
- LangChain is not yet dispatching tools; it is staged for scoped calls.

2. `plan`
- LangChain invokes RAG retrieval as advisory context.
- RAG returns attributed sources and relevance signals.
- Planning output is still constrained by contract-safe state semantics.

3. `dispatch`
- LangGraph calls the dispatch adapter.
- Dispatch adapter routes to Codex shim create/resume/rework flows.
- Request/output artifacts are emitted for auditability.

4. `verify`
- Acceptance and scope checks run before transition.
- Retrieval/tool traces remain auditable and correlated to step IDs.

5. `transition`
- LangGraph persists state/event updates into existing `schema_version=1.0.0` contracts.
- Succession and lifecycle metadata are updated without breaking release anchors.

## 4. Runtime proof from finalized wave evidence

The integrated reliability run from DKT-036 demonstrates the cooperation path in real execution:

- Runtime evidence report:
  - `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/report.md`
- Markerized command evidence:
  - `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/verification.log`
- Machine-readable runtime summary:
  - `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/integrated-reliability-summary.json`

Key proof points in that summary include:

- `runtime_mode=integrated`
- `resolved_runtime_engine=langgraph`
- `runtime_class=LangGraphOrchestratorRuntime`
- `takeover.handoff_applied=true`
- `checks.status_replay_consistent_after_recovery=true`
- `final_state.status=DONE`

## 5. Demo command paths

Use these repository scripts to replay integration behavior:

- Integrated reliability recovery chain:
  - `examples/cli/integrated_reliability_recovery_chain.sh`
- Observer-relay recovery chain:
  - `examples/cli/observer_relay_recovery_chain.sh`
- End-to-end backend onboarding chain:
  - `examples/cli/backend_to_agent_path.sh`

## 6. Compatibility guardrails

- Do not rename/remove CLI command names or existing argument names.
- Keep contract semantics compatible with `schema_version=1.0.0`.
- Keep `v1.0.0-rc1` anchor meaning and `docs/reports/final-run/` evidence structure unchanged.
