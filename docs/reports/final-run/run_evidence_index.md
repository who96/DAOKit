# Final Run Evidence Index

This index maps DKT-001 through DKT-018 to run IDs, ledger source, execution track status, and evidence completeness.

| Task | Run ID | Ledger Source | Execution Track | Evidence Trio | Final Assessment |
| --- | --- | --- | --- | --- | --- |
| DKT-001 | DKT-001_20260211T123153Z_r813113 | pre_batch_results.tsv | PRE_BATCH_COMPLETED | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-002 | DKT-002_20260211T124625Z_367c80d | batch_results.tsv | INITIAL_BATCH_FAILED | PASS (`report.md` / `verification.log` / `audit-summary.md`) | RECOVERED_ACCEPTED_WITH_EVIDENCE |
| DKT-003 | DKT-003_20260211T134056Z_ac778e9 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-004 | DKT-004_20260211T135013Z_657160f | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-005 | DKT-005_20260211T140915Z_e31fe5b | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-006 | DKT-006_20260211T141832Z_9507e94 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-007 | DKT-007_20260211T143434Z_67473c3 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-008 | DKT-008_20260211T144436Z_5f3293f | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-009 | DKT-009_20260211T145323Z_1dd8969 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-010 | DKT-010_20260211T150225Z_7c3db79 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-011 | DKT-011_20260211T151141Z_fe1044c | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-012 | DKT-012_20260211T152043Z_074a9b0 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-013 | DKT-013_20260211T152730Z_ba087a7 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-014 | DKT-014_20260211T153647Z_b3257c4 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-015 | DKT-015_20260211T155119Z_843a887 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-016 | DKT-016_20260211T160336Z_22ef426 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-017 | DKT-017_20260211T161523Z_cdc83ef | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |
| DKT-018 | DKT-018_20260211T162409Z_e01c993 | batch_resume_from_dkt003_results.tsv | RESUME_BATCH_SUCCESS | PASS (`report.md` / `verification.log` / `audit-summary.md`) | ACCEPTED |

## Notes
- `INITIAL_BATCH_FAILED` means the first batch ledger failed for that task.
- `RECOVERED_ACCEPTED_WITH_EVIDENCE` means artifacts prove completion despite initial batch failure status.
- Artifact paths in the TSV are repository-relative and reference local runtime outputs under `.artifacts/`.

## Paths
- `docs/reports/final-run/pre_batch_results.tsv`
- `docs/reports/final-run/batch_results.tsv`
- `docs/reports/final-run/batch_resume_from_dkt003_results.tsv`
- `docs/reports/final-run/run_evidence_index.tsv`
