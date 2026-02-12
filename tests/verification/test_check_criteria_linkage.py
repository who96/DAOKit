from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CheckCriteriaLinkageScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.script_path = self.repo_root / "scripts" / "check_criteria_linkage.py"

    def _run_script(self, criteria_map: Path, summary_json: Path) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        return subprocess.run(
            [
                sys.executable,
                self.script_path.as_posix(),
                "--criteria-map",
                criteria_map.as_posix(),
                "--summary-json",
                summary_json.as_posix(),
            ],
            cwd=self.repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def _base_payload(self) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "registry_name": "release-acceptance-v1.1",
            "task_id": "DKT-042",
            "run_id": "DKT-042_RUN",
            "step_id": "S1",
            "decision_status": "passed",
            "proof_id": "proof-criteria-linkage",
            "criteria": [
                {
                    "criterion_id": "RC-RC-001",
                    "criterion": "make release-check is first-class and reproducible.",
                    "status": "passed",
                    "evidence_refs": [
                        "EVIDENCE:verification.log@.artifacts/release-check/verification.log"
                    ],
                    "remediation_hint": "n/a",
                    "reason_codes": [],
                }
            ],
        }

    def test_script_passes_for_valid_pointer_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            criteria_map = tmpdir / "criteria-map.json"
            summary_json = tmpdir / "summary.json"
            criteria_map.write_text(
                json.dumps(self._base_payload(), indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )

            completed = self._run_script(criteria_map, summary_json)

            self.assertEqual(completed.returncode, 0)
            self.assertIn("[PASS] criteria linkage check passed", completed.stdout)
            payload = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(payload["issue_count"], 0)

    def test_script_fails_for_invalid_pointer_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            criteria_map = tmpdir / "criteria-map.json"
            summary_json = tmpdir / "summary.json"
            payload = self._base_payload()
            criteria_entry = payload["criteria"][0]
            if isinstance(criteria_entry, dict):
                criteria_entry["evidence_refs"] = ["verification.log"]
            criteria_map.write_text(
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )

            completed = self._run_script(criteria_map, summary_json)

            self.assertEqual(completed.returncode, 2)
            self.assertIn("[FAIL] criteria linkage check failed", completed.stdout)
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertGreater(summary["issue_count"], 0)


if __name__ == "__main__":
    unittest.main()
