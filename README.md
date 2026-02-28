# DAOKit

Language: **English** | [Chinese](README.zh-CN.md)

DAOKit is an open-source agent engineering kit for backend teams that need strict orchestration, auditable execution, and reliable continuity for long-running tasks.

## Why DAOKit

- **Observer-relay boundary**: the external window forwards and visualizes only; execution authority stays in the controller lane.
- **Evidence-first acceptance**: every accepted task is backed by artifacts (`report.md`, `verification.log`, `audit-summary.md`).
- **Heartbeat + lease succession**: long-running runs can detect stale ownership, trigger takeover, and continue safely.
- **Core-rotation continuity**: handoff packages support near-lossless recovery after window or context replacement.

## Release Anchors

Latest release snapshot and acceptance reports:

- [Release Snapshot](docs/reports/final-run/RELEASE_SNAPSHOT.md)
- [Final Acceptance](docs/reports/FINAL_ACCEPTANCE.md)
- [Evidence Bundle](docs/reports/final-run/evidence/)
- [Evidence Manifest SHA256](docs/reports/final-run/evidence_manifest.sha256)

## Quick Start

### 1. Clone and enter repository

```bash
git clone <repository-url> DAOKit
cd DAOKit
```

### 2. Create virtual environment and install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                # core only
pip install -e ".[llm]"        # + LLM dispatch (OpenAI-compatible APIs)
pip install -e ".[rag]"        # + RAG retrieval (Chroma + sentence-transformers)
pip install -e ".[llm,rag]"    # both
```

### 3. Initialize runtime layout

```bash
PYTHONPATH=src python3 -m cli init --root .
```

### 4. Run a core workflow

```bash
PYTHONPATH=src python3 -m cli run \
  --root . \
  --task-id DKT-018-DEMO \
  --run-id RUN-README-001 \
  --goal "README demo run"
```

### 5. Inspect state, events, and health

```bash
PYTHONPATH=src python3 -m cli status --root . --task-id DKT-018-DEMO --run-id RUN-README-001 --json
PYTHONPATH=src python3 -m cli replay --root . --source events --limit 10
PYTHONPATH=src python3 -m cli check --root .
```

## LLM Dispatch Backend

By default, the orchestrator dispatches steps via an external subprocess (`shim` backend).
To use a direct LLM API call instead (DeepSeek, OpenAI, or any OpenAI-compatible provider),
configure the following environment variables in a `.env` file at the project root:

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
DAOKIT_DISPATCH_BACKEND=llm
DAOKIT_LLM_API_KEY=sk-your-api-key
DAOKIT_LLM_BASE_URL=https://api.deepseek.com   # or https://api.openai.com/v1
DAOKIT_LLM_MODEL=deepseek-chat                  # or gpt-4o, etc.
DAOKIT_LLM_MAX_TOKENS=4096
DAOKIT_LLM_TEMPERATURE=0.0
DAOKIT_LLM_TIMEOUT_SECONDS=120
```

Run with the LLM backend:

```bash
PYTHONPATH=src python3 -m cli run \
  --root . \
  --task-id MY-TASK-001 \
  --goal "Implement a config parser with validation"
```

The orchestrator will call the LLM API directly during the `dispatch` phase.
All requests and responses are persisted as artifacts under `artifacts/dispatch/`.

| Backend | How it works | When to use |
|---------|-------------|-------------|
| `shim` (default) | Runs `codex-worker-shim` subprocess | Codex CLI available, want sandboxed execution |
| `llm` | Direct HTTP call to LLM API | No Codex, want lightweight DeepSeek/OpenAI integration |

## Demo Workflows

- [Orchestration consistency demo](examples/cli/quickstart.sh)
- [Observer-relay collaboration recovery-chain demo](examples/cli/observer_relay_recovery_chain.sh)
- [Integrated-mode reliability recovery-chain demo](examples/cli/integrated_reliability_recovery_chain.sh)
- [Recovery demo](examples/cli/recovery.sh)
- [Core-rotation continuity demo](examples/cli/core_rotation_continuity.sh)
- [Backend-to-agent transition path](examples/cli/backend_to_agent_path.sh)

Run demos:

```bash
bash examples/cli/quickstart.sh .
bash examples/cli/observer_relay_recovery_chain.sh .
bash examples/cli/integrated_reliability_recovery_chain.sh .artifacts/readme_demo/integrated .artifacts/readme_demo/integrated/integrated-reliability-summary.json
bash examples/cli/recovery.sh .
bash examples/cli/core_rotation_continuity.sh .
bash examples/cli/backend_to_agent_path.sh .
```

## Documentation Map

- [CLI quickstart](docs/cli-quickstart.md)
- [Architecture overview](docs/architecture.md)
- [Extension guide (tools/skills/hooks)](docs/extensions.md)
- [Backend-to-agent workflows](docs/backend-to-agent-workflows.md)
- [Multi-agent collaboration workflow (English)](docs/workflows/multi-agent-collaboration.en.md)
- [Multi-agent collaboration workflow (Chinese)](docs/workflows/multi-agent-collaboration.zh-CN.md)
- [LangChain + LangGraph + RAG cooperation (English)](docs/workflows/langchain-langgraph-rag-cooperation.en.md)
- [LangChain + LangGraph + RAG cooperation (Chinese)](docs/workflows/langchain-langgraph-rag-cooperation.zh-CN.md)
- [Codex integration runbook (English)](docs/workflows/codex-integration-runbook.en.md)
- [Codex integration runbook (Chinese)](docs/workflows/codex-integration-runbook.zh-CN.md)
- [Observer-relay feasibility report](docs/observer-relay-feasibility.md)
- [Observer-relay persona and compaction policy](docs/observer-relay-persona-and-compaction.md)
- [Observer-relay optimization plan](docs/observer-relay-optimization-plan.md)
- [Observer-relay rollback runbook](docs/observer-relay-rollback-runbook.md)
- [Error catalog](docs/error-catalog.md)
- [FAQ](docs/faq.md)
- [Roadmap](docs/roadmap.md)
- [Security policy](SECURITY.md)
- [Contribution guide](CONTRIBUTING.md)

## Development Verification

```bash
make lint
make test
```

If `make release-check` is unavailable in your branch, use `make lint && make test` plus the demo scripts above as a minimum verification baseline.

## Compatibility Guardrails

- Keep CLI command names and argument names unchanged.
- Keep contract semantics compatible with `schema_version=1.0.0`.
- Keep `v1.0.0-rc1` release-anchor semantics and `docs/reports/final-run/` evidence structure unchanged.

## RAG Embedding Default (v1.3 P1)

- Production default backend: `local/token-signature` (selected in DKT-062).
- Selection evidence:
  - `docs/reports/dkt-061/benchmark/retrieval-benchmark-metrics.json`
  - `docs/reports/dkt-061/benchmark/retrieval-benchmark-report.md`
- Test-mode contract remains deterministic via `deterministic/hash-fixture`.
- Optional API backend `openai/text-embedding-3-small` remains opt-in and non-default.
