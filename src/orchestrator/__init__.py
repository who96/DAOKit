"""Orchestrator runtime primitives for DAOKit."""

from .engine import (
    DispatchBackend,
    RuntimeEngine,
    RuntimeEngineError,
    ToolOrchestrationEngine,
    create_dispatch_adapter,
    create_runtime,
    create_tool_orchestration_layer,
    resolve_dispatch_backend,
    resolve_runtime_engine,
    resolve_tool_orchestration_engine,
)
from .state_machine import IllegalTransitionError, OrchestratorStatus, guard_transition

__all__ = [
    "IllegalTransitionError",
    "OrchestratorRuntime",
    "OrchestratorStatus",
    "DispatchBackend",
    "RuntimeEngine",
    "RuntimeEngineError",
    "ToolOrchestrationEngine",
    "create_dispatch_adapter",
    "create_runtime",
    "create_tool_orchestration_layer",
    "guard_transition",
    "resolve_dispatch_backend",
    "resolve_runtime_engine",
    "resolve_tool_orchestration_engine",
]


def __getattr__(name: str):
    if name == "OrchestratorRuntime":
        from .runtime import OrchestratorRuntime

        return OrchestratorRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
