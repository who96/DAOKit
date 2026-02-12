# Criteria Diagnostics Map

- Registry: `release-acceptance-v1.1`
- Schema Version: `1.0.0`
- Task: `DKT-046`
- Run: `DKT-046_20260212T165820Z_639xejo`
- Step: `S1`
- Decision Status: `passed`
- Proof ID: `proof-dkt046-final-packet`
- Evidence Pointer Convention:
  - `EVIDENCE:<output_name>@<path>`
  - `MISSING:<output_name>@<path>`
  - `BROKEN:<output_name>@<path>`
  - `UNRESOLVED:<output_name>`

| Criterion ID | Criterion | Status | Evidence Refs | Remediation Hint |
| --- | --- | --- | --- | --- |
| RC-RC-001 | make release-check is first-class and reproducible. | passed | `EVIDENCE:verification.log@docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/release-check-verification.log` | define a deterministic release-check flow and retain command evidence markers |
| RC-DIAG-001 | Criterion mapping diagnostics are explicit and artifact-linked. | passed | `EVIDENCE:criteria-map.json@docs/reports/criteria-map.json`, `EVIDENCE:criteria-map.md@docs/reports/criteria-map.md` | regenerate criteria diagnostics so every criterion has status and evidence pointers |
| RC-BUNDLE-001 | CLI bundle generation and re-verification are documented and operable. | passed | `EVIDENCE:report.md@docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/report.md`, `EVIDENCE:verification.log@docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/verification.log` | validate bundle generation and re-verification flow with deterministic evidence |
| RC-TPL-001 | Tool adapter and skill manifest templates exist with verification checklists. | passed | `EVIDENCE:report.md@docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/report.md`, `EVIDENCE:audit-summary.md@docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/audit-summary.md` | add or refresh contributor templates and link them to release verification steps |
| RC-LGO-001 | Rollout assets enforce LangGraph-only orchestration and remove legacy path. | passed | `EVIDENCE:report.md@docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/report.md` | remove legacy-path rollout language and keep LangGraph-only policy explicit |
| RC-COMP-001 | Compatibility guardrails are verified as non-breaking. | passed | `EVIDENCE:verification.log@docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/verification.log`, `EVIDENCE:audit-summary.md@docs/reports/final-run/evidence/agent_runs/DKT-046_20260212T165820Z_639xejo/reports/DKT-046/audit-summary.md` | verify CLI surface, schema semantics, and release anchors remain backward-compatible |
