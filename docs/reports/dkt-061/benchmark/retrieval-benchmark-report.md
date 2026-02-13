# DKT-061 Retrieval Benchmark Report

- Task: `DKT-061`
- Run: `DKT-061_20260213T122642Z_8z7kr4t`
- Dataset: `dkt-061-retrieval-benchmark-v1`
- Query count: `12`
- Chunk count: `15`
- Top-k thresholds: `1, 3, 5`

## Evidence Pointers
- EVIDENCE:retrieval-benchmark-dataset@docs/reports/dkt-061/benchmark/retrieval-benchmark-dataset.json
- EVIDENCE:retrieval-benchmark-metrics@docs/reports/dkt-061/benchmark/retrieval-benchmark-metrics.json

## Backend Summary
| Rank | Backend | Provider | Status | hit@1 | hit@3 | mrr@3 | ndcg@3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `local/token-signature` | `local/token-signature` | ok | 0.0833 | 0.5833 | 0.3056 | 0.3499 |
| 2 | `local/char-trigram` | `local/char-trigram` | ok | 0.3333 | 0.3333 | 0.3333 | 0.2689 |

## Decision Support Notes
- Primary ranking key: `ndcg_at_3`.
- Tie-breakers: `mrr_at_3`, then `hit_rate_at_3`, then backend id.
- Use this report and metrics JSON as inputs to DKT-062 default-model selection.
