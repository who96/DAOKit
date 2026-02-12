from __future__ import annotations

import unittest

from orchestrator.engine import RuntimeEngine, RuntimeEngineError, create_runtime, resolve_runtime_engine
from contracts.runtime_adapters import RuntimeStateStore


class RuntimeEngineSelectorTests(unittest.TestCase):
    def _new_store(self) -> RuntimeStateStore:
        class _MemoryStateStore:
            def __init__(self) -> None:
                self.state = {
                    "status": "PLANNING",
                    "task_id": "DKT-029",
                    "run_id": "RUN-LEGACY",
                }

            def load_state(self) -> dict[str, object]:
                return dict(self.state)

            def save_state(
                self,
                state: dict[str, object],
                *,
                node: str,
                from_status: str | None,
                to_status: str | None,
            ) -> dict[str, object]:
                self.state = dict(state)
                return dict(self.state)

            def append_event(
                self,
                *,
                task_id: str,
                run_id: str,
                step_id: str | None,
                event_type: str,
                severity: str,
                payload: dict[str, object],
                dedup_key: str | None,
            ) -> None:
                return None

        return _MemoryStateStore()

    def test_default_engine_is_legacy_when_not_configured(self) -> None:
        selected = resolve_runtime_engine(explicit_engine=None, env={})
        self.assertEqual(selected, RuntimeEngine.LEGACY)

    def test_env_engine_selection_supports_langgraph(self) -> None:
        selected = resolve_runtime_engine(explicit_engine=None, env={"DAOKIT_RUNTIME_ENGINE": "langgraph"})
        self.assertEqual(selected, RuntimeEngine.LANGGRAPH)

    def test_invalid_engine_value_is_rejected(self) -> None:
        with self.assertRaises(RuntimeEngineError) as ctx:
            resolve_runtime_engine(explicit_engine="experimental", env={})

        self.assertIn("unsupported runtime engine", str(ctx.exception))
        self.assertIn("legacy", str(ctx.exception))
        self.assertIn("langgraph", str(ctx.exception))

    def test_default_factory_path_uses_legacy_factory_without_optional_imports(self) -> None:
        imports_attempted: list[str] = []

        def recording_importer(name: str) -> object:
            imports_attempted.append(name)
            raise AssertionError("legacy path should not import optional dependencies")

        runtime = create_runtime(
            task_id="DKT-029",
            run_id="RUN-LEGACY",
            goal="Compatibility baseline",
            step_id="S1",
            state_store=self._new_store(),
            explicit_engine=None,
            env={},
            import_module=recording_importer,
            legacy_runtime_factory=lambda **kwargs: {
                "engine": "legacy",
                "run_id": kwargs["run_id"],
            },
        )

        self.assertEqual(runtime, {"engine": "legacy", "run_id": "RUN-LEGACY"})
        self.assertEqual(imports_attempted, [])

    def test_langgraph_path_is_gated_when_optional_dependencies_are_missing(self) -> None:
        def missing_importer(name: str) -> object:
            raise ModuleNotFoundError(name)

        with self.assertRaises(RuntimeEngineError) as ctx:
            create_runtime(
                task_id="DKT-029",
                run_id="RUN-LANGGRAPH",
                goal="Optional dependency gate",
                step_id="S1",
                state_store=self._new_store(),
                explicit_engine="langgraph",
                env={},
                import_module=missing_importer,
            )

        message = str(ctx.exception)
        self.assertIn("optional dependencies are not installed", message)
        self.assertIn("langchain", message)
        self.assertIn("langgraph", message)

    def test_langgraph_path_stays_feature_gated_after_dependency_check(self) -> None:
        def available_importer(_name: str) -> object:
            return object()

        with self.assertRaises(RuntimeEngineError) as ctx:
            create_runtime(
                task_id="DKT-029",
                run_id="RUN-LANGGRAPH",
                goal="Feature gate",
                step_id="S1",
                state_store=self._new_store(),
                explicit_engine="langgraph",
                env={},
                import_module=available_importer,
            )

        self.assertIn("feature-gated", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
