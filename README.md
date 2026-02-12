# DAOKit

DAOKit is an open-source agent engineering kit for backend engineers who need strict orchestration, auditable execution, and reliable continuity across long-running sessions.

## Why DAOKit

- `主控一致性` (Controller Consistency): the master controller dispatches, observes, and accepts only; it does not directly perform worker-side implementation.
- `证据验收` (Evidence-First Acceptance): no task is accepted without artifact evidence (`report.md`, `verification.log`, `audit-summary.md`).
- `心跳 + 租约接班` (Heartbeat + Lease Succession): long-running tasks can escalate, transfer ownership, and recover without losing execution integrity.
- `无损换芯恢复` (Near-Lossless Core Rotation): context/window resets recover from ledger + handoff package instead of fragile chat-only memory.

Latest release snapshot and merged acceptance report:
- `docs/reports/final-run/RELEASE_SNAPSHOT.md`
- `docs/reports/FINAL_ACCEPTANCE.md`
- `docs/reports/final-run/evidence/` (tracked evidence bundle)
- `docs/reports/final-run/evidence_manifest.sha256` (integrity hashes)

## What DAOKit Provides

- Deterministic orchestration workflow (`extract -> plan -> dispatch -> verify -> transition`)
- State-first execution model (`state/` ledger is source of truth)
- Core-rotation continuity via handoff package + successor takeover
- Extension points for function-calling tools, MCP tools, skills, and lifecycle hooks

Note: `state/` is runtime-generated and intentionally not versioned. Release-level audit reproducibility is anchored by `docs/reports/final-run/` plus the tracked evidence bundle and hash manifest above.

## Quick Start

### 1. Clone and Enter Repository

```bash
git clone <repository-url> DAOKit
cd DAOKit
```

### 2. (Optional) Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Initialize Runtime Layout

```bash
PYTHONPATH=src python3 -m cli init --root .
```

### 4. Run a Core Workflow

```bash
PYTHONPATH=src python3 -m cli run \
  --root . \
  --task-id DKT-018-DEMO \
  --run-id RUN-README-001 \
  --goal "README demo run"
```

### 5. Inspect State, Events, and Health

```bash
PYTHONPATH=src python3 -m cli status --root . --task-id DKT-018-DEMO --run-id RUN-README-001 --json
PYTHONPATH=src python3 -m cli replay --root . --source events --limit 10
PYTHONPATH=src python3 -m cli check --root .
```

## Demo Workflows

- Orchestration consistency demo: `examples/cli/quickstart.sh`
- Core-rotation continuity demo: `examples/cli/core_rotation_continuity.sh`
- Backend-to-agent transition path: `examples/cli/backend_to_agent_path.sh`

Run examples:

```bash
bash examples/cli/quickstart.sh .
bash examples/cli/core_rotation_continuity.sh .
bash examples/cli/backend_to_agent_path.sh .
```

## Documentation Map

- CLI onboarding: `docs/cli-quickstart.md`
- Architecture overview: `docs/architecture.md`
- Extension guide (tools/skills/hooks): `docs/extensions.md`
- Backend-to-agent workflows: `docs/backend-to-agent-workflows.md`
- FAQ: `docs/faq.md`
- Security policy: `SECURITY.md`
- Contribution guide: `CONTRIBUTING.md`
- Roadmap (v1.1 / v1.2): `docs/roadmap.md`

## Development Verification

```bash
make lint
make test
```

If `make release-check` is not available in your branch, run `make lint && make test` plus the demo scripts above as minimum baseline verification.
