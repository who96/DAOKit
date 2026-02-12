# DAOKit Execution Tasks (Spec-Workflow Equivalent)

This task pack is designed for strict orchestrator execution. Every task includes:
- Goal
- Concrete Actions
- Acceptance Criteria
- Deliverables
- Dependencies

## Stage 0 - Repo and Contracts

### Task DKT-001: Initialize repository skeleton
**Goal**
Create a clean, runnable DAOKit project skeleton for orchestrator-first development.

**Concrete Actions**
1. Create directories: `src/`, `contracts/`, `state/`, `artifacts/`, `docs/`, `tests/`, `examples/`.
2. Add baseline files: `README.md`, `Makefile`, `pyproject.toml`, `.gitignore`, `.env.example`.
3. Add bootstrap CLI command `daokit init`.

**Acceptance Criteria**
1. `daokit init` creates required folders and core state files idempotently.
2. Running bootstrap twice does not corrupt existing files.
3. Basic lint/test command runs without fatal errors.

**Deliverables**
- Repo skeleton and initialization command.

**Dependencies**
- None.

### Task DKT-002: Define canonical state contracts
**Goal**
Establish deterministic JSON schema contracts for state, events, heartbeat, and process leases.

**Concrete Actions**
1. Create JSON schemas for `pipeline_state`, `events`, `heartbeat_status`, `process_leases`.
2. Add schema validator utility and CI schema checks.
3. Version all contracts with `schema_version`.

**Acceptance Criteria**
1. Invalid sample payloads are rejected by validator.
2. Valid payloads pass schema checks.
3. Schema files are documented with field semantics.

**Deliverables**
- Contract schemas and validation utilities.

**Dependencies**
- DKT-001.

## Stage 1 - Orchestrator Runtime

### Task DKT-003: Implement orchestrator state machine
**Goal**
Build LangGraph workflow with explicit states and deterministic transitions.

**Concrete Actions**
1. Implement nodes: `extract`, `plan`, `dispatch`, `verify`, `transition`.
2. Persist state snapshots between node transitions.
3. Add transition guards for forbidden jumps.

**Acceptance Criteria**
1. Graph can run an end-to-end happy path from planning to acceptance.
2. Illegal transition attempts fail with explicit diagnostics.
3. State is recoverable after process restart.

**Deliverables**
- LangGraph orchestrator runtime module.

**Dependencies**
- DKT-002.

### Task DKT-004: Implement strict plan compiler
**Goal**
Compile requirements into step contracts usable by subagents.

**Concrete Actions**
1. Build plan compiler with deterministic `TASK_ID` and `RUN_ID` generation.
2. Enforce required fields: `goal`, `actions`, `acceptance_criteria`, `expected_outputs`, `dependencies`.
3. Add duplicate/contradiction checks across step definitions.

**Acceptance Criteria**
1. Compiler rejects malformed or under-specified steps.
2. Generated step contracts are stable across repeated runs for same input.
3. Compiler output is directly consumable by dispatch engine.

**Deliverables**
- Plan compiler and validation tests.

**Dependencies**
- DKT-003.

### Task DKT-005: Implement shim dispatch adapter
**Goal**
Provide create/resume/rework dispatch interface with artifact capture.

**Concrete Actions**
1. Implement wrapper around local shim call path.
2. Parse subagent outputs into structured result model.
3. Persist raw I/O and normalized output paths.

**Acceptance Criteria**
1. Adapter executes create/resume calls successfully in dry-run simulation.
2. Every call writes request/output/error artifacts.
3. Thread/run correlation remains stable across retries.

**Deliverables**
- Dispatch adapter module.

**Dependencies**
- DKT-004.

## Stage 2 - Acceptance and Audit

### Task DKT-006: Build acceptance engine
**Goal**
Verify step completion by evidence, not text claims.

**Concrete Actions**
1. Implement criterion evaluator for each step acceptance rule.
2. Add evidence resolver for required artifacts.
3. Emit machine-readable failure reasons and rework directives.

**Acceptance Criteria**
1. Missing evidence always yields deterministic failure output.
2. Passing steps produce acceptance proof records.
3. Rework payload references exact failed criteria.

**Deliverables**
- Acceptance evaluator and rework generator.

**Dependencies**
- DKT-005.

### Task DKT-007: Add scope guard and diff auditor
**Goal**
Prevent subagents from touching unrelated files.

**Concrete Actions**
1. Implement allowed-path policy checker per step.
2. Compare changed files against contract scope.
3. Auto-flag unrelated changes for rework.

**Acceptance Criteria**
1. Out-of-scope file edit causes rejection.
2. In-scope edits pass scope check.
3. Audit output clearly lists violating files.

**Deliverables**
- Scope guard policy module.

**Dependencies**
- DKT-006.

## Stage 3 - Tooling Integration

### Task DKT-008: Implement function-calling adapter
**Goal**
Provide typed, validated local tool execution.

**Concrete Actions**
1. Define tool registry with JSON-schema argument validation.
2. Add command execution wrappers and timeout handling.
3. Log all tool invocations with correlation IDs.

**Acceptance Criteria**
1. Invalid tool args are rejected before execution.
2. Timeouts are handled and recorded cleanly.
3. Invocation logs include request, result, and exit status.

**Deliverables**
- Function-calling tool adapter.

**Dependencies**
- DKT-003.

### Task DKT-009: Implement MCP adapter
**Goal**
Integrate external MCP tools while preserving auditability.

**Concrete Actions**
1. Add MCP server discovery and capability map.
2. Implement call wrapper with retry and structured errors.
3. Persist MCP request/response metadata.

**Acceptance Criteria**
1. MCP tools can be listed and invoked from orchestrator.
2. Failed MCP calls return actionable error details.
3. Full call trace is available in artifacts.

