# Observer Relay and Bilingual Experience Tasks

This task pack is execution-ready for strict controller dispatch and evidence-first acceptance.

## Stage A - Observer Relay Runtime

### Task DKT-019: Enforce observer relay boundary
**Goal**
Implement explicit relay-only behavior for the external main window.

**Concrete Actions**
1. Introduce relay-mode policy/guard abstraction for forwarding and observing behavior.
2. Block direct execution-role operations when relay mode is active.
3. Add tests for allowed relay actions and denied execution actions.

**Acceptance Criteria**
1. Relay mode deterministically rejects direct execution actions.
2. Relay mode keeps required context fields for forwarding/visualization.
3. Existing CLI command and argument names remain unchanged.

**Deliverables**
- Relay boundary implementation and tests.

**Dependencies**
- DKT-018.

### Task DKT-020: Put controller into subagent lane ownership
**Goal**
Ensure controller authority is represented as subagent-lane ownership, not external window ownership.

**Concrete Actions**
1. Integrate controller lane ownership into runtime dispatch path.
2. Persist ownership state through existing lease/lifecycle data structures.
3. Keep relay side read-only for status and message forwarding.

**Acceptance Criteria**
1. Active run records controller lane ownership in lease/lifecycle views.
2. Routing ownership is observable in status output without schema break.
3. Execution still works with unchanged CLI interface.

**Deliverables**
- Controller-lane integration and compatibility tests.

**Dependencies**
- DKT-019.

### Task DKT-021: Implement self-healing closed loop
**Goal**
Implement deterministic detect/decide/takeover/recover behavior for controller continuity.

**Concrete Actions**
1. Encode decision policy using heartbeat + lease signals.
2. Integrate takeover and handoff apply flows for recovery path.
3. Emit compatible diagnostic events and add regression tests.

**Acceptance Criteria**
1. WARNING state does not force takeover.
2. STALE or invalid lease state triggers takeover path.
3. Recovery updates succession metadata and remains schema-compatible.

**Deliverables**
- Self-healing logic and reliability tests.

**Dependencies**
- DKT-020.

### Task DKT-022: Implement compaction keep/drop policy
**Goal**
Enforce context hygiene for relay performance and availability.

**Concrete Actions**
1. Implement keep/drop compaction policy matching observer relay requirements.
2. Integrate policy at hook boundary (pre-compact) with idempotent behavior.
3. Add deduplication for repeated status/failure/API-noise lines.

**Acceptance Criteria**
1. Required relay context is preserved after compaction.
2. Stale logs and repeated noise are removed.
3. Re-running compaction does not introduce drift.

**Deliverables**
- Compaction policy implementation and tests.

**Dependencies**
- DKT-021.

## Stage B - Compatibility and Safety

### Task DKT-023: Add compatibility guardrails and rollback runbook
**Goal**
Guarantee non-breaking delivery for CLI/contracts/release-evidence anchors.

**Concrete Actions**
1. Add regression checks for CLI parser surface.
2. Add schema invariants checks for `schema_version=1.0.0` compatibility semantics.
3. Document rollback procedure for observer-relay feature rollback.

**Acceptance Criteria**
1. CLI commands/argument names are unchanged.
2. Schema invariants pass without enum/version break.
3. Rollback runbook is actionable and test-linked.

**Deliverables**
- Compatibility tests + rollback documentation.

**Dependencies**
- DKT-022.

## Stage C - Bilingual Documentation Surface

### Task DKT-024: Produce pure English README with language switch
**Goal**
Provide an English-only readme for global users with cross-link to Chinese version.

**Concrete Actions**
1. Rewrite `README.md` as pure English narrative.
2. Add top-level language switch link to Chinese readme.
3. Keep command snippets and doc links correct.

**Acceptance Criteria**
1. `README.md` contains no Chinese narrative text.
2. Language switch links to Chinese readme correctly.
3. Quickstart and docs map remain runnable/valid.

**Deliverables**
- Updated English `README.md`.

**Dependencies**
- DKT-023.

### Task DKT-025: Produce pure Chinese README with language switch
**Goal**
Provide a Chinese-only readme for local users with cross-link to English version.

**Concrete Actions**
1. Create `README.zh-CN.md` as pure Chinese narrative.
2. Add top-level language switch link to English readme.
3. Keep section mapping aligned with English version.

**Acceptance Criteria**
1. `README.zh-CN.md` is Chinese-first narrative only.
2. Language switch links back to English readme.
3. Section parity and core command accuracy match English version.

**Deliverables**
- New Chinese `README.zh-CN.md`.

**Dependencies**
- DKT-024.

### Task DKT-026: Add bilingual multi-agent collaboration workflow docs
**Goal**
Add bilingual workflow examples for observer relay + handoff recovery loop.

**Concrete Actions**
1. Create English and Chinese workflow docs with matched structure.
2. Include health-check decision branch and handoff/clear/restore chain.
3. Link workflow docs with existing architecture/quickstart docs.

**Acceptance Criteria**
1. English and Chinese workflow docs are both complete and cross-linked.
2. Both docs include equivalent flow diagrams and recovery steps.
3. Observer relay responsibilities are clearly separated from controller actions.

**Deliverables**
- Two workflow docs (`en` + `zh-CN`).

**Dependencies**
- DKT-025.

### Task DKT-027: Add runnable collaboration example and docs wiring
**Goal**
Ship one runnable example and integrate bilingual links across docs entry points.

**Concrete Actions**
1. Add a CLI example script for observer-relay collaboration flow.
2. Wire links from readmes and workflow overview docs.
3. Validate end-to-end doc navigation and command reproducibility.

**Acceptance Criteria**
1. Example script runs and demonstrates expected recovery chain.
2. Readmes and workflow docs link to the runnable example.
3. Navigation between English and Chinese docs is complete and consistent.

**Deliverables**
- Runnable example script + integrated docs navigation.

**Dependencies**
- DKT-026.

## Suggested Execution Order
DKT-019 -> DKT-020 -> DKT-021 -> DKT-022 -> DKT-023 -> DKT-024 -> DKT-025 -> DKT-026 -> DKT-027
