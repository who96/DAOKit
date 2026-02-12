from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from reliability.handoff.package import HandoffPackageError, HandoffPackageStore
from reliability.lease.registry import LeaseRegistry
from state.store import StateStore

DEFAULT_CONTROLLER_LANE = "controller"
KNOWN_HEARTBEAT_STATUSES = {"IDLE", "RUNNING", "WARNING", "STALE", "BLOCKED"}


@dataclass(frozen=True)
class SuccessionTakeoverResult:
    task_id: str
    run_id: str
    takeover_at: str
    adopted_step_ids: tuple[str, ...]
    failed_step_ids: tuple[str, ...]


@dataclass(frozen=True)
class SelfHealingDecision:
    action: str
    heartbeat_status: str
    lease_reason_code: str
    reason_code: str


@dataclass(frozen=True)
class SelfHealingCycleResult:
    action: str
    decision_reason_code: str
    heartbeat_status: str
    lease_reason_code: str
    takeover_result: SuccessionTakeoverResult | None
    handoff_applied: bool
    handoff_resume_step_id: str | None


class SuccessionManager:
    """Handle successor acceptance and lease adoption for active runs."""

    def __init__(
        self,
        *,
        task_id: str,
        run_id: str,
        state_store: StateStore,
        lease_registry: LeaseRegistry,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.state_store = state_store
        self.lease_registry = lease_registry
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def accept_successor(
        self,
        *,
        successor_thread_id: str,
        successor_pid: int,
        lease_ttl_seconds: int | None = None,
        trigger_reason: str | None = None,
    ) -> SuccessionTakeoverResult:
        takeover_at = _normalize_datetime(self._now_provider())

        takeover = self.lease_registry.takeover_running_leases(
            task_id=self.task_id,
            run_id=self.run_id,
            successor_thread_id=successor_thread_id,
            successor_pid=successor_pid,
            ttl_seconds=lease_ttl_seconds,
            at=takeover_at,
        )

        adopted_step_ids = _ordered_unique(
            lease["step_id"]
            for lease in takeover.adopted_leases
            if isinstance(lease.get("step_id"), str)
        )
        failed_step_ids = _ordered_unique(
            lease["step_id"]
            for lease in takeover.non_adopted_leases
            if isinstance(lease.get("step_id"), str)
        )

        self._persist_succession_state(
            takeover_at=takeover_at,
            adopted_step_ids=adopted_step_ids,
            failed_step_ids=failed_step_ids,
        )
        self._append_events(
            takeover_at=takeover_at,
            adopted_step_ids=adopted_step_ids,
            failed_step_ids=failed_step_ids,
            trigger_reason=trigger_reason,
        )

        return SuccessionTakeoverResult(
            task_id=self.task_id,
            run_id=self.run_id,
            takeover_at=takeover_at.isoformat(),
            adopted_step_ids=adopted_step_ids,
            failed_step_ids=failed_step_ids,
        )

    def run_self_healing_cycle(
        self,
        *,
        successor_thread_id: str,
        successor_pid: int,
        lease_ttl_seconds: int | None = None,
        handoff_store: HandoffPackageStore | None = None,
        include_accepted_steps: bool = False,
        heartbeat_status: str | None = None,
    ) -> SelfHealingCycleResult:
        decision_at = _normalize_datetime(self._now_provider())
        decision = self._decide_self_healing(
            at=decision_at,
            heartbeat_status=heartbeat_status,
        )
        self._append_decision_event(decision=decision, decision_at=decision_at)

        if decision.action != "TAKEOVER":
            return SelfHealingCycleResult(
                action=decision.action,
                decision_reason_code=decision.reason_code,
                heartbeat_status=decision.heartbeat_status,
                lease_reason_code=decision.lease_reason_code,
                takeover_result=None,
                handoff_applied=False,
                handoff_resume_step_id=None,
            )

        takeover_result = self.accept_successor(
            successor_thread_id=successor_thread_id,
            successor_pid=successor_pid,
            lease_ttl_seconds=lease_ttl_seconds,
            trigger_reason=decision.reason_code,
        )
        handoff_applied, handoff_resume_step_id = self._recover_from_handoff(
            takeover_at=decision_at,
            handoff_store=handoff_store,
            include_accepted_steps=include_accepted_steps,
        )
        return SelfHealingCycleResult(
            action=decision.action,
            decision_reason_code=decision.reason_code,
            heartbeat_status=decision.heartbeat_status,
            lease_reason_code=decision.lease_reason_code,
            takeover_result=takeover_result,
            handoff_applied=handoff_applied,
            handoff_resume_step_id=handoff_resume_step_id,
        )

    def _decide_self_healing(
        self,
        *,
        at: datetime,
        heartbeat_status: str | None,
    ) -> SelfHealingDecision:
        normalized_heartbeat = self._resolve_heartbeat_status(heartbeat_status)
        lease_reason_code, lease_valid = self._evaluate_controller_lease(at=at)

        if normalized_heartbeat == "STALE":
            return SelfHealingDecision(
                action="TAKEOVER",
                heartbeat_status=normalized_heartbeat,
                lease_reason_code=lease_reason_code,
                reason_code="HEARTBEAT_STALE",
            )
        if not lease_valid:
            return SelfHealingDecision(
                action="TAKEOVER",
                heartbeat_status=normalized_heartbeat,
                lease_reason_code=lease_reason_code,
                reason_code=f"INVALID_LEASE_{lease_reason_code}",
            )
        if normalized_heartbeat == "WARNING":
            return SelfHealingDecision(
                action="OBSERVE",
                heartbeat_status=normalized_heartbeat,
                lease_reason_code=lease_reason_code,
                reason_code="HEARTBEAT_WARNING_OBSERVE_ONLY",
            )
        return SelfHealingDecision(
            action="OBSERVE",
            heartbeat_status=normalized_heartbeat,
            lease_reason_code=lease_reason_code,
            reason_code=f"HEARTBEAT_{normalized_heartbeat}_NO_ACTION",
        )

    def _evaluate_controller_lease(self, *, at: datetime) -> tuple[str, bool]:
        state = self.state_store.load_state()
        controller_lane = self._resolve_controller_lane(state)
        controller_step_id = self._resolve_controller_step_id(
            state=state,
            controller_lane=controller_lane,
        )

        leases = self.lease_registry.list_leases(task_id=self.task_id, run_id=self.run_id)
        matching = [
            lease
            for lease in leases
            if self._lease_matches_controller(
                lease=lease,
                controller_lane=controller_lane,
                controller_step_id=controller_step_id,
            )
        ]
        if not matching:
            return ("MISSING_CONTROLLER_LEASE", False)

        active = [lease for lease in matching if _normalize_optional_text(lease.get("status")) == "ACTIVE"]
        if not active:
            return ("NON_ACTIVE_CONTROLLER_LEASE", False)

        lease = sorted(active, key=self._lease_sort_key)[-1]
        expiry = _normalize_optional_text(lease.get("expiry"))
        if expiry is None:
            return ("MALFORMED_LEASE_EXPIRY", False)
        try:
            expiry_at = _normalize_datetime(datetime.fromisoformat(expiry))
        except ValueError:
            return ("MALFORMED_LEASE_EXPIRY", False)
        if expiry_at <= at:
            return ("EXPIRED_CONTROLLER_LEASE", False)
        return ("VALID_ACTIVE_LEASE", True)

    def _resolve_heartbeat_status(self, explicit_status: str | None) -> str:
        if explicit_status is not None:
            candidate = explicit_status
        else:
            heartbeat = self.state_store.load_heartbeat_status()
            candidate = str(heartbeat.get("status") or "")
        normalized = candidate.strip().upper()
        if normalized in KNOWN_HEARTBEAT_STATUSES:
            return normalized
        return "UNKNOWN"

    def _recover_from_handoff(
        self,
        *,
        takeover_at: datetime,
        handoff_store: HandoffPackageStore | None,
        include_accepted_steps: bool,
    ) -> tuple[bool, str | None]:
        store = handoff_store or HandoffPackageStore(
            package_path=Path(self.state_store.root) / "handoff_package.json",
            now_provider=self._now_provider,
        )
        if store.load_package() is None:
            return (False, None)

        state = self.state_store.load_state()
        prior_status = str(state.get("status") or "EXECUTE")
        try:
            resume = store.apply_package(
                state,
                include_accepted_steps=include_accepted_steps,
            )
        except HandoffPackageError as exc:
            self.state_store.append_event(
                task_id=self.task_id,
                run_id=self.run_id,
                step_id=state.get("current_step"),
                event_type="SYSTEM",
                severity="ERROR",
                payload={
                    "operation": "HANDOFF_APPLY_FAILED",
                    "reason_code": "HANDOFF_APPLY_ERROR",
                    "error": str(exc),
                    "takeover_at": takeover_at.isoformat(),
                },
                dedup_key=f"handoff-failed:{self.task_id}:{self.run_id}:{takeover_at.isoformat()}",
            )
            raise

        self.state_store.save_state(
            state,
            node="succession_handoff_recover",
            from_status=prior_status,
            to_status=str(state.get("status") or prior_status),
        )
        self.state_store.append_event(
            task_id=self.task_id,
            run_id=self.run_id,
            step_id=resume.resume_step_id,
            event_type="SYSTEM",
            severity="INFO",
            payload={
                "operation": "HANDOFF_APPLIED",
                "takeover_at": takeover_at.isoformat(),
                "resume_step_id": resume.resume_step_id,
                "next_action": resume.next_action,
                "resumable_step_ids": list(resume.resumable_step_ids),
            },
            dedup_key=f"handoff-applied:{self.task_id}:{self.run_id}:{takeover_at.isoformat()}",
        )
        return (True, resume.resume_step_id)

    def _append_decision_event(
        self,
        *,
        decision: SelfHealingDecision,
        decision_at: datetime,
    ) -> None:
        event_type = "SYSTEM"
        severity = "INFO"
        if decision.action == "OBSERVE" and decision.heartbeat_status == "WARNING":
            event_type = "HEARTBEAT_WARNING"
            severity = "WARN"
        elif decision.heartbeat_status == "STALE":
            event_type = "HEARTBEAT_STALE"
            severity = "WARN"
        elif decision.action == "TAKEOVER":
            severity = "WARN"

        self.state_store.append_event(
            task_id=self.task_id,
            run_id=self.run_id,
            step_id=self.state_store.load_state().get("current_step"),
            event_type=event_type,
            severity=severity,
            payload={
                "stage": "decide",
                "decision_action": decision.action,
                "decision_reason_code": decision.reason_code,
                "heartbeat_status": decision.heartbeat_status,
                "lease_reason_code": decision.lease_reason_code,
                "takeover_required": decision.action == "TAKEOVER",
                "decided_at": decision_at.isoformat(),
            },
            dedup_key=(
                f"self-heal:{self.task_id}:{self.run_id}:{decision.action}:"
                f"{decision.heartbeat_status}:{decision.lease_reason_code}"
            ),
        )

    def _lease_matches_controller(
        self,
        *,
        lease: Mapping[str, Any],
        controller_lane: str,
        controller_step_id: str | None,
    ) -> bool:
        if _normalize_optional_text(lease.get("lane")) != controller_lane:
            return False
        if controller_step_id is None:
            return True
        return _normalize_optional_text(lease.get("step_id")) == controller_step_id

    def _resolve_controller_lane(self, state: Mapping[str, Any]) -> str:
        lifecycle = state.get("role_lifecycle")
        if isinstance(lifecycle, Mapping):
            lane = _normalize_optional_text(lifecycle.get("controller_lane"))
            if lane is not None:
                return lane
        return DEFAULT_CONTROLLER_LANE

    def _resolve_controller_step_id(
        self,
        *,
        state: Mapping[str, Any],
        controller_lane: str,
    ) -> str | None:
        lifecycle = state.get("role_lifecycle")
        if isinstance(lifecycle, Mapping):
            ownership = _normalize_optional_text(lifecycle.get("controller_ownership"))
            if ownership is not None and ":" in ownership:
                lane, _, step_id = ownership.partition(":")
                if lane == controller_lane and step_id and step_id != "unassigned":
                    return step_id
        return _normalize_optional_text(state.get("current_step"))

    def _lease_sort_key(self, lease: Mapping[str, Any]) -> tuple[str, str, str]:
        return (
            _normalize_optional_text(lease.get("updated_at")) or "",
            _normalize_optional_text(lease.get("created_at")) or "",
            _normalize_optional_text(lease.get("lease_token")) or "",
        )

    def _persist_succession_state(
        self,
        *,
        takeover_at: datetime,
        adopted_step_ids: tuple[str, ...],
        failed_step_ids: tuple[str, ...],
    ) -> None:
        state = self.state_store.load_state()
        prior_status = str(state.get("status") or "EXECUTE")
        changed = False

        if state.get("task_id") != self.task_id:
            state["task_id"] = self.task_id
            changed = True
        if state.get("run_id") != self.run_id:
            state["run_id"] = self.run_id
            changed = True

        succession = state.get("succession")
        if not isinstance(succession, dict):
            succession = {"enabled": True, "last_takeover_at": None}
            state["succession"] = succession
            changed = True

        if succession.get("last_takeover_at") != takeover_at.isoformat():
            succession["last_takeover_at"] = takeover_at.isoformat()
            changed = True

        lifecycle = state.get("role_lifecycle")
        if not isinstance(lifecycle, dict):
            lifecycle = {"orchestrator": "running"}
            state["role_lifecycle"] = lifecycle
            changed = True

        for step_id in failed_step_ids:
            key = f"step:{step_id}"
            if lifecycle.get(key) != "failed_non_adopted_lease":
                lifecycle[key] = "failed_non_adopted_lease"
                changed = True

        if changed:
            self.state_store.save_state(
                state,
                node="succession_takeover",
                from_status=prior_status,
                to_status=str(state.get("status") or prior_status),
            )

    def _append_events(
        self,
        *,
        takeover_at: datetime,
        adopted_step_ids: tuple[str, ...],
        failed_step_ids: tuple[str, ...],
        trigger_reason: str | None,
    ) -> None:
        takeover_key = takeover_at.isoformat()
        self.state_store.append_event(
            task_id=self.task_id,
            run_id=self.run_id,
            step_id=None,
            event_type="LEASE_TAKEOVER",
            severity="INFO",
            payload={
                "takeover_at": takeover_key,
                "adopted_step_ids": list(adopted_step_ids),
                "failed_step_ids": list(failed_step_ids),
                "reason_code": trigger_reason or "MANUAL_TAKEOVER",
            },
            dedup_key=f"succession:{self.task_id}:{self.run_id}:{takeover_key}",
        )

        for step_id in adopted_step_ids:
            self.state_store.append_event(
                task_id=self.task_id,
                run_id=self.run_id,
                step_id=step_id,
                event_type="SYSTEM",
                severity="INFO",
                payload={
                    "operation": "LEASE_ADOPTED",
                    "reason_code": "VALID_UNEXPIRED_LEASE",
                    "takeover_at": takeover_key,
                },
                dedup_key=f"lease-adopted:{self.task_id}:{self.run_id}:{step_id}:{takeover_key}",
            )

        for step_id in failed_step_ids:
            self.state_store.append_event(
                task_id=self.task_id,
                run_id=self.run_id,
                step_id=step_id,
                event_type="STEP_FAILED",
                severity="ERROR",
                payload={
                    "reason_code": "LEASE_NOT_ADOPTED",
                    "takeover_at": takeover_key,
                },
                dedup_key=f"step-failed:{self.task_id}:{self.run_id}:{step_id}:{takeover_key}",
            )


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized
