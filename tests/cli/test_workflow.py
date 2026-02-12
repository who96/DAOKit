from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CliWorkflowTests(unittest.TestCase):
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

    def test_end_to_end_cli_only_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_cli("init", "--root", str(root))

            run = self._run_cli(
                "run",
                "--root",
                str(root),
                "--task-id",
                "DKT-016",
                "--run-id",
                "RUN-CLI-E2E",
                "--goal",
                "Exercise CLI only workflow",
            )
            self.assertIn("status=DONE", run.stdout)

            status = self._run_cli(
                "status",
                "--root",
                str(root),
                "--task-id",
                "DKT-016",
                "--run-id",
                "RUN-CLI-E2E",
                "--json",
            )
            status_payload = json.loads(status.stdout)
            self.assertEqual(status_payload["pipeline_state"]["status"], "DONE")

            handoff = self._run_cli("handoff", "--root", str(root), "--create")
            handoff_payload = json.loads(handoff.stdout)
            self.assertEqual(handoff_payload["task_id"], "DKT-016")

            replay = self._run_cli("replay", "--root", str(root), "--limit", "5")
            self.assertIn("SYSTEM", replay.stdout)

            check = self._run_cli("check", "--root", str(root))
            self.assertIn("Health check: PASS", check.stdout)

    def test_takeover_recovers_from_forced_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_cli("init", "--root", str(root))

            interrupted = self._run_cli(
                "run",
                "--root",
                str(root),
                "--task-id",
                "DKT-016",
                "--run-id",
                "RUN-CLI-INT",
                "--goal",
                "Simulate interruption",
                "--simulate-interruption",
                expected_code=130,
            )
            self.assertIn("simulated interruption", interrupted.stderr.lower())

            takeover = self._run_cli(
                "takeover",
                "--root",
                str(root),
                "--task-id",
                "DKT-016",
                "--run-id",
                "RUN-CLI-INT",
                "--successor-thread-id",
                "thread-recover",
            )
            takeover_payload = json.loads(takeover.stdout)
            self.assertGreaterEqual(len(takeover_payload["adopted_step_ids"]), 1)

            status = self._run_cli(
                "status",
                "--root",
                str(root),
                "--task-id",
                "DKT-016",
                "--run-id",
                "RUN-CLI-INT",
                "--json",
            )
            status_payload = json.loads(status.stdout)
            self.assertEqual(
                status_payload["pipeline_state"]["succession"]["last_takeover_at"] is not None,
                True,
            )

    def test_check_fails_with_diagnostic_when_state_is_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_cli("init", "--root", str(root))

            pipeline_state = root / "state" / "pipeline_state.json"
            pipeline_state.write_text("{invalid-json", encoding="utf-8")

            failed = self._run_cli("check", "--root", str(root), expected_code=1)
            self.assertIn("E_CHECK_STATE_INVALID", failed.stderr)


if __name__ == "__main__":
    unittest.main()
