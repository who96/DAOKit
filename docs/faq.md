# DAOKit FAQ

## What problem does DAOKit solve?

DAOKit gives backend engineers a strict, auditable way to run multi-agent workflows without losing control of state, ownership, and acceptance evidence.

## Is chat history the source of truth?

No. Ledger state files under `state/` are the source of truth during runtime. Chat history is context only.

`state/` is runtime-generated and intentionally not versioned; release-level acceptance reproducibility is provided by `docs/reports/final-run/`, the tracked evidence bundle, and `evidence_manifest.sha256`.

## How does DAOKit handle long-running continuity?

Through heartbeat checks, lease ownership, takeover, and handoff package resume flows.

## How do I verify a run is consistent?

Use CLI commands:

```bash
PYTHONPATH=src python3 -m cli status --root . --json
PYTHONPATH=src python3 -m cli replay --root . --source events --limit 20
PYTHONPATH=src python3 -m cli check --root .
```

## How do I prove core rotation continuity?

Run the demo script:

```bash
bash examples/cli/core_rotation_continuity.sh .
```

The script enforces interruption (`exit 130`), successor takeover, handoff creation, and handoff apply.

## How can contributors add custom tools or skills?

Start with `docs/extensions.md`, then follow `CONTRIBUTING.md` for tests and PR requirements.

## Why might `make release-check` be missing?

Some branches only expose `make lint` and `make test`. In that case, run those plus demo scripts as release-equivalent verification and document command-to-coverage mapping in `verification.log`.
