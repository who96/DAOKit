from __future__ import annotations

import json
import re
from typing import Any, Callable, Mapping

from state.relay_policy import (
    REQUIRED_RELAY_CONTEXT_FIELDS,
    RelayModePolicy,
)


_STALE_EXECUTION_STATUSES = {
    "accepted",
    "completed",
    "done",
    "resolved",
    "success",
}
_NOISE_PATH_TOKENS = (
    "api_error_dump",
    "stacktrace",
    "stderr",
    "stdout",
    "traceback",
)
_NOISE_TEXT_TOKENS = (
    "<html",
    "api error dump",
    "stacktrace",
    "traceback",
)
_ERROR_CODE_PATTERN = re.compile(r"\bE_[A-Z0-9_]+\b")
_ROUTE_REQUIRED_FIELDS = (
    "task_id",
    "run_id",
    "active_lane",
    "active_step",
    "next_action",
)


def compact_observer_relay_context(
    *,
    ledger_state: Mapping[str, Any],
    context: dict[str, Any],
) -> None:
    """Apply deterministic keep/drop hygiene for observer relay compaction."""

    _compact_relay_context(ledger_state=ledger_state, context=context)
    _compact_list_field(context, "execution_logs", _normalize_execution_log)
    _compact_list_field(context, "status_reports", _normalize_status_report)
    _compact_list_field(context, "failure_noise", _normalize_failure_noise)
    _compact_list_field(context, "api_error_dumps", _normalize_api_error_dump)
    _compact_evidence_paths(context)


def _compact_relay_context(*, ledger_state: Mapping[str, Any], context: dict[str, Any]) -> None:
    source = context.get("relay_context")
    relay_context: dict[str, Any] = {}
    if isinstance(source, Mapping):
        relay_context.update(_copy_json(dict(source)))

    for field in REQUIRED_RELAY_CONTEXT_FIELDS:
        if field in relay_context:
            continue
        if field in ledger_state:
            relay_context[field] = _copy_json(ledger_state[field])

    policy = RelayModePolicy(relay_mode_enabled=True)
    try:
        context["relay_context"] = policy.preserve_relay_context(relay_context)
        return
    except Exception:
        pass

    fallback: dict[str, Any] = {}
    goal = relay_context.get("goal")
    if isinstance(goal, str) and goal.strip():
        fallback["goal"] = goal.strip()

    constraints = relay_context.get("constraints")
    if isinstance(constraints, list):
        normalized_constraints = _normalized_string_list(constraints)
        if normalized_constraints:
            fallback["constraints"] = normalized_constraints

    latest_instruction = relay_context.get("latest_instruction")
    if isinstance(latest_instruction, str) and latest_instruction.strip():
        fallback["latest_instruction"] = latest_instruction.strip()

    blockers = relay_context.get("current_blockers")
    if isinstance(blockers, list):
        normalized_blockers = _normalized_string_list(blockers)
        if normalized_blockers:
            fallback["current_blockers"] = normalized_blockers

    route = relay_context.get("controller_route_summary")
    if isinstance(route, Mapping):
        normalized_route: dict[str, str] = {}
        for field in _ROUTE_REQUIRED_FIELDS:
            value = route.get(field)
            if isinstance(value, str) and value.strip():
                normalized_route[field] = value.strip()
        if normalized_route:
            fallback["controller_route_summary"] = normalized_route

    if fallback:
        context["relay_context"] = fallback
    else:
        context.pop("relay_context", None)


def _compact_list_field(
    context: dict[str, Any],
    key: str,
    normalizer: Callable[[Any], Any | None],
) -> None:
    raw = context.get(key)
    if raw is None:
        return
    if not isinstance(raw, list):
        context.pop(key, None)
        return

    compacted: list[Any] = []
    seen: set[str] = set()
    for item in raw:
        normalized = normalizer(item)
        if normalized is None:
            continue
        dedup_key = _stable_fingerprint(normalized)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        compacted.append(normalized)

    if compacted:
        context[key] = compacted
    else:
        context.pop(key, None)


def _normalize_execution_log(entry: Any) -> Any | None:
    if not isinstance(entry, Mapping):
        return None
    normalized = _normalize_mapping(entry)
    status = normalized.get("status")
    if isinstance(status, str) and status.strip().lower() in _STALE_EXECUTION_STATUSES:
        return None
    if normalized.get("stale") is True:
        return None
    return normalized


def _normalize_status_report(entry: Any) -> Any | None:
    if not isinstance(entry, Mapping):
        return None
    normalized = _normalize_mapping(entry)
    if normalized.get("stale") is True:
        return None
    return normalized


def _normalize_failure_noise(entry: Any) -> Any | None:
    if not isinstance(entry, Mapping):
        return None
    normalized = _normalize_mapping(entry)
    if normalized.get("resolved") is True:
        return None
    if normalized.get("stale") is True:
        return None
    return normalized


def _normalize_api_error_dump(entry: Any) -> Any | None:
    if isinstance(entry, str):
        message = entry.strip()
        if not message:
            return None
        if _is_garbage_api_error(message) and not _ERROR_CODE_PATTERN.search(message):
            return None
        return {"message": message}

    if not isinstance(entry, Mapping):
        return None

    normalized = _normalize_mapping(entry)
    message = normalized.get("message")
    message_text = message.strip() if isinstance(message, str) else ""
    has_structured_signal = any(
        key in normalized for key in ("code", "hint", "reason_code", "retryable", "status")
    )
    if message_text and _is_garbage_api_error(message_text) and not has_structured_signal:
        return None
    if not has_structured_signal and not message_text:
        return None
    return normalized


def _compact_evidence_paths(context: dict[str, Any]) -> None:
    raw = context.get("evidence_paths")
    if raw is None:
        return
    if not isinstance(raw, list):
        context.pop("evidence_paths", None)
        return

    compacted: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if any(token in lowered for token in _NOISE_PATH_TOKENS):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        compacted.append(normalized)

    if compacted:
        context["evidence_paths"] = compacted
    else:
        context.pop("evidence_paths", None)


def _normalized_string_list(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text:
            continue
        normalized.append(text)
    return normalized


def _normalize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            normalized[key] = text
            continue
        if isinstance(item, Mapping):
            normalized[key] = _normalize_mapping(item)
            continue
        if isinstance(item, list):
            normalized[key] = _copy_json(item)
            continue
        normalized[key] = item
    return normalized


def _is_garbage_api_error(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in _NOISE_TEXT_TOKENS)


def _stable_fingerprint(value: Any) -> str:
    return json.dumps(_copy_json(value), sort_keys=True, separators=(",", ":"))


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))
