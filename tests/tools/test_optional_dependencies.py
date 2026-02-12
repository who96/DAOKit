from __future__ import annotations

import types
import unittest

from tools.common.optional_dependencies import (
    OptionalDependencyError,
    import_optional_dependency,
    is_dependency_available,
)


class OptionalDependenciesTests(unittest.TestCase):
    def test_is_dependency_available_returns_false_for_missing_module(self) -> None:
        def missing_importer(_name: str) -> object:
            raise ModuleNotFoundError("missing")

        self.assertFalse(is_dependency_available("langgraph", import_module=missing_importer))

    def test_import_optional_dependency_raises_actionable_error(self) -> None:
        def missing_importer(_name: str) -> object:
            raise ModuleNotFoundError("missing")

        with self.assertRaises(OptionalDependencyError) as ctx:
            import_optional_dependency(
                "langgraph",
                feature_name="langgraph runtime",
                extras_hint="pip install 'daokit[langgraph]'",
                import_module=missing_importer,
            )

        message = str(ctx.exception)
        self.assertIn("langgraph runtime", message)
        self.assertIn("pip install 'daokit[langgraph]'", message)

    def test_import_optional_dependency_returns_module_when_available(self) -> None:
        expected = types.SimpleNamespace(__name__="langchain")

        def importer(_name: str) -> object:
            return expected

        loaded = import_optional_dependency(
            "langchain",
            feature_name="langchain integration",
            extras_hint="pip install 'daokit[langchain]'",
            import_module=importer,
        )
        self.assertIs(loaded, expected)


if __name__ == "__main__":
    unittest.main()
