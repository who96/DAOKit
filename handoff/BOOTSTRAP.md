# DAOKit — Bootstrap Context

## Project
- **Name**: DAOKit — Orchestrator-first agent engineering kit
- **Repo**: github.com/who96/DAOKit
- **Local**: /Users/huluobo/workSpace/DAOKit
- **Lang**: Python 3.11+, setuptools build
- **Package layout**: `src/` (package-dir mapped to root via pyproject.toml)
- **Import prefix**: `from rag import ...` (not `from src.rag`)

## Key Directories
| Path | Purpose |
|------|---------|
| `src/rag/` | RAG module (ingest, index, retrieval, evaluation, engine) |
| `src/state/` | State persistence (filesystem + sqlite backends) |
| `src/orchestrator/` | Agent orchestration core |
| `src/cli/` | CLI entry points |
| `tests/` | unittest-based tests, mirrors src structure |

## Build & Test
```bash
# Install with optional deps
pip install -e ".[rag]"

# Run tests
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py' -v

# Lint
python -m compileall src tests
```

## Code Style
- `from __future__ import annotations` always first
- Frozen dataclasses for data records
- Type hints on all signatures, `str | None` union syntax
- Private helpers prefixed with `_`
- `__init__.py` with explicit `__all__` in each subpackage
- unittest.TestCase, no mocking, integration-style tests
- Deterministic hashing for IDs, JSON persistence with schema versions

## Dependencies (optional groups)
- `[rag]`: chromadb, sentence-transformers
- `[langchain]`: langchain
- `[langgraph]`: langgraph
