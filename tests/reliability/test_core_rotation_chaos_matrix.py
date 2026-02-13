from __future__ import annotations

import unittest

from reliability.scenarios.core_rotation_chaos_matrix import (
    CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG,
    CORE_ROTATION_HIGH_RISK_PATHS,
    DEFAULT_DETERMINISTIC_CONSTRAINTS,
    get_core_rotation_chaos_scenario,
    get_default_core_rotation_chaos_scenario,
    list_core_rotation_chaos_scenarios,
    summarize_core_rotation_chaos_matrix,
)


class CoreRotationChaosMatrixTests(unittest.TestCase):
    def test_matrix_covers_high_risk_paths_and_continuity_assertions(self) -> None:
        fixtures = list_core_rotation_chaos_scenarios()
        summary = summarize_core_rotation_chaos_matrix()

        self.assertGreaterEqual(len(fixtures), 4)
        self.assertEqual(set(summary["high_risk_paths_required"]), set(CORE_ROTATION_HIGH_RISK_PATHS))
        self.assertEqual(set(summary["high_risk_paths_covered"]), set(CORE_ROTATION_HIGH_RISK_PATHS))
        self.assertEqual(summary["missing_high_risk_paths"], [])
        self.assertTrue(summary["checks"]["high_risk_paths_covered"])
        self.assertTrue(summary["checks"]["assertion_mapping_complete"])

        for fixture in fixtures:
            self.assertGreaterEqual(len(fixture.continuity_assertions), 1)
            self.assertGreaterEqual(len(fixture.risk_tags), 1)
            for assertion_id in fixture.continuity_assertions:
                self.assertIn(assertion_id, CORE_ROTATION_CONTINUITY_ASSERTION_CATALOG)

    def test_default_fixture_lookup_is_stable(self) -> None:
        default_fixture = get_default_core_rotation_chaos_scenario()
        looked_up = get_core_rotation_chaos_scenario(default_fixture.scenario_id)

        self.assertEqual(default_fixture, looked_up)
        self.assertIn("rotation", default_fixture.risk_tags)
        self.assertIn("takeover", default_fixture.risk_tags)

    def test_unknown_fixture_lookup_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            get_core_rotation_chaos_scenario("non-existent-scenario")

    def test_deterministic_constraints_include_reproducibility_metadata(self) -> None:
        metadata = DEFAULT_DETERMINISTIC_CONSTRAINTS.to_dict()

        self.assertEqual(metadata["seed"], "DKT-051-core-rotation-chaos-matrix")
        self.assertEqual(metadata["check_interval_seconds"], 60)
        self.assertEqual(metadata["warning_after_seconds"], 900)
        self.assertEqual(metadata["stale_after_seconds"], 1200)
        self.assertEqual(metadata["second_tick_advance_seconds"], 120)
        self.assertEqual(metadata["replay_limit"], 500)
        self.assertTrue(metadata["clock_anchor_utc"].endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
