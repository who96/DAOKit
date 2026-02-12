from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class HandoffPackageError(ValueError):
    """Raised when handoff package payload or resume inputs are invalid."""


@dataclass(frozen=True)
class HandoffResumePlan:
    task_id: str
    run_id: str
    resume_step_id: str | None
    resumable_step_ids: tuple[str, ...]
    skipped_step_ids: tuple[str, ...]
    open_acceptance_items: tuple[dict[str, str], ...]
    next_action: str
    package_path: str
    loaded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "resume_step_id": self.resume_step_id,
            "resumable_step_ids": list(self.resumable_step_ids),
            "skipped_step_ids": list(self.skipped_step_ids),
            "open_acceptance_items": _copy_json(list(self.open_acceptance_items)),
            "next_action": self.next_action,
            "package_path": self.package_path,
            "loaded_at": self.loaded_at,
        }


class HandoffPackageStore:
    """Persist and restore deterministic core-rotation handoff packages."""

    def __init__(
        self,
        *,
        package_path: str | Path,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.package_path = Path(package_path)
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.package_path.parent.mkdir(parents=True, exist_ok=True)

    def write_package(
        self,
        ledger_state: Mapping[str, Any],
        *,
        evidence_paths: Sequence[str] | None = None,
        include_accepted_steps: bool = False,
    ) -> dict[str, Any]:
        _expect_mapping(ledger_state, name="ledger_state")
        if not isinstance(include_accepted_steps, bool):
            raise HandoffPackageError("include_accepted_steps must be boolean")

        package = self._build_package_payload(
            ledger_state=ledger_state,
            include_accepted_steps=include_accepted_steps,
            evidence_paths_override=evidence_paths,
        )
        self.package_path.write_text(
            json.dumps(package, indent=2) + "\n",
            encoding="utf-8",
        )
        return _copy_json(package)

    def load_package(self) -> dict[str, Any] | None:
        if not self.package_path.exists():
            return None
        if not self.package_path.is_file():
            raise HandoffPackageError(
                f"expected handoff package file at '{self.package_path}'"
            )

        try:
            payload = json.loads(self.package_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HandoffPackageError("handoff package is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise HandoffPackageError("handoff package root must be an object")

        self._validate_package_payload(payload)
        return _copy_json(payload)

    def apply_package(
        self,
        ledger_state: dict[str, Any],
        *,
        include_accepted_steps: bool = False,
    ) -> HandoffResumePlan:
        if not isinstance(ledger_state, dict):
            raise HandoffPackageError("ledger_state must be a mutable object")
        if not isinstance(include_accepted_steps, bool):
            raise HandoffPackageError("include_accepted_steps must be boolean")

        package = self.load_package()
        if package is None:
            raise HandoffPackageError(
                f"handoff package does not exist at '{self.package_path}'"
            )

        package_task_id = _expect_non_empty_string(package.get("task_id"), name="task_id")
        package_run_id = _expect_non_empty_string(package.get("run_id"), name="run_id")
        ledger_task_id = _normalize_optional_string(ledger_state.get("task_id"))
        ledger_run_id = _normalize_optional_string(ledger_state.get("run_id"))

        if ledger_task_id is not None and ledger_task_id != package_task_id:
            raise HandoffPackageError(
                "task_id mismatch between ledger and handoff package"
            )
        if ledger_run_id is not None and ledger_run_id != package_run_id:
            raise HandoffPackageError(
                "run_id mismatch between ledger and handoff package"
            )
        if ledger_task_id is None:
            ledger_state["task_id"] = package_task_id
        if ledger_run_id is None:
            ledger_state["run_id"] = package_run_id

        step_contracts = _extract_step_contracts(ledger_state)
        step_order = tuple(step_id for step_id, _step in step_contracts)
        accepted_step_ids, failed_step_ids, pending_step_ids = _classify_steps(
            ledger_state=ledger_state,
            step_order=step_order,
        )
        resumable_step_ids = _resumable_steps(
            step_order=step_order,
            accepted_step_ids=accepted_step_ids,
            include_accepted_steps=include_accepted_steps,
        )
        skipped_step_ids = tuple(step_id for step_id in step_order if step_id not in resumable_step_ids)

        resume_step_id = _pick_resume_step(
            ledger_current_step=_normalize_optional_string(ledger_state.get("current_step")),
            package_current_step=_normalize_optional_string(package.get("current_step")),
            resumable_step_ids=resumable_step_ids,
        )
        if resume_step_id is None:
            package_resumable = _expect_string_list(
                package.get("resumable_step_ids"),
                name="resumable_step_ids",
                allow_empty=True,
            )
            resume_step_id = package_resumable[0] if package_resumable else None
            if not resumable_step_ids and package_resumable:
                resumable_step_ids = package_resumable
                skipped_step_ids = ()

        open_acceptance_items = _collect_open_acceptance_items(
            step_contracts=step_contracts,
            resumable_step_ids=resumable_step_ids,
        )
        if not open_acceptance_items:
            open_acceptance_items = _normalize_open_acceptance_items(
                package.get("open_acceptance_items"),
                name="open_acceptance_items",
            )

        next_action = "complete" if resume_step_id is None else "resume"
        package_next_action = _normalize_optional_string(package.get("next_action"))
        if package_next_action is not None:
            next_action = package_next_action if resume_step_id is not None else "complete"

        ledger_state["current_step"] = resume_step_id
        role_lifecycle = _ensure_role_lifecycle(ledger_state)
        role_lifecycle["handoff_resume_step"] = resume_step_id or "none"
        role_lifecycle["handoff_next_action"] = next_action
        role_lifecycle["handoff_resumable_steps"] = ",".join(resumable_step_ids)
        role_lifecycle["handoff_skipped_steps"] = ",".join(skipped_step_ids)
        role_lifecycle["handoff_failed_steps"] = ",".join(
            step_id for step_id in failed_step_ids if step_id in resumable_step_ids
        )
        role_lifecycle["handoff_pending_steps"] = ",".join(
            step_id for step_id in pending_step_ids if step_id in resumable_step_ids
        )

        return HandoffResumePlan(
            task_id=package_task_id,
            run_id=package_run_id,
            resume_step_id=resume_step_id,
            resumable_step_ids=resumable_step_ids,
            skipped_step_ids=skipped_step_ids,
            open_acceptance_items=open_acceptance_items,
            next_action=next_action,
            package_path=self.package_path.as_posix(),
            loaded_at=_normalize_datetime(self._now_provider()).isoformat(),
        )

    def _build_package_payload(
        self,
        *,
        ledger_state: Mapping[str, Any],
        include_accepted_steps: bool,
        evidence_paths_override: Sequence[str] | None,
    ) -> dict[str, Any]:
        task_id = _expect_non_empty_string(ledger_state.get("task_id"), name="task_id")
        run_id = _expect_non_empty_string(ledger_state.get("run_id"), name="run_id")

        step_contracts = _extract_step_contracts(ledger_state)
        step_order = tuple(step_id for step_id, _step in step_contracts)
        accepted_step_ids, failed_step_ids, pending_step_ids = _classify_steps(
            ledger_state=ledger_state,
            step_order=step_order,
        )
        resumable_step_ids = _resumable_steps(
            step_order=step_order,
            accepted_step_ids=accepted_step_ids,
            include_accepted_steps=include_accepted_steps,
        )
        skipped_step_ids = tuple(step_id for step_id in step_order if step_id not in resumable_step_ids)
        resume_step_id = _pick_resume_step(
            ledger_current_step=_normalize_optional_string(ledger_state.get("current_step")),
            package_current_step=None,
            resumable_step_ids=resumable_step_ids,
        )
        open_acceptance_items = _collect_open_acceptance_items(
            step_contracts=step_contracts,
            resumable_step_ids=resumable_step_ids,
        )

        if evidence_paths_override is None:
            evidence_paths = _collect_expected_outputs(
                step_contracts=step_contracts,
                resumable_step_ids=resumable_step_ids,
            )
        else:
            evidence_paths = _expect_string_list(
                evidence_paths_override,
                name="evidence_paths",
                allow_empty=True,
            )

        next_action = "complete" if resume_step_id is None else "resume"
        payload = {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "run_id": run_id,
            "current_step": resume_step_id,
            "open_acceptance_items": _copy_json(list(open_acceptance_items)),
            "evidence_paths": list(evidence_paths),
            "next_action": next_action,
            "resumable_step_ids": list(resumable_step_ids),
            "skipped_step_ids": list(skipped_step_ids),
            "step_status": {
                "accepted": list(accepted_step_ids),
                "failed": list(failed_step_ids),
                "pending": list(pending_step_ids),
            },
            "created_at": _normalize_datetime(self._now_provider()).isoformat(),
        }
        payload["package_hash"] = _package_hash(payload)
        return payload

    def _validate_package_payload(self, payload: Mapping[str, Any]) -> None:
        _expect_non_empty_string(payload.get("schema_version"), name="schema_version")
        _expect_non_empty_string(payload.get("task_id"), name="task_id")
        _expect_non_empty_string(payload.get("run_id"), name="run_id")

        current_step = payload.get("current_step")
        if current_step is not None:
            _expect_non_empty_string(current_step, name="current_step")

        _normalize_open_acceptance_items(payload.get("open_acceptance_items"), name="open_acceptance_items")
        _expect_string_list(payload.get("evidence_paths"), name="evidence_paths", allow_empty=True)
        _expect_non_empty_string(payload.get("next_action"), name="next_action")
        _expect_string_list(payload.get("resumable_step_ids"), name="resumable_step_ids", allow_empty=True)
        _expect_string_list(payload.get("skipped_step_ids"), name="skipped_step_ids", allow_empty=True)

        raw_status = payload.get("step_status")
        status = _expect_mapping(raw_status, name="step_status")
        _expect_string_list(status.get("accepted"), name="step_status.accepted", allow_empty=True)
        _expect_string_list(status.get("failed"), name="step_status.failed", allow_empty=True)
        _expect_string_list(status.get("pending"), name="step_status.pending", allow_empty=True)

        _expect_non_empty_string(payload.get("created_at"), name="created_at")
        package_hash = _expect_non_empty_string(payload.get("package_hash"), name="package_hash")
        expected_hash = _package_hash(payload)
        if package_hash != expected_hash:
            raise HandoffPackageError("handoff package hash validation failed")


def _extract_step_contracts(
    ledger_state: Mapping[str, Any],
) -> tuple[tuple[str, dict[str, Any]], ...]:
    raw_steps = ledger_state.get("steps")
    if not isinstance(raw_steps, list):
        return ()

    contracts: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for raw_step in raw_steps:
        if not isinstance(raw_step, Mapping):
            continue
        step_id = _normalize_optional_string(raw_step.get("id"))
        if step_id is None or step_id in seen:
            continue
        contracts.append((step_id, _copy_json(dict(raw_step))))
        seen.add(step_id)
    return tuple(contracts)


def _classify_steps(
    *,
    ledger_state: Mapping[str, Any],
    step_order: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    role_lifecycle = ledger_state.get("role_lifecycle")
    lifecycle_map = role_lifecycle if isinstance(role_lifecycle, Mapping) else {}
    accepted: list[str] = []
    failed: list[str] = []
    pending: list[str] = []

    for step_id in step_order:
        lifecycle = lifecycle_map.get(f"step:{step_id}")
        classification = _classify_step_lifecycle(lifecycle)
        if classification == "accepted":
            accepted.append(step_id)
        elif classification == "failed":
            failed.append(step_id)
        else:
            pending.append(step_id)

    return tuple(accepted), tuple(failed), tuple(pending)


def _classify_step_lifecycle(value: Any) -> str:
    if not isinstance(value, str):
        return "pending"
    normalized = value.strip().lower()
    if not normalized:
        return "pending"

    accepted_markers = ("accepted", "done", "completed", "passed", "verified")
    if normalized in accepted_markers:
        return "accepted"
    if any(normalized.startswith(f"{marker}_") for marker in accepted_markers):
        return "accepted"
    if any(normalized.startswith(f"{marker}-") for marker in accepted_markers):
        return "accepted"

    if "failed" in normalized or normalized in {"error", "blocked"}:
        return "failed"
    return "pending"


def _resumable_steps(
    *,
    step_order: tuple[str, ...],
    accepted_step_ids: tuple[str, ...],
    include_accepted_steps: bool,
) -> tuple[str, ...]:
    if include_accepted_steps:
        return step_order
    accepted = set(accepted_step_ids)
    return tuple(step_id for step_id in step_order if step_id not in accepted)


def _pick_resume_step(
    *,
    ledger_current_step: str | None,
    package_current_step: str | None,
    resumable_step_ids: tuple[str, ...],
) -> str | None:
    if ledger_current_step is not None and ledger_current_step in resumable_step_ids:
        return ledger_current_step
    if package_current_step is not None and package_current_step in resumable_step_ids:
        return package_current_step
    if resumable_step_ids:
        return resumable_step_ids[0]
    return None


def _collect_open_acceptance_items(
    *,
    step_contracts: tuple[tuple[str, dict[str, Any]], ...],
    resumable_step_ids: tuple[str, ...],
) -> tuple[dict[str, str], ...]:
    resumable = set(resumable_step_ids)
    items: list[dict[str, str]] = []
    for step_id, step in step_contracts:
        if step_id not in resumable:
            continue
        criteria = step.get("acceptance_criteria")
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, str):
                continue
            normalized = criterion.strip()
            if not normalized:
                continue
            items.append({"step_id": step_id, "criterion": normalized})
    return tuple(items)


def _collect_expected_outputs(
    *,
    step_contracts: tuple[tuple[str, dict[str, Any]], ...],
    resumable_step_ids: tuple[str, ...],
) -> tuple[str, ...]:
    resumable = set(resumable_step_ids)
    outputs: list[str] = []
    seen: set[str] = set()

    for step_id, step in step_contracts:
        if step_id not in resumable:
            continue
        raw_outputs = step.get("expected_outputs")
        if not isinstance(raw_outputs, list):
            continue
        for output in raw_outputs:
            if not isinstance(output, str):
                continue
            normalized = output.strip()
            if not normalized or normalized in seen:
                continue
            outputs.append(normalized)
            seen.add(normalized)

    return tuple(outputs)


def _normalize_open_acceptance_items(
    value: Any,
    *,
    name: str,
) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        raise HandoffPackageError(f"{name} must be a list")

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        item_name = f"{name}[{index}]"
        mapping = _expect_mapping(item, name=item_name)
        step_id = _expect_non_empty_string(mapping.get("step_id"), name=f"{item_name}.step_id")
        criterion = _expect_non_empty_string(mapping.get("criterion"), name=f"{item_name}.criterion")
        normalized.append({"step_id": step_id, "criterion": criterion})
    return tuple(normalized)


def _ensure_role_lifecycle(ledger_state: dict[str, Any]) -> dict[str, str]:
    raw = ledger_state.get("role_lifecycle")
    if isinstance(raw, dict):
        if all(isinstance(key, str) and isinstance(value, str) for key, value in raw.items()):
            return raw
    lifecycle = {"orchestrator": "running"}
    ledger_state["role_lifecycle"] = lifecycle
    return lifecycle


def _expect_mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HandoffPackageError(f"{name} must be an object")
    return value


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise HandoffPackageError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise HandoffPackageError(f"{name} must be a non-empty string")
    return normalized


def _normalize_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _expect_string_list(
    value: Any,
    *,
    name: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise HandoffPackageError(f"{name} must be a list of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_name = f"{name}[{index}]"
        text = _expect_non_empty_string(item, name=item_name)
        if text in seen:
            continue
        normalized.append(text)
        seen.add(text)

    if not allow_empty and not normalized:
        raise HandoffPackageError(f"{name} must contain at least 1 entry")
    return tuple(normalized)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _package_hash(payload: Mapping[str, Any]) -> str:
    material = {
        key: value
        for key, value in payload.items()
        if key != "package_hash"
    }
    canonical = json.dumps(material, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))
