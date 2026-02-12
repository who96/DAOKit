from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import importlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from rag.retrieval import (
    PolicyAwareRetriever,
    RetrievalPolicyConfig,
    RetrievalResult,
    policy_from_mapping,
)
from skills.loader import LoadedSkill, SkillLoader
from tools.common.optional_dependencies import OptionalDependencyError, import_optional_dependency
from tools.function_calling.adapter import FunctionCallingAdapter, ToolInvocationResult
from tools.mcp.adapter import McpAdapter, McpInvocationResult


class ToolOrchestrationError(ValueError):
    """Raised when tool orchestration configuration or execution is invalid."""


ImportModule = Callable[[str], Any]


class ToolOrchestrationMode(str, Enum):
    LEGACY = "legacy"
    LANGCHAIN = "langchain"


class HookRuntimeLike(Protocol):
    def register_skill(self, loaded_skill: LoadedSkill) -> None: ...

    def run(
        self,
        *,
        hook_point: str,
        ledger_state: Mapping[str, Any],
        context: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        timeout_budget_seconds: float | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class ToolAdapterBundle:
    function_calling: FunctionCallingAdapter
    mcp: McpAdapter
    hooks: HookRuntimeLike | None
    skills: SkillLoader | None


@dataclass(frozen=True)
class ToolOrchestrationModeStatus:
    requested_mode: str
    active_mode: str
    fallback_reason: str | None


@dataclass(frozen=True)
class ToolTraceEntry:
    orchestration_mode: str
    adapter: str
    operation: str
    task_id: str
    run_id: str
    step_id: str
    correlation_id: str
    status: str
    payload: dict[str, Any]
    started_at: str
    finished_at: str


class ToolOrchestrationLayer:
    """Adapter-preserving tool orchestration layer with optional LangChain mode."""

    def __init__(
        self,
        *,
        function_calling_adapter: FunctionCallingAdapter,
        mcp_adapter: McpAdapter,
        hook_runtime: HookRuntimeLike | None = None,
        skill_loader: SkillLoader | None = None,
        requested_mode: str = ToolOrchestrationMode.LEGACY.value,
        allow_fallback_when_unavailable: bool = True,
        import_module: ImportModule | None = None,
        retriever: Any | None = None,
        retrieval_index_path: str | Path | None = None,
        default_retrieval_policies: Mapping[str, RetrievalPolicyConfig] | None = None,
    ) -> None:
        self._import_module = import_module or importlib.import_module
        self.adapters = ToolAdapterBundle(
            function_calling=function_calling_adapter,
            mcp=mcp_adapter,
            hooks=hook_runtime,
            skills=skill_loader,
        )
        self.retriever = retriever or PolicyAwareRetriever(index_path=retrieval_index_path)
        self._retrieval_cache: dict[str, RetrievalResult] = {}
        self._default_retrieval_policies = {
            "planning": RetrievalPolicyConfig(
                enabled=True,
                top_k=3,
                min_relevance_score=0.2,
                allow_global_fallback=True,
            ),
            "troubleshooting": RetrievalPolicyConfig(
                enabled=True,
                top_k=3,
                min_relevance_score=0.2,
                allow_global_fallback=True,
            ),
        }
        if default_retrieval_policies is not None:
            self._default_retrieval_policies.update(default_retrieval_policies)
        self._requested_mode = _parse_mode(requested_mode)
        self._trace_logs: list[ToolTraceEntry] = []
        self._fallback_reason: str | None = None
        self._active_mode = self._resolve_mode(
            allow_fallback_when_unavailable=allow_fallback_when_unavailable,
            import_module=self._import_module,
        )

    def mode_status(self) -> ToolOrchestrationModeStatus:
        return ToolOrchestrationModeStatus(
            requested_mode=self._requested_mode.value,
            active_mode=self._active_mode.value,
            fallback_reason=self._fallback_reason,
        )

    def trace_logs(self) -> tuple[ToolTraceEntry, ...]:
        return tuple(self._trace_logs)

    def invoke_function_tool(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        tool_name: str,
        arguments: Mapping[str, Any] | None,
        correlation_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> ToolInvocationResult:
        normalized_task_id = _expect_non_empty_string(task_id, name="task_id")
        normalized_run_id = _expect_non_empty_string(run_id, name="run_id")
        normalized_step_id = _expect_non_empty_string(step_id, name="step_id")
        normalized_tool_name = _expect_non_empty_string(tool_name, name="tool_name")
        normalized_correlation = _resolve_correlation_id(
            correlation_id=correlation_id,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            adapter="fc",
        )

        started_at = _utc_now()
        result = self.adapters.function_calling.invoke(
            tool_name=normalized_tool_name,
            arguments=arguments,
            correlation_id=normalized_correlation,
            timeout_seconds=timeout_seconds,
        )
        finished_at = _utc_now()

        self._append_trace(
            adapter="function-calling",
            operation=normalized_tool_name,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            correlation_id=normalized_correlation,
            status=result.status,
            payload={
                "request": result.request,
                "result": result.result,
                "error": result.error,
                "timed_out": result.timed_out,
            },
            started_at=started_at,
            finished_at=finished_at,
        )
        return result

    def invoke_mcp_tool(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        server_name: str,
        tool_name: str,
        arguments: Mapping[str, Any] | None,
        correlation_id: str | None = None,
        max_retries: int | None = None,
    ) -> McpInvocationResult:
        normalized_task_id = _expect_non_empty_string(task_id, name="task_id")
        normalized_run_id = _expect_non_empty_string(run_id, name="run_id")
        normalized_step_id = _expect_non_empty_string(step_id, name="step_id")
        normalized_server_name = _expect_non_empty_string(server_name, name="server_name")
        normalized_tool_name = _expect_non_empty_string(tool_name, name="tool_name")
        normalized_correlation = _resolve_correlation_id(
            correlation_id=correlation_id,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            adapter="mcp",
        )

        started_at = _utc_now()
        result = self.adapters.mcp.invoke(
            server_name=normalized_server_name,
            tool_name=normalized_tool_name,
            arguments=arguments,
            correlation_id=normalized_correlation,
            max_retries=max_retries,
        )
        finished_at = _utc_now()

        self._append_trace(
            adapter="mcp",
            operation=f"{normalized_server_name}.{normalized_tool_name}",
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            correlation_id=normalized_correlation,
            status=result.status,
            payload={
                "request": result.request,
                "result": result.result,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "error_action": result.error_action,
                "attempt_count": result.attempt_count,
            },
            started_at=started_at,
            finished_at=finished_at,
        )
        return result

    def latest_retrieval(self, use_case: str) -> RetrievalResult | None:
        normalized_use_case = _expect_non_empty_string(use_case, name="use_case")
        return self._retrieval_cache.get(normalized_use_case)

    def invoke_retrieval(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        use_case: str,
        query: str,
        policy: RetrievalPolicyConfig | Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> RetrievalResult:
        normalized_task_id = _expect_non_empty_string(task_id, name="task_id")
        normalized_run_id = _expect_non_empty_string(run_id, name="run_id")
        normalized_step_id = _expect_non_empty_string(step_id, name="step_id")
        normalized_use_case = _expect_non_empty_string(use_case, name="use_case")
        if not isinstance(query, str):
            raise ToolOrchestrationError("query must be a string")
        normalized_correlation = _resolve_correlation_id(
            correlation_id=correlation_id,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            adapter="retrieval",
        )
        resolved_policy = self._resolve_retrieval_policy(
            use_case=normalized_use_case,
            policy=policy,
        )

        started_at = _utc_now()
        raw_result = self.retriever.retrieve(
            use_case=normalized_use_case,
            query=query,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            policy=resolved_policy,
        )
        result = self._coerce_retrieval_result(raw_result)
        self._retrieval_cache[normalized_use_case] = result
        finished_at = _utc_now()

        self._append_trace(
            adapter="retrieval",
            operation=normalized_use_case,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            correlation_id=normalized_correlation,
            status="success",
            payload={
                "query": result.query,
                "enabled": result.enabled,
                "top_k": result.top_k,
                "min_relevance_score": result.min_relevance_score,
                "source_count": len(result.sources),
                "sources": [
                    {
                        "chunk_id": source.chunk_id,
                        "source_path": source.source_path,
                        "source_type": source.source_type,
                        "task_id": source.task_id,
                        "run_id": source.run_id,
                        "relevance_score": source.relevance_score,
                    }
                    for source in result.sources
                ],
            },
            started_at=started_at,
            finished_at=finished_at,
        )
        return result

    def invoke_retrieval_documents(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        use_case: str,
        query: str,
        policy: RetrievalPolicyConfig | Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> tuple[Any, ...]:
        result = self.invoke_retrieval(
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            use_case=use_case,
            query=query,
            policy=policy,
            correlation_id=correlation_id,
        )
        try:
            module = import_optional_dependency(
                "langchain_core.documents",
                feature_name="langchain retrieval bridge",
                extras_hint="pip install 'daokit[langchain]'",
                import_module=self._import_module,
            )
            document_type = getattr(module, "Document")
            return tuple(
                document_type(
                    page_content=source.text,
                    metadata={
                        "chunk_id": source.chunk_id,
                        "source_path": source.source_path,
                        "source_type": source.source_type,
                        "task_id": source.task_id,
                        "run_id": source.run_id,
                        "relevance_score": source.relevance_score,
                    },
                )
                for source in result.sources
            )
        except (OptionalDependencyError, AttributeError):
            return tuple(self._to_document_mapping(source) for source in result.sources)

    def load_skill(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        skill_name: str,
        correlation_id: str | None = None,
    ) -> LoadedSkill:
        if self.adapters.skills is None:
            raise ToolOrchestrationError("skill loader is required to load skills")

        normalized_task_id = _expect_non_empty_string(task_id, name="task_id")
        normalized_run_id = _expect_non_empty_string(run_id, name="run_id")
        normalized_step_id = _expect_non_empty_string(step_id, name="step_id")
        normalized_skill_name = _expect_non_empty_string(skill_name, name="skill_name")
        normalized_correlation = _resolve_correlation_id(
            correlation_id=correlation_id,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            adapter="skills",
        )

        started_at = _utc_now()
        try:
            loaded = self.adapters.skills.load(normalized_skill_name)
            if self.adapters.hooks is not None:
                self.adapters.hooks.register_skill(loaded)
        except Exception as exc:
            finished_at = _utc_now()
            self._append_trace(
                adapter="skills",
                operation=normalized_skill_name,
                task_id=normalized_task_id,
                run_id=normalized_run_id,
                step_id=normalized_step_id,
                correlation_id=normalized_correlation,
                status="error",
                payload={"error": f"{exc.__class__.__name__}: {exc}"},
                started_at=started_at,
                finished_at=finished_at,
            )
            raise

        finished_at = _utc_now()
        self._append_trace(
            adapter="skills",
            operation=normalized_skill_name,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            correlation_id=normalized_correlation,
            status="success",
            payload={
                "name": loaded.manifest.name,
                "version": loaded.manifest.version,
                "hook_count": len(loaded.manifest.hooks),
                "hooks_registered": self.adapters.hooks is not None,
            },
            started_at=started_at,
            finished_at=finished_at,
        )
        return loaded

    def run_hook(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        hook_point: str,
        ledger_state: Mapping[str, Any],
        context: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        timeout_budget_seconds: float | None = None,
        correlation_id: str | None = None,
    ) -> Any:
        if self.adapters.hooks is None:
            raise ToolOrchestrationError("hook runtime is required to execute hooks")

        normalized_task_id = _expect_non_empty_string(task_id, name="task_id")
        normalized_run_id = _expect_non_empty_string(run_id, name="run_id")
        normalized_step_id = _expect_non_empty_string(step_id, name="step_id")
        normalized_hook_point = _expect_non_empty_string(hook_point, name="hook_point")
        normalized_correlation = _resolve_correlation_id(
            correlation_id=correlation_id,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            adapter="hooks",
        )
        normalized_idempotency_key = (
            normalized_correlation
            if idempotency_key is None
            else _expect_non_empty_string(idempotency_key, name="idempotency_key")
        )

        started_at = _utc_now()
        result = self.adapters.hooks.run(
            hook_point=normalized_hook_point,
            ledger_state=ledger_state,
            context=context,
            idempotency_key=normalized_idempotency_key,
            timeout_budget_seconds=timeout_budget_seconds,
        )
        finished_at = _utc_now()

        status = _normalize_status(getattr(result, "status", "unknown"))
        entry_count = len(getattr(result, "entries", ()))
        self._append_trace(
            adapter="hooks",
            operation=normalized_hook_point,
            task_id=normalized_task_id,
            run_id=normalized_run_id,
            step_id=normalized_step_id,
            correlation_id=normalized_correlation,
            status=status,
            payload={
                "idempotency_key": normalized_idempotency_key,
                "entry_count": entry_count,
                "status": status,
            },
            started_at=started_at,
            finished_at=finished_at,
        )
        return result

    def _resolve_retrieval_policy(
        self,
        *,
        use_case: str,
        policy: RetrievalPolicyConfig | Mapping[str, Any] | None,
    ) -> RetrievalPolicyConfig:
        base = self._default_retrieval_policies.get(use_case)
        base_policy = base if base is not None else RetrievalPolicyConfig()
        if policy is None:
            return base_policy
        if isinstance(policy, RetrievalPolicyConfig):
            return policy
        if isinstance(policy, Mapping):
            return policy_from_mapping(policy, base=base_policy)
        raise ToolOrchestrationError(
            "policy must be a RetrievalPolicyConfig, mapping, or None"
        )

    def _coerce_retrieval_result(self, value: Any) -> RetrievalResult:
        if isinstance(value, RetrievalResult):
            return value
        raise ToolOrchestrationError(
            "retriever must return rag.retrieval.RetrievalResult for advisory retrieval"
        )

    def _to_document_mapping(self, source: Any) -> dict[str, Any]:
        return {
            "page_content": source.text,
            "metadata": {
                "chunk_id": source.chunk_id,
                "source_path": source.source_path,
                "source_type": source.source_type,
                "task_id": source.task_id,
                "run_id": source.run_id,
                "relevance_score": source.relevance_score,
            },
        }

    def _resolve_mode(
        self,
        *,
        allow_fallback_when_unavailable: bool,
        import_module: ImportModule | None,
    ) -> ToolOrchestrationMode:
        if not isinstance(allow_fallback_when_unavailable, bool):
            raise ToolOrchestrationError("allow_fallback_when_unavailable must be a boolean")
        if self._requested_mode == ToolOrchestrationMode.LEGACY:
            return ToolOrchestrationMode.LEGACY

        importer = import_module or importlib.import_module
        try:
            import_optional_dependency(
                "langchain",
                feature_name="langchain tool orchestration",
                extras_hint="pip install 'daokit[langchain]'",
                import_module=importer,
            )
        except OptionalDependencyError as exc:
            if not allow_fallback_when_unavailable:
                raise ToolOrchestrationError(str(exc)) from exc
            self._fallback_reason = str(exc)
            return ToolOrchestrationMode.LEGACY

        self._fallback_reason = None
        return ToolOrchestrationMode.LANGCHAIN

    def _append_trace(
        self,
        *,
        adapter: str,
        operation: str,
        task_id: str,
        run_id: str,
        step_id: str,
        correlation_id: str,
        status: str,
        payload: Mapping[str, Any],
        started_at: str,
        finished_at: str,
    ) -> None:
        self._trace_logs.append(
            ToolTraceEntry(
                orchestration_mode=self._active_mode.value,
                adapter=_expect_non_empty_string(adapter, name="adapter"),
                operation=_expect_non_empty_string(operation, name="operation"),
                task_id=task_id,
                run_id=run_id,
                step_id=step_id,
                correlation_id=correlation_id,
                status=_normalize_status(status),
                payload=_copy_json(dict(payload)),
                started_at=started_at,
                finished_at=finished_at,
            )
        )


def _parse_mode(raw_mode: str) -> ToolOrchestrationMode:
    normalized = _expect_non_empty_string(raw_mode, name="requested_mode").lower()
    if normalized == ToolOrchestrationMode.LEGACY.value:
        return ToolOrchestrationMode.LEGACY
    if normalized == ToolOrchestrationMode.LANGCHAIN.value:
        return ToolOrchestrationMode.LANGCHAIN
    raise ToolOrchestrationError(
        f"unsupported tool orchestration mode '{normalized}'. Supported values: legacy, langchain."
    )


def _resolve_correlation_id(
    *,
    correlation_id: str | None,
    task_id: str,
    run_id: str,
    step_id: str,
    adapter: str,
) -> str:
    if correlation_id is not None:
        return _expect_non_empty_string(correlation_id, name="correlation_id")
    return f"{task_id}:{run_id}:{step_id}:{adapter}:{uuid4().hex[:8]}"


def _normalize_status(value: Any) -> str:
    if value is None:
        return "unknown"
    if not isinstance(value, str):
        return str(value)
    normalized = value.strip()
    return normalized or "unknown"


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise ToolOrchestrationError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ToolOrchestrationError(f"{name} must be a non-empty string")
    return normalized


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def _json_default(value: Any) -> Any:
    return {
        "__type__": value.__class__.__name__,
        "__repr__": repr(value),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
