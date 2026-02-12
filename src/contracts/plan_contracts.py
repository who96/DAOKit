from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REQUIRED_STEP_FIELDS = (
    "goal",
    "actions",
    "acceptance_criteria",
    "expected_outputs",
    "dependencies",
)


class PlanContractError(ValueError):
    """Raised when planner payload cannot be normalized into step contracts."""


def _expect_mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PlanContractError(f"{path} must be an object")
    return value


def _expect_non_empty_string(value: Any, *, path: str) -> str:
    if not isinstance(value, str):
        raise PlanContractError(f"{path} must be a string")
    normalized = value.strip()
    if not normalized:
        raise PlanContractError(f"{path} must be a non-empty string")
    return normalized


def _expect_string_list(
    value: Any,
    *,
    path: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PlanContractError(f"{path} must be a list of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        entry_path = f"{path}[{index}]"
        text = _expect_non_empty_string(item, path=entry_path)
        if text in seen:
            raise PlanContractError(f"{path} must not contain duplicate entries")
        normalized.append(text)
        seen.add(text)

    if not allow_empty and not normalized:
        raise PlanContractError(f"{path} must contain at least 1 entry")
    return tuple(normalized)


@dataclass(frozen=True)
class StepContract:
    id: str
    title: str
    category: str
    goal: str
    actions: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    dependencies: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw_step: Any, *, index: int) -> "StepContract":
        step = _expect_mapping(raw_step, path=f"steps[{index}]")

        for field in REQUIRED_STEP_FIELDS:
            if field not in step:
                raise PlanContractError(f"steps[{index}] missing required field '{field}'")

        step_id = (
            _expect_non_empty_string(step["id"], path=f"steps[{index}].id")
            if "id" in step
            else f"S{index + 1}"
        )
        title = (
            _expect_non_empty_string(step["title"], path=f"steps[{index}].title")
            if "title" in step
            else f"Step {index + 1}"
        )
        category = (
            _expect_non_empty_string(step["category"], path=f"steps[{index}].category")
            if "category" in step
            else "implementation"
        )
        goal = _expect_non_empty_string(step["goal"], path=f"steps[{index}].goal")
        actions = _expect_string_list(
            step["actions"],
            path=f"steps[{index}].actions",
            allow_empty=False,
        )
        acceptance_criteria = _expect_string_list(
            step["acceptance_criteria"],
            path=f"steps[{index}].acceptance_criteria",
            allow_empty=False,
        )
        expected_outputs = _expect_string_list(
            step["expected_outputs"],
            path=f"steps[{index}].expected_outputs",
            allow_empty=False,
        )
        dependencies = _expect_string_list(
            step["dependencies"],
            path=f"steps[{index}].dependencies",
            allow_empty=True,
        )
        return cls(
            id=step_id,
            title=title,
            category=category,
            goal=goal,
            actions=actions,
            acceptance_criteria=acceptance_criteria,
            expected_outputs=expected_outputs,
            dependencies=dependencies,
        )

    def to_dispatch_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "goal": self.goal,
            "actions": list(self.actions),
            "acceptance_criteria": list(self.acceptance_criteria),
            "expected_outputs": list(self.expected_outputs),
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True)
class CompiledPlan:
    task_id: str
    run_id: str
    goal: str
    steps: tuple[StepContract, ...]

    def to_dispatch_payload(self) -> dict[str, Any]:
        step_payload = [step.to_dispatch_dict() for step in self.steps]
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "goal": self.goal,
            "steps": step_payload,
            "step_index": {step["id"]: index for index, step in enumerate(step_payload)},
        }
