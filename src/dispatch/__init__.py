"""Dispatch primitives for subagent shim execution."""

from .shim_adapter import DispatchCallResult, DispatchError, ShimDispatchAdapter

__all__ = ["DispatchCallResult", "DispatchError", "LLMDispatchAdapter", "ShimDispatchAdapter"]


def __getattr__(name: str):
    if name == "LLMDispatchAdapter":
        from .llm_adapter import LLMDispatchAdapter

        return LLMDispatchAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
