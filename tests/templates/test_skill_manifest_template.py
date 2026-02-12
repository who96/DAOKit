from __future__ import annotations

import json
from pathlib import Path
import unittest

from skills.loader import SUPPORTED_HOOK_EVENTS, parse_skill_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "templates" / "skill-manifest" / "skill.json.template"
DOC_PATH = REPO_ROOT / "docs" / "contributors" / "skill-manifest-template.md"


class SkillManifestTemplateTests(unittest.TestCase):
    def test_template_is_valid_json_with_required_metadata(self) -> None:
        payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0.0")
        self.assertTrue(isinstance(payload["name"], str) and payload["name"].strip())
        self.assertTrue(isinstance(payload["version"], str) and payload["version"].strip())

    def test_template_is_accepted_by_loader_contract(self) -> None:
        payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        manifest = parse_skill_manifest(payload)
        self.assertEqual(manifest.schema_version, "1.0.0")
        self.assertGreaterEqual(len(manifest.hooks), 1)

    def test_template_hooks_use_supported_events(self) -> None:
        payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        hooks = payload.get("hooks", [])
        self.assertTrue(hooks)
        for hook in hooks:
            self.assertIn(hook["event"], SUPPORTED_HOOK_EVENTS)

    def test_contributor_doc_includes_deterministic_release_checklist(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("Deterministic Validation Checklist", text)
        self.assertIn("make lint && make test && make release-check", text)
        self.assertIn("Command: make lint", text)
        self.assertIn("=== COMMAND ENTRY [0-9]+ START ===", text)

    def test_contributor_doc_includes_failure_examples(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("Failure Examples", text)
        self.assertIn("name must be a non-empty string", text)
        self.assertIn("hooks[0].event must be one of", text)


if __name__ == "__main__":
    unittest.main()
