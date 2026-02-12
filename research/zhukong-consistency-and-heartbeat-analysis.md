# Why Zhukong Stays Consistent + How Heartbeat Actually Works

## Executive Conclusion
1. `zhukong-orchestrator` consistency is mainly from **role hard constraints + single execution entry + strict artifact-based acceptance**.
2. `heartbeat / lease / succession` logic is primarily implemented in `single-master-orchestrator` scripts, not inside zhukong prompt itself.
3. The model is not "smart by magic"; it is constrained by a deterministic operational envelope.

## A. Why Zhukong Orchestrator Stays Strict

### A1. Role hard constraints are explicit and narrow
- `zhukong` hard-rules explicitly forbid direct file edits and side-effect commands by master.
- Source: `/Users/huluobo/.codex/skills/zhukong-orchestrator/SKILL.md:17`
- Critical clause (single entry): `/Users/huluobo/.codex/skills/zhukong-orchestrator/SKILL.md:21`

### A2. Only one local shim execution path is allowed
- Wrapper path is fixed and preferred, reducing runtime variation.
- Source: `/Users/huluobo/.codex/skills/zhukong-orchestrator/SKILL.md:57`
- Wrapper implementation pins bundled shim source:
  - `/Users/huluobo/.codex/skills/zhukong-orchestrator/assets/bin/gxd-subagent-shim:10`
  - `/Users/huluobo/.codex/skills/zhukong-orchestrator/assets/bin/gxd-subagent-shim:20`

### A3. Long-run policy is explicit (not vague)
- `NO_OUTPUT_20M` and `TIMEOUT_60M` are declared in skill policy.
- Source: `/Users/huluobo/.codex/skills/zhukong-orchestrator/SKILL.md:42`

### A4. Artifacts are first-class audit objects
- Run bootstrap creates `meta.json` + `events.jsonl` (run.init).
- Source: `/Users/huluobo/.codex/skills/zhukong-orchestrator/assets/gxd-subagent-shim-0.2.3/gxd_subagent_shim/artifacts/store.py:129`
- Per-call persistence records request/output/error and appends step events.
- Source: `/Users/huluobo/.codex/skills/zhukong-orchestrator/assets/gxd-subagent-shim-0.2.3/gxd_subagent_shim/artifacts/store.py:393`

### A5. Streaming capture avoids false "no output" interpretation
- Subprocess stdout/stderr are drained by threads and optionally compacted.
- Source: `/Users/huluobo/.codex/skills/zhukong-orchestrator/assets/gxd-subagent-shim-0.2.3/gxd_subagent_shim/backend.py:119`
- Source: `/Users/huluobo/.codex/skills/zhukong-orchestrator/assets/gxd-subagent-shim-0.2.3/gxd_subagent_shim/cli.py:252`

## B. Where Heartbeat and Succession Really Live

### B1. Auto-reconcile is attached to pipeline state mutation
- `pipeline_state.sh` calls lane sync + heartbeat daemon reconcile + planning sync after updates.
- Source:
  - `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/pipeline_state.sh:556`
  - `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/pipeline_state.sh:575`
  - `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/pipeline_state.sh:585`

### B2. Heartbeat daemon controls start/stop lifecycle
- Desired running state is derived from current step + execution lifecycle.
- Source: `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/heartbeat_daemon.sh:81`
- Daemon loop runs check and fill-active-missing continuously.
- Source: `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/heartbeat_daemon.sh:224`

### B3. Heartbeat check uses both explicit and implicit signals
- Explicit beat updates `last_heartbeat_at`.
- Source: `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/heartbeat_check.sh:257`
- Implicit signal: artifact mtime update marks heartbeat advancement.
- Source: `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/heartbeat_check.sh:265`
- Status model includes ACTIVE / STALE / WAIT_GATE / IDLE.
- Source: `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/heartbeat_check.sh:283`

### B4. Stale escalation is deduplicated
- Dedup key: `task_id|last_heartbeat_at|reason`.
- Source: `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/heartbeat_daemon.sh:177`
- First stale in streak triggers health-based succession emit.
- Source: `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/heartbeat_daemon.sh:248`

### B5. Lease is the continuity contract during takeover
- Lease operations: register/heartbeat/renew/release/takeover.
- Source: `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/process_lease.sh:245`
- Expired/non-active lease cannot keep running ownership.
- Source: `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/process_lease.sh:286`

### B6. Succession adoption is validity-gated
- Accepted successor adopts only valid running leases; unmatched running steps become failed.
- Source:
  - `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/succession_vote.sh:328`
  - `/Users/huluobo/.codex/skills/single-master-orchestrator/scripts/succession_vote.sh:372`

## C. Practical Interpretation
1. Zhukong's consistency is mostly **governance design**, not model personality.
2. Heartbeat is **file-ledger + artifact activity driven**, not pure in-memory ping.
3. Stable long-run behavior comes from combining:
   - strict role boundaries,
   - deterministic state transitions,
   - lease-based ownership,
   - evidence-based acceptance.

## D. What DAOKit Should Reuse
1. Keep `pipeline_state` as single source of truth.
2. Keep local shim pinning to avoid runtime drift.
3. Keep heartbeat signal dual-source (beat + artifact mtime).
4. Keep succession takeover lease-gated.
5. Keep acceptance based on artifact evidence, not dialogue claims.

