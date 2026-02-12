# Tool Adapter Contributor Template

This template provides a copy-ready scaffold for adding a DAOKit tool adapter.
It is designed to run without ad-hoc edits.

## Template Contents

- `templates/tool_adapter/adapter.py`: interface + default adapter implementation
- `templates/tool_adapter/tests/test_adapter.py`: starter test file with one placeholder test

## Quick Start

1. Copy this template into your feature branch.
2. Run the template smoke tests:

```bash
PYTHONPATH=templates/tool_adapter python3 -m unittest templates/tool_adapter/tests/test_adapter.py -v
```

3. Extend `ToolAdapterTemplate` with adapter-specific validation and execution logic.
4. Replace the skipped placeholder test with adapter-specific assertions.

## Release Verification Linkage

After implementing your adapter contribution, run:

```bash
make lint && make test && make release-check
```

Expected evidence outputs:

- `.artifacts/release-check/verification.log`
- `.artifacts/release-check/summary.json`

## Compatibility Expectations

- Keep public CLI parameter names unchanged.
- Preserve `schema_version=1.0.0` semantics.
- Keep `docs/reports/final-run/` evidence topology unchanged.
- Keep rollout guidance LangGraph-only; do not introduce parameterized engine switching.
