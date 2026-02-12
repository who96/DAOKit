from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class RuntimeStateStore(Protocol):
    """Engine-agnostic state persistence adapter for orchestrator runtimes."""

    def load_state(self) -> dict[str, Any]: ...

    def save_state(
        self,
        state: Mapping[str, Any],
        *,
        node: str,
        from_status: str | None,
        to_status: str | None,
    ) -> dict[str, Any]: ...

    def append_event(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str | None,
        event_type: str,
        severity: str,
        payload: Mapping[str, Any],
        dedup_key: str | None,
    ) -> None: ...


@runtime_checkable
class RuntimeRetriever(Protocol):
    """Engine-agnostic retrieval adapter used during planning/verification."""

    def retrieve(
        self,
        *,
        use_case: str,
        query: str,
        task_id: str | None,
        run_id: str | None,
        policy: Any,
    ) -> Any: ...


@runtime_checkable
class RuntimeRelayPolicy(Protocol):
    """Engine-agnostic relay boundary adapter."""

    def guard_action(self, *, action: str) -> None: ...

    def build_relay_payload(
        self,
        *,
        action: str,
        relay_context: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...
