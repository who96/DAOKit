"""Scenario runners for reliability validation workflows."""

from typing import Any

from .core_rotation_chaos_matrix import (
    CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG,
    CORE_ROTATION_HIGH_RISK_PATHS,
    CORE_ROTATION_MATRIX_VERSION,
    DEFAULT_DETERMINISTIC_CONSTRAINTS,
    CoreRotationChaosScenarioFixture,
    DeterministicExecutionConstraints,
    get_core_rotation_chaos_scenario,
    get_default_core_rotation_chaos_scenario,
    list_core_rotation_chaos_scenarios,
    summarize_core_rotation_chaos_matrix,
)

__all__ = [
    "CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG",
    "CORE_ROTATION_HIGH_RISK_PATHS",
    "CORE_ROTATION_MATRIX_VERSION",
    "DEFAULT_DETERMINISTIC_CONSTRAINTS",
    "CoreRotationChaosScenarioFixture",
    "DeterministicExecutionConstraints",
    "get_core_rotation_chaos_scenario",
    "get_default_core_rotation_chaos_scenario",
    "list_core_rotation_chaos_scenarios",
    "summarize_core_rotation_chaos_matrix",
    "run_core_rotation_chaos_matrix",
    "run_integrated_reliability_scenario",
]


def run_core_rotation_chaos_matrix(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .integrated_reliability import run_core_rotation_chaos_matrix as _runner

    return _runner(*args, **kwargs)


def run_integrated_reliability_scenario(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .integrated_reliability import run_integrated_reliability_scenario as _runner

    return _runner(*args, **kwargs)
