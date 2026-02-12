# LangChain + LangGraph + RAG + Codex Integration Requirements

## 1. Objective
Turn DAOKit from a design-claimed architecture into a runtime-proven architecture where LangChain, LangGraph, and RAG are all operational and auditable, while preserving backward compatibility for existing CLI/contracts/release evidence anchors.

## 2. Problem Statement
Current DAOKit has a capability gap against target positioning:
1. LangGraph is described but not yet running as the execution engine.
2. LangChain is not connected as the orchestration/tool composition layer.
3. RAG exists, but needs explicit role in a combined LangChain+LangGraph production path.
4. Codex-based agent team execution is not yet integrated as first-class runtime dispatch.

## 3. Product Principles
1. Never break userspace: no CLI argument rename/removal and no contract semantic break.
2. Engine dual-run safety: keep legacy runtime path while introducing LangGraph path.
3. State-first authority: ledger/contracts remain source of truth; retrieval and model outputs are advisory.
4. Evidence-first delivery: each integration stage must produce verifiable artifacts.
5. Progressive hardening: add integration in reversible increments with rollback points.

## 4. In Scope
- LangChain integration for tool/retrieval orchestration.
- LangGraph runtime graph implementation for orchestrator lifecycle.
- RAG bridge integration in planning/troubleshooting nodes.
- Dispatch bridge from runtime into actual shim adapter calls.
- Codex worker shim protocol and runbook integration.
- Engine-selection rollout mechanism without CLI surface break.
- End-to-end reliability validation with takeover/handoff in LangGraph mode.
- Portfolio-grade bilingual docs explaining architecture and operation.

## 5. Out of Scope
- Breaking schema changes (`schema_version` remains `1.0.0`).
- Breaking command/argument changes in current CLI.
- Full SaaS control plane and multi-tenant hosting.
- Release evidence directory restructure under `docs/reports/final-run/`.

## 6. Functional Requirements

### A. LangGraph Runtime
- FR-LG-001: System must provide a LangGraph-backed orchestrator runtime path.
- FR-LG-002: LangGraph nodes must preserve lifecycle semantics (`extract -> plan -> dispatch -> verify -> transition`).
- FR-LG-003: LangGraph runtime must persist transitions to existing ledger contracts.

### B. LangChain Orchestration Layer
- FR-LC-001: System must provide a LangChain integration layer for tool/retrieval orchestration.
- FR-LC-002: LangChain path must reuse existing function-calling, MCP, skills, hooks adapters.
- FR-LC-003: Tool call traces must remain auditable and step-correlated.

### C. RAG Integration Role
- FR-RAG-001: RAG retrieval must be available to planning and troubleshooting stages.
- FR-RAG-002: Retrieval results must include source attribution and relevance signals.
- FR-RAG-003: Retrieval must remain advisory and must not directly mutate authoritative state.

### D. Codex Agent-Team Dispatch
- FR-CDX-001: Runtime dispatch must support Codex worker shim create/resume/rework flow.
- FR-CDX-002: Dispatch artifacts must persist request/output/error evidence.
- FR-CDX-003: Retry/rework behavior must remain deterministic and bounded.

### E. Compatibility and Rollout
- FR-COMP-001: Existing CLI command and argument names must not change.
- FR-COMP-002: Existing contracts must remain semantically compatible with `schema_version=1.0.0`.
- FR-COMP-003: `v1.0.0-rc1` anchor semantics and `docs/reports/final-run/` structure must remain intact.
- FR-COMP-004: System must support rollback from LangGraph mode to legacy mode without state migration break.

### F. Documentation and Learning Value
- FR-DOC-001: Project must include a clear bilingual explanation of how LangChain/LangGraph/RAG cooperate in production.
- FR-DOC-002: Project must include practical Codex integration runbook for agent-team execution.
- FR-DOC-003: Docs must be sufficient for backend engineers to reproduce one complete agent workflow.

## 7. Non-Functional Requirements
- NFR-001 Reliability: no takeover storm under transient heartbeat jitter.
- NFR-002 Determinism: identical ledger + inputs produce stable node transitions.
- NFR-003 Observability: dispatch/retrieval/transition must be traceable in logs and events.
- NFR-004 Performance: runtime overhead from integration should remain bounded and measurable.
- NFR-005 Maintainability: legacy and LangGraph modes must have clear boundaries and tests.

## 8. Acceptance Gate
1. LangGraph engine can execute full lifecycle with persisted ledger transitions.
2. LangChain integration can orchestrate tools/retrieval without bypassing audit contracts.
3. RAG role is explicit, test-covered, and advisory-safe.
4. Codex shim dispatch is wired and evidence-producing.
5. Compatibility constraints are all verified non-breaking.
6. Bilingual portfolio docs explain architecture and operation end-to-end.

## 9. Hard Constraints
1. No CLI argument rename/removal.
2. No schema semantic break for `1.0.0` contracts.
3. No release evidence layout break.
4. Every task must preserve strict artifacts-based verification discipline.
