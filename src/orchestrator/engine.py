from __future__ import annotations

import importlib
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

from contracts.runtime_adapters import RuntimeRelayPolicy, RuntimeRetriever
from state.backend import StateBackend
from tools.common.optional_dependencies import OptionalDependencyError, import_optional_dependency

if TYPE_CHECKING:
    from rag.retrieval import RetrievalPolicyConfig
    from .runtime import RuntimeDispatchAdapter


DEFAULT_DISPATCH_MAX_RESUME_RETRIES = 1
DEFAULT_DISPATCH_MAX_REWORK_ATTEMPTS = 1


ENV_RUNTIME_ENGINE = "DAOKIT_RUNTIME_ENGINE"
ENV_TOOL_ORCHESTRATION_ENGINE = "DAOKIT_TOOL_ORCHESTRATION_ENGINE"
ENV_ENGINE_MODE = "DAOKIT_ENGINE_MODE"
CONFIG_RUNTIME_ENGINE_PATHS = (
    ("runtime", "engine"),
    ("runtime", "mode"),
)
CONFIG_TOOL_ORCHESTRATION_ENGINE_PATHS = (
    ("runtime", "tool_orchestration_engine"),
    ("runtime", "mode"),
)


class RuntimeEngine(str, Enum):
    LEGACY = "legacy"
    LANGGRAPH = "langgraph"


class ToolOrchestrationEngine(str, Enum):
    LEGACY = "legacy"
    LANGCHAIN = "langchain"


class RuntimeEngineError(ValueError):
    """Raised when runtime engine selection or bootstrap fails."""


ImportModule = Callable[[str], Any]
LegacyRuntimeFactory = Callable[..., Any]
LangGraphRuntimeFactory = Callable[..., Any]


def resolve_runtime_engine(
    *,
    explicit_engine: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> RuntimeEngine:
    source = explicit_engine
    if source is None and env is not None:
        source = env.get(ENV_RUNTIME_ENGINE)
    if source is None and env is not None:
        source = env.get(ENV_ENGINE_MODE)
    if source is None:
        source = _read_config_string(
            config,
            path_candidates=CONFIG_RUNTIME_ENGINE_PATHS,
        )
    normalized = "legacy" if source is None else source.strip().lower()

    if normalized == RuntimeEngine.LEGACY.value:
        return RuntimeEngine.LEGACY
    if normalized in (RuntimeEngine.LANGGRAPH.value, "integrated"):
        return RuntimeEngine.LANGGRAPH

    raise RuntimeEngineError(
        "unsupported runtime engine "
        f"'{normalized}'. Supported values: legacy, langgraph, integrated."
    )


def create_runtime(
    *,
    task_id: str,
    run_id: str,
    goal: str,
    state_store: StateBackend,
    step_id: str = "S1",
    retriever: RuntimeRetriever | None = None,
    retrieval_index_path: str | Path | None = None,
    default_retrieval_policies: Mapping[str, RetrievalPolicyConfig] | None = None,
    relay_policy: RuntimeRelayPolicy | None = None,
    dispatch_adapter: RuntimeDispatchAdapter | None = None,
    dispatch_max_resume_retries: int = DEFAULT_DISPATCH_MAX_RESUME_RETRIES,
    dispatch_max_rework_attempts: int = DEFAULT_DISPATCH_MAX_REWORK_ATTEMPTS,
    llm_client: Any | None = None,
    workspace_base_dir: str | Path | None = None,
    explicit_engine: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
    import_module: ImportModule | None = None,
    legacy_runtime_factory: LegacyRuntimeFactory | None = None,
    langgraph_runtime_factory: LangGraphRuntimeFactory | None = None,
) -> Any:
    selected_engine = resolve_runtime_engine(
        explicit_engine=explicit_engine,
        env=env,
        config=config,
    )
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
            dispatch_adapter=dispatch_adapter,
            dispatch_max_resume_retries=dispatch_max_resume_retries,
            dispatch_max_rework_attempts=dispatch_max_rework_attempts,
            llm_client=llm_client,
            workspace_base_dir=workspace_base_dir,
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
        dispatch_adapter=dispatch_adapter,
        dispatch_max_resume_retries=dispatch_max_resume_retries,
        dispatch_max_rework_attempts=dispatch_max_rework_attempts,
        llm_client=llm_client,
        workspace_base_dir=workspace_base_dir,
        langgraph_available=dependencies_available,
        missing_optional_dependencies=missing_optional_dependencies,
        import_module=import_module,
    )


