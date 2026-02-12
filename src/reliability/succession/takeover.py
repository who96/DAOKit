from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

from reliability.lease.registry import LeaseRegistry
from state.store import StateStore


@dataclass(frozen=True)
class SuccessionTakeoverResult:
    task_id: str
    run_id: str
    takeover_at: str
    adopted_step_ids: tuple[str, ...]
    failed_step_ids: tuple[str, ...]


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
        )

        return SuccessionTakeoverResult(
            task_id=self.task_id,
            run_id=self.run_id,
            takeover_at=takeover_at.isoformat(),
            adopted_step_ids=adopted_step_ids,
            failed_step_ids=failed_step_ids,
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

        if adopted_step_ids and succession.get("last_takeover_at") != takeover_at.isoformat():
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
    ) -> None:
        takeover_key = takeover_at.isoformat()
        self.state_store.append_event(
            task_id=self.task_id,
            run_id=self.run_id,
            step_id=None,
            event_type="SUCCESSION_ACCEPTED",
            severity="INFO",
            payload={
                "takeover_at": takeover_key,
                "adopted_step_ids": list(adopted_step_ids),
                "failed_step_ids": list(failed_step_ids),
            },
            dedup_key=f"succession:{self.task_id}:{self.run_id}:{takeover_key}",
        )

        for step_id in adopted_step_ids:
            self.state_store.append_event(
                task_id=self.task_id,
                run_id=self.run_id,
                step_id=step_id,
                event_type="LEASE_ADOPTED",
                severity="INFO",
                payload={
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
