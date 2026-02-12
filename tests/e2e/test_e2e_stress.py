from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class EndToEndStressTests(unittest.TestCase):
    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_stress_scenario_covers_recovery_takeover_rework_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = Path(tmp) / "scenario"
            summary_path = Path(tmp) / "summary.json"

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/chaos/e2e_stress_hardening.py",
                    "--scenario-root",
                    str(scenario_root),
                    "--output-json",
                    str(summary_path),
                ],
                cwd=self._repo_root(),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                proc.returncode,
                0,
                msg=f"scenario script failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertTrue(summary_path.is_file())

            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            checks = payload["checks"]

            self.assertEqual(payload["task_id"], "DKT-017")
            self.assertEqual(payload["run_id"], "RUN-E2E-STRESS")
            self.assertEqual(payload["final_state"]["status"], "DONE")
            self.assertGreaterEqual(payload["event_count"], 1)

            self.assertTrue(checks["recovered_without_manual_json_repair"])
            self.assertTrue(checks["rework_loop_executed"])
            self.assertTrue(checks["succession_takeover_executed"])
            self.assertTrue(checks["forced_stale_interval_2h_plus"])
            self.assertTrue(checks["deduplicated_stale_event"])
            self.assertTrue(checks["completed_step_links_valid_evidence"])
            self.assertTrue(checks["final_state_event_log_consistent_replayable"])

            self.assertEqual(payload["rework"]["first_status"], "failed")
            self.assertEqual(payload["rework"]["second_status"], "passed")
            self.assertGreaterEqual(len(payload["command_log"]), 5)
            self.assertEqual(payload["replay_count"], payload["event_count"])


if __name__ == "__main__":
    unittest.main()