def resolve_tool_orchestration_engine(
    *,
    explicit_mode: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> ToolOrchestrationEngine:
    source = explicit_mode
    if source is None and env is not None:
        source = env.get(ENV_TOOL_ORCHESTRATION_ENGINE)
    if source is None and env is not None:
        source = env.get(ENV_ENGINE_MODE)
    if source is None:
        source = _read_config_string(
            config,
            path_candidates=CONFIG_TOOL_ORCHESTRATION_ENGINE_PATHS,
        )
    normalized = "legacy" if source is None else source.strip().lower()

    if normalized == ToolOrchestrationEngine.LEGACY.value:
        return ToolOrchestrationEngine.LEGACY
    if normalized in (ToolOrchestrationEngine.LANGCHAIN.value, "integrated"):
        return ToolOrchestrationEngine.LANGCHAIN

    raise RuntimeEngineError(
        "unsupported tool orchestration engine "
        f"'{normalized}'. Supported values: legacy, langchain, integrated."
    )


def create_tool_orchestration_layer(
    *,
    function_calling_adapter: Any,
    mcp_adapter: Any,
    hook_runtime: Any | None = None,
    skill_loader: Any | None = None,
    explicit_mode: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
    allow_fallback_when_unavailable: bool = True,
    import_module: ImportModule | None = None,
) -> Any:
    from tools.langchain.orchestration import ToolOrchestrationLayer

    selected_mode = resolve_tool_orchestration_engine(
        explicit_mode=explicit_mode,
        env=env,
        config=config,
    )
    return ToolOrchestrationLayer(
        function_calling_adapter=function_calling_adapter,
        mcp_adapter=mcp_adapter,
        hook_runtime=hook_runtime,
        skill_loader=skill_loader,
        requested_mode=selected_mode.value,
        allow_fallback_when_unavailable=allow_fallback_when_unavailable,
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


def _read_config_string(
    config: Mapping[str, Any] | None,
    *,
    path_candidates: tuple[tuple[str, ...], ...],
) -> str | None:
    for path in path_candidates:
        value = _get_nested_config_value(config, path=path)
        if value is not None:
            return value
    return None


def _get_nested_config_value(config: Mapping[str, Any] | None, *, path: tuple[str, ...]) -> str | None:
    node: Any = config
    for token in path:
        if not isinstance(node, dict):
            return None
        if token not in node:
            return None
        node = node[token]
    if isinstance(node, str):
        return node
    return None


# ---- Dispatch backend resolution ----

ENV_DISPATCH_BACKEND = "DAOKIT_DISPATCH_BACKEND"
CONFIG_DISPATCH_BACKEND_PATHS = (
    ("dispatch", "backend"),
    ("runtime", "dispatch_backend"),
)


class DispatchBackend(str, Enum):
    SHIM = "shim"
    LLM = "llm"


def resolve_dispatch_backend(
    *,
    explicit_backend: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> DispatchBackend:
    """Resolve which dispatch backend to use. Default: shim."""
    source = explicit_backend
    if source is None and env is not None:
        source = env.get(ENV_DISPATCH_BACKEND)
    if source is None:
        source = _read_config_string(
            config,
            path_candidates=CONFIG_DISPATCH_BACKEND_PATHS,
        )
    normalized = "shim" if source is None else source.strip().lower()
    if normalized == DispatchBackend.SHIM.value:
        return DispatchBackend.SHIM
    if normalized == DispatchBackend.LLM.value:
        return DispatchBackend.LLM
    raise RuntimeEngineError(
        f"unsupported dispatch backend '{normalized}'. "
        f"Supported values: shim, llm."
    )


def create_dispatch_adapter(
    *,
    artifact_store: Any,
    shim_path: str | Path = "codex-worker-shim",
    shim_command_prefix: tuple[str, ...] | None = None,
    command_runner: Any | None = None,
    relay_policy: Any | None = None,
    llm_client: Any | None = None,
    llm_system_prompt: str | None = None,
    workspace: Any | None = None,
    tool_orchestration_layer: Any | None = None,
    explicit_llm_api_key: str | None = None,
    explicit_llm_base_url: str | None = None,
    explicit_llm_model: str | None = None,
    explicit_backend: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> RuntimeDispatchAdapter:
    selected_backend = resolve_dispatch_backend(
        explicit_backend=explicit_backend,
        env=env,
        config=config,
    )
    if selected_backend == DispatchBackend.SHIM:
        from dispatch.shim_adapter import ShimDispatchAdapter

        return ShimDispatchAdapter(
            shim_path=shim_path,
            shim_command_prefix=shim_command_prefix,
            artifact_store=artifact_store,
            command_runner=command_runner,
            relay_policy=relay_policy,
        )

    from dispatch.llm_adapter import LLMDispatchAdapter

    tools_schema: list[dict[str, Any]] | None = None
    active_tool_layer = tool_orchestration_layer
    if workspace is not None:
        from tools.agent_tools import agent_tools_openai_schema, register_agent_tools
        from tools.function_calling.adapter import FunctionCallingAdapter
        from tools.mcp.adapter import McpAdapter

        if active_tool_layer is None:
            function_calling_adapter = FunctionCallingAdapter()
            register_agent_tools(function_calling_adapter, workspace)
            active_tool_layer = create_tool_orchestration_layer(
                function_calling_adapter=function_calling_adapter,
                mcp_adapter=McpAdapter(),
                env=env,
                config=config,
            )
            tools_schema = agent_tools_openai_schema(function_calling_adapter)
        else:
            adapters = getattr(active_tool_layer, "adapters", None)
            function_calling_adapter = getattr(adapters, "function_calling", None)
            if function_calling_adapter is not None:
                tools_schema = agent_tools_openai_schema(function_calling_adapter)

    if llm_client is None:
        from llm.client import LLMClient, resolve_llm_config

        llm_config = resolve_llm_config(
            explicit_api_key=explicit_llm_api_key,
            explicit_base_url=explicit_llm_base_url,
            explicit_model=explicit_llm_model,
            env=env,
            config=config,
        )
        llm_client = LLMClient(llm_config)
    return LLMDispatchAdapter(
        llm_client=llm_client,
        artifact_store=artifact_store,
        relay_policy=relay_policy,
        system_prompt=llm_system_prompt,
        tool_orchestration_layer=active_tool_layer,
        tools_schema=tools_schema,
    )
