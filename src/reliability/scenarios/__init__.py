"""Scenario runners for reliability validation workflows."""

from typing import Any

__all__ = ["run_integrated_reliability_scenario"]


def run_integrated_reliability_scenario(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .integrated_reliability import run_integrated_reliability_scenario as _runner

    return _runner(*args, **kwargs)
