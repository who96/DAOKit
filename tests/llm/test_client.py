from __future__ import annotations

import unittest

from llm.client import LLMCallError, LLMClient, resolve_llm_config


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeUsage:
    def __init__(self) -> None:
        self.prompt_tokens = 10
        self.completion_tokens = 20
        self.total_tokens = 30


class _FakeResponse:
    def __init__(self, content: str = "ok", model: str = "deepseek-chat") -> None:
        self.choices = [_FakeChoice(content)]
        self.model = model
        self.usage = _FakeUsage()

    def model_dump(self) -> dict[str, str]:
        return {"id": "fake", "model": self.model}


class _FakeCompletions:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return self._response


class _FakeChat:
    def __init__(self, response: _FakeResponse) -> None:
        self.completions = _FakeCompletions(response)


class _FakeOpenAIClient:
    def __init__(self, response: _FakeResponse | None = None) -> None:
        self._response = response or _FakeResponse()
        self.chat = _FakeChat(self._response)


class _RaisingCompletions:
    def create(self, **kwargs: object) -> _FakeResponse:
        _ = kwargs
        raise RuntimeError("sdk boom")


class _RaisingChat:
    def __init__(self) -> None:
        self.completions = _RaisingCompletions()


class _RaisingOpenAIClient:
    def __init__(self) -> None:
        self.chat = _RaisingChat()


class LLMClientTests(unittest.TestCase):
    def test_resolve_llm_config_from_env(self) -> None:
        env = {
            "DAOKIT_LLM_API_KEY": "env-key",
            "DAOKIT_LLM_BASE_URL": "https://example.com",
            "DAOKIT_LLM_MODEL": "env-model",
            "DAOKIT_LLM_MAX_TOKENS": "1234",
            "DAOKIT_LLM_TEMPERATURE": "0.25",
            "DAOKIT_LLM_TIMEOUT_SECONDS": "9",
        }

        config = resolve_llm_config(env=env)

        self.assertEqual(config.api_key, "env-key")
        self.assertEqual(config.base_url, "https://example.com")
        self.assertEqual(config.model, "env-model")
        self.assertEqual(config.max_tokens, 1234)
        self.assertEqual(config.temperature, 0.25)
        self.assertEqual(config.timeout_seconds, 9)

    def test_resolve_llm_config_explicit_overrides_env(self) -> None:
        env = {
            "DAOKIT_LLM_API_KEY": "env-key",
            "DAOKIT_LLM_BASE_URL": "https://env.example.com",
            "DAOKIT_LLM_MODEL": "env-model",
        }

        config = resolve_llm_config(
            explicit_api_key="explicit-key",
            explicit_base_url="https://explicit.example.com",
            explicit_model="explicit-model",
            env=env,
        )

        self.assertEqual(config.api_key, "explicit-key")
        self.assertEqual(config.base_url, "https://explicit.example.com")
        self.assertEqual(config.model, "explicit-model")

    def test_resolve_llm_config_missing_api_key_raises(self) -> None:
        with self.assertRaises(LLMCallError) as ctx:
            resolve_llm_config(env={})

        self.assertIn("DAOKIT_LLM_API_KEY is required", str(ctx.exception))

    def test_resolve_llm_config_defaults(self) -> None:
        config = resolve_llm_config(explicit_api_key="explicit-key")

        self.assertEqual(config.api_key, "explicit-key")
        self.assertEqual(config.base_url, "https://api.deepseek.com")
        self.assertEqual(config.model, "deepseek-chat")
        self.assertEqual(config.max_tokens, 4096)
        self.assertEqual(config.temperature, 0.0)
        self.assertEqual(config.timeout_seconds, 60)

    def test_chat_completion_returns_result(self) -> None:
        fake_client = _FakeOpenAIClient(response=_FakeResponse(content="hello", model="m1"))
        client = LLMClient(
            resolve_llm_config(explicit_api_key="k", explicit_model="m1"),
            openai_client=fake_client,
        )

        result = client.chat_completion(messages=[{"role": "user", "content": "hi"}])

        self.assertEqual(result.content, "hello")
        self.assertEqual(result.model, "m1")
        self.assertEqual(
            result.usage,
            {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.raw_response, {"id": "fake", "model": "m1"})

    def test_chat_completion_passes_config_to_sdk(self) -> None:
        fake_client = _FakeOpenAIClient()
        client = LLMClient(
            resolve_llm_config(
                explicit_api_key="k",
                explicit_model="custom-model",
                config={"llm": {"max_tokens": 333, "temperature": 0.3}},
            ),
            openai_client=fake_client,
        )

        messages = [{"role": "user", "content": "hello"}]
        client.chat_completion(messages=messages)

        calls = fake_client.chat.completions.calls
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "custom-model")
        self.assertEqual(calls[0]["messages"], messages)
        self.assertEqual(calls[0]["max_tokens"], 333)
        self.assertEqual(calls[0]["temperature"], 0.3)

    def test_chat_completion_error_wraps_as_llm_call_error(self) -> None:
        client = LLMClient(
            resolve_llm_config(explicit_api_key="k"),
            openai_client=_RaisingOpenAIClient(),
        )

        with self.assertRaises(LLMCallError) as ctx:
            client.chat_completion(messages=[{"role": "user", "content": "boom"}])

        self.assertIn("sdk boom", str(ctx.exception))

    def test_client_config_property(self) -> None:
        config = resolve_llm_config(explicit_api_key="k", explicit_model="my-model")
        client = LLMClient(config, openai_client=_FakeOpenAIClient())

        self.assertIs(client.config, config)


if __name__ == "__main__":
    unittest.main()
