# DAOKit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver DAOKit V1 as a strict, auditable multi-agent orchestration toolkit with near-lossless long-run continuity.

**Architecture:** LangGraph orchestrator + shim-based dispatch + acceptance gates + ledger-centered state + heartbeat/lease/succession reliability + RAG advisory memory.

**Tech Stack:** Python 3.11+, LangGraph, Pydantic/JSON Schema, local CLI, vector index (provider-pluggable), markdown/json artifacts.

---

## Execution Order
1. Contracts and state foundation (`DKT-001` ~ `DKT-002`)
2. Runtime and dispatch (`DKT-003` ~ `DKT-005`)
3. Acceptance and governance (`DKT-006` ~ `DKT-007`)
4. Tool abstraction (`DKT-008` ~ `DKT-010`)
5. RAG and memory (`DKT-011` ~ `DKT-012`)
6. Long-run continuity (`DKT-013` ~ `DKT-015`)
7. Productization and release (`DKT-016` ~ `DKT-018`)

## Quality Gates
- Gate A: Schema validation and deterministic transitions pass.
- Gate B: Step acceptance enforces evidence and scope controls.
- Gate C: Heartbeat stale + succession takeover tested.
- Gate D: Long-run core rotation resumes without state loss.
- Gate E: OSS quickstart validated by clean environment run.

## Session-Based Estimate (not calendar-week estimate)
- Baseline: 8-12 focused sessions.
- Aggressive parallel: 5-8 sessions.
- Hard stop condition: do not release before Gate E passes.

## Dispatch Rule for Zhukong
- Keep master pure: dispatch + observe + accept only.
- One step per subagent when acceptance is strict.
- Rework must be diff-based and criterion-mapped.
- Never mark DONE from chat claim; only from artifact evidence.

## Evidence Checklist per Task
1. Step report (`report.md`)
2. Verification output (`verification.log`)
3. Audit result (`audit-summary.md`)
4. State transition event (`events.jsonl` entry)

