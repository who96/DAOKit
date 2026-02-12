from __future__ import annotations

import hashlib
import json
import posixpath
from typing import Any, Mapping

from contracts.plan_contracts import CompiledPlan, PlanContractError, StepContract


class PlanCompilationError(ValueError):
    """Raised when the input payload cannot be compiled into strict step contracts."""


def compile_plan(payload: Mapping[str, Any]) -> CompiledPlan:
    if not isinstance(payload, Mapping):
        raise PlanCompilationError("plan payload must be an object")

    goal = _expect_non_empty_string(payload.get("goal"), path="goal")
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise PlanCompilationError("steps must be a non-empty list")

    try:
        steps = [StepContract.from_mapping(step, index=index) for index, step in enumerate(raw_steps)]
    except PlanContractError as exc:
        raise PlanCompilationError(str(exc)) from exc

    external_dependencies = _parse_external_dependencies(payload.get("dependencies"))
    _assert_unique_step_ids(steps)
    _assert_no_conflicting_expected_outputs(steps)
    _assert_no_dependency_contradictions(steps, external_dependencies=external_dependencies)

    task_id = _resolve_task_id(payload=payload, goal=goal, steps=steps)
    run_id = _resolve_run_id(payload=payload, task_id=task_id, goal=goal, steps=steps)
    return CompiledPlan(task_id=task_id, run_id=run_id, goal=goal, steps=tuple(steps))


def compile_plan_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return compile_plan(payload).to_dispatch_payload()


def _resolve_task_id(*, payload: Mapping[str, Any], goal: str, steps: list[StepContract]) -> str:
    provided = payload.get("task_id")
    if provided is not None:
        return _expect_non_empty_string(provided, path="task_id")

    digest = _stable_hash({"goal": goal, "steps": [step.to_dispatch_dict() for step in steps]})
    return f"TASK-{digest[:12]}"


def _resolve_run_id(
    *,
    payload: Mapping[str, Any],
    task_id: str,
    goal: str,
    steps: list[StepContract],
) -> str:
    provided = payload.get("run_id")
    if provided is not None:
        return _expect_non_empty_string(provided, path="run_id")

    digest = _stable_hash(
        {
            "task_id": task_id,
            "goal": goal,
            "steps": [step.to_dispatch_dict() for step in steps],
        }
    )
    return f"{task_id}_{digest[12:24]}"


def _expect_non_empty_string(value: Any, *, path: str) -> str:
    if not isinstance(value, str):
        raise PlanCompilationError(f"{path} must be a string")
    normalized = value.strip()
    if not normalized:
        raise PlanCompilationError(f"{path} must be a non-empty string")
    return normalized


def _assert_unique_step_ids(steps: list[StepContract]) -> None:
    seen: set[str] = set()
    for step in steps:
        if step.id in seen:
            raise PlanCompilationError(f"duplicate step id '{step.id}'")
        seen.add(step.id)


def _assert_no_conflicting_expected_outputs(steps: list[StepContract]) -> None:
    owners: dict[str, tuple[str, str]] = {}
    for step in steps:
        for output in step.expected_outputs:
            normalized = _normalize_output_key(output)
            if normalized in owners:
                previous_step, previous_output = owners[normalized]
                raise PlanCompilationError(
                    "expected output conflict across multiple steps: "
                    f"{previous_step}:{previous_output} vs {step.id}:{output}"
                )
            owners[normalized] = (step.id, output)


def _assert_no_dependency_contradictions(
    steps: list[StepContract],
    *,
    external_dependencies: set[str],
) -> None:
    step_ids = {step.id for step in steps}
    dependencies_by_step: dict[str, tuple[str, ...]] = {}

    for step in steps:
        for dependency in step.dependencies:
            if dependency == step.id:
                raise PlanCompilationError(f"step '{step.id}' cannot depend on itself")
            if dependency not in step_ids and dependency not in external_dependencies:
                raise PlanCompilationError(
                    f"step '{step.id}' depends on unknown step '{dependency}'"
                )
        dependencies_by_step[step.id] = tuple(dep for dep in step.dependencies if dep in step_ids)

    dependents: dict[str, list[str]] = {step.id: [] for step in steps}
    in_degree: dict[str, int] = {}
    for step_id, dependencies in dependencies_by_step.items():
        in_degree[step_id] = len(dependencies)
        for dependency in dependencies:
            dependents[dependency].append(step_id)

    ready = sorted(step_id for step_id, degree in in_degree.items() if degree == 0)
    processed = 0
    while ready:
        current = ready.pop(0)
        processed += 1
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                ready.append(dependent)
        ready.sort()

    if processed != len(steps):
        blocked = sorted(step_id for step_id, degree in in_degree.items() if degree > 0)
        rendered = ", ".join(blocked)
        raise PlanCompilationError(f"dependency cycle detected: {rendered}")


def _stable_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest.upper()


def _parse_external_dependencies(value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list):
        raise PlanCompilationError("dependencies must be a list of strings when provided")

    dependencies: set[str] = set()
    for index, item in enumerate(value):
        normalized = _expect_non_empty_string(item, path=f"dependencies[{index}]")
        dependencies.add(normalized)
    return dependencies


def _normalize_output_key(value: str) -> str:
    normalized = value.replace("\\", "/")
    return posixpath.normpath(normalized)
