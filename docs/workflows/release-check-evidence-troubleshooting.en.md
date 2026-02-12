# Release-Check Evidence Troubleshooting (v1.1)

## When to Use
Use this flow when `make release-check` passes/fails but acceptance linkage is unclear, or when criteria diagnostics include `MISSING`/`BROKEN` evidence pointers.

## Baseline Sequence
1. Run baseline verification:

```bash
make lint && make test && make release-check
```

2. Validate criteria linkage conventions:

```bash
PYTHONPATH=src python3 scripts/check_criteria_linkage.py \
  --criteria-map docs/reports/criteria-map.json \
  --summary-json .artifacts/release-check/criteria-linkage-check.json
```

3. Inspect generated outputs:
- `.artifacts/release-check/verification.log`
- `.artifacts/release-check/summary.json`
- `docs/reports/criteria-map.json`
- `docs/reports/criteria-map.md`
- `.artifacts/release-check/criteria-linkage-check.json`

## Failure Diagnosis by Pointer State
- `MISSING:<output>@<path>`:
  - Artifact not found at expected location.
  - Action: regenerate the artifact and rerun baseline + linkage check.

- `BROKEN:<output>@<path>`:
  - Pointer path is invalid (for example outside evidence root) or cannot be trusted.
  - Action: fix output path wiring and rerun release-check.

- `UNRESOLVED:<output>`:
  - Pointer could not be deterministically resolved.
  - Action: ensure the output is declared in acceptance expected outputs and produced in the evidence root.

## Fast Validation Rules
1. Every criterion row must include at least one pointer.
2. `status=passed` rows must only use `EVIDENCE:` pointers.
3. `EVIDENCE:` and `BROKEN:` pointers must include explicit `@<path>`.
4. If parser compatibility issues appear, verify `verification.log` contains `Command:` and/or `=== COMMAND ENTRY` markers.

## Compatibility Guardrails
- Do not change public CLI parameter names.
- Keep `schema_version=1.0.0` semantics intact.
- Preserve `v1.0.0-rc1` anchors and `docs/reports/final-run/` evidence topology.
- Keep LangGraph-only rollout policy wording unchanged.
