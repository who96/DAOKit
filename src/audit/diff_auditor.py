from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .scope_guard import ScopeGuardError, normalize_relative_path, normalize_scope, path_is_allowed


@dataclass(frozen=True)
class DiffAuditResult:
    allowed_scope: tuple[str, ...]
    changed_files: tuple[str, ...]
    violating_files: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return len(self.violating_files) == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "allowed_scope": list(self.allowed_scope),
            "changed_files": list(self.changed_files),
            "violating_files": list(self.violating_files),
        }


def _normalize_changed_files(changed_files: Sequence[str]) -> tuple[str, ...]:
    if isinstance(changed_files, str) or not isinstance(changed_files, Sequence):
        raise ScopeGuardError("changed_files must be a list of relative file paths")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(changed_files):
        path = normalize_relative_path(item, name=f"changed_files[{index}]")
        if path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return tuple(normalized)


def audit_changed_files(
    *,
    changed_files: Sequence[str],
    allowed_scope: Sequence[str],
) -> DiffAuditResult:
    normalized_scope = normalize_scope(allowed_scope)
    normalized_changed = _normalize_changed_files(changed_files)
    violating = tuple(
        path for path in normalized_changed if not path_is_allowed(path, normalized_scope)
    )
    return DiffAuditResult(
        allowed_scope=normalized_scope,
        changed_files=normalized_changed,
        violating_files=violating,
    )


def build_audit_summary(
    result: DiffAuditResult,
    *,
    task_id: str,
    step_id: str,
) -> str:
    lines = [
        "# Audit Summary",
        f"- task_id: {task_id}",
        f"- step_id: {step_id}",
        "",
        "## Allowed Scope",
    ]
    lines.extend(f"- `{entry}`" for entry in result.allowed_scope)

    lines.extend(["", "## Changed Files"])
    lines.extend(f"- `{entry}`" for entry in result.changed_files)

    lines.extend(["", "## Result"])
    if result.passed:
        lines.append("PASS: all changed files are inside allowed scope.")
    else:
        lines.append("FAIL: found violating files outside allowed scope.")

    lines.append("")
    lines.append("### Violating Files")
    if result.violating_files:
        lines.extend(f"- `{entry}`" for entry in result.violating_files)
    else:
        lines.append("- (none)")

    lines.append("")
    return "\n".join(lines)
