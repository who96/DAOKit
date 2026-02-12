# DAOKit CLI Quickstart

This guide is the release-facing CLI runbook for first-run and recovery.

## Prerequisites

- Python 3.11+
- Commands executed from repository root
- `PYTHONPATH=src`

```bash
export PYTHONPATH=src
```

## Command Surface

- `init`
- `check`
- `run`
- `status`
- `replay`
- `takeover`
- `handoff`

## Happy Path Demo

```bash
bash examples/cli/quickstart.sh .
```

This runs:

1. `cli init`
2. `cli run`
3. `cli status`
4. `cli replay`
5. `cli handoff --create`
6. `cli check`

## Recovery Demo

```bash
bash examples/cli/recovery.sh .
```

This validates interruption + takeover continuity.

## Core-Rotation Continuity Demo

```bash
bash examples/cli/core_rotation_continuity.sh .
```

This validates interruption -> takeover -> handoff create/apply continuity.

## Full Onboarding Path

```bash
bash examples/cli/backend_to_agent_path.sh .
```

## Observer-Relay Recovery Workflow (Bilingual)

- English: `docs/workflows/multi-agent-collaboration.en.md`
- 中文: `docs/workflows/multi-agent-collaboration.zh-CN.md`

Use these docs for the explicit health-check branch and handoff -> clear -> restore chain behind the recovery demos.

For error interpretation, see `docs/error-catalog.md`.
