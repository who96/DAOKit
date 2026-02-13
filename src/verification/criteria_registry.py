from __future__ import annotations

from contracts.diagnostics_contracts import CriterionRegistryEntry


RELEASE_CRITERIA_REGISTRY_NAME = "release-acceptance-v1.1"
RELEASE_CRITERIA_REGISTRY_VERSION = "1.0.0"

RELEASE_ACCEPTANCE_CRITERIA: tuple[CriterionRegistryEntry, ...] = (
    CriterionRegistryEntry(
        criterion_id="RC-RC-001",
        criterion="make release-check is first-class and reproducible.",
        evidence_refs=("verification.log",),
        remediation_hint=(
            "define a deterministic release-check flow and retain command evidence markers"
        ),
    ),
    CriterionRegistryEntry(
        criterion_id="RC-DIAG-001",
        criterion="Criterion mapping diagnostics are explicit and artifact-linked.",
        evidence_refs=("criteria-map.json", "criteria-map.md"),
        remediation_hint=(
            "regenerate criteria diagnostics so every criterion has status and evidence pointers"
        ),
    ),
    CriterionRegistryEntry(
        criterion_id="RC-BUNDLE-001",
        criterion="CLI bundle generation and re-verification are documented and operable.",
        evidence_refs=("report.md", "verification.log"),
        remediation_hint=(
            "validate bundle generation and re-verification flow with deterministic evidence"
        ),
    ),
    CriterionRegistryEntry(
        criterion_id="RC-TPL-001",
        criterion="Tool adapter and skill manifest templates exist with verification checklists.",
        evidence_refs=("report.md", "audit-summary.md"),
        remediation_hint=(
            "add or refresh contributor templates and link them to release verification steps"
        ),
    ),
    CriterionRegistryEntry(
        criterion_id="RC-LGO-001",
        criterion="Rollout assets enforce LangGraph-only orchestration and remove legacy path.",
        evidence_refs=("report.md",),
        remediation_hint=(
            "remove legacy-path rollout language and keep LangGraph-only policy explicit"
        ),
    ),
    CriterionRegistryEntry(
        criterion_id="RC-COMP-001",
        criterion="Compatibility guardrails are verified as non-breaking.",
        evidence_refs=("verification.log", "audit-summary.md"),
        remediation_hint=(
            "verify CLI surface, schema semantics, and release anchors remain backward-compatible"
        ),
    ),
    CriterionRegistryEntry(
        criterion_id="RC-REL-001",
        criterion=(
            "Reliability diagnostics and continuity assertions are executed by the "
            "release readiness gate."
        ),
        evidence_refs=("reliability-gate-summary.json", "verification.log"),
        remediation_hint=(
            "add a dedicated reliability gate and verify it is wired into ci-hardening-gate"
        ),
    ),
    CriterionRegistryEntry(
        criterion_id="RC-REL-002",
        criterion="Reliability coverage and continuity outputs are included in the release evidence.",
        evidence_refs=("reliability-gate-summary.json", "verification.log"),
        remediation_hint=(
            "emit machine-readable reliability-gate evidence and include it in task reports"
        ),
    ),
)
