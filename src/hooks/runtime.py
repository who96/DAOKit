from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from time import monotonic
from typing import Any, Callable, Mapping

from skills.loader import LoadedSkill, SkillLoaderError, resolve_skill_handler


class HookRuntimeError(ValueError):
    """Raised when hook registration or execution input is invalid."""


class HookPoint(str, Enum):
    PRE_DISPATCH = "pre-dispatch"
    POST_ACCEPT = "post-accept"
    PRE_COMPACT = "pre-compact"
    SESSION_START = "session-start"

    @classmethod
    def parse(cls, value: str) -> "HookPoint":
        normalized = _expect_non_empty_string(value, name="hook_point").replace("_", "-").lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            known = ", ".join(point.value for point in HookPoint)
            raise HookRuntimeError(
                f"unknown hook point '{value}'. expected one of: {known}"
            ) from exc


HookCallback = Callable[[dict[str, Any], dict[str, Any]], Any]


@dataclass(frozen=True)
class HookExecutionEntry:
    hook_name: str
    hook_point: str
    status: str
    duration_seconds: float
    error: str | None


@dataclass(frozen=True)
class HookRunResult:
    hook_point: str
    idempotency_key: str | None
    status: str
    ledger_state: dict[str, Any]
    entries: tuple[HookExecutionEntry, ...]
    started_at: str
    finished_at: str


@dataclass(frozen=True)
class _RegisteredHook:
    hook_name: str
    hook_point: HookPoint
    callback: HookCallback
    timeout_seconds: float | None
    idempotent: bool


