# Backend-to-Agent Transition Workflows

This guide provides a practical migration path from backend engineering habits to DAOKit multi-agent operations.

## Observer-Relay Collaboration Reference (Bilingual)

- English: `docs/workflows/multi-agent-collaboration.en.md`
- 中文: `docs/workflows/multi-agent-collaboration.zh-CN.md`

These paired docs define the health-check decision branch plus the handoff -> clear -> restore recovery chain used by the transition drills below.

## LangChain + LangGraph + RAG + Codex Reference (Bilingual)

- English: `docs/workflows/langchain-langgraph-rag-cooperation.en.md`
- 中文: `docs/workflows/langchain-langgraph-rag-cooperation.zh-CN.md`
- Runbook (EN): `docs/workflows/codex-integration-runbook.en.md`
- 运行手册（中文）: `docs/workflows/codex-integration-runbook.zh-CN.md`

These docs explain runtime responsibility boundaries and provide reproducible backend command flows tied to finalized evidence artifacts.

## Workflow A: Deterministic First Run

Goal: build confidence in state and acceptance contracts.

```bash
bash examples/cli/quickstart.sh .
```

Outcome:

- Initializes required state files.
- Runs one orchestrator workflow.
- Verifies status, replay, handoff, and health checks.

## Workflow B: Observer-Relay Recovery Chain Drill

Goal: run the observer-relay recovery chain end-to-end (`health-check -> takeover -> handoff create/apply -> resumed status`).

```bash
bash examples/cli/observer_relay_recovery_chain.sh .
```

Outcome:

- Simulates interruption with active lease.
- Captures health-check snapshot before recovery actions.
- Executes successor takeover and handoff create/apply.
- Verifies resumable post-handoff status and replay trace.

## Workflow C: Failure and Recovery Drill

Goal: practice lease takeover after interruption.

```bash
bash examples/cli/recovery.sh .
```

Outcome:

- Simulates interruption with active lease.
- Adopts lease via successor takeover.
- Confirms post-takeover state and event trace.

## Workflow D: Core-Rotation Continuity Drill

Goal: prove continuity across interruption + takeover + handoff apply.

```bash
bash examples/cli/core_rotation_continuity.sh .
```

Outcome:

- Enforces interruption contract (`run` exits with 130).
- Verifies successor takeover keeps run lineage.
- Creates and applies handoff package.

## Workflow E: Full Transition Path

Goal: run all drills as one onboarding sequence.

```bash
bash examples/cli/backend_to_agent_path.sh .
```

Outcome:

- Replays deterministic run, recovery, and continuity patterns in one path.
- Suitable for onboarding backend contributors in under one hour.

## Workflow F: Integrated Runtime Reliability Drill (Codex Runbook Path)

Goal: reproduce the integrated-mode reliability path used for finalized LangGraph + Codex evidence.

```bash
bash examples/cli/integrated_reliability_recovery_chain.sh \
  .artifacts/manual_runs/codex_integration_demo/scenario \
  .artifacts/manual_runs/codex_integration_demo/integrated-reliability-summary.json
```

Outcome:

- Exercises integrated runtime recovery chain with deterministic stale/takeover/handoff flow.
- Produces machine-readable checkpoints used by the Codex integration runbook.
