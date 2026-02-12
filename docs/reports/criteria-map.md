# Criteria Diagnostics Map

- Registry: `release-acceptance-v1.1`
- Schema Version: `1.0.0`
- Task: `DKT-040`
- Run: `DKT-040_SNAPSHOT`
- Step: `S1`
- Decision Status: `failed`
- Proof ID: `proof-dkt040-snapshot`

| Criterion ID | Criterion | Status | Evidence Refs | Remediation Hint |
| --- | --- | --- | --- | --- |
| RC-RC-001 | make release-check is first-class and reproducible. | passed | `verification.log` | define a deterministic release-check flow and retain command evidence markers |
| RC-DIAG-001 | Criterion mapping diagnostics are explicit and artifact-linked. | passed | `criteria-map.json`, `criteria-map.md` | regenerate criteria diagnostics so every criterion has status and evidence pointers |
| RC-BUNDLE-001 | CLI bundle generation and re-verification are documented and operable. | missing | `verification.log` | criterion is missing from acceptance output; align acceptance criteria input with the release criteria registry |
| RC-TPL-001 | Tool adapter and skill manifest templates exist with verification checklists. | missing | `MISSING:audit-summary.md` | criterion is missing from acceptance output; align acceptance criteria input with the release criteria registry |
| RC-LGO-001 | Rollout assets enforce LangGraph-only orchestration and remove legacy path. | missing | `criteria-map.json` | criterion is missing from acceptance output; align acceptance criteria input with the release criteria registry |
| RC-COMP-001 | Compatibility guardrails are verified as non-breaking. | failed | `verification.log`, `MISSING:audit-summary.md` | create missing evidence artifacts and rerun verification |
