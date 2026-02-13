from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from reliability.scenarios.text_input_minimal_flow import run_text_input_minimal_flow


REQUIRED_EVIDENCE_PACKET = (
    "report.md",
    "verification.log",
    "audit-summary.md",
    "events.jsonl",
)


class TextInputMinimalFlowScenarioTests(unittest.TestCase):
    def _assert_complete_evidence_packet(self, payload: dict[str, object]) -> None:
        evidence = payload["evidence"]
        self.assertIsInstance(evidence, dict)
        paths = evidence["paths"]
        self.assertIsInstance(paths, dict)

        required_files = tuple(evidence["required_files"])
        self.assertEqual(required_files, REQUIRED_EVIDENCE_PACKET)

        for file_name in REQUIRED_EVIDENCE_PACKET:
            candidate = Path(str(paths[file_name]))
            self.assertTrue(candidate.is_file(), msg=f"missing evidence file: {candidate}")

        verification_text = Path(str(paths["verification.log"])).read_text(encoding="utf-8")
        self.assertIn("=== COMMAND ENTRY 1 START ===", verification_text)
        self.assertIn("Command:", verification_text)
        self.assertIn("=== COMMAND ENTRY 1 END ===", verification_text)

    def _assert_acceptance_checks(self, payload: dict[str, object]) -> None:
        acceptance = payload["acceptance"]
        self.assertIsInstance(acceptance, dict)

        checks = acceptance["checks"]
        self.assertIsInstance(checks, dict)
        self.assertTrue(checks["process_path_consistent"])
        self.assertTrue(checks["artifact_structure_consistent"])
        self.assertTrue(checks["release_anchor_compatible"])

        process_path = acceptance["process_path"]
        self.assertIsInstance(process_path, dict)
        self.assertEqual(process_path["signature"], process_path["expected_signature"])

        artifact_structure = acceptance["artifact_structure"]
        self.assertIsInstance(artifact_structure, dict)
        self.assertEqual(
            tuple(artifact_structure["required_files"]),
            REQUIRED_EVIDENCE_PACKET,
        )

        release_anchor = acceptance["release_anchor"]
        self.assertIsInstance(release_anchor, dict)
        self.assertEqual(release_anchor["required_paths_missing"], [])
        self.assertTrue(release_anchor["run_evidence_index_header_matches"])

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
            self._assert_complete_evidence_packet(payload)
            self._assert_acceptance_checks(payload)

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
            self._assert_complete_evidence_packet(payload)
            self._assert_acceptance_checks(payload)

    def test_repeated_runs_keep_process_path_and_artifact_structure_signatures_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload_first = run_text_input_minimal_flow(
                repo_root=Path(__file__).resolve().parents[1],
                scenario_root=root / "scenario-first",
                task_input="Implement deterministic evidence checks for minimal scenario",
                task_id="DKT-058",
                run_id="DKT-058_RUN_A",
                env_overrides={
                    "DAOKIT_CODEX_BIN": str(root / "missing-codex-binary"),
                },
            )
            payload_second = run_text_input_minimal_flow(
                repo_root=Path(__file__).resolve().parents[1],
                scenario_root=root / "scenario-second",
                task_input="Implement deterministic evidence checks for minimal scenario",
                task_id="DKT-058",
                run_id="DKT-058_RUN_B",
                env_overrides={
                    "DAOKIT_CODEX_BIN": str(root / "missing-codex-binary"),
                },
            )

            first_acceptance = payload_first["acceptance"]
            second_acceptance = payload_second["acceptance"]

            first_process = first_acceptance["process_path"]
            second_process = second_acceptance["process_path"]
            self.assertEqual(first_process["signature"], second_process["signature"])

            first_artifacts = first_acceptance["artifact_structure"]
            second_artifacts = second_acceptance["artifact_structure"]
            self.assertEqual(first_artifacts["signature"], second_artifacts["signature"])


if __name__ == "__main__":
    unittest.main()
