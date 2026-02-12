from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Callable, Mapping
from uuid import uuid4

from state.store import StateStore


class LeaseRegistryError(ValueError):
    """Raised when lease lifecycle operations receive invalid input or state."""


@dataclass(frozen=True)
class LeaseTakeoverBatchResult:
    adopted_leases: tuple[dict[str, Any], ...]
    non_adopted_leases: tuple[dict[str, Any], ...]


class LeaseRegistry:
    """File-backed process lease lifecycle manager."""

    def __init__(
        self,
        *,
        state_store: StateStore,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.state_store = state_store
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._leases_path = self.state_store.root / "process_leases.json"
        self._ensure_registry()

    def register(
        self,
        *,
        lane: str,
        step_id: str,
        task_id: str,
        run_id: str,
        thread_id: str,
        pid: int,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        normalized_lane = self._normalize_lane(lane)
        self._expect_non_empty_text(step_id, name="step_id")
        self._expect_non_empty_text(task_id, name="task_id")
        self._expect_non_empty_text(run_id, name="run_id")
        self._expect_non_empty_text(thread_id, name="thread_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise LeaseRegistryError("pid must be a positive integer")

        ttl = self._expect_positive_seconds(ttl_seconds, name="ttl_seconds")
        now = _normalize_datetime(self._now_provider())

        payload = self._load_registry()
        record = {
            "lane": normalized_lane,
            "step_id": step_id,
            "task_id": task_id,
            "run_id": run_id,
            "thread_id": thread_id,
            "pid": pid,
            "lease_token": self._new_token(),
            "expiry": (now + timedelta(seconds=ttl)).isoformat(),
            "status": "ACTIVE",
            "last_heartbeat_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        payload["leases"].append(record)
        self._save_registry(payload, updated_at=now)
        self._sync_lane_ownership_lifecycle(record)
        return _copy_json(record)

    def heartbeat(
        self,
        *,
        lease_token: str,
        task_id: str,
        run_id: str,
        step_id: str,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        now = _normalize_datetime(at or self._now_provider())
        payload = self._load_registry()
        lease = self._find_bound_lease(
            payload,
            lease_token=lease_token,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
        )
        self._require_active_or_raise(lease)

        if self._is_expired(lease, now=now):
            lease["status"] = "EXPIRED"
            lease["updated_at"] = now.isoformat()
            self._save_registry(payload, updated_at=now)
            raise LeaseRegistryError("lease is expired and cannot heartbeat")

        lease["last_heartbeat_at"] = now.isoformat()
        lease["updated_at"] = now.isoformat()
        self._save_registry(payload, updated_at=now)
        return _copy_json(lease)

    def renew(
        self,
        *,
        lease_token: str,
        task_id: str,
        run_id: str,
        step_id: str,
        ttl_seconds: int,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        ttl = self._expect_positive_seconds(ttl_seconds, name="ttl_seconds")
        now = _normalize_datetime(at or self._now_provider())
        payload = self._load_registry()
        lease = self._find_bound_lease(
            payload,
            lease_token=lease_token,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
        )
        self._require_active_or_raise(lease)

        if self._is_expired(lease, now=now):
            lease["status"] = "EXPIRED"
            lease["updated_at"] = now.isoformat()
            self._save_registry(payload, updated_at=now)
            raise LeaseRegistryError("lease is expired and cannot renew")

        lease["last_heartbeat_at"] = now.isoformat()
        lease["expiry"] = (now + timedelta(seconds=ttl)).isoformat()
        lease["updated_at"] = now.isoformat()
        self._save_registry(payload, updated_at=now)
        return _copy_json(lease)

    def release(
        self,
        *,
        lease_token: str,
        task_id: str,
        run_id: str,
        step_id: str,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        now = _normalize_datetime(at or self._now_provider())
        payload = self._load_registry()
        lease = self._find_bound_lease(
            payload,
            lease_token=lease_token,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
        )

        lease["status"] = "RELEASED"
        lease["updated_at"] = now.isoformat()
        self._save_registry(payload, updated_at=now)
        self._sync_lane_ownership_lifecycle(lease)
        return _copy_json(lease)

    def takeover(
        self,
        *,
        lease_token: str,
        task_id: str,
        run_id: str,
        step_id: str,
        successor_thread_id: str,
        successor_pid: int,
        ttl_seconds: int | None = None,
        at: datetime | None = None,
    ) -> dict[str, Any] | None:
        now = _normalize_datetime(at or self._now_provider())
        payload = self._load_registry()
        lease = self._find_bound_lease(
            payload,
            lease_token=lease_token,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
        )
        if lease.get("status") != "ACTIVE":
            return None

        if self._is_expired(lease, now=now):
            lease["status"] = "EXPIRED"
            lease["updated_at"] = now.isoformat()
            self._save_registry(payload, updated_at=now)
            return None

        self._apply_takeover(
            lease,
            successor_thread_id=successor_thread_id,
            successor_pid=successor_pid,
            at=now,
            ttl_seconds=ttl_seconds,
        )
        self._save_registry(payload, updated_at=now)
        self._sync_lane_ownership_lifecycle(lease)
        return _copy_json(lease)

    def takeover_running_leases(
        self,
        *,
        task_id: str,
        run_id: str,
        successor_thread_id: str,
        successor_pid: int,
        ttl_seconds: int | None = None,
        at: datetime | None = None,
    ) -> LeaseTakeoverBatchResult:
        self._expect_non_empty_text(task_id, name="task_id")
        self._expect_non_empty_text(run_id, name="run_id")
        now = _normalize_datetime(at or self._now_provider())

        payload = self._load_registry()
        adopted: list[dict[str, Any]] = []
        non_adopted: list[dict[str, Any]] = []
        mutated = False

        for lease in payload["leases"]:
            if lease.get("task_id") != task_id or lease.get("run_id") != run_id:
                continue
            if lease.get("status") != "ACTIVE":
                continue

            if self._is_expired(lease, now=now):
                lease["status"] = "EXPIRED"
                lease["updated_at"] = now.isoformat()
                non_adopted.append(_copy_json(lease))
                mutated = True
                continue

            self._apply_takeover(
                lease,
                successor_thread_id=successor_thread_id,
                successor_pid=successor_pid,
                at=now,
                ttl_seconds=ttl_seconds,
            )
            adopted.append(_copy_json(lease))
            mutated = True

        if mutated:
            self._save_registry(payload, updated_at=now)
            for lease in adopted:
                self._sync_lane_ownership_lifecycle(lease)
            for lease in non_adopted:
                self._sync_lane_ownership_lifecycle(lease)

        return LeaseTakeoverBatchResult(
            adopted_leases=tuple(adopted),
            non_adopted_leases=tuple(non_adopted),
        )

    def list_leases(
        self,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        payload = self._load_registry()
        records = payload["leases"]

        if task_id is not None:
            self._expect_non_empty_text(task_id, name="task_id")
            records = [lease for lease in records if lease.get("task_id") == task_id]
        if run_id is not None:
            self._expect_non_empty_text(run_id, name="run_id")
            records = [lease for lease in records if lease.get("run_id") == run_id]

        return [_copy_json(lease) for lease in records]

    def _apply_takeover(
        self,
        lease: dict[str, Any],
        *,
        successor_thread_id: str,
        successor_pid: int,
        at: datetime,
        ttl_seconds: int | None,
    ) -> None:
        self._expect_non_empty_text(successor_thread_id, name="successor_thread_id")
        if isinstance(successor_pid, bool) or not isinstance(successor_pid, int) or successor_pid <= 0:
            raise LeaseRegistryError("successor_pid must be a positive integer")

        lease["thread_id"] = successor_thread_id
        lease["pid"] = successor_pid
        lease["lease_token"] = self._new_token()
        lease["last_heartbeat_at"] = at.isoformat()
        lease["updated_at"] = at.isoformat()

        if ttl_seconds is not None:
            ttl = self._expect_positive_seconds(ttl_seconds, name="ttl_seconds")
            lease["expiry"] = (at + timedelta(seconds=ttl)).isoformat()

    def _ensure_registry(self) -> None:
        if self._leases_path.exists():
            if not self._leases_path.is_file():
                raise LeaseRegistryError(
                    f"expected lease registry file at '{self._leases_path}'"
                )
            return

        now = _normalize_datetime(self._now_provider())
        payload = {
            "schema_version": "1.0.0",
            "leases": [],
            "updated_at": now.isoformat(),
        }
        self._leases_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _load_registry(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._leases_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LeaseRegistryError("process_leases.json is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise LeaseRegistryError("process_leases.json root must be an object")
        leases = payload.get("leases")
        if not isinstance(leases, list):
            raise LeaseRegistryError("process_leases.json field 'leases' must be a list")

        normalized = {
            "schema_version": str(payload.get("schema_version") or "1.0.0"),
            "leases": leases,
            "updated_at": str(payload.get("updated_at") or _normalize_datetime(self._now_provider()).isoformat()),
        }
        return normalized

    def _save_registry(self, payload: Mapping[str, Any], *, updated_at: datetime) -> None:
        persisted = _copy_json(dict(payload))
        persisted["schema_version"] = "1.0.0"
        persisted["updated_at"] = _normalize_datetime(updated_at).isoformat()
        self._leases_path.write_text(json.dumps(persisted, indent=2) + "\n", encoding="utf-8")

    def _find_bound_lease(
        self,
        payload: Mapping[str, Any],
        *,
        lease_token: str,
        task_id: str,
        run_id: str,
        step_id: str,
    ) -> dict[str, Any]:
        self._expect_non_empty_text(lease_token, name="lease_token")
        self._expect_non_empty_text(task_id, name="task_id")
        self._expect_non_empty_text(run_id, name="run_id")
        self._expect_non_empty_text(step_id, name="step_id")

        for candidate in payload["leases"]:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("lease_token") != lease_token:
                continue
            if (
                candidate.get("task_id") == task_id
                and candidate.get("run_id") == run_id
                and candidate.get("step_id") == step_id
            ):
                return candidate
            break

        raise LeaseRegistryError("lease token is not bound to the provided task/run/step")

    def _require_active_or_raise(self, lease: Mapping[str, Any]) -> None:
        status = lease.get("status")
        if status != "ACTIVE":
            raise LeaseRegistryError(f"lease is not ACTIVE (status={status!r})")

    def _is_expired(self, lease: Mapping[str, Any], *, now: datetime) -> bool:
        raw_expiry = lease.get("expiry")
        if not isinstance(raw_expiry, str) or not raw_expiry.strip():
            raise LeaseRegistryError("lease expiry must be an ISO timestamp")
        expiry = _normalize_datetime(datetime.fromisoformat(raw_expiry))
        return expiry <= _normalize_datetime(now)

    def _new_token(self) -> str:
        return f"lease_{uuid4().hex}"

    def _expect_positive_seconds(self, value: int, *, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise LeaseRegistryError(f"{name} must be a positive integer")
        return value

    def _expect_non_empty_text(self, value: str, *, name: str) -> str:
        if not isinstance(value, str):
            raise LeaseRegistryError(f"{name} must be a string")
        normalized = value.strip()
        if not normalized:
            raise LeaseRegistryError(f"{name} must be non-empty")
        return normalized

    def _normalize_lane(self, lane: str) -> str:
        normalized = self._expect_non_empty_text(lane, name="lane")
        if normalized.lower() in {"default", "controller"}:
            return "controller"
        return normalized

    def _sync_lane_ownership_lifecycle(self, lease: Mapping[str, Any]) -> None:
        lane = self._normalize_optional_text(lease.get("lane"))
        step_id = self._normalize_optional_text(lease.get("step_id"))
        task_id = self._normalize_optional_text(lease.get("task_id"))
        run_id = self._normalize_optional_text(lease.get("run_id"))
        lease_status = self._normalize_optional_text(lease.get("status"))
        if None in {lane, step_id, task_id, run_id, lease_status}:
            return

        state = self.state_store.load_state()
        if state.get("task_id") != task_id or state.get("run_id") != run_id:
            return

        lifecycle = state.get("role_lifecycle")
        if not isinstance(lifecycle, dict):
            lifecycle = {}
            state["role_lifecycle"] = lifecycle

        changed = False
        if lease_status == "ACTIVE":
            changed = self._set_lifecycle_field(lifecycle, "controller_lane", lane) or changed
            changed = (
                self._set_lifecycle_field(
                    lifecycle,
                    "controller_ownership",
                    f"{lane}:{step_id}",
                )
                or changed
            )
            changed = self._set_lifecycle_field(
                lifecycle,
                f"lane:{lane}",
                f"active_step:{step_id}",
            ) or changed
            changed = self._set_lifecycle_field(
                lifecycle,
                f"step:{step_id}",
                f"owned_by_lane:{lane}",
            ) or changed
            if state.get("current_step") is None:
                state["current_step"] = step_id
                changed = True
        else:
            changed = self._set_lifecycle_field(
                lifecycle,
                f"step:{step_id}",
                f"lease_{lease_status.lower()}:{lane}",
            ) or changed
            if lifecycle.get("controller_ownership") == f"{lane}:{step_id}":
                changed = (
                    self._set_lifecycle_field(
                        lifecycle,
                        "controller_ownership",
                        f"{lane}:unassigned",
                    )
                    or changed
                )

        if not changed:
            return

        pipeline_status = self._normalize_optional_text(state.get("status")) or "PLANNING"
        self.state_store.save_state(
            state,
            node="lease_lifecycle_sync",
            from_status=pipeline_status,
            to_status=pipeline_status,
        )

    def _set_lifecycle_field(self, lifecycle: dict[str, Any], key: str, value: str) -> bool:
        if lifecycle.get(key) == value:
            return False
        lifecycle[key] = value
        return True

    def _normalize_optional_text(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))
