from __future__ import annotations

from pathlib import Path
import unittest


ROOT_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT_DIR / "docs" / "reports"
FINAL_RUN_DIR = REPORTS_DIR / "final-run"

REQUIRED_FINAL_RUN_PATHS = (
    FINAL_RUN_DIR / "pre_batch_results.tsv",
    FINAL_RUN_DIR / "batch_results.tsv",
    FINAL_RUN_DIR / "batch_resume_from_dkt003_results.tsv",
    FINAL_RUN_DIR / "run_evidence_index.tsv",
    FINAL_RUN_DIR / "run_evidence_index.md",
    FINAL_RUN_DIR / "evidence_manifest.sha256",
    FINAL_RUN_DIR / "evidence",
    FINAL_RUN_DIR / "RELEASE_SNAPSHOT.md",
)

REQUIRED_INDEX_COLUMNS = (
    "task_id",
    "run_id",
    "ledger_source",
    "execution_track",
    "evidence_complete",
    "final_assessment",
    "report_md",
    "verification_log",
    "audit_summary",
)


class ReleaseEvidenceAnchorTests(unittest.TestCase):
    def test_final_acceptance_mentions_v1_rc1_anchor(self) -> None:
        final_acceptance = REPORTS_DIR / "FINAL_ACCEPTANCE.md"
        text = final_acceptance.read_text(encoding="utf-8")
        self.assertIn("v1.0.0-rc1", text)

    def test_final_run_anchor_paths_exist(self) -> None:
        for required_path in REQUIRED_FINAL_RUN_PATHS:
            self.assertTrue(required_path.exists(), f"missing anchor path: {required_path}")

    def test_run_evidence_index_header_is_stable(self) -> None:
        index_tsv = FINAL_RUN_DIR / "run_evidence_index.tsv"
        header = index_tsv.read_text(encoding="utf-8").splitlines()[0].split("\t")
        self.assertEqual(tuple(header), REQUIRED_INDEX_COLUMNS)


if __name__ == "__main__":
    unittest.main()
