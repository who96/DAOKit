from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from acceptance.engine import AcceptanceEngine


class AcceptanceEngineTests(unittest.TestCase):
    def test_missing_evidence_yields_deterministic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "report.md").write_text("# report\n", encoding="utf-8")

            engine = AcceptanceEngine()
            kwargs = {
                "task_id": "DKT-006",
                "run_id": "DKT-006_RUN",
                "step_id": "S1",
                "acceptance_criteria": [
                    "Missing evidence yields deterministic failure",
                    "Passing steps produce acceptance proof records",
                    "Rework payload references exact failed criteria",
                ],
                "expected_outputs": [
                    "report.md",
                    "verification.log",
                    "audit-summary.md",
                ],
                "evidence_root": root,
            }

            first = engine.evaluate_step(**kwargs).to_dict()
            second = engine.evaluate_step(**kwargs).to_dict()

            self.assertEqual(first, second)
            self.assertEqual(first["status"], "failed")

            missing = [
                entry["details"]["missing_output"]
                for entry in first["failure_reasons"]
                if entry["code"] == "MISSING_EVIDENCE"
            ]
            self.assertEqual(missing, ["verification.log", "audit-summary.md"])

    def test_passing_steps_produce_acceptance_proof_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "report.md").write_text("# report\n", encoding="utf-8")
            (root / "audit-summary.md").write_text("# audit\n", encoding="utf-8")
            (root / "verification.log").write_text(
                "=== COMMAND ENTRY 1 START ===\n"
                "Command: make test-acceptance\n"
                "Exit Code: 0\n"
                "=== COMMAND ENTRY 1 END ===\n",
                encoding="utf-8",
            )

            engine = AcceptanceEngine()
            decision = engine.evaluate_step(
                task_id="DKT-006",
                run_id="DKT-006_RUN",
                step_id="S1",
                acceptance_criteria=[
                    "Missing evidence yields deterministic failure",
                    "Passing steps produce acceptance proof records",
                    "Rework payload references exact failed criteria",
                ],
                expected_outputs=["report.md", "verification.log", "audit-summary.md"],
                evidence_root=root,
            ).to_dict()

            self.assertEqual(decision["status"], "passed")
            self.assertEqual(decision["proof"]["status"], "passed")
            self.assertTrue(decision["proof"]["proof_id"].startswith("proof-"))
            self.assertIsNone(decision["rework"])
            self.assertEqual(decision["failure_reasons"], [])
            self.assertTrue(all(item["passed"] for item in decision["proof"]["criteria"]))

    def test_rework_payload_references_exact_failed_criteria(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "report.md").write_text("# report\n", encoding="utf-8")
            (root / "audit-summary.md").write_text("# audit\n", encoding="utf-8")
            (root / "verification.log").write_text(
                "test output without command markers\n",
                encoding="utf-8",
            )

            engine = AcceptanceEngine()
            decision = engine.evaluate_step(
                task_id="DKT-006",
                run_id="DKT-006_RUN",
                step_id="S1",
                acceptance_criteria=[
                    "verification.log command evidence must include Command: marker",
                    "Passing steps produce acceptance proof records",
                ],
                expected_outputs=["report.md", "verification.log", "audit-summary.md"],
                evidence_root=root,
            ).to_dict()

            self.assertEqual(decision["status"], "failed")
            self.assertIsNotNone(decision["rework"])
            self.assertEqual(decision["rework"]["next_action"], "rework")

            failed = decision["rework"]["failed_criteria"]
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0]["criterion_id"], "AC-001")
            self.assertEqual(
                failed[0]["criterion"],
                "verification.log command evidence must include Command: marker",
            )
            self.assertIn("MISSING_COMMAND_EVIDENCE", failed[0]["reason_codes"])

    def test_expected_output_path_cannot_escape_evidence_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "evidence"
            root.mkdir(parents=True, exist_ok=True)
            (base / "outside.txt").write_text("outside\n", encoding="utf-8")

            engine = AcceptanceEngine()
            decision = engine.evaluate_step(
                task_id="DKT-006",
                run_id="DKT-006_RUN",
                step_id="S1",
                acceptance_criteria=[
                    "Missing evidence yields deterministic failure",
                ],
                expected_outputs=["../outside.txt"],
                evidence_root=root,
            ).to_dict()

            self.assertEqual(decision["status"], "failed")
            self.assertIsNotNone(decision["rework"])
            self.assertEqual(
                decision["failure_reasons"][0]["code"],
                "INVALID_EVIDENCE_PATH",
            )


if __name__ == "__main__":
    unittest.main()
