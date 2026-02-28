from __future__ import annotations

import unittest

from orchestrator.agent_prompts import (
    DISPATCH_SYSTEM_PROMPT,
    EXTRACT_SYSTEM_PROMPT,
    PLAN_REVIEW_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
    VERIFY_SYSTEM_PROMPT,
)


class AgentPromptsTests(unittest.TestCase):
    def test_all_prompts_non_empty(self) -> None:
        prompts = (
            EXTRACT_SYSTEM_PROMPT,
            PLAN_SYSTEM_PROMPT,
            PLAN_REVIEW_SYSTEM_PROMPT,
            DISPATCH_SYSTEM_PROMPT,
            VERIFY_SYSTEM_PROMPT,
        )

        for prompt in prompts:
            self.assertIsInstance(prompt, str)
            self.assertTrue(prompt.strip())

    def test_prompts_contain_role_keywords(self) -> None:
        self.assertIn("Window Agent", EXTRACT_SYSTEM_PROMPT)
        self.assertIn("Planner Agent", PLAN_SYSTEM_PROMPT)
        self.assertIn("Plan Reviewer", PLAN_REVIEW_SYSTEM_PROMPT)
        self.assertIn("Worker Agent", DISPATCH_SYSTEM_PROMPT)
        self.assertIn("Audit Agent", VERIFY_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
