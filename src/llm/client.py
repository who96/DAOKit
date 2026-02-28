from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Mapping

from tools.common.optional_dependencies import import_optional_dependency


ENV_LLM_API_KEY = "DAOKIT_LLM_API_KEY"
ENV_LLM_BASE_URL = "DAOKIT_LLM_BASE_URL"
ENV_LLM_MODEL = "DAOKIT_LLM_MODEL"
ENV_LLM_MAX_TOKENS = "DAOKIT_LLM_MAX_TOKENS"
ENV_LLM_TEMPERATURE = "DAOKIT_LLM_TEMPERATURE"
ENV_LLM_TIMEOUT_SECONDS = "DAOKIT_LLM_TIMEOUT_SECONDS"


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout_seconds: int = 60


@dataclass(frozen=True)
class LLMCompletionResult:
    content: str
    model: str
    usage: dict[str, int]
    finish_reason: str
    raw_response: dict[str, Any]
    tool_calls: tuple[dict[str, Any], ...] = ()


class LLMCallError(RuntimeError):
    """Raised when LLM API call fails."""


def resolve_llm_config(
    *,
    explicit_api_key: str | None = None,
    explicit_base_url: str | None = None,
    explicit_model: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> LLMConfig:
    env_values = os.environ if env is None else env

    api_key = _resolve_setting(
        explicit=explicit_api_key,
        env=env_values,
        env_key=ENV_LLM_API_KEY,
        config=config,
        config_path=("llm", "api_key"),
        default=None,
    )
    if api_key is None or (isinstance(api_key, str) and not api_key.strip()):
        raise LLMCallError(
            "DAOKIT_LLM_API_KEY is required to configure LLM client. "
            "Provide explicit_api_key, environment variable, or config['llm']['api_key']."
        )

    base_url = _resolve_setting(
        explicit=explicit_base_url,
        env=env_values,
        env_key=ENV_LLM_BASE_URL,
        config=config,
        config_path=("llm", "base_url"),
        default="https://api.deepseek.com",
    )
    model = _resolve_setting(
        explicit=explicit_model,
        env=env_values,
        env_key=ENV_LLM_MODEL,
        config=config,
        config_path=("llm", "model"),
        default="deepseek-chat",
    )
    max_tokens = _resolve_setting(
        explicit=None,
        env=env_values,
        env_key=ENV_LLM_MAX_TOKENS,
        config=config,
        config_path=("llm", "max_tokens"),
        default=4096,
    )
    temperature = _resolve_setting(
        explicit=None,
        env=env_values,
        env_key=ENV_LLM_TEMPERATURE,
        config=config,
        config_path=("llm", "temperature"),
        default=0.0,
    )
    timeout_seconds = _resolve_setting(
        explicit=None,
        env=env_values,
        env_key=ENV_LLM_TIMEOUT_SECONDS,
        config=config,
        config_path=("llm", "timeout_seconds"),
        default=60,
    )

    return LLMConfig(
        api_key=_coerce_non_empty_string(api_key, setting_name=ENV_LLM_API_KEY),
        base_url=_coerce_non_empty_string(base_url, setting_name=ENV_LLM_BASE_URL),
        model=_coerce_non_empty_string(model, setting_name=ENV_LLM_MODEL),
        max_tokens=_coerce_int(max_tokens, setting_name=ENV_LLM_MAX_TOKENS),
        temperature=_coerce_float(temperature, setting_name=ENV_LLM_TEMPERATURE),
        timeout_seconds=_coerce_int(timeout_seconds, setting_name=ENV_LLM_TIMEOUT_SECONDS),
    )


class LLMClient:
    def __init__(self, config: LLMConfig, *, openai_client: Any | None = None) -> None:
        self._config = config
        if openai_client is not None:
            self._client = openai_client
        else:
            openai_module = import_optional_dependency(
                "openai",
                feature_name="LLM dispatch",
                extras_hint="pip install 'daokit[llm]'",
            )
            self._client = openai_module.OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=config.timeout_seconds,
            )

    @property
    def config(self) -> LLMConfig:
        return self._config

    def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMCompletionResult:
        try:
            request_payload: dict[str, Any] = {
                "model": self._config.model,
                "messages": messages,
                "max_tokens": self._config.max_tokens,
                "temperature": self._config.temperature,
            }
            if tools is not None:
                request_payload["tools"] = tools
            response = self._client.chat.completions.create(**request_payload)
            choice = response.choices[0]
            usage_data: dict[str, int] = {}
            if response.usage is not None:
                usage_data = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            tool_calls = _extract_tool_calls(getattr(choice.message, "tool_calls", None))
            return LLMCompletionResult(
                content=choice.message.content or "",
                model=response.model,
                usage=usage_data,
                finish_reason=choice.finish_reason or "stop",
                raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
                tool_calls=tool_calls,
            )
        except Exception as exc:
            raise LLMCallError(str(exc)) from exc


def _resolve_setting(
    *,
    explicit: Any,
    env: Mapping[str, str],
    env_key: str,
    config: Mapping[str, Any] | None,
    config_path: tuple[str, ...],
    default: Any,
) -> Any:
    if explicit is not None:
        return explicit
    if env_key in env:
        return env[env_key]
    config_value = _get_nested_config_value(config, path=config_path)
    if config_value is not None:
        return config_value
    return default


def _get_nested_config_value(config: Mapping[str, Any] | None, *, path: tuple[str, ...]) -> Any:
    node: Any = config
    for token in path:
        if not isinstance(node, Mapping):
            return None
        if token not in node:
            return None
        node = node[token]
    return node


def _coerce_non_empty_string(value: Any, *, setting_name: str) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    raise LLMCallError(f"{setting_name} must be a non-empty string.")


def _coerce_int(value: Any, *, setting_name: str) -> int:
    if isinstance(value, bool):
        raise LLMCallError(f"{setting_name} must be an integer.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise LLMCallError(f"{setting_name} must be an integer.")
        try:
            return int(normalized)
        except ValueError as exc:
            raise LLMCallError(f"{setting_name} must be an integer.") from exc
    raise LLMCallError(f"{setting_name} must be an integer.")


def _coerce_float(value: Any, *, setting_name: str) -> float:
    if isinstance(value, bool):
        raise LLMCallError(f"{setting_name} must be a float.")
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise LLMCallError(f"{setting_name} must be a float.")
        try:
            return float(normalized)
        except ValueError as exc:
            raise LLMCallError(f"{setting_name} must be a float.") from exc
    raise LLMCallError(f"{setting_name} must be a float.")


def _extract_tool_calls(tool_calls: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(tool_calls, list):
        return ()
    normalized: list[dict[str, Any]] = []
    for call in tool_calls:
        if call is None:
            continue
        call_id = getattr(call, "id", None)
        function = getattr(call, "function", None)
        function_name = getattr(function, "name", None)
        raw_arguments = getattr(function, "arguments", None)
        if not isinstance(call_id, str) or not call_id.strip():
            continue
        if not isinstance(function_name, str) or not function_name.strip():
            continue
        arguments = _parse_tool_arguments(raw_arguments)
        normalized.append(
            {
                "id": call_id.strip(),
                "function_name": function_name.strip(),
                "arguments": arguments,
            }
        )
    return tuple(normalized)


def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return dict(raw_arguments)
    if not isinstance(raw_arguments, str):
        return {}
    text = raw_arguments.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}
