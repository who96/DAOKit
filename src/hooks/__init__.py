from .runtime import (
    HookExecutionEntry,
    HookPoint,
    HookRunResult,
    HookRuntime,
    HookRuntimeError,
)

__all__ = [
    "HookExecutionEntry",
    "HookPoint",
    "HookRunResult",
    "HookRuntime",
    "HookRuntimeError",
    "CoreRotationHandoffHooks",
    "register_core_rotation_hooks",
]


def __getattr__(name: str):
    if name in {"CoreRotationHandoffHooks", "register_core_rotation_hooks"}:
        from .handoff import CoreRotationHandoffHooks, register_core_rotation_hooks

        mapping = {
            "CoreRotationHandoffHooks": CoreRotationHandoffHooks,
            "register_core_rotation_hooks": register_core_rotation_hooks,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
