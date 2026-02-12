from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


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


class BundleWorkflowTests(unittest.TestCase):
    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _run_cli(
        self,
        *args: str,
        expected_code: int | None = 0,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        process = subprocess.run(
            [sys.executable, "-m", "cli", *args],
            cwd=cwd or self._repo_root(),
            env=env,
            capture_output=True,
            text=True,
        )
        if expected_code is not None:
            self.assertEqual(
                process.returncode,
                expected_code,
                msg=(
                    f"command failed: {' '.join(args)}\n"
                    f"stdout:\n{process.stdout}\n"
                    f"stderr:\n{process.stderr}"
                ),
            )
        return process

    def _write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        digest.update(path.read_bytes())
        return digest.hexdigest()

    def _prepare_source_bundle(self, root: Path) -> Path:
        final_run = root / "docs" / "reports" / "final-run"
        self._write_text(final_run / "pre_batch_results.tsv", "task_id\tstatus\nDKT-001\tACCEPTED\n")
        self._write_text(final_run / "batch_results.tsv", "task_id\tstatus\nDKT-002\tACCEPTED\n")
        self._write_text(
            final_run / "batch_resume_from_dkt003_results.tsv",
            "task_id\tstatus\nDKT-003\tACCEPTED\n",
        )
        self._write_text(
            final_run / "run_evidence_index.tsv",
            "\t".join(REQUIRED_INDEX_COLUMNS)
            + "\n"
            + "\t".join(
                [
                    "DKT-041",
                    "DKT-041_RUN",
                    "batch_results.tsv",
                    "MAIN",
                    "true",
                    "ACCEPTED",
                    "docs/reports/final-run/evidence/agent_runs/DKT-041_RUN/reports/DKT-041/report.md",
                    (
                        "docs/reports/final-run/evidence/agent_runs/DKT-041_RUN/"
                        "reports/DKT-041/verification.log"
                    ),
                    (
                        "docs/reports/final-run/evidence/agent_runs/DKT-041_RUN/"
                        "reports/DKT-041/audit-summary.md"
                    ),
                ]
            )
            + "\n",
        )
        self._write_text(final_run / "run_evidence_index.md", "# Evidence Index\n")
        self._write_text(final_run / "RELEASE_SNAPSHOT.md", "# Snapshot\n")

        report_dir = final_run / "evidence" / "agent_runs" / "DKT-041_RUN" / "reports" / "DKT-041"
        self._write_text(report_dir / "report.md", "# Report\n")
        self._write_text(
            report_dir / "verification.log",
            "=== COMMAND ENTRY 1 START ===\nCommand: make lint\nExit Code: 0\n=== COMMAND ENTRY 1 END ===\n",
        )
        self._write_text(report_dir / "audit-summary.md", "# Audit\n")

        manifest_entries: list[str] = []
        for path in sorted(report_dir.iterdir()):
            if not path.is_file():
                continue
            manifest_rel = path.relative_to(root).as_posix()
            manifest_entries.append(f"{self._sha256(path)}  {manifest_rel}")
        self._write_text(final_run / "evidence_manifest.sha256", "\n".join(manifest_entries) + "\n")
        return final_run

    def test_bundle_generate_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_source_bundle(root)

            bundle_root = ".artifacts/evidence-bundles/run1"
            summary_path = root / ".artifacts" / "evidence-bundles" / "run1" / "generate-summary.json"

            first = self._run_cli(
                "bundle",
                "--generate",
                "--root",
                str(root),
                "--source-dir",
                "docs/reports/final-run",
                "--bundle-root",
                bundle_root,
                "--summary-json",
                ".artifacts/evidence-bundles/run1/generate-summary.json",
                "--json",
            )
            second = self._run_cli(
                "bundle",
                "--generate",
                "--root",
                str(root),
                "--source-dir",
                "docs/reports/final-run",
                "--bundle-root",
                bundle_root,
                "--summary-json",
                ".artifacts/evidence-bundles/run1/generate-summary.json",
                "--json",
            )

            self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
            self.assertTrue(summary_path.exists())
            self.assertTrue(
                (
                    root
                    / ".artifacts"
                    / "evidence-bundles"
                    / "run1"
                    / "docs"
                    / "reports"
                    / "final-run"
                    / "run_evidence_index.tsv"
                ).exists()
            )

    def test_bundle_review_and_reverify_pass_for_generated_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_source_bundle(root)
            bundle_root = ".artifacts/evidence-bundles/run2"

            self._run_cli(
                "bundle",
                "--generate",
                "--root",
                str(root),
                "--bundle-root",
                bundle_root,
                "--summary-json",
                ".artifacts/evidence-bundles/run2/generate-summary.json",
            )

            review = self._run_cli(
                "bundle",
                "--review",
                "--root",
                str(root),
                "--bundle-root",
                bundle_root,
                "--summary-json",
                ".artifacts/evidence-bundles/run2/review-summary.json",
                "--json",
            )
            review_payload = json.loads(review.stdout)
            self.assertEqual(review_payload["status"], "passed")
            self.assertEqual(review_payload["manifest_entries"], 3)

            reverify = self._run_cli(
                "bundle",
                "--reverify",
                "--root",
                str(root),
                "--bundle-root",
                bundle_root,
                "--summary-json",
                ".artifacts/evidence-bundles/run2/reverify-summary.json",
                "--json",
            )
            reverify_payload = json.loads(reverify.stdout)
            self.assertEqual(reverify_payload["status"], "passed")
            self.assertEqual(reverify_payload["manifest_entries_checked"], 3)
            self.assertGreaterEqual(reverify_payload["verification_logs_checked"], 1)

    def test_bundle_reverify_detects_manifest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_source_bundle(root)
            bundle_root = root / ".artifacts" / "evidence-bundles" / "run3"

            self._run_cli(
                "bundle",
                "--generate",
                "--root",
                str(root),
                "--bundle-root",
                str(bundle_root),
                "--summary-json",
                str(bundle_root / "generate-summary.json"),
            )

            drift_target = (
                bundle_root
                / "docs"
                / "reports"
                / "final-run"
                / "evidence"
                / "agent_runs"
                / "DKT-041_RUN"
                / "reports"
                / "DKT-041"
                / "report.md"
            )
            drift_target.write_text("# Report\nDrift\n", encoding="utf-8")

            reverify = self._run_cli(
                "bundle",
                "--reverify",
                "--root",
                str(root),
                "--bundle-root",
                str(bundle_root),
                "--summary-json",
                str(bundle_root / "reverify-summary.json"),
                "--json",
                expected_code=2,
            )
            payload = json.loads(reverify.stdout)
            self.assertEqual(payload["status"], "failed")
            self.assertGreaterEqual(len(payload["manifest_mismatches"]), 1)


if __name__ == "__main__":
    unittest.main()
