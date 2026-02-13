from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from reliability.scenarios.text_input_minimal_flow import run_text_input_minimal_flow


class TextInputMinimalFlowScenarioTests(unittest.TestCase):
    def _write_fake_codex(self, root: Path) -> tuple[Path, Path]:
        log_path = root / "fake-codex.log"
        script_path = root / "fake-codex"
        script_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import os",
                    "import pathlib",
                    "import sys",
                    "",
                    "args = sys.argv[1:]",
                    "log_path = pathlib.Path(os.environ['DAOKIT_FAKE_CODEX_LOG'])",
                    "log_path.write_text(' '.join(args) + '\\n', encoding='utf-8')",
                    "if '--output-last-message' in args:",
                    "    i = args.index('--output-last-message')",
                    "    out_path = pathlib.Path(args[i + 1])",
                    "    out_path.write_text('Implemented by fake codex', encoding='utf-8')",
                    "print('fake codex ok')",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script_path.chmod(0o755)
        return script_path, log_path

    def test_real_dispatch_path_is_invoked_and_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_codex, codex_log = self._write_fake_codex(root)

            payload = run_text_input_minimal_flow(
                repo_root=Path(__file__).resolve().parents[1],
                scenario_root=root / "scenario",
                task_input="Implement minimal parser compatibility guard for verification logs",
                task_id="DKT-057",
                run_id="DKT-057_REAL_LLM",
                env_overrides={
                    "DAOKIT_CODEX_BIN": str(fake_codex),
                    "DAOKIT_FAKE_CODEX_LOG": str(codex_log),
                },
            )

            self.assertEqual(payload["final_state"]["status"], "DONE")
            self.assertGreaterEqual(payload["planner"]["step_count"], 2)
            self.assertLessEqual(payload["planner"]["step_count"], 3)
            self.assertGreaterEqual(payload["dispatch"]["call_count"], 1)
            self.assertTrue(payload["dispatch"]["llm_invoked"])
            self.assertEqual(payload["dispatch"]["execution_mode"], "real_llm")
            self.assertTrue(codex_log.exists())
            self.assertIn("exec", codex_log.read_text(encoding="utf-8"))

    def test_flow_completes_without_external_api_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            payload = run_text_input_minimal_flow(
                repo_root=Path(__file__).resolve().parents[1],
                scenario_root=root / "scenario",
                task_input="Refactor planner to bound step outputs and keep contracts stable",
                task_id="DKT-057",
                run_id="DKT-057_FALLBACK",
                env_overrides={
                    "DAOKIT_CODEX_BIN": str(root / "missing-codex-binary"),
                },
            )

            self.assertEqual(payload["final_state"]["status"], "DONE")
            self.assertGreaterEqual(payload["planner"]["step_count"], 2)
            self.assertLessEqual(payload["planner"]["step_count"], 3)
            self.assertGreaterEqual(payload["dispatch"]["call_count"], 1)
            self.assertFalse(payload["dispatch"]["llm_invoked"])
            self.assertEqual(payload["dispatch"]["execution_mode"], "fallback")


if __name__ == "__main__":
    unittest.main()
