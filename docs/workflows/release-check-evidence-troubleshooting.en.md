# Release-Check Evidence Troubleshooting (v1.1)

## When to Use
Use this flow when `make release-check` passes/fails but acceptance linkage is unclear, or when criteria diagnostics include `MISSING`/`BROKEN` evidence pointers.

## CI-Aligned Hardening Gate Order
Run the same gate sequence locally that CI executes in `.github/workflows/v11-hardening-gate.yml`.

1. RC-RC-001 release-check baseline gate:

```bash
make gate-release-check
```

2. RC-REL-001 reliability readiness gate:

```bash
make gate-reliability-readiness
```

3. RC-DIAG-001 criteria linkage diagnostics gate:

```bash
make gate-criteria-linkage
```

4. RC-TPL-001 template verification gate:

```bash
make gate-template-checks
```

5. Optional one-shot wrapper (same order and checks):

 ```bash
 make ci-hardening-gate
 ```

6. Inspect generated outputs:
- `.artifacts/release-check/verification.log`
- `.artifacts/release-check/summary.json`
- `docs/reports/criteria-map.json`
- `docs/reports/criteria-map.md`
- `.artifacts/release-check/criteria-linkage-check.json`
- `.artifacts/reliability-gate/verification.log`
- `.artifacts/reliability-gate/summary.json`

## Criterion to Evidence Mapping

| Criterion ID | Gate Command | Primary Evidence |
| --- | --- | --- |
| RC-RC-001 | `make gate-release-check` | `.artifacts/release-check/verification.log`, `.artifacts/release-check/summary.json` |
| RC-REL-001 | `make gate-reliability-readiness` | `.artifacts/reliability-gate/verification.log`, `.artifacts/reliability-gate/summary.json` |
| RC-DIAG-001 | `make gate-criteria-linkage` | `docs/reports/criteria-map.json`, `docs/reports/criteria-map.md`, `.artifacts/release-check/criteria-linkage-check.json` |
| RC-TPL-001 | `make gate-template-checks` | template-suite command output (`tests/templates/`) plus release-check evidence pointers |

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
