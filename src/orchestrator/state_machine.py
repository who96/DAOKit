from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping


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

    def __init__(self, message: str, *, diagnostics: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


RoutePredicate = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class ConditionalRoute:
    route_id: str
    target: OrchestratorStatus
    reason: str
    predicate_name: str
    predicate: RoutePredicate


@dataclass(frozen=True)
class ConditionalRouteDecision:
    node_name: str
    current: OrchestratorStatus
    target: OrchestratorStatus
    route_id: str
    reason: str
    predicate_name: str


def _always(_state: Mapping[str, Any]) -> bool:
    return True


def _acceptance_failed(state: Mapping[str, Any]) -> bool:
    lifecycle = state.get("role_lifecycle")
    if not isinstance(lifecycle, Mapping):
        return False
    outcome = lifecycle.get("acceptance")
    if not isinstance(outcome, str):
        return False
    normalized = outcome.strip().lower()
    return normalized in {"failed", "fail", "rejected", "rework_required"}


def _acceptance_not_failed(state: Mapping[str, Any]) -> bool:
    return not _acceptance_failed(state)


CONDITIONAL_ROUTES: dict[str, tuple[ConditionalRoute, ...]] = {
    "extract": (
        ConditionalRoute(
            route_id="extract.default.analysis",
            target=OrchestratorStatus.ANALYSIS,
            reason="extract_completed",
            predicate_name="always",
            predicate=_always,
        ),
    ),
    "plan": (
        ConditionalRoute(
            route_id="plan.default.freeze",
            target=OrchestratorStatus.FREEZE,
            reason="plan_completed",
            predicate_name="always",
            predicate=_always,
        ),
    ),
    "dispatch": (
        ConditionalRoute(
            route_id="dispatch.default.execute",
            target=OrchestratorStatus.EXECUTE,
            reason="dispatch_completed",
            predicate_name="always",
            predicate=_always,
        ),
    ),
    "verify": (
        ConditionalRoute(
            route_id="verify.default.accept",
            target=OrchestratorStatus.ACCEPT,
            reason="verify_completed",
            predicate_name="always",
            predicate=_always,
        ),
    ),
    "transition": (
        ConditionalRoute(
            route_id="transition.acceptance_failed.rework",
            target=OrchestratorStatus.EXECUTE,
            reason="acceptance_failed_rework",
            predicate_name="acceptance_failed",
            predicate=_acceptance_failed,
        ),
        ConditionalRoute(
            route_id="transition.acceptance_not_failed.done",
            target=OrchestratorStatus.DONE,
            reason="acceptance_not_failed_finalize",
            predicate_name="acceptance_not_failed",
            predicate=_acceptance_not_failed,
        ),
    ),
}


def parse_status(value: str) -> OrchestratorStatus:
    try:
        return OrchestratorStatus(value)
    except ValueError as exc:
        known = ", ".join(status.value for status in OrchestratorStatus)
        raise IllegalTransitionError(
            f"Unknown orchestrator status '{value}'. Known statuses: {known}",
            diagnostics={
                "diagnostic_type": "status_unknown",
                "invalid_status": value,
                "known_statuses": [status.value for status in OrchestratorStatus],
            },
        ) from exc


def guard_transition(
    *,
    current: OrchestratorStatus,
    target: OrchestratorStatus,
    trigger: str,
    route_id: str | None = None,
    route_reason: str | None = None,
    predicate_name: str | None = None,
) -> None:
    allowed_targets = ALLOWED_TRANSITIONS[current]
    if target in allowed_targets:
        return

    allowed = ", ".join(item.value for item in allowed_targets) or "<none>"
    diagnostics: dict[str, Any] = {
        "diagnostic_type": "route_guard_failure",
        "trigger": trigger,
        "current_status": current.value,
        "attempted_target": target.value,
        "allowed_targets": [item.value for item in allowed_targets],
    }
    route_parts: list[str] = []
    if route_id is not None:
        diagnostics["route_id"] = route_id
        route_parts.append(f"route_id={route_id}")
    if route_reason is not None:
        diagnostics["route_reason"] = route_reason
        route_parts.append(f"route_reason={route_reason}")
    if predicate_name is not None:
        diagnostics["predicate_name"] = predicate_name
        route_parts.append(f"predicate={predicate_name}")

    route_suffix = ""
    if route_parts:
        route_suffix = f" Route diagnostics: {', '.join(route_parts)}."

    raise IllegalTransitionError(
        f"Illegal transition via '{trigger}': {current.value} -> {target.value}. "
        f"Allowed targets from {current.value}: {allowed}.{route_suffix} "
        "Action: restore ledger status to an allowed source or execute the correct predecessor node.",
        diagnostics=diagnostics,
    )


def conditional_routes_for_node(node_name: str) -> tuple[ConditionalRoute, ...]:
    routes = CONDITIONAL_ROUTES.get(node_name)
    if routes is not None:
        return routes

    known = ", ".join(sorted(CONDITIONAL_ROUTES))
    raise IllegalTransitionError(
        f"Undefined conditional route policy for node '{node_name}'. Known route nodes: {known}. "
        "Action: add explicit route predicates and reason codes for the node.",
        diagnostics={
            "diagnostic_type": "route_policy_missing",
            "node": node_name,
            "known_route_nodes": sorted(CONDITIONAL_ROUTES),
        },
    )


def resolve_conditional_route(
    *,
    node_name: str,
    current: OrchestratorStatus,
    state: Mapping[str, Any] | None,
) -> ConditionalRouteDecision:
    routes = conditional_routes_for_node(node_name)
    route_state = state if isinstance(state, Mapping) else {}

    matches = [route for route in routes if route.predicate(route_state)]
    if not matches:
        predicate_names = ", ".join(route.predicate_name for route in routes)
        raise IllegalTransitionError(
            f"No conditional route matched for node '{node_name}' at status {current.value}. "
            f"Evaluated predicates: {predicate_names}. "
            "Action: inspect route inputs (for example role_lifecycle markers) and retry with a valid state.",
            diagnostics={
                "diagnostic_type": "route_policy_no_match",
                "node": node_name,
                "current_status": current.value,
                "candidate_routes": [route.route_id for route in routes],
                "evaluated_predicates": [route.predicate_name for route in routes],
            },
        )

    if len(matches) > 1:
        matched_route_ids = [route.route_id for route in matches]
        raise IllegalTransitionError(
            f"Ambiguous conditional routes for node '{node_name}' at status {current.value}: "
            f"{', '.join(matched_route_ids)}. "
            "Action: make route predicates mutually exclusive so exactly one route matches.",
            diagnostics={
                "diagnostic_type": "route_policy_ambiguous",
                "node": node_name,
                "current_status": current.value,
                "matched_routes": matched_route_ids,
            },
        )

    selected = matches[0]
    guard_transition(
        current=current,
        target=selected.target,
        trigger=node_name,
        route_id=selected.route_id,
        route_reason=selected.reason,
        predicate_name=selected.predicate_name,
    )
    return ConditionalRouteDecision(
        node_name=node_name,
        current=current,
        target=selected.target,
        route_id=selected.route_id,
        reason=selected.reason,
        predicate_name=selected.predicate_name,
    )
