# DAOKit Architecture Overview

This document is a release-facing architecture summary for operators and contributors.
For complete design rationale, see `specs/001-daokit-agent-platform/design.md`.

## Design Priorities

1. Keep the orchestrator pure (dispatch + verification, no uncontrolled side effects).
2. Keep state deterministic (`pipeline_state` + append-only events as source of truth).
3. Keep long-running workflows recoverable (heartbeat, lease, succession, handoff).

## Runtime Flow

`extract -> plan -> dispatch -> verify -> transition`

- `extract`: normalize execution input and constraints.
- `plan`: compile step contract with acceptance criteria and expected outputs.
- `dispatch`: execute worker actions via controlled interfaces.
- `verify`: enforce evidence and scope checks.
- `transition`: persist state transition and lifecycle metadata.

## Core Components

- Orchestrator runtime: `src/orchestrator/`
- Plan compiler: `src/planner/`
- Dispatch shim adapter: `src/dispatch/`
- Acceptance and scope guard: `src/acceptance/`, `src/audit/`
- State ledger and persistence: `src/state/`
- Reliability (heartbeat, lease, handoff, succession): `src/reliability/`
- Tool layer (function-calling, MCP): `src/tools/`
- Skill and hook runtime: `src/skills/`, `src/hooks/`

## Continuity Model

DAOKit continuity is achieved by combining:

- heartbeat health evaluation
- process lease ownership
- takeover adoption rules
- handoff package generation + apply

This prevents silent ownership drift and preserves run lineage during window/context replacement.

## Evidence Contract

Release and step acceptance expects evidence artifacts:

- `report.md`
- `verification.log`
- `audit-summary.md`

Claims without these artifacts are considered incomplete.
