from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from contracts.acceptance_contracts import (
    AcceptanceDecision,
    CriterionResult,
    FailureReason,
)
from contracts.diagnostics_contracts import (
    CriteriaDiagnosticsReport,
    CriterionDiagnosticEntry,
    CriterionRegistryEntry,
)
from verification.criteria_registry import (
    RELEASE_ACCEPTANCE_CRITERIA,
    RELEASE_CRITERIA_REGISTRY_NAME,
    RELEASE_CRITERIA_REGISTRY_VERSION,
)


REASON_REMEDIATION_HINTS = {
    "MISSING_EVIDENCE": "create missing evidence artifacts and rerun verification",
    "MISSING_COMMAND_EVIDENCE": (
        "add command evidence markers to verification.log "
        "('Command: <cmd>' and/or '=== COMMAND ENTRY N START/END ===')"
    ),
    "OUT_OF_SCOPE_CHANGE": "remove out-of-scope changes and keep only allowed files",
    "INVALID_EVIDENCE_PATH": "keep expected evidence paths inside the evidence root",
    "SCOPE_AUDIT_INPUT_INCOMPLETE": (
        "provide both changed_files and allowed_scope for scope verification"
    ),
    "SCOPE_AUDIT_INPUT_INVALID": "fix scope-audit inputs and rerun acceptance checks",
}


def build_release_diagnostics_report(
    decision: AcceptanceDecision,
    *,
    registry: tuple[CriterionRegistryEntry, ...] = RELEASE_ACCEPTANCE_CRITERIA,
) -> CriteriaDiagnosticsReport:
    criteria_by_id = {item.criterion_id: item for item in decision.proof.criteria}
    criteria_by_text = {_normalize_text(item.criterion): item for item in decision.proof.criteria}
    existing_refs = tuple(
        sorted(item.output_name for item in decision.proof.evidence if item.exists)
    )
    missing_refs = _collect_missing_evidence_refs(decision.failure_reasons)

    mapped: list[CriterionDiagnosticEntry] = []
    for registry_entry in registry:
        criterion_result = _resolve_result(
            registry_entry=registry_entry,
            criteria_by_id=criteria_by_id,
            criteria_by_text=criteria_by_text,
        )
        status = _resolve_status(criterion_result)
        reason_codes = (
            ("UNMAPPED_CRITERION",)
            if criterion_result is None
            else tuple(criterion_result.reason_codes)
        )
        evidence_refs = _resolve_evidence_refs(
            registry_entry=registry_entry,
            criterion_result=criterion_result,
            existing_refs=existing_refs,
            missing_refs=missing_refs,
        )
        remediation_hint = _resolve_remediation_hint(
            registry_entry=registry_entry,
            reason_codes=reason_codes,
        )
        mapped.append(
            CriterionDiagnosticEntry(
                criterion_id=registry_entry.criterion_id,
                criterion=registry_entry.criterion,
                status=status,
                evidence_refs=evidence_refs,
                remediation_hint=remediation_hint,
                reason_codes=reason_codes,
            )
        )

    return CriteriaDiagnosticsReport(
        schema_version=RELEASE_CRITERIA_REGISTRY_VERSION,
        registry_name=RELEASE_CRITERIA_REGISTRY_NAME,
        task_id=decision.proof.task_id,
        run_id=decision.proof.run_id,
        step_id=decision.proof.step_id,
        decision_status=decision.status,
        proof_id=decision.proof.proof_id,
        criteria=tuple(mapped),
    )


