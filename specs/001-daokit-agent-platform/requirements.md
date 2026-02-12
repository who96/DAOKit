# DAOKit Requirements Specification

## 1. Objective
Build an open-source, production-grade agent engineering kit that enables backend engineers to design, run, and recover multi-agent workflows with strict traceability, stable execution, and near-lossless context/core rotation.

## 2. Problem Statement
Current multi-agent coding workflows often fail in three ways:
1. Orchestrator drift: the controller starts doing worker tasks and breaks consistency.
2. Long-run degradation: context compaction weakens execution quality over time.
3. Weak recoverability: when a session/window dies, state and ownership are unclear.

DAOKit must solve these issues with explicit contracts, deterministic ledgers, and replayable execution evidence.

## 3. Product Principles
1. State-first architecture: ledger state is source-of-truth, chat history is auxiliary.
2. Controller purity: orchestrator dispatches/verifies only, no direct implementation side-effects.
3. Evidence over claims: every "done" must map to artifacts and verification logs.
4. Safe succession: running work survives window replacement only through explicit lease adoption.
5. Backward-safe evolution: no breaking of existing workflow contracts unless versioned.

## 4. Scope
### In Scope
- Multi-agent orchestration framework with strict acceptance gates.
- LangGraph-based workflow runtime and state machine.
- Tool abstraction for Function Calling, MCP tools, skill plugins, and hooks.
- RAG-enhanced knowledge retrieval for diagnosis/planning/execution hints.
- Heartbeat + lease + succession mechanics for long-running tasks.
- Handoff/core-rotation flow with deterministic state continuity.
- CLI-first developer experience with optional lightweight dashboard.

### Out of Scope (V1)
- Full visual low-code workflow editor.
- Auto-training/custom model fine-tuning pipeline.
- Multi-tenant SaaS hosting.

## 5. Primary Users
1. Backend engineer transitioning to agent engineering.
2. Technical lead running strict, auditable AI-assisted delivery.
3. Open-source contributor extending orchestration patterns.

## 6. Functional Requirements

### A. Orchestration Core
- FR-001: System must provide exactly one active master orchestrator per task run.
- FR-002: Orchestrator must support step-level dispatch to subagents via a standard shim interface.
- FR-003: Orchestrator must support create/resume/rework loop per step.
- FR-004: Orchestrator must enforce acceptance criteria before advancing state.
- FR-005: Orchestrator must reject out-of-scope file modifications at step acceptance.

### B. Planning and Contracts
- FR-006: System must support machine-readable task plans with step id, dependencies, actions, acceptance criteria, expected outputs.
- FR-007: Each step contract must include explicit allowed actions and prohibited actions.
- FR-008: System must maintain a requirements-to-implementation trace map.

### C. State and Ledger
- FR-009: `pipeline_state` (JSON) must be the single authoritative state ledger.
- FR-010: State transitions must be deterministic and append event metadata.
- FR-011: System must persist run metadata, step events, and evidence paths under an artifacts directory.
- FR-012: System must support full run replay from ledger + events + artifacts.

### D. Heartbeat, Lease, Succession
- FR-013: System must maintain heartbeat status for active execution with configurable intervals.
- FR-014: System must support process lease register/heartbeat/renew/release/takeover operations.
- FR-015: Running steps may survive controller replacement only when lease takeover succeeds.
- FR-016: On stale heartbeat threshold breach, system must emit one deduplicated escalation event.
- FR-017: Succession voting and human override must be supported.

### E. Long-Run Core Rotation
- FR-018: System must support context handoff package generation at compaction boundary.
- FR-019: New execution context must recover task progress from ledger + handoff package.
- FR-020: Core rotation must not reset acceptance history or evidence lineage.

### F. Tooling Layer (Function Calling / MCP / Skills / Hooks)
- FR-021: Function Calling tools must support typed schemas and deterministic validation.
- FR-022: MCP tools must support external capability registration and invocation.
- FR-023: Skill plugins must support versioned instruction bundles and local scripts.
- FR-024: Hooks must support event-based interception (pre-step, post-step, pre-compact, session-start).
- FR-025: Tool invocations must be auditable with arguments, outputs, and status.

### G. RAG and Knowledge Layer
- FR-026: System must support indexed retrieval from docs, prior incidents, and run artifacts.
- FR-027: RAG retrieval must be optional per step and policy-controlled.
- FR-028: Retrieved context must include source attribution and confidence signal.
- FR-029: RAG must not directly mutate authoritative state.

### H. Verification and Quality Gates
- FR-030: Each execution step must define verification commands and expected outcomes.
- FR-031: Acceptance gate must require evidence trio (`report`, `verification log`, `audit summary`) when configured.
- FR-032: System must support automatic rework generation from failed criteria.

### I. Developer Experience
- FR-033: CLI must support init/check/run/status/replay/rollover commands.
- FR-034: Templates must generate ready-to-edit specs/design/tasks for new projects.
- FR-035: Documentation must include fast-start runbook and troubleshooting matrix.

## 7. Non-Functional Requirements
- NFR-001 Reliability: no state corruption under abrupt process kill; recovery must be possible from persisted files.
- NFR-002 Determinism: identical inputs and same ledger state produce identical transition outputs.
- NFR-003 Observability: every step state change must produce timestamped structured events.
- NFR-004 Performance: state transition operations should complete within 200ms for normal task sizes.
- NFR-005 Extensibility: tool adapter and memory adapter must be replaceable through interfaces.
- NFR-006 Security: command/tool allowlist and sensitive data redaction in logs.
- NFR-007 Portability: runs on macOS/Linux with Python 3.11+.

## 8. Success Metrics (V1)
1. 95%+ runs complete without manual state repair.
2. 100% completed steps have linked evidence artifacts.
3. Long-run tasks (>= 2h) maintain execution continuity across at least one core rotation.
4. New backend engineer can run first end-to-end workflow within 60 minutes.

## 9. Delivery Envelope (Vibe Coding Reality)
Traditional calendar-week estimates are not used as primary planning unit.
DAOKit V1 should be estimated by focused execution sessions:
- Target: 8-12 focused sessions, each 2-4 hours.
- Effective effort: ~30-60 engineering hours with subagent parallel dispatch.
- Quality gate: ship when acceptance criteria pass, not when a date is reached.

