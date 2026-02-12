from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from contracts.acceptance_contracts import (
    AcceptanceDecision,
    CriterionResult,
    EvidenceRecord,
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
    "MISSING_EVIDENCE_POINTER": (
        "restore missing evidence pointers and rerun release-check diagnostics"
    ),
    "BROKEN_EVIDENCE_POINTER": (
        "repair broken evidence pointers so they resolve inside the evidence root"
    ),
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

POINTER_PRESENT = "EVIDENCE"
POINTER_MISSING = "MISSING"
POINTER_BROKEN = "BROKEN"
POINTER_UNRESOLVED = "UNRESOLVED"
POINTER_STATES = {POINTER_PRESENT, POINTER_MISSING, POINTER_BROKEN, POINTER_UNRESOLVED}


def build_release_diagnostics_report(
    decision: AcceptanceDecision,
    *,
    registry: tuple[CriterionRegistryEntry, ...] = RELEASE_ACCEPTANCE_CRITERIA,
) -> CriteriaDiagnosticsReport:
    criteria_by_id = {item.criterion_id: item for item in decision.proof.criteria}
    criteria_by_text = {_normalize_text(item.criterion): item for item in decision.proof.criteria}
    evidence_by_output = _index_evidence_by_output(decision.proof.evidence)
    missing_outputs = _collect_missing_evidence_outputs(decision.failure_reasons)
    invalid_paths_by_output = _collect_invalid_evidence_paths(decision.failure_reasons)

    mapped: list[CriterionDiagnosticEntry] = []
    for registry_entry in registry:
        criterion_result = _resolve_result(
            registry_entry=registry_entry,
            criteria_by_id=criteria_by_id,
            criteria_by_text=criteria_by_text,
        )
        base_reason_codes = (
            ("UNMAPPED_CRITERION",)
            if criterion_result is None
            else tuple(criterion_result.reason_codes)
        )
        evidence_refs, pointer_reason_codes = _resolve_evidence_pointers(
            registry_entry=registry_entry,
            evidence_by_output=evidence_by_output,
            missing_outputs=missing_outputs,
            invalid_paths_by_output=invalid_paths_by_output,
        )
        reason_codes = _merge_reason_codes(
            base_reason_codes,
            () if criterion_result is None else pointer_reason_codes,
        )
        status = _resolve_status(
            criterion_result=criterion_result,
            pointer_reason_codes=() if criterion_result is None else pointer_reason_codes,
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


def check_evidence_pointer_consistency(
    report: CriteriaDiagnosticsReport,
) -> tuple[str, ...]:
    issues: list[str] = []
    for entry in report.criteria:
        if not entry.evidence_refs:
            issues.append(f"{entry.criterion_id}:missing_evidence_pointer")
            continue

        has_non_present_pointer = False
        for pointer in entry.evidence_refs:
            pointer_state = _pointer_state(pointer)
            if pointer_state is None:
                issues.append(f"{entry.criterion_id}:invalid_pointer_format:{pointer}")
                continue
            if pointer_state != POINTER_PRESENT:
                has_non_present_pointer = True
        if entry.status == "passed" and has_non_present_pointer:
            issues.append(
                f"{entry.criterion_id}:passed_with_non_present_pointer"
            )

    return tuple(issues)


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


def _resolve_status(
    *,
    criterion_result: CriterionResult | None,
    pointer_reason_codes: tuple[str, ...],
) -> str:
    if criterion_result is None:
        return "missing"
    if not criterion_result.passed:
        return "failed"
    if pointer_reason_codes:
        return "failed"
    return "passed"


def _index_evidence_by_output(
    evidence_records: Iterable[EvidenceRecord],
) -> dict[str, tuple[EvidenceRecord, ...]]:
    indexed: dict[str, list[EvidenceRecord]] = {}
    for record in evidence_records:
        indexed.setdefault(record.output_name, []).append(record)
    return {
        output_name: tuple(
            sorted(
                records,
                key=lambda item: (0 if item.exists else 1, _normalize_path(item.path)),
            )
        )
        for output_name, records in indexed.items()
    }


def _collect_missing_evidence_outputs(
    failure_reasons: Iterable[FailureReason],
) -> tuple[str, ...]:
    missing: list[str] = []
    for reason in failure_reasons:
        if reason.code != "MISSING_EVIDENCE":
            continue
        missing_output = reason.details.get("missing_output")
        if not isinstance(missing_output, str):
            continue
        if missing_output not in missing:
            missing.append(missing_output)
    return tuple(sorted(missing))


def _collect_invalid_evidence_paths(
    failure_reasons: Iterable[FailureReason],
) -> dict[str, tuple[str, ...]]:
    invalid: dict[str, list[str]] = {}
    for reason in failure_reasons:
        if reason.code != "INVALID_EVIDENCE_PATH":
            continue
        output_name = reason.details.get("output_name")
        raw_path = reason.details.get("path")
        if not isinstance(output_name, str):
            continue
        if isinstance(raw_path, str) and raw_path.strip():
            invalid.setdefault(output_name, []).append(_normalize_path(raw_path))
        else:
            invalid.setdefault(output_name, [])
    return {
        output_name: tuple(sorted(set(paths)))
        for output_name, paths in invalid.items()
    }


def _resolve_evidence_pointers(
    *,
    registry_entry: CriterionRegistryEntry,
    evidence_by_output: dict[str, tuple[EvidenceRecord, ...]],
    missing_outputs: tuple[str, ...],
    invalid_paths_by_output: dict[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    resolved: list[str] = []
    pointer_reason_codes: list[str] = []
    missing_set = set(missing_outputs)

    for expected in registry_entry.evidence_refs:
        evidence_records = evidence_by_output.get(expected, ())
        present_paths = tuple(
            _normalize_path(item.path) for item in evidence_records if item.exists
        )
        declared_paths = tuple(_normalize_path(item.path) for item in evidence_records)
        invalid_paths = invalid_paths_by_output.get(expected, ())

        if present_paths:
            for path in present_paths:
                resolved.append(_format_pointer(POINTER_PRESENT, expected, path))
            continue

        if invalid_paths:
            for path in invalid_paths:
                resolved.append(_format_pointer(POINTER_BROKEN, expected, path))
            pointer_reason_codes.append("BROKEN_EVIDENCE_POINTER")
            continue

        if expected in missing_set or declared_paths:
            path = declared_paths[0] if declared_paths else None
            resolved.append(_format_pointer(POINTER_MISSING, expected, path))
            pointer_reason_codes.append("MISSING_EVIDENCE_POINTER")
        else:
            resolved.append(_format_pointer(POINTER_MISSING, expected))
            pointer_reason_codes.append("MISSING_EVIDENCE_POINTER")

    return (_dedupe_preserve_order(resolved), _dedupe_preserve_order(pointer_reason_codes))


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


def _merge_reason_codes(*groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item not in merged:
                merged.append(item)
    return tuple(merged)


def _format_pointer(kind: str, output_name: str, path: str | None = None) -> str:
    if path is None or not path.strip():
        return f"{kind}:{output_name}"
    return f"{kind}:{output_name}@{_normalize_path(path)}"


def _pointer_state(pointer: str) -> str | None:
    prefix, _, _ = pointer.partition(":")
    if prefix in POINTER_STATES:
        return prefix
    return None


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _dedupe_preserve_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _escape_markdown(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
