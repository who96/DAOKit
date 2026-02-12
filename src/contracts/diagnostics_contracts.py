from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CriterionRegistryEntry:
    criterion_id: str
    criterion: str
    evidence_refs: tuple[str, ...]
    remediation_hint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "criterion": self.criterion,
            "evidence_refs": list(self.evidence_refs),
            "remediation_hint": self.remediation_hint,
        }


@dataclass(frozen=True)
class CriterionDiagnosticEntry:
    criterion_id: str
    criterion: str
    status: str
    evidence_refs: tuple[str, ...]
    remediation_hint: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "criterion": self.criterion,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "remediation_hint": self.remediation_hint,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class CriteriaDiagnosticsReport:
    schema_version: str
    registry_name: str
    task_id: str
    run_id: str
    step_id: str
    decision_status: str
    proof_id: str
    criteria: tuple[CriterionDiagnosticEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "registry_name": self.registry_name,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "decision_status": self.decision_status,
            "proof_id": self.proof_id,
            "criteria": [item.to_dict() for item in self.criteria],
        }
