from __future__ import annotations

import importlib
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from contracts.runtime_adapters import RuntimeRelayPolicy, RuntimeRetriever, RuntimeStateStore
from rag.retrieval import RetrievalPolicyConfig
from tools.common.optional_dependencies import OptionalDependencyError, import_optional_dependency


ENV_RUNTIME_ENGINE = "DAOKIT_RUNTIME_ENGINE"


class RuntimeEngine(str, Enum):
    LEGACY = "legacy"
    LANGGRAPH = "langgraph"


class RuntimeEngineError(ValueError):
    """Raised when runtime engine selection or bootstrap fails."""


ImportModule = Callable[[str], Any]
LegacyRuntimeFactory = Callable[..., Any]
LangGraphRuntimeFactory = Callable[..., Any]


def resolve_runtime_engine(
    *,
    explicit_engine: str | None = None,
    env: Mapping[str, str] | None = None,
) -> RuntimeEngine:
    source = explicit_engine
    if source is None and env is not None:
        source = env.get(ENV_RUNTIME_ENGINE)
    normalized = "legacy" if source is None else source.strip().lower()

    if normalized == RuntimeEngine.LEGACY.value:
        return RuntimeEngine.LEGACY
    if normalized == RuntimeEngine.LANGGRAPH.value:
        return RuntimeEngine.LANGGRAPH

    raise RuntimeEngineError(
        f"unsupported runtime engine '{normalized}'. Supported values: legacy, langgraph."
    )


def create_runtime(
    *,
    task_id: str,
    run_id: str,
    goal: str,
    state_store: RuntimeStateStore,
    step_id: str = "S1",
    retriever: RuntimeRetriever | None = None,
    retrieval_index_path: str | Path | None = None,
    default_retrieval_policies: Mapping[str, RetrievalPolicyConfig] | None = None,
    relay_policy: RuntimeRelayPolicy | None = None,
    explicit_engine: str | None = None,
    env: Mapping[str, str] | None = None,
    import_module: ImportModule | None = None,
    legacy_runtime_factory: LegacyRuntimeFactory | None = None,
    langgraph_runtime_factory: LangGraphRuntimeFactory | None = None,
) -> Any:
    selected_engine = resolve_runtime_engine(explicit_engine=explicit_engine, env=env)
    if selected_engine == RuntimeEngine.LEGACY:
        factory = legacy_runtime_factory or _build_legacy_runtime
        return factory(
            task_id=task_id,
            run_id=run_id,
            goal=goal,
            state_store=state_store,
            step_id=step_id,
            retriever=retriever,
            retrieval_index_path=retrieval_index_path,
            default_retrieval_policies=default_retrieval_policies,
            relay_policy=relay_policy,
        )

    dependencies_available, missing_optional_dependencies = _inspect_langgraph_optional_dependencies(
        import_module=import_module
    )
    factory = langgraph_runtime_factory or _build_langgraph_runtime
    return factory(
        task_id=task_id,
        run_id=run_id,
        goal=goal,
        state_store=state_store,
        step_id=step_id,
        retriever=retriever,
        retrieval_index_path=retrieval_index_path,
        default_retrieval_policies=default_retrieval_policies,
        relay_policy=relay_policy,
        langgraph_available=dependencies_available,
        missing_optional_dependencies=missing_optional_dependencies,
        import_module=import_module,
    )


def _build_legacy_runtime(**kwargs: Any) -> Any:
    from orchestrator.runtime import OrchestratorRuntime

    return OrchestratorRuntime(**kwargs)


def _build_langgraph_runtime(**kwargs: Any) -> Any:
    from orchestrator.langgraph_runtime import LangGraphOrchestratorRuntime

    return LangGraphOrchestratorRuntime(**kwargs)


def _inspect_langgraph_optional_dependencies(
    *,
    import_module: ImportModule | None,
) -> tuple[bool, tuple[str, ...]]:
    importer = import_module or importlib.import_module
    missing_modules: list[str] = []
    for module_name in ("langchain", "langgraph"):
        try:
            import_optional_dependency(
                module_name,
                feature_name="langgraph runtime",
                extras_hint="pip install 'daokit[integration]'",
                import_module=importer,
            )
        except OptionalDependencyError:
            missing_modules.append(module_name)
    return len(missing_modules) == 0, tuple(missing_modules)
