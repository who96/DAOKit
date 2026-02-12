from __future__ import annotations

from pathlib import PurePosixPath
from typing import Iterable, Sequence


class ScopeGuardError(ValueError):
    """Raised when scope policy inputs are invalid."""


def _expect_non_empty_string(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise ScopeGuardError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ScopeGuardError(f"{name} must be a non-empty string")
    return normalized


def normalize_relative_path(path: str, *, name: str = "path") -> str:
    raw = _expect_non_empty_string(path, name=name).replace("\\", "/")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute():
        raise ScopeGuardError(f"{name} must be a relative path: {path}")

    normalized_parts: list[str] = []
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ScopeGuardError(f"{name} cannot contain parent traversal: {path}")
        normalized_parts.append(part)

    if not normalized_parts:
        raise ScopeGuardError(f"{name} must contain at least one path segment")

    return "/".join(normalized_parts)


def normalize_scope_entry(entry: str, *, name: str = "allowed_scope entry") -> str:
    raw = _expect_non_empty_string(entry, name=name)
    is_directory = raw.endswith("/")
    normalized = normalize_relative_path(raw, name=name)
    if is_directory:
        return f"{normalized}/"
    return normalized


def normalize_scope(allowed_scope: Iterable[str]) -> tuple[str, ...]:
    if isinstance(allowed_scope, str) or not isinstance(allowed_scope, Iterable):
        raise ScopeGuardError("allowed_scope must be a list of path entries")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(allowed_scope):
        normalized_entry = normalize_scope_entry(
            entry,
            name=f"allowed_scope[{index}]",
        )
        if normalized_entry in seen:
            continue
        seen.add(normalized_entry)
        normalized.append(normalized_entry)

    if not normalized:
        raise ScopeGuardError("allowed_scope must contain at least one entry")

    return tuple(normalized)


def _matches_scope(path: str, scope_entry: str) -> bool:
    if scope_entry.endswith("/"):
        return path.startswith(scope_entry)
    return path == scope_entry or path.startswith(f"{scope_entry}/")


def path_is_allowed(path: str, allowed_scope: Sequence[str]) -> bool:
    normalized_path = normalize_relative_path(path, name="changed_files entry")
    normalized_scope = normalize_scope(allowed_scope)
    return any(_matches_scope(normalized_path, entry) for entry in normalized_scope)