def render_criteria_map_json(report: CriteriaDiagnosticsReport) -> str:
    return json.dumps(report.to_dict(), sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def render_criteria_map_markdown(report: CriteriaDiagnosticsReport) -> str:
    lines = [
        "# Criteria Diagnostics Map",
        "",
        f"- Registry: `{report.registry_name}`",
        f"- Schema Version: `{report.schema_version}`",
        f"- Task: `{report.task_id}`",
        f"- Run: `{report.run_id}`",
        f"- Step: `{report.step_id}`",
        f"- Decision Status: `{report.decision_status}`",
        f"- Proof ID: `{report.proof_id}`",
        "",
        "| Criterion ID | Criterion | Status | Evidence Refs | Remediation Hint |",
        "| --- | --- | --- | --- | --- |",
    ]

    for item in report.criteria:
        evidence_text = ", ".join(f"`{ref}`" for ref in item.evidence_refs)
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown(item.criterion_id),
                    _escape_markdown(item.criterion),
                    _escape_markdown(item.status),
                    evidence_text if evidence_text else "`NO_EVIDENCE`",
                    _escape_markdown(item.remediation_hint),
                ]
            )
            + " |"
        )

    lines.append("")
    return "\n".join(lines)


def write_criteria_mapping_outputs(
    report: CriteriaDiagnosticsReport,
    output_dir: str | Path,
) -> dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    json_path = target / "criteria-map.json"
    markdown_path = target / "criteria-map.md"

    json_path.write_text(render_criteria_map_json(report), encoding="utf-8")
    markdown_path.write_text(render_criteria_map_markdown(report), encoding="utf-8")

    return {
        "json": json_path.as_posix(),
        "markdown": markdown_path.as_posix(),
    }


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _resolve_result(
    *,
    registry_entry: CriterionRegistryEntry,
    criteria_by_id: dict[str, CriterionResult],
    criteria_by_text: dict[str, CriterionResult],
) -> CriterionResult | None:
    direct = criteria_by_id.get(registry_entry.criterion_id)
    if direct is not None:
        return direct
    return criteria_by_text.get(_normalize_text(registry_entry.criterion))


def _resolve_status(criterion_result: CriterionResult | None) -> str:
    if criterion_result is None:
        return "missing"
    return "passed" if criterion_result.passed else "failed"


def _collect_missing_evidence_refs(failure_reasons: Iterable[FailureReason]) -> tuple[str, ...]:
    missing: list[str] = []
    for reason in failure_reasons:
        if reason.code != "MISSING_EVIDENCE":
            continue
        missing_output = reason.details.get("missing_output")
        if not isinstance(missing_output, str):
            continue
        marker = f"MISSING:{missing_output}"
        if marker not in missing:
            missing.append(marker)
    return tuple(sorted(missing))


def _resolve_evidence_refs(
    *,
    registry_entry: CriterionRegistryEntry,
    criterion_result: CriterionResult | None,
    existing_refs: tuple[str, ...],
    missing_refs: tuple[str, ...],
) -> tuple[str, ...]:
    resolved: list[str] = []
    for expected in registry_entry.evidence_refs:
        if expected in existing_refs:
            resolved.append(expected)
            continue
        missing_marker = f"MISSING:{expected}"
        if missing_marker in missing_refs:
            resolved.append(missing_marker)

    if criterion_result is not None and "MISSING_EVIDENCE" in criterion_result.reason_codes:
        for marker in missing_refs:
            if marker not in resolved:
                resolved.append(marker)
    if criterion_result is not None and "MISSING_COMMAND_EVIDENCE" in criterion_result.reason_codes:
        if "verification.log" in existing_refs and "verification.log" not in resolved:
            resolved.append("verification.log")

    if not resolved:
        if existing_refs:
            resolved.append(existing_refs[0])
        elif missing_refs:
            resolved.append(missing_refs[0])
        else:
            resolved.append("NO_EVIDENCE")

    unique: list[str] = []
    seen: set[str] = set()
    for item in resolved:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return tuple(unique)


def _resolve_remediation_hint(
    *,
    registry_entry: CriterionRegistryEntry,
    reason_codes: tuple[str, ...],
) -> str:
    for reason_code in reason_codes:
        hint = REASON_REMEDIATION_HINTS.get(reason_code)
        if hint is not None:
            return hint
    if reason_codes == ("UNMAPPED_CRITERION",):
        return (
            "criterion is missing from acceptance output; align acceptance criteria "
            "input with the release criteria registry"
        )
    return registry_entry.remediation_hint


def _escape_markdown(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
