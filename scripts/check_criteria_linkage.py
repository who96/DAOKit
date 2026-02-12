#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from contracts.diagnostics_contracts import (
    CriteriaDiagnosticsReport,
    CriterionDiagnosticEntry,
)
from verification.diagnostics_mapper import check_evidence_pointer_consistency


NON_PRESENT_PREFIXES = ("MISSING:", "BROKEN:", "UNRESOLVED:")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-criteria-linkage",
        description=(
            "Validate criteria-map evidence pointer conventions and status linkage."
        ),
    )
    parser.add_argument(
        "--criteria-map",
        default="docs/reports/criteria-map.json",
        help="Path to criteria-map.json",
    )
    parser.add_argument(
        "--summary-json",
        default=".artifacts/release-check/criteria-linkage-check.json",
        help="Path to write machine-readable linkage check summary",
    )
    return parser


def _load_report(path: Path) -> CriteriaDiagnosticsReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_criteria = payload.get("criteria")
    if not isinstance(raw_criteria, list):
        raise ValueError("criteria-map payload must include a list field: criteria")

    criteria: list[CriterionDiagnosticEntry] = []
    for item in raw_criteria:
        if not isinstance(item, dict):
            raise ValueError("criteria-map criteria entries must be objects")
        evidence_refs = item.get("evidence_refs")
        reason_codes = item.get("reason_codes")
        if not isinstance(evidence_refs, list) or not all(
            isinstance(value, str) for value in evidence_refs
        ):
            raise ValueError("criteria entry evidence_refs must be a list of strings")
        if not isinstance(reason_codes, list) or not all(
            isinstance(value, str) for value in reason_codes
        ):
            raise ValueError("criteria entry reason_codes must be a list of strings")
        criteria.append(
            CriterionDiagnosticEntry(
                criterion_id=_require_string(item, "criterion_id"),
                criterion=_require_string(item, "criterion"),
                status=_require_string(item, "status"),
                evidence_refs=tuple(evidence_refs),
                remediation_hint=_require_string(item, "remediation_hint"),
                reason_codes=tuple(reason_codes),
            )
        )

    return CriteriaDiagnosticsReport(
        schema_version=_require_string(payload, "schema_version"),
        registry_name=_require_string(payload, "registry_name"),
        task_id=_require_string(payload, "task_id"),
        run_id=_require_string(payload, "run_id"),
        step_id=_require_string(payload, "step_id"),
        decision_status=_require_string(payload, "decision_status"),
        proof_id=_require_string(payload, "proof_id"),
        criteria=tuple(criteria),
    )


def _require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"criteria-map payload field must be non-empty string: {field}")
    return value


def _evaluate_report(report: CriteriaDiagnosticsReport) -> tuple[str, ...]:
    issues: list[str] = list(check_evidence_pointer_consistency(report))

    seen_ids: set[str] = set()
    for entry in report.criteria:
        if entry.criterion_id in seen_ids:
            issues.append(f"{entry.criterion_id}:duplicate_criterion_id")
        seen_ids.add(entry.criterion_id)

        has_non_present_pointer = any(
            pointer.startswith(NON_PRESENT_PREFIXES)
            for pointer in entry.evidence_refs
        )
        if has_non_present_pointer and entry.status not in {"failed", "missing"}:
            issues.append(
                f"{entry.criterion_id}:non_present_pointer_without_failure_status"
            )

        for pointer in entry.evidence_refs:
            state, _, remainder = pointer.partition(":")
            output_name, has_path, path = remainder.partition("@")
            if state in {"EVIDENCE", "BROKEN"} and (
                not has_path or not path.strip() or not output_name.strip()
            ):
                issues.append(
                    f"{entry.criterion_id}:pointer_missing_path:{pointer}"
                )

    return tuple(issues)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    criteria_map_path = Path(args.criteria_map)
    summary_path = Path(args.summary_json)

    try:
        report = _load_report(criteria_map_path)
    except FileNotFoundError:
        print(f"[FAIL] criteria map not found: {criteria_map_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"[FAIL] criteria map is not valid JSON: {exc}")
        return 1
    except ValueError as exc:
        print(f"[FAIL] criteria map payload is invalid: {exc}")
        return 1

    issues = _evaluate_report(report)
    status = "passed" if not issues else "failed"

    summary = {
        "schema_version": "1.0.0",
        "workflow": "criteria-linkage-check",
        "status": status,
        "criteria_map": criteria_map_path.as_posix(),
        "criteria_count": len(report.criteria),
        "issue_count": len(issues),
        "issues": list(issues),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    if issues:
        print(f"[FAIL] criteria linkage check failed with {len(issues)} issue(s)")
        for item in issues:
            print(f"- {item}")
        print(f"Summary written to: {summary_path.as_posix()}")
        return 2

    print(f"[PASS] criteria linkage check passed ({len(report.criteria)} criteria)")
    print(f"Summary written to: {summary_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
