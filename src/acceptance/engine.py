from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from audit.diff_auditor import audit_changed_files
from audit.scope_guard import ScopeGuardError
from contracts.acceptance_contracts import (
    AcceptanceDecision,
    AcceptanceProofRecord,
    CriterionResult,
    EvidenceRecord,
    FailureReason,
    ReworkCriterion,
    ReworkPayload,
)


class AcceptanceError(ValueError):
    """Raised when acceptance input cannot be normalized safely."""


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise AcceptanceError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise AcceptanceError(f"{name} must be a non-empty string")
    return normalized


def _expect_string_list(value: Any, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AcceptanceError(f"{name} must be a list of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_name = f"{name}[{index}]"
        text = _expect_non_empty_string(item, name=item_name)
        if text in seen:
            continue
        normalized.append(text)
        seen.add(text)

    if not normalized:
        raise AcceptanceError(f"{name} must contain at least 1 entry")
    return tuple(normalized)


def _expect_mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AcceptanceError(f"{name} must be an object")
    return value


def _expect_optional_string_list(value: Any, *, name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _expect_string_list(value, name=name)


def _digest_file(path: Path) -> tuple[str, int]:
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    return digest, len(content)


def _criterion_id(index: int) -> str:
    return f"AC-{index + 1:03d}"


def _contains_command_evidence(text: str) -> bool:
    return "Command:" in text or "COMMAND ENTRY" in text


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _stable_proof_id(payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]
    return f"proof-{digest}"


def _normalize_evidence_path(output_name: str, evidence_root: Path) -> Path:
    target = Path(output_name)
    if not target.is_absolute():
        target = evidence_root / target
    return target.resolve()


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class AcceptanceEngine:
    """Evaluates step acceptance using concrete evidence artifacts."""

    def evaluate_step(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        acceptance_criteria: list[str],
        expected_outputs: list[str],
        evidence_root: str | Path,
        changed_files: list[str] | None = None,
        allowed_scope: list[str] | None = None,
    ) -> AcceptanceDecision:
        normalized_task_id = _expect_non_empty_string(task_id, name="task_id")
        normalized_run_id = _expect_non_empty_string(run_id, name="run_id")
        normalized_step_id = _expect_non_empty_string(step_id, name="step_id")
        normalized_criteria = _expect_string_list(
            acceptance_criteria,
            name="acceptance_criteria",
        )
        normalized_outputs = _expect_string_list(expected_outputs, name="expected_outputs")

        root = Path(evidence_root).resolve()
        evidence_records, invalid_paths = self._resolve_evidence(
            expected_outputs=normalized_outputs,
            evidence_root=root,
        )

        criterion_index = {
            _criterion_id(index): criterion
            for index, criterion in enumerate(normalized_criteria)
        }
        reason_codes_by_criterion: dict[str, list[str]] = {
            criterion_id: [] for criterion_id in criterion_index
        }
        failure_reasons: list[FailureReason] = []

        if invalid_paths:
            target_ids = self._match_criteria(
                criteria=criterion_index,
                preferred_phrases=("evidence path", "evidence", "artifact"),
                fallback_phrases=("output",),
            )
            for invalid_path in invalid_paths:
                reason = FailureReason(
                    code="INVALID_EVIDENCE_PATH",
                    message=(
                        "expected output path escapes evidence root and cannot be used as evidence"
                    ),
                    details=dict(invalid_path),
                )
                failure_reasons.append(reason)
                self._attach_reason_code(
                    target_ids=target_ids,
                    reason_code=reason.code,
                    bucket=reason_codes_by_criterion,
                )

        invalid_output_names = {str(item["output_name"]) for item in invalid_paths}
        missing_outputs = [
            item.output_name
            for item in evidence_records
            if not item.exists and item.output_name not in invalid_output_names
        ]
        if missing_outputs:
            target_ids = self._match_criteria(
                criteria=criterion_index,
                preferred_phrases=("missing evidence",),
                fallback_phrases=("evidence",),
            )
            for output_name in missing_outputs:
                reason = FailureReason(
                    code="MISSING_EVIDENCE",
                    message=f"required evidence is missing: {output_name}",
                    details={"missing_output": output_name},
                )
                failure_reasons.append(reason)
                self._attach_reason_code(
                    target_ids=target_ids,
                    reason_code=reason.code,
                    bucket=reason_codes_by_criterion,
                )

        verification_record = None
        for item in evidence_records:
            if Path(item.output_name).name == "verification.log":
                verification_record = item
                break

        if verification_record is not None and verification_record.exists:
            verification_text = Path(verification_record.path).read_text(encoding="utf-8")
            if not _contains_command_evidence(verification_text):
                target_ids = self._match_criteria(
                    criteria=criterion_index,
                    preferred_phrases=("command evidence", "verification.log"),
                    fallback_phrases=("verification", "command"),
                )
                reason = FailureReason(
                    code="MISSING_COMMAND_EVIDENCE",
                    message=(
                        "verification.log must include command evidence markers "
                        "('Command:' or 'COMMAND ENTRY')"
                    ),
                    details={"path": verification_record.path},
                )
                failure_reasons.append(reason)
                self._attach_reason_code(
                    target_ids=target_ids,
                    reason_code=reason.code,
                    bucket=reason_codes_by_criterion,
                )

        self._evaluate_scope_audit(
            criterion_index=criterion_index,
            reason_codes_by_criterion=reason_codes_by_criterion,
            failure_reasons=failure_reasons,
            changed_files=changed_files,
            allowed_scope=allowed_scope,
        )

        criterion_results: list[CriterionResult] = []
        for criterion_id, criterion in criterion_index.items():
            reason_codes = tuple(reason_codes_by_criterion[criterion_id])
            criterion_results.append(
                CriterionResult(
                    criterion_id=criterion_id,
                    criterion=criterion,
                    passed=len(reason_codes) == 0,
                    reason_codes=reason_codes,
                )
            )

        status = "failed" if failure_reasons else "passed"

        proof_payload = {
            "task_id": normalized_task_id,
            "run_id": normalized_run_id,
            "step_id": normalized_step_id,
            "status": status,
            "criteria": [item.to_dict() for item in criterion_results],
            "evidence": [item.to_dict() for item in evidence_records],
            "failure_reasons": [item.to_dict() for item in failure_reasons],
        }
        proof = AcceptanceProofRecord(
            proof_id=_stable_proof_id(proof_payload),
            status=status,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            criteria=tuple(criterion_results),
            evidence=evidence_records,
        )

        rework = None
        if status == "failed":
            failed_criteria = tuple(
                ReworkCriterion(
                    criterion_id=item.criterion_id,
                    criterion=item.criterion,
                    reason_codes=item.reason_codes,
                )
                for item in criterion_results
                if not item.passed
            )
            directives = self._build_rework_directives(failure_reasons)
            rework = ReworkPayload(
                next_action="rework",
                step_id=normalized_step_id,
                failed_criteria=failed_criteria,
                directives=directives,
            )

        return AcceptanceDecision(
            status=status,
            proof=proof,
            failure_reasons=tuple(failure_reasons),
            rework=rework,
        )

    def evaluate_step_contract(
        self,
        *,
        task_id: str,
        run_id: str,
        step_contract: Mapping[str, Any],
        evidence_root: str | Path,
        changed_files: list[str] | None = None,
    ) -> AcceptanceDecision:
        step = _expect_mapping(step_contract, name="step_contract")
        raw_allowed_scope = step.get("allowed_scope")
        if raw_allowed_scope is None:
            raw_allowed_scope = step.get("allowed_paths")
        normalized_scope = _expect_optional_string_list(
            raw_allowed_scope,
            name="step_contract.allowed_scope",
        )
        return self.evaluate_step(
            task_id=task_id,
            run_id=run_id,
            step_id=_expect_non_empty_string(step.get("id"), name="step_contract.id"),
            acceptance_criteria=list(
                _expect_string_list(
                    step.get("acceptance_criteria"),
                    name="step_contract.acceptance_criteria",
                )
            ),
            expected_outputs=list(
                _expect_string_list(
                    step.get("expected_outputs"),
                    name="step_contract.expected_outputs",
                )
            ),
            evidence_root=evidence_root,
            changed_files=changed_files,
            allowed_scope=None if normalized_scope is None else list(normalized_scope),
        )

    def _resolve_evidence(
        self,
        *,
        expected_outputs: tuple[str, ...],
        evidence_root: Path,
    ) -> tuple[tuple[EvidenceRecord, ...], tuple[Mapping[str, str], ...]]:
        records: list[EvidenceRecord] = []
        invalid_paths: list[Mapping[str, str]] = []
        for output_name in expected_outputs:
            resolved = _normalize_evidence_path(output_name, evidence_root)
            within_root = _is_within_root(resolved, evidence_root)
            exists = within_root and resolved.is_file()
            if not within_root:
                invalid_paths.append(
                    {
                        "output_name": output_name,
                        "path": resolved.as_posix(),
                        "evidence_root": evidence_root.as_posix(),
                    }
                )
            sha256 = None
            size_bytes = None
            if exists:
                sha256, size_bytes = _digest_file(resolved)
            records.append(
                EvidenceRecord(
                    output_name=output_name,
                    path=resolved.as_posix(),
                    exists=exists,
                    sha256=sha256,
                    size_bytes=size_bytes,
                )
            )
        return tuple(records), tuple(invalid_paths)

    def _match_criteria(
        self,
        *,
        criteria: Mapping[str, str],
        preferred_phrases: tuple[str, ...],
        fallback_phrases: tuple[str, ...],
    ) -> tuple[str, ...]:
        lowered = {key: text.lower() for key, text in criteria.items()}

        preferred_matches = [
            key
            for key, text in lowered.items()
            if any(phrase in text for phrase in preferred_phrases)
        ]
        if preferred_matches:
            return tuple(preferred_matches)

        fallback_matches = [
            key
            for key, text in lowered.items()
            if any(phrase in text for phrase in fallback_phrases)
        ]
        if fallback_matches:
            return tuple(fallback_matches)

        return tuple(criteria.keys())

    def _attach_reason_code(
        self,
        *,
        target_ids: tuple[str, ...],
        reason_code: str,
        bucket: dict[str, list[str]],
    ) -> None:
        for criterion_id in target_ids:
            existing = bucket[criterion_id]
            if reason_code in existing:
                continue
            existing.append(reason_code)

    def _evaluate_scope_audit(
        self,
        *,
        criterion_index: Mapping[str, str],
        reason_codes_by_criterion: dict[str, list[str]],
        failure_reasons: list[FailureReason],
        changed_files: list[str] | None,
        allowed_scope: list[str] | None,
    ) -> None:
        if changed_files is None and allowed_scope is None:
            return

        target_ids = self._match_criteria(
            criteria=criterion_index,
            preferred_phrases=("out-of-scope", "scope", "unrelated"),
            fallback_phrases=("change", "file"),
        )

        if changed_files is None or allowed_scope is None:
            reason = FailureReason(
                code="SCOPE_AUDIT_INPUT_INCOMPLETE",
                message=(
                    "scope audit requires both changed_files and allowed_scope "
                    "to be present together"
                ),
                details={},
            )
            failure_reasons.append(reason)
            self._attach_reason_code(
                target_ids=target_ids,
                reason_code=reason.code,
                bucket=reason_codes_by_criterion,
            )
            return

        try:
            scope_result = audit_changed_files(
                changed_files=changed_files,
                allowed_scope=allowed_scope,
            )
        except ScopeGuardError as exc:
            reason = FailureReason(
                code="SCOPE_AUDIT_INPUT_INVALID",
                message=str(exc),
                details={},
            )
            failure_reasons.append(reason)
            self._attach_reason_code(
                target_ids=target_ids,
                reason_code=reason.code,
                bucket=reason_codes_by_criterion,
            )
            return

        if scope_result.passed:
            return

        reason = FailureReason(
            code="OUT_OF_SCOPE_CHANGE",
            message="changed files violate allowed scope policy",
            details={
                "allowed_scope": list(scope_result.allowed_scope),
                "violating_files": list(scope_result.violating_files),
            },
        )
        failure_reasons.append(reason)
        self._attach_reason_code(
            target_ids=target_ids,
            reason_code=reason.code,
            bucket=reason_codes_by_criterion,
        )

    def _build_rework_directives(self, failure_reasons: list[FailureReason]) -> tuple[str, ...]:
        directives: list[str] = []
        for reason in failure_reasons:
            if reason.code == "MISSING_EVIDENCE":
                missing_output = str(reason.details.get("missing_output") or "<unknown>")
                directives.append(f"create missing evidence artifact: {missing_output}")
                continue
            if reason.code == "MISSING_COMMAND_EVIDENCE":
                directives.append(
                    "add command evidence markers to verification.log: "
                    "include 'Command: <cmd>' and/or '=== COMMAND ENTRY N START/END ==='"
                )
                continue
            if reason.code == "OUT_OF_SCOPE_CHANGE":
                violating_files = ", ".join(
                    str(item) for item in reason.details.get("violating_files", [])
                )
                detail = violating_files or "<unknown>"
                directives.append(
                    "remove out-of-scope edits and keep only allowed files: "
                    f"{detail}"
                )
                continue
            if reason.code in {"SCOPE_AUDIT_INPUT_INCOMPLETE", "SCOPE_AUDIT_INPUT_INVALID"}:
                directives.append(
                    "provide valid scope audit inputs: changed_files and allowed_scope"
                )
                continue
            directives.append("resolve acceptance failure and rerun verification")

        unique: list[str] = []
        seen: set[str] = set()
        for directive in directives:
            if directive in seen:
                continue
            seen.add(directive)
            unique.append(directive)
        return tuple(unique)
