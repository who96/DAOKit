from __future__ import annotations

import unittest

from verification.criteria_registry import (
    RELEASE_ACCEPTANCE_CRITERIA,
    RELEASE_CRITERIA_REGISTRY_VERSION,
)


class CriteriaRegistryTests(unittest.TestCase):
    def test_registry_has_unique_stable_ids(self) -> None:
        ids = [item.criterion_id for item in RELEASE_ACCEPTANCE_CRITERIA]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            ids,
            [
                "RC-RC-001",
                "RC-DIAG-001",
                "RC-BUNDLE-001",
                "RC-TPL-001",
                "RC-LGO-001",
                "RC-COMP-001",
            ],
        )

    def test_registry_entries_define_evidence_and_remediation_defaults(self) -> None:
        self.assertEqual(RELEASE_CRITERIA_REGISTRY_VERSION, "1.0.0")
        for item in RELEASE_ACCEPTANCE_CRITERIA:
            self.assertTrue(item.criterion.strip())
            self.assertTrue(item.remediation_hint.strip())
            self.assertGreaterEqual(len(item.evidence_refs), 1)


if __name__ == "__main__":
    unittest.main()
