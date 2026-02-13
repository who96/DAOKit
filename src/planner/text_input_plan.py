from __future__ import annotations

import re
from typing import Any


def _normalize_goal(goal: str) -> str:
    normalized = goal.strip()
    return normalized if normalized else "Complete the requested text task"


def _parse_step_index(step_id: str) -> int:
    match = re.fullmatch(r"S(\d+)", step_id.strip())
    if match is None:
        return 1
    return max(int(match.group(1)), 1)


def _next_step_id(base_index: int, offset: int) -> str:
    return f"S{base_index + offset}"


def build_minimal_text_input_steps(*, goal: str, step_id: str = "S1") -> tuple[dict[str, Any], ...]:
    """Build a bounded, executable 3-step plan from plain text task input."""
    normalized_goal = _normalize_goal(goal)
    base_index = _parse_step_index(step_id)

    first_step_id = _next_step_id(base_index, 0)
    second_step_id = _next_step_id(base_index, 1)
    third_step_id = _next_step_id(base_index, 2)

    return (
        {
            "id": first_step_id,
            "title": "Extract actionable scope from text input",
            "category": "analysis",
            "goal": f"Translate text input into an executable implementation scope: {normalized_goal}",
            "actions": [
                "Identify the smallest deliverable that satisfies the user request",
                "Capture explicit constraints and non-goals from the text input",
            ],
            "acceptance_criteria": [
                "Task scope is concrete and implementation-ready",
                "Constraints and exclusions are explicit",
            ],
            "expected_outputs": [
                "planning/scope-summary.md",
            ],
            "dependencies": [],
            "planner_source": "text_input_minimal_v1",
        },
        {
            "id": second_step_id,
            "title": "Implement the minimal viable change set",
            "category": "implementation",
            "goal": f"Implement the bounded solution for: {normalized_goal}",
            "actions": [
                "Apply focused code changes for the requested behavior",
                "Preserve compatibility constraints and existing public CLI surface",
            ],
            "acceptance_criteria": [
                "Requested behavior is implemented end-to-end",
                "Compatibility constraints remain non-breaking",
            ],
            "expected_outputs": [
                "implementation/change-set.patch",
            ],
            "dependencies": [first_step_id],
            "planner_source": "text_input_minimal_v1",
        },
        {
            "id": third_step_id,
            "title": "Verify and capture auditable evidence",
            "category": "verification",
            "goal": "Verify outcomes and capture reproducible validation evidence",
            "actions": [
                "Run validation commands required by repository standards",
                "Record evidence paths and acceptance status for auditability",
            ],
            "acceptance_criteria": [
                "Validation commands complete with auditable outputs",
                "Acceptance status is explicit and reproducible",
            ],
            "expected_outputs": [
                "report.md",
                "verification.log",
                "audit-summary.md",
            ],
            "dependencies": [second_step_id],
            "planner_source": "text_input_minimal_v1",
        },
    )
