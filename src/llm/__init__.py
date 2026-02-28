"""LLM client module for DAOKit with OpenAI-compatible API support."""

__all__ = ["LLMCallError", "LLMClient", "LLMCompletionResult", "LLMConfig", "resolve_llm_config"]


def __getattr__(name: str):
    if name in __all__:
        from llm.client import (
            LLMCallError,
            LLMClient,
            LLMCompletionResult,
            LLMConfig,
            resolve_llm_config,
        )

        globals().update(
            LLMCallError=LLMCallError,
            LLMClient=LLMClient,
            LLMCompletionResult=LLMCompletionResult,
            LLMConfig=LLMConfig,
            resolve_llm_config=resolve_llm_config,
        )
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
