# Criteria Diagnostics Map

- Registry: `release-acceptance-v1.1`
- Schema Version: `1.0.0`
- Task: `DKT-042`
- Run: `DKT-042_SNAPSHOT`
- Step: `S1`
- Decision Status: `failed`
- Proof ID: `proof-dkt042-snapshot`
- Evidence Pointer Convention:
  - `EVIDENCE:<output_name>@<path>`
  - `MISSING:<output_name>@<path>`
  - `BROKEN:<output_name>@<path>`
  - `UNRESOLVED:<output_name>`

| Criterion ID | Criterion | Status | Evidence Refs | Remediation Hint |
| --- | --- | --- | --- | --- |
| RC-RC-001 | make release-check is first-class and reproducible. | passed | `EVIDENCE:verification.log@.artifacts/release-check/verification.log` | define a deterministic release-check flow and retain command evidence markers |
| RC-DIAG-001 | Criterion mapping diagnostics are explicit and artifact-linked. | passed | `EVIDENCE:criteria-map.json@docs/reports/criteria-map.json`, `EVIDENCE:criteria-map.md@docs/reports/criteria-map.md` | regenerate criteria diagnostics so every criterion has status and evidence pointers |
| RC-BUNDLE-001 | CLI bundle generation and re-verification are documented and operable. | missing | `MISSING:report.md@.artifacts/agent_runs/DKT-042_SNAPSHOT/reports/DKT-042/report.md`, `EVIDENCE:verification.log@.artifacts/release-check/verification.log` | criterion is missing from acceptance output; align acceptance criteria input with the release criteria registry |
| RC-TPL-001 | Tool adapter and skill manifest templates exist with verification checklists. | missing | `MISSING:report.md@.artifacts/agent_runs/DKT-042_SNAPSHOT/reports/DKT-042/report.md`, `MISSING:audit-summary.md@.artifacts/agent_runs/DKT-042_SNAPSHOT/reports/DKT-042/audit-summary.md` | criterion is missing from acceptance output; align acceptance criteria input with the release criteria registry |
| RC-LGO-001 | Rollout assets enforce LangGraph-only orchestration and remove legacy path. | missing | `MISSING:report.md@.artifacts/agent_runs/DKT-042_SNAPSHOT/reports/DKT-042/report.md` | criterion is missing from acceptance output; align acceptance criteria input with the release criteria registry |
| RC-COMP-001 | Compatibility guardrails are verified as non-breaking. | failed | `EVIDENCE:verification.log@.artifacts/release-check/verification.log`, `MISSING:audit-summary.md@.artifacts/agent_runs/DKT-042_SNAPSHOT/reports/DKT-042/audit-summary.md` | create missing evidence artifacts and rerun verification |