class HookRuntime:
    """Lifecycle hook engine with idempotency and transactional ledger protection."""

    def __init__(self, *, default_timeout_seconds: float | None = None) -> None:
        self._default_timeout_seconds = _normalize_optional_timeout(
            default_timeout_seconds,
            name="default_timeout_seconds",
        )
        self._hooks: dict[HookPoint, list[_RegisteredHook]] = {
            point: [] for point in HookPoint
        }
        self._execution_logs: list[HookRunResult] = []
        self._idempotency_cache: dict[tuple[str, str, str], dict[str, Any]] = {}

    def register(
        self,
        *,
        hook_point: str,
        hook_name: str,
        callback: HookCallback,
        timeout_seconds: float | None = None,
        idempotent: bool = True,
    ) -> None:
        point = HookPoint.parse(hook_point)
        normalized_name = _expect_non_empty_string(hook_name, name="hook_name")
        if not callable(callback):
            raise HookRuntimeError("callback must be callable")
        if not isinstance(idempotent, bool):
            raise HookRuntimeError("idempotent must be boolean")
        normalized_timeout = _normalize_optional_timeout(timeout_seconds, name="timeout_seconds")

        already_registered = {
            item.hook_name for item in self._hooks[point]
        }
        if normalized_name in already_registered:
            raise HookRuntimeError(
                f"hook '{normalized_name}' is already registered at point '{point.value}'"
            )

        self._hooks[point].append(
            _RegisteredHook(
                hook_name=normalized_name,
                hook_point=point,
                callback=callback,
                timeout_seconds=normalized_timeout,
                idempotent=idempotent,
            )
        )

    def register_skill(self, loaded_skill: LoadedSkill) -> None:
        for index, hook in enumerate(loaded_skill.manifest.hooks):
            try:
                callback = resolve_skill_handler(loaded_skill, hook.handler)
            except SkillLoaderError as exc:
                raise HookRuntimeError(str(exc)) from exc
            self.register(
                hook_point=hook.event,
                hook_name=f"{loaded_skill.manifest.name}#{index}",
                callback=callback,
                timeout_seconds=hook.timeout_seconds,
                idempotent=hook.idempotent,
            )

    def run(
        self,
        *,
        hook_point: str,
        ledger_state: Mapping[str, Any],
        context: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        timeout_budget_seconds: float | None = None,
    ) -> HookRunResult:
        point = HookPoint.parse(hook_point)
        original_ledger = _copy_value(dict(ledger_state))
        working_ledger = _copy_value(original_ledger)
        working_context = _copy_value(dict(context or {}))
        normalized_idempotency_key = (
            None
            if idempotency_key is None
            else _expect_non_empty_string(idempotency_key, name="idempotency_key")
        )
        timeout_budget = _normalize_optional_timeout(
            timeout_budget_seconds,
            name="timeout_budget_seconds",
        )

        entries: list[HookExecutionEntry] = []
        pending_cache: list[tuple[tuple[str, str, str], dict[str, Any]]] = []
        started_at = _utc_now()
        run_started = monotonic()
        run_status = "success"

        for hook in self._hooks[point]:
            elapsed_before = monotonic() - run_started
            if timeout_budget is not None and elapsed_before >= timeout_budget:
                entries.append(
                    HookExecutionEntry(
                        hook_name=hook.hook_name,
                        hook_point=point.value,
                        status="timeout_budget_exceeded",
                        duration_seconds=0.0,
                        error=(
                            f"timeout budget exceeded before executing hook "
                            f"'{hook.hook_name}'"
                        ),
                    )
                )
                run_status = "timeout"
                break

            cache_key: tuple[str, str, str] | None = None
            if normalized_idempotency_key is not None and hook.idempotent:
                cache_key = (point.value, hook.hook_name, normalized_idempotency_key)
                cached_ledger = self._idempotency_cache.get(cache_key)
                if cached_ledger is not None:
                    working_ledger = _copy_value(cached_ledger)
                    entries.append(
                        HookExecutionEntry(
                            hook_name=hook.hook_name,
                            hook_point=point.value,
                            status="skipped",
                            duration_seconds=0.0,
                            error=None,
                        )
                    )
                    continue

            remaining_budget = (
                None
                if timeout_budget is None
                else max(timeout_budget - elapsed_before, 0.0)
            )
            effective_timeout = _effective_timeout(
                hook_timeout=hook.timeout_seconds,
                default_timeout=self._default_timeout_seconds,
                remaining_budget=remaining_budget,
            )

            started = monotonic()
            try:
                hook.callback(working_ledger, working_context)
            except Exception as exc:
                entries.append(
                    HookExecutionEntry(
                        hook_name=hook.hook_name,
                        hook_point=point.value,
                        status="error",
                        duration_seconds=max(monotonic() - started, 0.0),
                        error=f"{exc.__class__.__name__}: {exc}",
                    )
                )
                run_status = "error"
                break

            duration = max(monotonic() - started, 0.0)
            if effective_timeout is not None and duration > effective_timeout:
                entries.append(
                    HookExecutionEntry(
                        hook_name=hook.hook_name,
                        hook_point=point.value,
                        status="timeout",
                        duration_seconds=duration,
                        error=(
                            f"hook '{hook.hook_name}' exceeded timeout of "
                            f"{effective_timeout:.6f}s"
                        ),
                    )
                )
                run_status = "timeout"
                break

            entries.append(
                HookExecutionEntry(
                    hook_name=hook.hook_name,
                    hook_point=point.value,
                    status="success",
                    duration_seconds=duration,
                    error=None,
                )
            )
            if cache_key is not None:
                pending_cache.append((cache_key, _copy_value(working_ledger)))

        if run_status == "success":
            for key, cached in pending_cache:
                self._idempotency_cache[key] = _copy_value(cached)
            final_ledger = working_ledger
        else:
            final_ledger = original_ledger

        finished_at = _utc_now()
        result = HookRunResult(
            hook_point=point.value,
            idempotency_key=normalized_idempotency_key,
            status=run_status,
            ledger_state=final_ledger,
            entries=tuple(entries),
            started_at=started_at,
            finished_at=finished_at,
        )
        self._execution_logs.append(result)
        return result

    def list_registered(self, *, hook_point: str | None = None) -> tuple[str, ...]:
        if hook_point is None:
            names = [
                hook.hook_name
                for point in HookPoint
                for hook in self._hooks[point]
            ]
            return tuple(names)
        point = HookPoint.parse(hook_point)
        return tuple(hook.hook_name for hook in self._hooks[point])

    def execution_logs(self) -> tuple[HookRunResult, ...]:
        return tuple(self._execution_logs)


def _effective_timeout(
    *,
    hook_timeout: float | None,
    default_timeout: float | None,
    remaining_budget: float | None,
) -> float | None:
    timeout = hook_timeout if hook_timeout is not None else default_timeout
    if timeout is None:
        return remaining_budget
    if remaining_budget is None:
        return timeout
    return min(timeout, remaining_budget)


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise HookRuntimeError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise HookRuntimeError(f"{name} must be a non-empty string")
    return normalized


def _normalize_optional_timeout(value: Any, *, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HookRuntimeError(f"{name} must be a positive number")
    timeout = float(value)
    if timeout <= 0:
        raise HookRuntimeError(f"{name} must be > 0")
    return timeout


def _copy_value(value: Any) -> Any:
    return copy.deepcopy(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
