from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from acceptance.engine import AcceptanceEngine
from audit.diff_auditor import audit_changed_files, build_audit_summary


class ScopeGuardTests(unittest.TestCase):
    def test_out_of_scope_edit_causes_rejection(self) -> None:
        result = audit_changed_files(
            changed_files=["src/acceptance/engine.py", "README.md"],
            allowed_scope=["src/audit/", "src/acceptance/", "tests/audit/"],
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.violating_files, ("README.md",))

    def test_in_scope_edits_pass(self) -> None:
        result = audit_changed_files(
            changed_files=["src/acceptance/engine.py", "tests/audit/test_scope_guard.py"],
            allowed_scope=["src/audit/", "src/acceptance/", "tests/audit/"],
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.violating_files, ())

    def test_audit_output_lists_violating_files(self) -> None:
        result = audit_changed_files(
            changed_files=["src/acceptance/engine.py", "docs/notes.md", "README.md"],
            allowed_scope=["src/audit/", "src/acceptance/", "tests/audit/"],
        )

        summary = build_audit_summary(result, task_id="DKT-007", step_id="S1")
        self.assertIn("docs/notes.md", summary)
        self.assertIn("README.md", summary)
        self.assertIn("violating files", summary.lower())


class AcceptanceEngineScopeAuditTests(unittest.TestCase):
    def test_acceptance_engine_rejects_out_of_scope_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "report.md").write_text("# report\n", encoding="utf-8")
            (root / "audit-summary.md").write_text("# audit\n", encoding="utf-8")
            (root / "verification.log").write_text(
                "=== COMMAND ENTRY 1 START ===\n"
                "Command: make test-audit\n"
                "Exit Code: 0\n"
                "=== COMMAND ENTRY 1 END ===\n",
                encoding="utf-8",
            )

            engine = AcceptanceEngine()
            decision = engine.evaluate_step(
                task_id="DKT-007",
                run_id="DKT-007_RUN",
                step_id="S1",
                acceptance_criteria=[
                    "Out-of-scope edit causes rejection",
                    "In-scope edits pass",
                    "Audit output lists violating files",
                ],
                expected_outputs=["report.md", "verification.log", "audit-summary.md"],
                evidence_root=root,
                changed_files=["src/acceptance/engine.py", "README.md"],
                allowed_scope=["src/audit/", "src/acceptance/", "tests/audit/"],
            ).to_dict()

            self.assertEqual(decision["status"], "failed")
            out_of_scope = [
                reason
                for reason in decision["failure_reasons"]
                if reason["code"] == "OUT_OF_SCOPE_CHANGE"
            ]
            self.assertEqual(len(out_of_scope), 1)
            self.assertEqual(
                out_of_scope[0]["details"]["violating_files"],
                ["README.md"],
            )


if __name__ == "__main__":
    unittest.main()
