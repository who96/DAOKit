from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class IntegratedReliabilityE2ETests(unittest.TestCase):
    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_integrated_mode_recovers_from_forced_stale_takeover_handoff_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = Path(tmp) / "scenario"
            summary_path = Path(tmp) / "integrated-summary.json"

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reliability.scenarios.integrated_reliability",
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
                msg=f"scenario command failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertTrue(summary_path.is_file())

            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            checks = payload["checks"]

            self.assertEqual(payload["task_id"], "DKT-036")
            self.assertEqual(payload["run_id"], "RUN-INTEGRATED-RELIABILITY")
            self.assertEqual(payload["resolved_runtime_engine"], "langgraph")
            self.assertEqual(payload["runtime_mode"], "integrated")

            self.assertTrue(checks["forced_stale_condition"])
            self.assertTrue(checks["takeover_and_handoff_applied_during_active_run"])
            self.assertTrue(checks["event_lease_state_consistent"])
            self.assertTrue(checks["status_replay_consistent_after_recovery"])
            self.assertTrue(checks["recovered_without_manual_state_repair"])

            self.assertGreaterEqual(payload["event_count"], 3)
            self.assertEqual(payload["replay_count"], payload["event_count"])
            self.assertEqual(payload["final_state"]["status"], "DONE")


if __name__ == "__main__":
    unittest.main()
