# DKT-061 Retrieval Benchmark Harness and Dataset

## Scope

Deliver a reproducible retrieval benchmark harness and representative dataset for v1.3 P1 embedding backend comparison, with top-k metrics and evidence-linked report artifacts for DKT-062 default-model selection.

## What Was Produced

1. Benchmark harness module and script entrypoint:
   - `src/rag/evaluation/benchmark.py`
   - `scripts/rag/run_retrieval_benchmark.py`
2. Representative benchmark dataset (12 queries, 15 chunks):
   - `src/rag/evaluation/datasets/dkt-061-retrieval-benchmark-v1.json`
3. Benchmark artifacts for this run:
   - `docs/reports/dkt-061/benchmark/retrieval-benchmark-dataset.json`
   - `docs/reports/dkt-061/benchmark/retrieval-benchmark-metrics.json`
   - `docs/reports/dkt-061/benchmark/retrieval-benchmark-report.md`
4. Baseline verification evidence:
   - `docs/reports/dkt-061/verification.log`
   - `docs/reports/dkt-061/release-check-summary.json`
   - `docs/reports/dkt-061/release-check-verification.log`

## Backend Metrics Snapshot (Top-k Quality)

| Rank | Backend | hit@1 | hit@3 | mrr@3 | ndcg@3 |
| --- | --- | --- | --- | --- | --- |
| 1 | `local/token-signature` | 0.083333 | 0.583333 | 0.305556 | 0.349947 |
| 2 | `local/char-trigram` | 0.333333 | 0.333333 | 0.333333 | 0.268858 |

Primary ordering key is `ndcg_at_3` (then `mrr_at_3`, `hit_rate_at_3`, backend id), matching benchmark report logic.

## Evidence Pointers

- EVIDENCE:retrieval-benchmark-dataset@docs/reports/dkt-061/benchmark/retrieval-benchmark-dataset.json
- EVIDENCE:retrieval-benchmark-metrics@docs/reports/dkt-061/benchmark/retrieval-benchmark-metrics.json
- EVIDENCE:retrieval-benchmark-report@docs/reports/dkt-061/benchmark/retrieval-benchmark-report.md
- EVIDENCE:retrieval-benchmark-run-dataset@.artifacts/agent_runs/DKT-061_20260213T122642Z_8z7kr4t/retrieval-benchmark/retrieval-benchmark-dataset.json
- EVIDENCE:retrieval-benchmark-run-metrics@.artifacts/agent_runs/DKT-061_20260213T122642Z_8z7kr4t/retrieval-benchmark/retrieval-benchmark-metrics.json
- EVIDENCE:verification-log@docs/reports/dkt-061/verification.log

## Notes for DKT-062

- Current benchmark evidence ranks `local/token-signature` above `local/char-trigram` by `ndcg_at_3`.
- DKT-062 should combine this quality signal with operational constraints (latency/cost/dependency profile) before final default-model decision.
