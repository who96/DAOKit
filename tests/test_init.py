import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from daokit.bootstrap import RepositoryInitError, initialize_repository
from daokit.cli import main


class InitCommandTests(unittest.TestCase):
    def _run_main_with_capture(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_initialize_repository_creates_required_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = initialize_repository(root)

            expected_dirs = [
                "src",
                "contracts",
                "state",
                "artifacts",
                "docs",
                "tests",
                "examples",
            ]
            for name in expected_dirs:
                self.assertTrue((root / name).is_dir(), f"missing directory: {name}")

            json_state_files = [
                "pipeline_state.json",
                "heartbeat_status.json",
                "process_leases.json",
            ]
            for name in json_state_files:
                path = root / "state" / name
                self.assertTrue(path.is_file(), f"missing state file: {name}")
                json.loads(path.read_text(encoding="utf-8"))

            events_path = root / "state" / "events.jsonl"
            self.assertTrue(events_path.is_file(), "missing state file: events.jsonl")
            self.assertIn("state/pipeline_state.json", result.created)

    def test_initialize_repository_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked_files = [
                root / "state" / "pipeline_state.json",
                root / "state" / "heartbeat_status.json",
                root / "state" / "process_leases.json",
                root / "state" / "events.jsonl",
            ]

            initialize_repository(root)
            sentinels = {}
            for path in tracked_files:
                value = f"{path.name}-sentinel\n"
                path.write_text(value, encoding="utf-8")
                sentinels[path] = value

            second = initialize_repository(root)

            for path, value in sentinels.items():
                self.assertEqual(path.read_text(encoding="utf-8"), value)
            self.assertIn("state/events.jsonl", second.skipped)
            self.assertIn("state/heartbeat_status.json", second.skipped)
            self.assertIn("state/pipeline_state.json", second.skipped)
            self.assertIn("state/process_leases.json", second.skipped)

    def test_initialize_repository_rejects_directory_path_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").write_text("occupied", encoding="utf-8")

            with self.assertRaises(RepositoryInitError):
                initialize_repository(root)

    def test_initialize_repository_rejects_state_file_path_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir(parents=True, exist_ok=True)
            (root / "state" / "pipeline_state.json").mkdir()

            with self.assertRaises(RepositoryInitError):
                initialize_repository(root)

    def test_cli_init_supports_custom_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = self._run_main_with_capture(["init", "--root", tmp])
            self.assertEqual(code, 0)
            self.assertIn("Initialized DAOKit skeleton", stdout)
            self.assertEqual(stderr, "")
            self.assertTrue((Path(tmp) / "state" / "events.jsonl").is_file())

    def test_cli_init_returns_error_for_invalid_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_file = Path(tmp) / "root-file"
            root_file.write_text("not-a-directory", encoding="utf-8")

            code, stdout, stderr = self._run_main_with_capture(["init", "--root", str(root_file)])

            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("Initialization failed:", stderr)
            self.assertNotIn("Initialized DAOKit skeleton", stderr)

    def test_cli_init_returns_error_when_required_directory_is_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").write_text("occupied", encoding="utf-8")

            code, stdout, stderr = self._run_main_with_capture(["init", "--root", str(root)])

            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("expected directory", stderr)

    def test_cli_init_returns_error_when_state_file_path_is_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir(parents=True, exist_ok=True)
            (root / "state" / "pipeline_state.json").mkdir()

            code, stdout, stderr = self._run_main_with_capture(["init", "--root", str(root)])

            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("expected file", stderr)


if __name__ == "__main__":
    unittest.main()
