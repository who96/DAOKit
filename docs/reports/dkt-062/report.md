# DKT-062 Default Embedding Selection (Benchmark-Backed)

## Scope

Select the v1.3 P1 default embedding backend using DKT-061 benchmark evidence, align runtime configuration and docs with the selected default, and preserve compatibility constraints.

## Selection Outcome

- Selected default production backend: `local/token-signature`
- Not selected as default: `local/char-trigram`, `openai/text-embedding-3-small`
- Runtime integration points:
  - `src/rag/index/providers.py`
  - `src/rag/index/__init__.py`

## Benchmark Evidence Snapshot (DKT-061)

| Rank | Backend | hit@1 | hit@3 | mrr@3 | ndcg@3 |
| --- | --- | --- | --- | --- | --- |
| 1 | `local/token-signature` | 0.083333 | 0.583333 | 0.305556 | 0.349947 |
| 2 | `local/char-trigram` | 0.333333 | 0.333333 | 0.333333 | 0.268858 |

Decision rule for ranking follows DKT-061 benchmark report ordering: primary key `ndcg_at_3`, then `mrr_at_3`, then `hit_rate_at_3`, then backend id.

## Rationale and Tradeoffs

1. **Primary quality objective (`ndcg@3`) favors `local/token-signature`.**
   - `local/token-signature` leads by `ndcg@3` (0.349947 vs 0.268858) and `hit@3` (0.583333 vs 0.333333), which aligns with default retrieval `top_k=3` usage.
2. **`local/char-trigram` has stronger top-1 precision but weaker top-3 ranking quality.**
   - `local/char-trigram` improves `hit@1` but underperforms on the selected ranking objective and multi-hit retrieval window.
3. **OpenAI backend remains opt-in, not default, for operational reasons in v1.3.**
   - `openai/text-embedding-3-small` requires external API credentials and package availability; DKT-061 baseline benchmark did not include optional API backend runs.
4. **Deterministic test contract is preserved.**
   - Test mode still resolves to `deterministic/hash-fixture` and remains unchanged.

## Compatibility and Constraint Check

- CLI public command/argument names: unchanged.
- `schema_version=1.0.0` release-check semantics: unchanged.
- `v1.0.0-rc1` and `docs/reports/final-run/` anchor semantics: unchanged.
- Runtime policy remains LangGraph-default / legacy maintenance-only: unchanged by this step.

## What Was Produced

1. Runtime default selection constants and helper function:
   - `DEFAULT_PRODUCTION_EMBEDDING_BACKEND`
   - `DKT_062_SELECTION_EVIDENCE_PATHS`
   - `default_production_embedding_backend()`
2. Runtime wiring updates for explicit default and OpenAI fallback behavior:
   - `src/rag/index/providers.py`
3. Public export alignment:
   - `src/rag/index/__init__.py`
4. Test coverage for default selection and evidence linkage:
   - `tests/rag/test_embedding_providers.py`
5. Documentation alignment:
   - `README.md`
   - `specs/006-v1-3-real-workload-proof/tasks.md`
6. Baseline verification evidence:
   - `docs/reports/dkt-062/verification.log`
   - `docs/reports/dkt-062/release-check-summary.json`
   - `docs/reports/dkt-062/release-check-verification.log`

## Evidence Pointers

- EVIDENCE:benchmark-metrics@docs/reports/dkt-061/benchmark/retrieval-benchmark-metrics.json
- EVIDENCE:benchmark-report@docs/reports/dkt-061/benchmark/retrieval-benchmark-report.md
- EVIDENCE:dkt-062-verification-log@docs/reports/dkt-062/verification.log
- EVIDENCE:dkt-062-release-check-summary@docs/reports/dkt-062/release-check-summary.json
- EVIDENCE:dkt-062-release-check-verification@docs/reports/dkt-062/release-check-verification.log
- EVIDENCE:dkt-062-run-selection@.artifacts/agent_runs/DKT-062_20260213T123613Z_874htwm/selection/default-embedding-selection.json
