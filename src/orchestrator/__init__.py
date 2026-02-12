"""Orchestrator runtime primitives for DAOKit."""

from .engine import RuntimeEngine, RuntimeEngineError, create_runtime, resolve_runtime_engine
from .state_machine import IllegalTransitionError, OrchestratorStatus, guard_transition

__all__ = [
    "IllegalTransitionError",
    "OrchestratorRuntime",
    "OrchestratorStatus",
    "RuntimeEngine",
    "RuntimeEngineError",
    "create_runtime",
    "guard_transition",
    "resolve_runtime_engine",
]


def __getattr__(name: str):
    if name == "OrchestratorRuntime":
        from .runtime import OrchestratorRuntime

        return OrchestratorRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
