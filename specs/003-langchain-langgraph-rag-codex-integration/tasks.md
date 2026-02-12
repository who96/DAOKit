# LangChain + LangGraph + RAG + Codex Integration Tasks

This task pack is designed for strict orchestrator execution with evidence-first acceptance.

## Stage A - Runtime Foundation

### Task DKT-028: Freeze integration architecture and compatibility contracts
**Goal**
Define integration boundaries and compatibility invariants for LangChain/LangGraph/RAG/Codex runtime rollout.

**Concrete Actions**
1. Produce ADR-style integration baseline and invariants.
2. Define compatibility checklist for CLI contracts and release evidence anchors.
3. Define rollback trigger criteria and operational gates.

**Acceptance Criteria**
1. Integration boundaries and ownership are explicit.
2. Compatibility invariants are testable and traceable.
3. Rollback triggers are actionable and documented.

**Deliverables**
- Architecture ADR + compatibility checklist + rollback criteria doc.

**Dependencies**
- DKT-027.

### Task DKT-029: Introduce optional LangChain and LangGraph dependencies and abstraction layer
**Goal**
Add optional dependencies and adapter interfaces without breaking legacy runtime behavior.

**Concrete Actions**
1. Add optional dependency entries and guarded imports.
2. Introduce engine-agnostic adapter interfaces for runtime services.
3. Add tests that prove legacy mode still runs with defaults.

**Acceptance Criteria**
1. Project installs and tests pass with backward-compatible defaults.
2. Legacy runtime path remains functional.
3. Optional dependency path is feature-gated and tested.

**Deliverables**
- Dependency/config updates + abstraction interfaces + compatibility tests.

**Dependencies**
- DKT-028.

## Stage B - LangGraph and Dispatch Wiring

### Task DKT-030: Implement LangGraph orchestrator runtime
**Goal**
Build LangGraph-based runtime that preserves extract/plan/dispatch/verify/transition lifecycle semantics.

**Concrete Actions**
1. Implement LangGraph node graph for orchestrator lifecycle.
2. Implement transition guards and deterministic lifecycle mapping.
3. Persist transition outcomes to existing ledger structures.

**Acceptance Criteria**
1. LangGraph runtime completes lifecycle happy path.
2. Illegal transitions are blocked with explicit diagnostics.
3. Ledger writes remain contract-compatible.

**Deliverables**
- LangGraph runtime module + tests.

**Dependencies**
- DKT-029.

### Task DKT-031: Wire runtime dispatch to shim adapter for real create/resume/rework
**Goal**
Replace dispatch placeholder with real shim adapter calls and evidence capture flow.

**Concrete Actions**
1. Integrate dispatch node with shim adapter create/resume/rework.
2. Persist dispatch artifacts and correlation IDs per call.
3. Add bounded retry and rework integration.

**Acceptance Criteria**
1. Dispatch node performs real shim actions.
2. Dispatch artifacts are produced per invocation.
3. Retry and rework behavior is deterministic and evidence-backed.

**Deliverables**
- Runtime dispatch integration + dispatch evidence tests.

**Dependencies**
- DKT-030.

## Stage C - LangChain and RAG Cooperation

### Task DKT-032: Integrate LangChain tool orchestration layer
**Goal**
Use LangChain as tool orchestration glue while reusing existing adapter contracts.

**Concrete Actions**
1. Implement LangChain wrapper for function-calling, MCP, skills, and hooks.
2. Preserve step/task/run correlation IDs in tool traces.
3. Add fallback behavior when LangChain path is disabled.

**Acceptance Criteria**
1. Tool orchestration works in LangChain mode with audit traces.
2. Existing adapters remain reusable and contract-compatible.
3. Disabling LangChain path does not break legacy execution.

**Deliverables**
- LangChain tool orchestration integration + tests.

**Dependencies**
- DKT-029.

### Task DKT-033: Integrate RAG as policy-aware retriever in LangChain and LangGraph path
**Goal**
Make RAG a first-class advisory component in integrated runtime path with strict attribution.

**Concrete Actions**
1. Bridge existing RAG index and retriever into LangChain retrieval primitives.
2. Enforce source attribution and relevance threshold behavior.
3. Verify retrieval-only operations remain ledger side-effect free.

**Acceptance Criteria**
1. Planning and troubleshooting retrieval returns sources and scores.
2. Retrieval policies are configurable and test-covered.
3. Retrieval does not mutate authoritative state.

**Deliverables**
- RAG bridge integration + policy tests.

**Dependencies**
- DKT-030, DKT-032.

## Stage D - Codex Team Runtime Integration

### Task DKT-034: Implement Codex worker shim integration contract
**Goal**
Make Codex agent-team execution a first-class dispatch target in runtime.

**Concrete Actions**
1. Implement Codex-specific shim contract mapping for create/resume/rework.
2. Add runbook-aligned payload schema and validation.
3. Add tests for thread/run consistency and error normalization.

**Acceptance Criteria**
1. Codex shim calls are normalized and accepted by dispatch runtime.
2. Error handling and status mapping are deterministic.
3. Artifacts remain compatible with existing audit flow.

**Deliverables**
- Codex shim integration module + tests.

**Dependencies**
- DKT-029.

### Task DKT-035: Add engine rollout controls and rollback runbook implementation
**Goal**
Enable safe rollout between legacy and LangGraph/LangChain integrated modes.

**Concrete Actions**
1. Add engine selector control via non-breaking config/env path.
2. Add compatibility regression tests for CLI and contracts.
3. Add operational rollback runbook with test-linked procedures.

**Acceptance Criteria**
1. Engine can be switched without CLI argument changes.
2. Compatibility regression tests pass for contracts and CLI surface.
3. Rollback path is documented and reproducible.

**Deliverables**
- Engine selector implementation + compatibility tests + rollback doc.

**Dependencies**
- DKT-031, DKT-033, DKT-034.

## Stage E - Reliability Proof and Portfolio Assets

### Task DKT-036: Validate long-running reliability in integrated mode
**Goal**
Prove takeover/handoff continuity under LangGraph+Codex integrated execution.

**Concrete Actions**
1. Run long-run scenario with forced stale condition in integrated mode.
2. Trigger takeover and handoff apply during active run.
3. Validate event/lease/state consistency with replay checks.

**Acceptance Criteria**
1. Integrated mode recovers without manual state repair.
2. Recovery evidence artifacts are complete.
3. Replay and status outputs remain consistent after recovery.

**Deliverables**
- Reliability report and evidence set for integrated mode.

**Dependencies**
- DKT-035.

### Task DKT-037: Publish bilingual portfolio docs and Codex integration runbook
**Goal**
Ship portfolio-grade bilingual narrative proving production use of LangChain, LangGraph, and RAG.

**Concrete Actions**
1. Add bilingual docs explaining architecture cooperation and runtime roles.
2. Publish Codex integration runbook with reproducible command flow.
3. Link docs to concrete evidence artifacts and demo paths.

**Acceptance Criteria**
1. English and Chinese docs clearly explain LC/LG/RAG cooperation.
2. Codex runbook is reproducible by backend engineers.
3. Docs link to evidence artifacts and demo paths.

**Deliverables**
- Bilingual portfolio docs + Codex runbook.

**Dependencies**
- DKT-036.

## Suggested Execution Order (Parallel Waves)
Wave 0: DKT-028
Wave 1: DKT-029
Wave 2 (parallel): DKT-030 + DKT-032
Wave 3 (parallel): DKT-031 + DKT-033 + DKT-034
Wave 4: DKT-035
Wave 5: DKT-036
Wave 6: DKT-037
