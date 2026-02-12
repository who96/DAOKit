# DAOKit Canonical Contract Schemas

This directory defines deterministic JSON contracts for DAOKit runtime state and audit records.

## Contract Index

| Schema | Purpose |
| --- | --- |
| `pipeline_state.schema.json` | Single source-of-truth ledger snapshot for task/run lifecycle. |
| `events.schema.json` | Append-only structured event entry used for replay and diagnostics. |
| `heartbeat_status.schema.json` | Liveness status and escalation thresholds for active execution. |
| `process_leases.schema.json` | Lease ownership records for heartbeat/renew/release/takeover semantics. |

## Versioning Rule

- Every contract requires `schema_version`.
- Current canonical version is `1.0.0`.
- Breaking changes must be released via a new `schema_version`.
