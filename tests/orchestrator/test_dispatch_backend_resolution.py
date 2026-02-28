from __future__ import annotations

import unittest

from orchestrator.engine import (
    DispatchBackend,
    RuntimeEngineError,
    resolve_dispatch_backend,
)


class DispatchBackendResolutionTests(unittest.TestCase):
    def test_default_resolves_to_shim(self) -> None:
        result = resolve_dispatch_backend()
        self.assertEqual(result, DispatchBackend.SHIM)

    def test_explicit_shim(self) -> None:
        result = resolve_dispatch_backend(explicit_backend="shim")
        self.assertEqual(result, DispatchBackend.SHIM)

    def test_explicit_llm(self) -> None:
        result = resolve_dispatch_backend(explicit_backend="llm")
        self.assertEqual(result, DispatchBackend.LLM)

    def test_env_var_selects_llm(self) -> None:
        result = resolve_dispatch_backend(env={"DAOKIT_DISPATCH_BACKEND": "llm"})
        self.assertEqual(result, DispatchBackend.LLM)

    def test_env_var_selects_shim(self) -> None:
        result = resolve_dispatch_backend(env={"DAOKIT_DISPATCH_BACKEND": "shim"})
        self.assertEqual(result, DispatchBackend.SHIM)

    def test_config_selects_llm(self) -> None:
        result = resolve_dispatch_backend(config={"dispatch": {"backend": "llm"}})
        self.assertEqual(result, DispatchBackend.LLM)

    def test_config_alternative_path(self) -> None:
        result = resolve_dispatch_backend(config={"runtime": {"dispatch_backend": "llm"}})
        self.assertEqual(result, DispatchBackend.LLM)

    def test_explicit_overrides_env(self) -> None:
        result = resolve_dispatch_backend(
            explicit_backend="shim",
            env={"DAOKIT_DISPATCH_BACKEND": "llm"},
        )
        self.assertEqual(result, DispatchBackend.SHIM)

    def test_env_overrides_config(self) -> None:
        result = resolve_dispatch_backend(
            env={"DAOKIT_DISPATCH_BACKEND": "shim"},
            config={"dispatch": {"backend": "llm"}},
        )
        self.assertEqual(result, DispatchBackend.SHIM)

    def test_unsupported_backend_raises(self) -> None:
        with self.assertRaises(RuntimeEngineError) as ctx:
            resolve_dispatch_backend(explicit_backend="unknown")
        self.assertIn("unsupported dispatch backend", str(ctx.exception))
        self.assertIn("unknown", str(ctx.exception))

    def test_case_insensitive(self) -> None:
        result = resolve_dispatch_backend(explicit_backend="LLM")
        self.assertEqual(result, DispatchBackend.LLM)

    def test_whitespace_stripped(self) -> None:
        result = resolve_dispatch_backend(explicit_backend="  llm  ")
        self.assertEqual(result, DispatchBackend.LLM)


if __name__ == "__main__":
    unittest.main()
