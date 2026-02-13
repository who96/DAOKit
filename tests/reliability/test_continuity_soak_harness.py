from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from reliability.scenarios.integrated_reliability import run_long_run_soak_harness


class ContinuitySoakHarnessTests(unittest.TestCase):
    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_long_run_soak_harness_persists_assertions_and_release_gate_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            soak_root = Path(tmp) / "soak"

            payload = run_long_run_soak_harness(
                repo_root=self._repo_root(),
                soak_root=soak_root,
                iterations=2,
                scenario_ids=("stale-takeover-handoff-resume",),
            )

            self.assertEqual(payload["task_id"], "DKT-052")
            self.assertEqual(payload["iterations"], 2)
            self.assertEqual(payload["scenario_ids"], ["stale-takeover-handoff-resume"])

            checks = payload["checks"]
            self.assertTrue(checks["continuity_assertions_all_passed"])
            self.assertTrue(checks["takeover_handoff_replay_consistent"])
            self.assertTrue(checks["deterministic_checkpoint_hashes"])
            self.assertTrue(checks["bounded_variance"])

            release_gate = payload["release_gate"]
            self.assertEqual(release_gate["status"], "PASS")
            self.assertTrue(release_gate["eligible"])

            outputs = payload["assertion_outputs"]
            for path in outputs.values():
                self.assertTrue(Path(path).is_file(), msg=f"expected output file missing: {path}")

            persisted = json.loads(Path(outputs["json"]).read_text(encoding="utf-8"))
            self.assertEqual(persisted["task_id"], "DKT-052")
            self.assertEqual(persisted["checks"], payload["checks"])
            self.assertEqual(persisted["release_gate"], payload["release_gate"])

            self.assertGreaterEqual(len(payload["checkpoints"]), 2)
            for checkpoint in payload["checkpoints"]:
                self.assertIn("checkpoint_hash", checkpoint)
                self.assertIn("continuity_assertion_results", checkpoint)


if __name__ == "__main__":
    unittest.main()
