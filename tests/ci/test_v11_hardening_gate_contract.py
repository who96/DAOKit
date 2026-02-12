from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "v11-hardening-gate.yml"
RUNBOOK_PATH = (
    REPO_ROOT / "docs" / "workflows" / "release-check-evidence-troubleshooting.en.md"
)
CODEX_RUNBOOK_EN_PATH = REPO_ROOT / "docs" / "workflows" / "codex-integration-runbook.en.md"
CODEX_RUNBOOK_ZH_PATH = (
    REPO_ROOT / "docs" / "workflows" / "codex-integration-runbook.zh-CN.md"
)


class V11HardeningGateContractTests(unittest.TestCase):
    def test_makefile_exposes_hardening_gate_targets(self) -> None:
        text = MAKEFILE_PATH.read_text(encoding="utf-8")
        required_phrases = (
            "CRITERIA_LINKAGE_SUMMARY ?= .artifacts/release-check/criteria-linkage-check.json",
            "gate-release-check: release-check",
            "gate-criteria-linkage:",
            "gate-template-checks:",
            "ci-hardening-gate: gate-release-check gate-criteria-linkage gate-template-checks",
        )
        for phrase in required_phrases:
            self.assertIn(phrase, text)

    def test_workflow_runs_criterion_mapped_gate_order(self) -> None:
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        required_phrases = (
            "RC-RC-001 Release-check baseline gate",
            "run: make gate-release-check",
            "RC-DIAG-001 Criteria linkage diagnostics gate",
            "run: make gate-criteria-linkage",
            "RC-TPL-001 Template verification gate",
            "run: make gate-template-checks",
            "Upload hardening gate evidence",
            ".artifacts/release-check/verification.log",
            ".artifacts/release-check/criteria-linkage-check.json",
            "docs/reports/criteria-map.json",
        )
        for phrase in required_phrases:
            self.assertIn(phrase, text)

        first = text.find("RC-RC-001 Release-check baseline gate")
        second = text.find("RC-DIAG-001 Criteria linkage diagnostics gate")
        third = text.find("RC-TPL-001 Template verification gate")
        self.assertTrue(first < second < third, "criterion gate order must be deterministic")

    def test_release_check_runbook_matches_ci_gate_sequence(self) -> None:
        text = RUNBOOK_PATH.read_text(encoding="utf-8")
        required_phrases = (
            "CI-Aligned Hardening Gate Order",
            "make gate-release-check",
            "make gate-criteria-linkage",
            "make gate-template-checks",
            "make ci-hardening-gate",
            "RC-RC-001",
            "RC-DIAG-001",
            "RC-TPL-001",
            ".artifacts/release-check/verification.log",
            ".artifacts/release-check/criteria-linkage-check.json",
        )
        for phrase in required_phrases:
            self.assertIn(phrase, text)

    def test_codex_integration_runbooks_reference_hardening_gate(self) -> None:
        en_text = CODEX_RUNBOOK_EN_PATH.read_text(encoding="utf-8")
        zh_text = CODEX_RUNBOOK_ZH_PATH.read_text(encoding="utf-8")

        self.assertIn("make ci-hardening-gate", en_text)
        self.assertIn("gate-release-check", en_text)
        self.assertIn("gate-criteria-linkage", en_text)
        self.assertIn("gate-template-checks", en_text)
        self.assertIn("make ci-hardening-gate", zh_text)
        self.assertIn("gate-release-check", zh_text)
        self.assertIn("gate-criteria-linkage", zh_text)
        self.assertIn("gate-template-checks", zh_text)


if __name__ == "__main__":
    unittest.main()
