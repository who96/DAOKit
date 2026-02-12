from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reliability.handoff import HandoffPackageStore

from .compaction import compact_observer_relay_context
from .runtime import HookPoint, HookRuntime


@dataclass(frozen=True)
class CoreRotationHandoffHooks:
    """Bridge pre-compact/session-start hooks to handoff package operations."""

    handoff_store: HandoffPackageStore
    include_accepted_steps: bool = False

    def on_pre_compact(
        self,
        ledger_state: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        compact_observer_relay_context(ledger_state=ledger_state, context=context)
        evidence_paths = context.get("evidence_paths")
        package = self.handoff_store.write_package(
            ledger_state,
            evidence_paths=evidence_paths if isinstance(evidence_paths, list) else None,
            include_accepted_steps=self._resolve_include_accepted(context),
        )
        lifecycle = _ensure_lifecycle(ledger_state)
        lifecycle["handoff_package_path"] = self.handoff_store.package_path.as_posix()
        lifecycle["handoff_package_hash"] = str(package["package_hash"])
        context["handoff_package"] = package

    def on_session_start(
        self,
        ledger_state: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        if self.handoff_store.load_package() is None:
            return

        resume = self.handoff_store.apply_package(
            ledger_state,
            include_accepted_steps=self._resolve_include_accepted(context),
        )
        lifecycle = _ensure_lifecycle(ledger_state)
        lifecycle["handoff_resume_step"] = resume.resume_step_id or "none"
        lifecycle["handoff_next_action"] = resume.next_action
        context["handoff_resume"] = resume.to_dict()

    def _resolve_include_accepted(self, context: dict[str, Any]) -> bool:
        raw = context.get("include_accepted_steps")
        if raw is None:
            return self.include_accepted_steps
        return bool(raw)


def register_core_rotation_hooks(
    runtime: HookRuntime,
    *,
    handoff_store: HandoffPackageStore,
    include_accepted_steps: bool = False,
) -> CoreRotationHandoffHooks:
    """Register deterministic handoff package hooks for core rotation."""

    hooks = CoreRotationHandoffHooks(
        handoff_store=handoff_store,
        include_accepted_steps=include_accepted_steps,
    )
    runtime.register(
        hook_point=HookPoint.PRE_COMPACT.value,
        hook_name="core-rotation-handoff#pre-compact",
        callback=hooks.on_pre_compact,
        idempotent=True,
    )
    runtime.register(
        hook_point=HookPoint.SESSION_START.value,
        hook_name="core-rotation-handoff#session-start",
        callback=hooks.on_session_start,
        idempotent=True,
    )
    return hooks


def _ensure_lifecycle(ledger_state: dict[str, Any]) -> dict[str, str]:
    raw = ledger_state.get("role_lifecycle")
    if isinstance(raw, dict):
        if all(isinstance(key, str) and isinstance(value, str) for key, value in raw.items()):
            return raw

    lifecycle = {"orchestrator": "running"}
    ledger_state["role_lifecycle"] = lifecycle
    return lifecycle
