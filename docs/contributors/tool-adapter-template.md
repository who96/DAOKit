# Tool Adapter Contribution Checklist (DKT-043)

Use this guide with `templates/tool_adapter/` when introducing a new tool adapter.
The checklist is acceptance-mapped and evidence-first.

## Template Assets

- `templates/tool_adapter/adapter.py`
- `templates/tool_adapter/tests/test_adapter.py`
- `templates/tool_adapter/README.md`

## Acceptance Mapping

| Acceptance ID | Requirement | Checklist Evidence |
| --- | --- | --- |
| AC-DKT-043-01 | Template scaffold is usable without ad-hoc edits. | `tests/templates/test_tool_adapter_template.py` validates adapter import + smoke invocation against the template. |
| AC-DKT-043-02 | Checklist maps to verifiable acceptance points. | Checklist items below tie commands to `verification.log`, `.artifacts/release-check/summary.json`, and `audit-summary.md` evidence anchors. |
| AC-DKT-043-03 | Extension guidance preserves compatibility constraints. | Compatibility section below binds guardrails for CLI surface, schema semantics, release anchors, and LangGraph-only rollout policy. |

## Contributor Checklist

- [ ] Copy or adapt `templates/tool_adapter/` in your branch and keep a working smoke path.
- [ ] Keep adapter interface methods explicit (`register_tool`, `invoke`) and testable.
- [ ] Replace the skipped placeholder test in `templates/tool_adapter/tests/test_adapter.py` with adapter-specific assertions.
- [ ] Run `make lint && make test && make release-check`.
- [ ] Verify command evidence markers are present in `.artifacts/release-check/verification.log`.
- [ ] Verify release summary contains deterministic status in `.artifacts/release-check/summary.json`.
- [ ] Record acceptance notes in `report.md` and compatibility notes in `audit-summary.md` for review.

## Release-Check Evidence Contract

| Checklist Item | Command | Required Evidence |
| --- | --- | --- |
| Baseline quality gates | `make lint` + `make test` | Passing command entries in `.artifacts/release-check/verification.log` |
| Deterministic release verification | `make release-check` | Markerized command entries + deterministic sequence in `.artifacts/release-check/summary.json` |
| Template and docs linkage | `make test` | `tests/templates/test_tool_adapter_template.py` passing in unit test output |
| Release acceptance traceability | artifact review | `report.md`, `verification.log`, `audit-summary.md` |

## Criteria Linkage

- `RC-TPL-001`: Tool adapter template exists and is coupled to verification checklist evidence.
- `RC-COMP-001`: Compatibility guardrails are explicitly checked before acceptance.

## Compatibility Expectations

Keep all adapter contributions compatible with v1.1 hardening guardrails:

1. Do not rename/remove public CLI parameters (GR-COMP-001).
2. Preserve `schema_version=1.0.0` semantics (GR-COMP-002).
3. Do not change `v1.0.0-rc1` or `docs/reports/final-run/` evidence topology (GR-COMP-003/004).
4. Keep rollout and verification guidance LangGraph-only and avoid parameterized orchestration-engine switching (GR-LGO-001/003).
