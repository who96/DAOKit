# Core-Rotation Chaos Matrix (DKT-051)

## 1. Purpose

This workflow documents the expanded core-rotation chaos matrix introduced for DKT-051.
It defines scenario fixtures, deterministic execution constraints, continuity assertion mapping,
and where evidence artifacts are generated for downstream DKT-052 continuity work.

## 2. Scenario Matrix

Matrix version: `dkt-051-core-rotation-v1`

| Scenario ID | Risk Paths | Fixture Intent | Continuity Assertions |
| --- | --- | --- | --- |
| `stale-takeover-handoff-resume` | `rotation`, `takeover` | Force stale heartbeat while lease is still active; verify takeover + handoff resume continuity. | `CONT-001`, `CONT-002`, `CONT-003`, `CONT-004`, `CONT-006`, `CONT-007`, `CONT-008` |
| `warning-invalid-lease-forced-takeover` | `takeover`, `stale_lease` | Keep heartbeat at WARNING but expire controller lease to force takeover from invalid lease path. | `CONT-001`, `CONT-002`, `CONT-003`, `CONT-004`, `CONT-005`, `CONT-007`, `CONT-008` |
| `stale-invalid-lease-core-rotation` | `rotation`, `takeover`, `stale_lease` | Combine stale heartbeat and expired lease for highest-risk takeover path. | `CONT-001`, `CONT-002`, `CONT-003`, `CONT-004`, `CONT-005`, `CONT-006`, `CONT-007`, `CONT-008` |
| `stale-active-lease-dedup-escalation` | `rotation`, `takeover` | Re-check stale path with deterministic second tick to assert stale-event de-dup behavior. | `CONT-001`, `CONT-002`, `CONT-003`, `CONT-004`, `CONT-006`, `CONT-007`, `CONT-008` |

## 3. Fixture Fields

Each scenario fixture is defined in:

- `src/reliability/scenarios/core_rotation_chaos_matrix.py`

Core fixture fields:

- `scenario_id`: Stable scenario identity for evidence indexing.
- `risk_tags`: Coverage labels used by matrix-level high-risk path checks.
- `heartbeat_silence_seconds`: Synthetic silence age used to force WARNING/STALE transitions.
- `controller_lease_ttl_seconds`: Lease TTL used before self-healing cycle.
- `lease_expiry_advance_seconds`: Optional deterministic clock advance to force expired lease takeover.
- `include_accepted_steps_in_handoff`: Handoff package behavior toggle for continuity replay.
- `expected_*` fields: Expected takeover/heartbeat/handoff/adoption outcomes used for assertion mapping.

## 4. Deterministic Execution Constraints

Shared deterministic constraints:

- `seed`: `DKT-051-core-rotation-chaos-matrix`
- `clock_anchor_utc`: `2026-02-12T09:46:00+00:00`
- `check_interval_seconds`: `60`
- `warning_after_seconds`: `900`
- `stale_after_seconds`: `1200`
- `second_tick_advance_seconds`: `120`
- `replay_limit`: `500`

These constraints are emitted in every scenario summary and in matrix summary payloads.

## 5. Continuity Assertion Catalog

Assertion catalog source:

- `CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG` in `src/reliability/scenarios/core_rotation_chaos_matrix.py`

Key continuity assertions:

- `CONT-001`: takeover timestamp sync into succession state.
- `CONT-002`: handoff apply + resume-step continuity.
- `CONT-003`: replay/event count continuity.
- `CONT-004`: no manual JSON state repair required.
- `CONT-005`: invalid lease escalation path forces takeover.
- `CONT-006`: stale escalation de-dup on deterministic second tick.
- `CONT-007`: adopted/failed step sets match fixture expectation.
- `CONT-008`: post-takeover lease ownership matches expected adoption path.

## 6. Execution Commands

Single scenario (default fixture):

```bash
PYTHONPATH=src python3 -m reliability.scenarios.integrated_reliability \
  --scenario-root .artifacts/dkt051/single \
  --output-json .artifacts/dkt051/single-summary.json
```

Full matrix:

```bash
PYTHONPATH=src python3 -m reliability.scenarios.integrated_reliability \
  --matrix \
  --matrix-root .artifacts/dkt051/matrix \
  --output-json .artifacts/dkt051/matrix-summary.json
```

## 7. Evidence Output Points

Matrix summary payload provides:

- `matrix_summary`: coverage and assertion mapping checks.
- `scenario_results[*].reproducibility`: deterministic metadata.
- `scenario_results[*].continuity_assertion_results`: scenario assertion outcomes.
- `scenario_results[*].evidence_output_points`: per-scenario paths:
  - `scenario_root`
  - `state_dir`
  - `events_log`
  - `handoff_package`
  - `runtime_settings`
- `scenario_results[*].command_log`: parser-compatible command evidence with exit codes.
