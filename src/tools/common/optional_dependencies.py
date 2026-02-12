from __future__ import annotations

import importlib
from typing import Any, Callable


ImportModule = Callable[[str], Any]


class OptionalDependencyError(ImportError):
    """Raised when an optional dependency is required but unavailable."""


def is_dependency_available(
    module_name: str,
    *,
    import_module: ImportModule | None = None,
) -> bool:
    importer = import_module or importlib.import_module
    try:
        importer(module_name)
    except ModuleNotFoundError:
        return False
    return True


def import_optional_dependency(
    module_name: str,
    *,
    feature_name: str,
    extras_hint: str,
    import_module: ImportModule | None = None,
) -> Any:
    importer = import_module or importlib.import_module
    try:
        return importer(module_name)
    except ModuleNotFoundError as exc:
        raise OptionalDependencyError(
            f"{feature_name} requires optional dependency '{module_name}', "
            f"but it is not installed. Install with: {extras_hint}"
        ) from exc
