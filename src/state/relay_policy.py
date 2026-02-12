from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping


REQUIRED_RELAY_CONTEXT_FIELDS = (
    "goal",
    "constraints",
    "latest_instruction",
    "current_blockers",
    "controller_route_summary",
)

REQUIRED_CONTROLLER_ROUTE_FIELDS = (
    "task_id",
    "run_id",
    "active_lane",
    "active_step",
    "next_action",
)

DEFAULT_ALLOWED_RELAY_ACTIONS = (
    "forward",
    "observe",
    "visualize",
)


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _require_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise RelayPolicyError(f"{name} must be a string")
    return value


def _require_string_list(value: Any, *, name: str) -> list[str]:
    if not isinstance(value, list):
        raise RelayPolicyError(f"{name} must be a list")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise RelayPolicyError(f"{name}[{index}] must be a string")
        normalized.append(item)
    return normalized


class RelayPolicyError(RuntimeError):
    """Raised when relay-mode guardrails reject an action or context payload."""


@dataclass(frozen=True)
class RelayModePolicy:
    relay_mode_enabled: bool = False
    allowed_relay_actions: tuple[str, ...] = DEFAULT_ALLOWED_RELAY_ACTIONS

    def guard_action(self, *, action: str) -> None:
        normalized_action = self._normalize_action(action)
        if not self.relay_mode_enabled:
            return
        if normalized_action in self.allowed_relay_actions:
            return
        allowed = ", ".join(self.allowed_relay_actions)
        raise RelayPolicyError(
            f"relay mode blocks execution action '{normalized_action}'; "
            f"allowed relay actions: {allowed}"
        )

    def preserve_relay_context(self, relay_context: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(relay_context, Mapping):
            raise RelayPolicyError("relay context must be an object")

        missing = [
            field for field in REQUIRED_RELAY_CONTEXT_FIELDS if field not in relay_context
        ]
        if missing:
            raise RelayPolicyError(
                "relay context missing required fields: " + ", ".join(sorted(missing))
            )

        goal = _require_string(relay_context["goal"], name="relay_context.goal")
        latest_instruction = _require_string(
            relay_context["latest_instruction"],
            name="relay_context.latest_instruction",
        )
        constraints = _require_string_list(
            relay_context["constraints"],
            name="relay_context.constraints",
        )
        current_blockers = _require_string_list(
            relay_context["current_blockers"],
            name="relay_context.current_blockers",
        )

        raw_route_summary = relay_context["controller_route_summary"]
        if not isinstance(raw_route_summary, Mapping):
            raise RelayPolicyError("relay_context.controller_route_summary must be an object")

        missing_route = [
            field for field in REQUIRED_CONTROLLER_ROUTE_FIELDS if field not in raw_route_summary
        ]
        if missing_route:
            raise RelayPolicyError(
                "relay_context.controller_route_summary missing required fields: "
                + ", ".join(sorted(missing_route))
            )

        route_summary = dict(raw_route_summary)
        for field in REQUIRED_CONTROLLER_ROUTE_FIELDS:
            route_summary[field] = _require_string(
                route_summary[field],
                name=f"relay_context.controller_route_summary.{field}",
            )

        return {
            "goal": goal,
            "constraints": _copy_json(constraints),
            "latest_instruction": latest_instruction,
            "current_blockers": _copy_json(current_blockers),
            "controller_route_summary": _copy_json(route_summary),
        }

    def build_relay_payload(
        self,
        *,
        action: str,
        relay_context: Mapping[str, Any],
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_action = self._normalize_action(action)
        self.guard_action(action=normalized_action)
        normalized_payload: Mapping[str, Any] = payload or {}
        return {
            "mode": "relay" if self.relay_mode_enabled else "controller",
            "action": normalized_action,
            "relay_context": self.preserve_relay_context(relay_context),
            "payload": _copy_json(dict(normalized_payload)),
        }

    @staticmethod
    def _normalize_action(action: str) -> str:
        normalized = _require_string(action, name="action").strip()
        if not normalized:
            raise RelayPolicyError("action must be a non-empty string")
        return normalized
