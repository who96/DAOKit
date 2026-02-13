from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from reliability.consistency.cross_backend import run_cross_backend_consistency_suite


class CrossBackendConsistencySuiteTests(unittest.TestCase):
    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_suite_reports_equivalent_contract_outputs_for_filesystem_and_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "cross-backend"
            report_json = output_root / "consistency-report.json"
            report_markdown = output_root / "consistency-report.md"

            payload = run_cross_backend_consistency_suite(
                repo_root=self._repo_root(),
                output_root=output_root,
                task_id="DKT-070",
                run_id="RUN-UNITTEST",
                report_json=report_json,
                report_markdown=report_markdown,
            )

            self.assertTrue(payload["passed"], msg=payload)
            self.assertEqual(payload["backends"], ["filesystem", "sqlite"])

            scenarios = payload["scenarios"]
            self.assertEqual({entry["id"] for entry in scenarios}, set(payload["scenario_ids"]))
            for entry in scenarios:
                comparison = entry["comparison"]
                self.assertTrue(
                    comparison["equivalent"],
                    msg=f"scenario {entry['id']} mismatch: {comparison}",
                )

            self.assertTrue(report_json.is_file())
            self.assertTrue(report_markdown.is_file())


if __name__ == "__main__":
    unittest.main()

