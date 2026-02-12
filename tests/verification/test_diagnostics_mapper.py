from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from contracts.acceptance_contracts import (
    AcceptanceDecision,
    AcceptanceProofRecord,
    CriterionResult,
    EvidenceRecord,
    FailureReason,
)
from verification.criteria_registry import RELEASE_ACCEPTANCE_CRITERIA
from verification.diagnostics_mapper import (
    build_release_diagnostics_report,
    render_criteria_map_json,
    render_criteria_map_markdown,
    write_criteria_mapping_outputs,
)


class DiagnosticsMapperTests(unittest.TestCase):
    def _build_decision(self) -> AcceptanceDecision:
        proof = AcceptanceProofRecord(
            proof_id="proof-1234567890abcdef",
            status="failed",
            task_id="DKT-040",
            run_id="DKT-040_RUN",
            step_id="S1",
            criteria=(
                CriterionResult(
                    criterion_id="AC-001",
                    criterion=RELEASE_ACCEPTANCE_CRITERIA[0].criterion,
                    passed=True,
                    reason_codes=(),
                ),
                CriterionResult(
                    criterion_id="AC-002",
                    criterion=RELEASE_ACCEPTANCE_CRITERIA[1].criterion,
                    passed=False,
                    reason_codes=("MISSING_COMMAND_EVIDENCE",),
                ),
            ),
            evidence=(
                EvidenceRecord(
                    output_name="report.md",
                    path="/evidence/report.md",
                    exists=True,
                    sha256="sha-report",
                    size_bytes=10,
                ),
                EvidenceRecord(
                    output_name="verification.log",
                    path="/evidence/verification.log",
                    exists=True,
                    sha256="sha-verification",
                    size_bytes=11,
                ),
                EvidenceRecord(
                    output_name="audit-summary.md",
                    path="/evidence/audit-summary.md",
                    exists=False,
                    sha256=None,
                    size_bytes=None,
                ),
            ),
        )

        return AcceptanceDecision(
            status="failed",
            proof=proof,
            failure_reasons=(
                FailureReason(
                    code="MISSING_COMMAND_EVIDENCE",
                    message="verification.log missing command markers",
                    details={"path": "/evidence/verification.log"},
                ),
            ),
            rework=None,
        )

    def test_report_covers_every_registry_criterion(self) -> None:
        report = build_release_diagnostics_report(self._build_decision())
        payload = report.to_dict()
        self.assertEqual(payload["schema_version"], "1.0.0")
        self.assertEqual(len(payload["criteria"]), len(RELEASE_ACCEPTANCE_CRITERIA))

        by_id = {entry["criterion_id"]: entry for entry in payload["criteria"]}
        self.assertEqual(by_id["RC-RC-001"]["status"], "passed")
        self.assertEqual(by_id["RC-DIAG-001"]["status"], "failed")
        self.assertEqual(by_id["RC-BUNDLE-001"]["status"], "missing")
        self.assertIn("verification.log", by_id["RC-DIAG-001"]["evidence_refs"])
        self.assertTrue(by_id["RC-DIAG-001"]["remediation_hint"])

    def test_rendering_includes_required_fields(self) -> None:
        report = build_release_diagnostics_report(self._build_decision())
        rendered_json = render_criteria_map_json(report)
        rendered_markdown = render_criteria_map_markdown(report)

        self.assertIn('"criterion_id": "RC-DIAG-001"', rendered_json)
        self.assertIn('"status": "failed"', rendered_json)
        self.assertIn('"evidence_refs"', rendered_json)
        self.assertIn('"remediation_hint"', rendered_json)

        self.assertIn("| Criterion ID |", rendered_markdown)
        self.assertIn("| RC-DIAG-001 |", rendered_markdown)
        self.assertIn("verification.log", rendered_markdown)

    def test_output_files_are_stable_across_repeated_writes(self) -> None:
        report = build_release_diagnostics_report(self._build_decision())
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            first = write_criteria_mapping_outputs(report, output_dir)
            json_first = Path(first["json"]).read_text(encoding="utf-8")
            markdown_first = Path(first["markdown"]).read_text(encoding="utf-8")

            second = write_criteria_mapping_outputs(report, output_dir)
            json_second = Path(second["json"]).read_text(encoding="utf-8")
            markdown_second = Path(second["markdown"]).read_text(encoding="utf-8")

            self.assertEqual(json_first, json_second)
            self.assertEqual(markdown_first, markdown_second)


if __name__ == "__main__":
    unittest.main()
