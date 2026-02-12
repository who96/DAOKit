# Skill Manifest Contributor Template

This guide standardizes `skill.json` manifests for DAOKit skills.

## Template Location

- Template file: `templates/skill-manifest/skill.json.template`
- Target file in a skill package: `<skill-dir>/skill.json`

## Required Metadata Fields

These fields are mandatory and must remain non-empty strings:

1. `schema_version`
2. `name`
3. `version`

The template pins `schema_version` to `1.0.0` to preserve compatibility semantics.

## Optional Sections

Use optional sections only when needed:

- `description`: non-empty string.
- `instructions`: list of non-empty strings.
- `scripts`: object mapping script aliases to file paths.
- `hooks`: list of objects with:
  - `event`: one of `pre-dispatch`, `post-accept`, `pre-compact`, `session-start`
  - `handler`: `<module_or_file>:<callable>` reference
  - `timeout_seconds`: positive number when provided
  - `idempotent`: boolean

## Deterministic Validation Checklist

Run each step in order from repository root.

1. Copy and edit template
   - Command: `cp templates/skill-manifest/skill.json.template /tmp/skill.json`
   - Pass condition: file exists and placeholders are replaced for your skill.
2. Validate JSON syntax
   - Command: `python3 -m json.tool /tmp/skill.json >/dev/null`
   - Pass condition: command exits `0`.
3. Validate manifest against loader contract
   - Command: `PYTHONPATH=src python3 -m unittest discover -s tests/templates -p 'test_skill_manifest_template.py' -v`
   - Pass condition: all tests pass.
4. Run release baseline checks
   - Command: `make lint && make test && make release-check`
   - Pass condition: all commands exit `0`.
5. Confirm command-evidence markers in release log
   - Command: `rg -n "Command: make lint|Command: make test|=== COMMAND ENTRY [0-9]+ START ===" .artifacts/release-check/verification.log`
   - Pass condition: expected markers exist for parser-compatible evidence.

## Release-Check Linkage

Manifest quality is release acceptance input for template criterion `RC-TPL-001`.
Treat `make release-check` as mandatory before merge, and keep command-evidence markers
(`Command: <cmd>` and command entry start/end blocks) in `verification.log`.

## Failure Examples (Deterministic)

Each example below maps to concrete loader validation failures.

### Example A: Missing required `name`

```json
{
  "schema_version": "1.0.0",
  "version": "0.1.0"
}
```

Expected failure from loader: `name must be a non-empty string`

### Example B: Invalid hook event

```json
{
  "schema_version": "1.0.0",
  "name": "bad-hook-skill",
  "version": "0.1.0",
  "hooks": [
    {
      "event": "before-dispatch",
      "handler": "handlers.py:before_dispatch",
      "idempotent": true
    }
  ]
}
```

Expected failure from loader: `hooks[0].event must be one of: post-accept, pre-compact, pre-dispatch, session-start`
