from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EvidenceRecord:
    output_name: str
    path: str
    exists: bool
    sha256: str | None
    size_bytes: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_name": self.output_name,
            "path": self.path,
            "exists": self.exists,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class FailureReason:
    code: str
    message: str
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class CriterionResult:
    criterion_id: str
    criterion: str
    passed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "criterion": self.criterion,
            "passed": self.passed,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class AcceptanceProofRecord:
    proof_id: str
    status: str
    task_id: str
    run_id: str
    step_id: str
    criteria: tuple[CriterionResult, ...]
    evidence: tuple[EvidenceRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "status": self.status,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "criteria": [item.to_dict() for item in self.criteria],
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class ReworkCriterion:
    criterion_id: str
    criterion: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "criterion": self.criterion,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ReworkPayload:
    next_action: str
    step_id: str
    failed_criteria: tuple[ReworkCriterion, ...]
    directives: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "next_action": self.next_action,
            "step_id": self.step_id,
            "failed_criteria": [item.to_dict() for item in self.failed_criteria],
            "directives": list(self.directives),
        }


@dataclass(frozen=True)
class AcceptanceDecision:
    status: str
    proof: AcceptanceProofRecord
    failure_reasons: tuple[FailureReason, ...]
    rework: ReworkPayload | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "proof": self.proof.to_dict(),
            "failure_reasons": [item.to_dict() for item in self.failure_reasons],
            "rework": None if self.rework is None else self.rework.to_dict(),
        }
