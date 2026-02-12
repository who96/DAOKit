from __future__ import annotations

from enum import Enum


class OrchestratorStatus(str, Enum):
    PLANNING = "PLANNING"
    ANALYSIS = "ANALYSIS"
    FREEZE = "FREEZE"
    EXECUTE = "EXECUTE"
    ACCEPT = "ACCEPT"
    DONE = "DONE"
    DRAINING = "DRAINING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


ALLOWED_TRANSITIONS: dict[OrchestratorStatus, tuple[OrchestratorStatus, ...]] = {
    OrchestratorStatus.PLANNING: (OrchestratorStatus.ANALYSIS,),
    OrchestratorStatus.ANALYSIS: (OrchestratorStatus.FREEZE,),
    OrchestratorStatus.FREEZE: (OrchestratorStatus.EXECUTE,),
    OrchestratorStatus.EXECUTE: (
        OrchestratorStatus.ACCEPT,
        OrchestratorStatus.DRAINING,
    ),
    OrchestratorStatus.ACCEPT: (
        OrchestratorStatus.DONE,
        OrchestratorStatus.EXECUTE,
    ),
    OrchestratorStatus.DRAINING: (
        OrchestratorStatus.EXECUTE,
        OrchestratorStatus.BLOCKED,
    ),
    OrchestratorStatus.BLOCKED: (OrchestratorStatus.EXECUTE,),
    OrchestratorStatus.DONE: (),
    OrchestratorStatus.FAILED: (),
}


NODE_TRANSITIONS: dict[str, tuple[OrchestratorStatus, OrchestratorStatus]] = {
    "extract": (OrchestratorStatus.PLANNING, OrchestratorStatus.ANALYSIS),
    "plan": (OrchestratorStatus.ANALYSIS, OrchestratorStatus.FREEZE),
    "dispatch": (OrchestratorStatus.FREEZE, OrchestratorStatus.EXECUTE),
    "verify": (OrchestratorStatus.EXECUTE, OrchestratorStatus.ACCEPT),
    "transition": (OrchestratorStatus.ACCEPT, OrchestratorStatus.DONE),
}


STATUS_TO_NODE: dict[OrchestratorStatus, str] = {
    source: node_name for node_name, (source, _target) in NODE_TRANSITIONS.items()
}


class IllegalTransitionError(RuntimeError):
    """Raised when a state transition violates the deterministic transition table."""


def parse_status(value: str) -> OrchestratorStatus:
    try:
        return OrchestratorStatus(value)
    except ValueError as exc:
        known = ", ".join(status.value for status in OrchestratorStatus)
        raise IllegalTransitionError(
            f"Unknown orchestrator status '{value}'. Known statuses: {known}"
        ) from exc


def guard_transition(
    *,
    current: OrchestratorStatus,
    target: OrchestratorStatus,
    trigger: str,
) -> None:
    allowed_targets = ALLOWED_TRANSITIONS[current]
    if target in allowed_targets:
        return
    allowed = ", ".join(item.value for item in allowed_targets) or "<none>"
    raise IllegalTransitionError(
        f"Illegal transition via '{trigger}': {current.value} -> {target.value}. "
        f"Allowed targets from {current.value}: {allowed}."
    )

