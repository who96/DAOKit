from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest

from cli.main import _build_parser, _cmd_run
from daokit.bootstrap import initialize_repository


class StateBackendSelectionCliTests(unittest.TestCase):
    def _run_args(self, root: Path) -> argparse.Namespace:
        parser = _build_parser()
        return parser.parse_args(
            [
                "run",
                "--root",
                str(root),
                "--task-id",
                "DKT-069",
                "--run-id",
                "RUN-SQLITE-CLI",
                "--goal",
                "Validate sqlite backend selection for runtime lifecycle",
                "--no-lease",
            ]
        )

    def test_run_uses_sqlite_backend_when_configured_in_runtime_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initialize_repository(root)
            settings_path = root / "state" / "runtime_settings.json"
            settings_path.write_text(
                json.dumps({"runtime": {"state_backend": "sqlite"}}, indent=2) + "\n",
                encoding="utf-8",
            )

            args = self._run_args(root)
            exit_code = _cmd_run(args)

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "state" / "state.sqlite3").is_file())

            state_payload = json.loads((root / "state" / "pipeline_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state_payload.get("status"), "DONE")
            self.assertEqual(state_payload.get("task_id"), "DKT-069")
            self.assertEqual(state_payload.get("run_id"), "RUN-SQLITE-CLI")


if __name__ == "__main__":
    unittest.main()

