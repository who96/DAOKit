# Release-Check Evidence Linkage Conventions

## Goal
Define one stable pointer format across `verification.log`, run reports, and criteria diagnostics so release acceptance remains auditable and machine-checkable.

## Pointer Format
Criteria diagnostics (`docs/reports/criteria-map.json` and `docs/reports/criteria-map.md`) use these canonical tokens:

- `EVIDENCE:<output_name>@<path>`: evidence exists and is linked to an explicit path.
- `MISSING:<output_name>@<path>`: expected evidence pointer exists but artifact is absent.
- `BROKEN:<output_name>@<path>`: pointer resolves outside allowed evidence root or to an invalid target.
- `UNRESOLVED:<output_name>`: no deterministic path could be resolved.

## Linkage Rules
1. Every criterion must publish at least one evidence pointer.
2. Pointers with `MISSING`, `BROKEN`, or `UNRESOLVED` must not appear with `status=passed`.
3. `EVIDENCE` pointers must always include an explicit `@<path>` segment.
4. Pointer order is deterministic and follows registry evidence reference order.

## Consistency Check Command
Run this after generating criteria diagnostics:

```bash
PYTHONPATH=src python3 scripts/check_criteria_linkage.py \
  --criteria-map docs/reports/criteria-map.json \
  --summary-json .artifacts/release-check/criteria-linkage-check.json
```

Expected result:

- Exit code `0` with `[PASS]` output when linkage is consistent.
- Exit code `2` with issue list when pointers are malformed or status linkage is inconsistent.

## Troubleshooting Link
For operator triage workflow, see:

- `docs/workflows/release-check-evidence-troubleshooting.en.md`
