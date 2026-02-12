from __future__ import annotations

from pathlib import Path
import re
import tempfile
import unittest

from contracts.acceptance_contracts import (
    AcceptanceDecision,
    AcceptanceProofRecord,
    CriterionResult,
    EvidenceRecord,
    FailureReason,
)
from contracts.diagnostics_contracts import (
    CriteriaDiagnosticsReport,
    CriterionDiagnosticEntry,
)
from verification.criteria_registry import RELEASE_ACCEPTANCE_CRITERIA
from verification.diagnostics_mapper import (
    build_release_diagnostics_report,
    check_evidence_pointer_consistency,
    render_criteria_map_json,
    render_criteria_map_markdown,
    write_criteria_mapping_outputs,
)


class DiagnosticsMapperTests(unittest.TestCase):
    POINTER_PATTERN = re.compile(
        r"^(?:EVIDENCE|MISSING|BROKEN|UNRESOLVED):[^@]+(?:@.+)?$"
    )

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
        self.assertIn("MISSING:criteria-map.json", by_id["RC-DIAG-001"]["evidence_refs"])
        self.assertIn("MISSING:criteria-map.md", by_id["RC-DIAG-001"]["evidence_refs"])
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
        self.assertIn("MISSING:criteria-map.json", rendered_markdown)

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

    def test_pointer_conventions_are_machine_parseable(self) -> None:
        report = build_release_diagnostics_report(self._build_decision())
        payload = report.to_dict()

        for entry in payload["criteria"]:
            for pointer in entry["evidence_refs"]:
                self.assertRegex(pointer, self.POINTER_PATTERN)

    def test_missing_pointer_for_passed_criterion_forces_explicit_failure(self) -> None:
        proof = AcceptanceProofRecord(
            proof_id="proof-pointer-missing",
            status="passed",
            task_id="DKT-042",
            run_id="DKT-042_RUN",
            step_id="S1",
            criteria=(
                CriterionResult(
                    criterion_id="RC-RC-001",
                    criterion=RELEASE_ACCEPTANCE_CRITERIA[0].criterion,
                    passed=True,
                    reason_codes=(),
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
            ),
        )
        decision = AcceptanceDecision(
            status="passed",
            proof=proof,
            failure_reasons=(),
            rework=None,
        )

        report = build_release_diagnostics_report(decision)
        payload = report.to_dict()
        by_id = {entry["criterion_id"]: entry for entry in payload["criteria"]}

        self.assertEqual(by_id["RC-RC-001"]["status"], "failed")
        self.assertIn("MISSING_EVIDENCE_POINTER", by_id["RC-RC-001"]["reason_codes"])
        self.assertIn(
            "MISSING:verification.log",
            by_id["RC-RC-001"]["evidence_refs"],
        )

    def test_invalid_pointer_is_marked_as_broken(self) -> None:
        proof = AcceptanceProofRecord(
            proof_id="proof-pointer-broken",
            status="failed",
            task_id="DKT-042",
            run_id="DKT-042_RUN",
            step_id="S1",
            criteria=(
                CriterionResult(
                    criterion_id="RC-RC-001",
                    criterion=RELEASE_ACCEPTANCE_CRITERIA[0].criterion,
                    passed=False,
                    reason_codes=("INVALID_EVIDENCE_PATH",),
                ),
            ),
            evidence=(
                EvidenceRecord(
                    output_name="verification.log",
                    path="/tmp/escape/verification.log",
                    exists=False,
                    sha256=None,
                    size_bytes=None,
                ),
            ),
        )
        decision = AcceptanceDecision(
            status="failed",
            proof=proof,
            failure_reasons=(
                FailureReason(
                    code="INVALID_EVIDENCE_PATH",
                    message="expected output path escapes evidence root and cannot be used as evidence",
                    details={
                        "output_name": "verification.log",
                        "path": "/tmp/escape/verification.log",
                        "evidence_root": "/evidence",
                    },
                ),
            ),
            rework=None,
        )

        report = build_release_diagnostics_report(decision)
        payload = report.to_dict()
        by_id = {entry["criterion_id"]: entry for entry in payload["criteria"]}

        self.assertIn(
            "BROKEN:verification.log@/tmp/escape/verification.log",
            by_id["RC-RC-001"]["evidence_refs"],
        )
        self.assertIn("BROKEN_EVIDENCE_POINTER", by_id["RC-RC-001"]["reason_codes"])

    def test_consistency_check_flags_invalid_pointer_format(self) -> None:
        report = CriteriaDiagnosticsReport(
            schema_version="1.0.0",
            registry_name="release-acceptance-v1.1",
            task_id="DKT-042",
            run_id="DKT-042_RUN",
            step_id="S1",
            decision_status="failed",
            proof_id="proof-invalid-pointer",
            criteria=(
                CriterionDiagnosticEntry(
                    criterion_id="RC-RC-001",
                    criterion=RELEASE_ACCEPTANCE_CRITERIA[0].criterion,
                    status="failed",
                    evidence_refs=("verification.log",),
                    remediation_hint="fix pointer format",
                    reason_codes=("BROKEN_EVIDENCE_POINTER",),
                ),
            ),
        )

        issues = check_evidence_pointer_consistency(report)
        self.assertIn(
            "RC-RC-001:invalid_pointer_format:verification.log",
            issues,
        )

    def test_consistency_check_flags_passed_status_with_missing_pointer(self) -> None:
        report = CriteriaDiagnosticsReport(
            schema_version="1.0.0",
            registry_name="release-acceptance-v1.1",
            task_id="DKT-042",
            run_id="DKT-042_RUN",
            step_id="S1",
            decision_status="failed",
            proof_id="proof-status-mismatch",
            criteria=(
                CriterionDiagnosticEntry(
                    criterion_id="RC-RC-001",
                    criterion=RELEASE_ACCEPTANCE_CRITERIA[0].criterion,
                    status="passed",
                    evidence_refs=("MISSING:verification.log",),
                    remediation_hint="regenerate missing artifact",
                    reason_codes=(),
                ),
            ),
        )

        issues = check_evidence_pointer_consistency(report)
        self.assertIn(
            "RC-RC-001:passed_with_non_present_pointer",
            issues,
        )


if __name__ == "__main__":
    unittest.main()
