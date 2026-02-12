from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPO_ROOT / "templates" / "tool_adapter"
ADAPTER_TEMPLATE = TEMPLATE_ROOT / "adapter.py"
README_TEMPLATE = TEMPLATE_ROOT / "README.md"
TEMPLATE_TEST = TEMPLATE_ROOT / "tests" / "test_adapter.py"
CONTRIBUTOR_GUIDE = REPO_ROOT / "docs" / "contributors" / "tool-adapter-template.md"


def _load_module(module_path: Path, module_name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class ToolAdapterTemplateContractTests(unittest.TestCase):
    def test_template_assets_exist(self) -> None:
        self.assertTrue(ADAPTER_TEMPLATE.is_file())
        self.assertTrue(README_TEMPLATE.is_file())
        self.assertTrue(TEMPLATE_TEST.is_file())
        self.assertTrue(CONTRIBUTOR_GUIDE.is_file())

    def test_adapter_scaffold_is_immediately_runnable(self) -> None:
        module = _load_module(ADAPTER_TEMPLATE, "tool_adapter_template")
        adapter = module.ToolAdapterTemplate()

        adapter.register_tool(
            name="echo",
            handler=lambda arguments: {"echo": arguments["message"]},
        )

        success = adapter.invoke(tool_name="echo", arguments={"message": "ok"})
        missing = adapter.invoke(tool_name="missing", arguments={})

        self.assertEqual(success.status, "success")
        self.assertEqual(success.output, {"echo": "ok"})
        self.assertIsNone(success.error)
        self.assertEqual(missing.status, "error")
        self.assertIsNone(missing.output)
        self.assertIn("not registered", missing.error or "")

    def test_readme_links_template_to_release_check(self) -> None:
        text = README_TEMPLATE.read_text(encoding="utf-8")
        required_phrases = (
            "make lint && make test && make release-check",
            ".artifacts/release-check/verification.log",
            ".artifacts/release-check/summary.json",
            "LangGraph-only",
        )
        for phrase in required_phrases:
            self.assertIn(phrase, text)

    def test_contributor_checklist_maps_acceptance_and_evidence(self) -> None:
        text = CONTRIBUTOR_GUIDE.read_text(encoding="utf-8")
        required_phrases = (
            "AC-DKT-043-01",
            "AC-DKT-043-02",
            "AC-DKT-043-03",
            "RC-TPL-001",
            "RC-COMP-001",
            "make lint && make test && make release-check",
            "verification.log",
            "audit-summary.md",
            "schema_version=1.0.0",
            "LangGraph-only",
        )
        for phrase in required_phrases:
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