**Deliverables**
- MCP adapter and integration tests.

**Dependencies**
- DKT-008.

### Task DKT-010: Implement skill plugin and hook runtime
**Goal**
Support reusable workflow skills and lifecycle hooks.

**Concrete Actions**
1. Define skill manifest format and loader.
2. Implement hook points: pre-dispatch, post-accept, pre-compact, session-start.
3. Enforce hook idempotency and timeout budget.

**Acceptance Criteria**
1. Skills can be discovered and loaded from configured paths.
2. Hooks run at correct lifecycle points.
3. Hook failure does not corrupt ledger state.

**Deliverables**
- Skill runtime and hook engine.

**Dependencies**
- DKT-009.

## Stage 4 - RAG and Memory

### Task DKT-011: Build RAG ingestion pipeline
**Goal**
Ingest project docs and run artifacts into retrievable memory index.

**Concrete Actions**
1. Implement chunking for markdown/json/log evidence.
2. Add embeddings index and metadata storage.
3. Tag chunks with source type and task/run lineage.

**Acceptance Criteria**
1. New documents are indexed and searchable.
2. Retrieval can filter by task_id/run_id.
3. Index rebuild process is deterministic and documented.

**Deliverables**
- RAG indexing pipeline.

**Dependencies**
- DKT-002.

### Task DKT-012: Integrate retrieval policies into orchestrator
**Goal**
Use RAG as advisory context without replacing ledger authority.

**Concrete Actions**
1. Add retrieval nodes for planning and troubleshooting.
2. Enforce source attribution and confidence thresholds.
3. Add policy switch to disable/enable retrieval per step.

**Acceptance Criteria**
1. Retrieval results include sources and relevance scores.
2. Disabling retrieval does not break core execution flow.
3. Ledger remains unchanged by retrieval-only operations.

**Deliverables**
- Retrieval policy integration.

**Dependencies**
- DKT-011.

## Stage 5 - Long-Run Reliability

### Task DKT-013: Implement heartbeat daemon and status evaluator
**Goal**
Detect stalled long-running execution using explicit + implicit signals.

**Concrete Actions**
1. Implement heartbeat checker with interval/watch/stale thresholds.
2. Use artifact mtime as implicit output signal.
3. Emit deduplicated stale escalation events.

**Acceptance Criteria**
1. Active execution with output remains ACTIVE.
2. Silence crossing threshold becomes STALE with reason code.
3. Duplicate stale alerts in same streak are suppressed.

**Deliverables**
- Heartbeat subsystem.

**Dependencies**
- DKT-005.

### Task DKT-014: Implement lease lifecycle and succession takeover
**Goal**
Enable safe controller replacement during active runs.

**Concrete Actions**
1. Implement lease register/heartbeat/renew/release/takeover.
2. Bind lease ownership to task_id/run_id/step_id.
3. On succession acceptance, adopt only valid unexpired leases.

**Acceptance Criteria**
1. Expired leases cannot be adopted.
2. Valid running leases are transferred to successor window.
3. Non-adopted running steps are marked failed explicitly.

**Deliverables**
- Lease and takeover subsystem.

**Dependencies**
- DKT-013.

### Task DKT-015: Implement core rotation handoff package
**Goal**
Provide near-lossless continuation across context/window reset.

**Concrete Actions**
1. Generate handoff package at pre-compact boundary.
2. Load handoff package on new session start.
3. Resume from ledger current step and open acceptance items.

**Acceptance Criteria**
1. After rotation, orchestrator resumes correct step.
2. No accepted step is re-executed by default.
3. Pending/failed steps remain resumable.

**Deliverables**
- Handoff and resume flow.

**Dependencies**
- DKT-014.

## Stage 6 - Productization

### Task DKT-016: Build CLI workflow and operator runbooks
**Goal**
Give engineers a clear command surface to run and recover workflows.

**Concrete Actions**
1. Implement commands: `init`, `check`, `run`, `status`, `replay`, `takeover`, `handoff`.
2. Add error catalog and troubleshooting docs.
3. Provide example projects and quickstart scripts.

**Acceptance Criteria**
1. End-to-end scenario can be run from CLI only.
2. Recovery commands work after forced process interruption.
3. Docs are sufficient for first-run onboarding.

**Deliverables**
- DAOKit CLI and runbook set.

**Dependencies**
- DKT-015.

### Task DKT-017: End-to-end stress test and hardening
**Goal**
Validate stability under long-run, rework, and succession pressure.

**Concrete Actions**
1. Execute 2+ hour long-run simulation with forced stale interval.
2. Trigger at least one succession takeover and one rework loop.
3. Verify event timeline and state consistency after chaos scenarios.

**Acceptance Criteria**
1. System recovers without manual JSON repair.
2. Every completed step links to valid evidence artifacts.
3. Final state and event log are consistent and replayable.

**Deliverables**
- Stress test report and hardening fixes.

**Dependencies**
- DKT-016.

### Task DKT-018: Open-source release package
**Goal**
Ship a credible public project for agent-engineering portfolio use.

**Concrete Actions**
1. Finalize docs (architecture, contribution, security, FAQ).
2. Add sample workflows for backend-to-agent transition path.
3. Publish release tag and roadmap for v1.1/v1.2.

**Acceptance Criteria**
1. Repository can be cloned and run using documented steps.
2. Core demo shows orchestrator consistency + core rotation continuity.
3. Contributors can add tools/skills through documented extension points.

**Deliverables**
- Release-ready repository.

**Dependencies**
- DKT-017.

## Suggested Execution Cadence (Vibe Coding)
- Solo + subagent strict mode: 8-12 focused sessions.
- Parallel dispatch mode: can compress to 5-8 sessions.
- Ship gate: acceptance completion, not calendar duration.

