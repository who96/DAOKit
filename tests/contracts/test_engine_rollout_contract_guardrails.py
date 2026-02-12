from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from contracts.validator import validate_payload
from daokit.bootstrap import initialize_repository
from orchestrator.engine import create_runtime
from state.store import StateStore


ROOT_DIR = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = ROOT_DIR / "contracts"
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
SCHEMA_NAMES = (
    "pipeline_state",
    "events",
    "heartbeat_status",
    "process_leases",
)
EXPECTED_SCHEMA_FILES = (
    "events.schema.json",
    "heartbeat_status.schema.json",
    "pipeline_state.schema.json",
    "process_leases.schema.json",
)


class EngineRolloutContractGuardrailsTests(unittest.TestCase):
    def _assert_frozen_contract_samples_still_validate(self) -> None:
        for schema_name in SCHEMA_NAMES:
            payload = json.loads((SAMPLES_DIR / f"{schema_name}.valid.json").read_text(encoding="utf-8"))
            validate_payload(schema_name, payload, contracts_dir=CONTRACTS_DIR)

    def _run_and_validate(
        self,
        *,
        config: dict[str, object] | None,
        env: dict[str, str] | None,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initialize_repository(root)
            state_store = StateStore(root / "state")

            runtime = create_runtime(
                task_id="DKT-035",
                run_id="RUN-CONTRACT-GUARD",
                goal="Verify rollout contract compatibility",
                step_id="S1",
                state_store=state_store,
                config=config,
                env=env,
            )
            final_state = runtime.run()

            self.assertEqual(final_state.get("status"), "DONE")
            self.assertEqual(final_state.get("schema_version"), "1.0.0")
            self._assert_frozen_contract_samples_still_validate()

    def test_integrated_selector_from_runtime_settings_preserves_contracts(self) -> None:
        self._run_and_validate(config={"runtime": {"mode": "integrated"}}, env={})

    def test_env_selector_can_rollback_to_legacy_without_contract_drift(self) -> None:
        self._run_and_validate(
            config={"runtime": {"mode": "integrated"}},
            env={"DAOKIT_RUNTIME_ENGINE": "legacy"},
        )

    def test_engine_rollout_controls_do_not_add_new_contract_schema_files(self) -> None:
        schema_files = sorted(path.name for path in CONTRACTS_DIR.glob("*.schema.json"))
        self.assertEqual(tuple(schema_files), EXPECTED_SCHEMA_FILES)


if __name__ == "__main__":
    unittest.main()
