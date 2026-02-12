import json
import tempfile
import unittest
from pathlib import Path

from cli.release_check import CommandResult, run_release_check


class ReleaseCheckTests(unittest.TestCase):
    def test_run_release_check_writes_markerized_log_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            verification_log = root / "verification.log"
            summary_json = root / "summary.json"
            working_directory = root / "workspace"
            working_directory.mkdir(parents=True, exist_ok=True)

            observed_commands: list[str] = []
            canned = {
                "make lint": CommandResult(exit_code=0, output="lint ok\n"),
                "make test": CommandResult(exit_code=0, output="test ok\n"),
            }

            def fake_runner(command: str, cwd: Path) -> CommandResult:
                self.assertEqual(cwd, working_directory)
                observed_commands.append(command)
                return canned[command]

            exit_code = run_release_check(
                commands=("make lint", "make test"),
                verification_log=verification_log,
                summary_json=summary_json,
                working_directory=working_directory,
                runner=fake_runner,
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(observed_commands, ["make lint", "make test"])

            verification_text = verification_log.read_text(encoding="utf-8")
            self.assertIn("=== COMMAND ENTRY 1 START ===", verification_text)
            self.assertIn("Command: make lint", verification_text)
            self.assertIn("=== COMMAND ENTRY 2 START ===", verification_text)
            self.assertIn("Command: make test", verification_text)
            self.assertIn("=== COMMAND ENTRY 2 END ===", verification_text)

            summary = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(summary["deterministic_sequence"], ["make lint", "make test"])
            self.assertEqual(summary["commands"][0]["command"], "make lint")
            self.assertEqual(summary["commands"][0]["exit_code"], 0)
            self.assertEqual(summary["commands"][1]["command"], "make test")
            self.assertEqual(summary["commands"][1]["exit_code"], 0)

    def test_run_release_check_fails_fast_after_first_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            verification_log = root / "verification.log"
            summary_json = root / "summary.json"
            working_directory = root / "workspace"
            working_directory.mkdir(parents=True, exist_ok=True)

            observed_commands: list[str] = []
            canned = {
                "make lint": CommandResult(exit_code=2, output="lint failed\n"),
                "make test": CommandResult(exit_code=0, output="test ok\n"),
            }

            def fake_runner(command: str, cwd: Path) -> CommandResult:
                self.assertEqual(cwd, working_directory)
                observed_commands.append(command)
                return canned[command]

            exit_code = run_release_check(
                commands=("make lint", "make test"),
                verification_log=verification_log,
                summary_json=summary_json,
                working_directory=working_directory,
                runner=fake_runner,
            )

            self.assertEqual(exit_code, 2)
            self.assertEqual(observed_commands, ["make lint"])

            summary = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["failed_command"], "make lint")
            self.assertEqual(len(summary["commands"]), 1)


if __name__ == "__main__":
    unittest.main()
