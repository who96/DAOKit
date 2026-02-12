from __future__ import annotations

import json
from pathlib import Path
import unittest

from contracts.validator import (
    SchemaValidationError,
    validate_payload,
    validate_payload_file,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = ROOT_DIR / "contracts"
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

SCHEMA_NAMES = (
    "pipeline_state",
    "events",
    "heartbeat_status",
    "process_leases",
)

INVALID_ERROR_HINTS = {
    "pipeline_state": "$.schema_version",
    "events": "$.severity",
    "heartbeat_status": "$.status",
    "process_leases": "$.leases[0].pid",
}


class ContractValidatorTests(unittest.TestCase):
    def test_valid_payload_samples_pass(self) -> None:
        for schema_name in SCHEMA_NAMES:
            sample_path = SAMPLES_DIR / f"{schema_name}.valid.json"
            validate_payload_file(schema_name, sample_path, contracts_dir=CONTRACTS_DIR)

    def test_invalid_payload_samples_are_rejected(self) -> None:
        for schema_name in SCHEMA_NAMES:
            sample_path = SAMPLES_DIR / f"{schema_name}.invalid.json"
            with self.assertRaises(SchemaValidationError) as ctx:
                validate_payload_file(schema_name, sample_path, contracts_dir=CONTRACTS_DIR)
            self.assertIn(INVALID_ERROR_HINTS[schema_name], str(ctx.exception))

    def test_schema_files_document_field_semantics(self) -> None:
        for schema_name in SCHEMA_NAMES:
            schema_path = CONTRACTS_DIR / f"{schema_name}.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            properties = schema.get("properties", {})

            self.assertTrue(schema.get("description"), f"{schema_name} missing root description")
            self.assertIn("schema_version", properties, f"{schema_name} missing schema_version")

            for field_name, field_schema in properties.items():
                self.assertTrue(
                    field_schema.get("description"),
                    f"{schema_name}.{field_name} missing description",
                )

    def test_datetime_requires_full_timestamp_with_timezone(self) -> None:
        payload = {
            "schema_version": "1.0.0",
            "event_id": "evt_001",
            "task_id": "DKT-002",
            "run_id": "run_001",
            "step_id": None,
            "event_type": "SYSTEM",
            "severity": "INFO",
            "timestamp": "2026-02-11",
            "payload": {},
            "dedup_key": None,
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            validate_payload("events", payload, contracts_dir=CONTRACTS_DIR)
        self.assertIn("$.timestamp", str(ctx.exception))

    def test_heartbeat_stale_threshold_must_not_be_less_than_warning(self) -> None:
        payload = {
            "schema_version": "1.0.0",
            "status": "RUNNING",
            "last_heartbeat_at": "2026-02-11T20:32:00+00:00",
            "reason_code": None,
            "warning_after_seconds": 1200,
            "stale_after_seconds": 900,
            "updated_at": "2026-02-11T20:32:00+00:00",
            "last_escalation_at": None,
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            validate_payload("heartbeat_status", payload, contracts_dir=CONTRACTS_DIR)
        self.assertIn("$.stale_after_seconds", str(ctx.exception))

    def test_heartbeat_legacy_payload_without_threshold_fields_passes(self) -> None:
        payload = {
            "schema_version": "1.0.0",
            "status": "IDLE",
            "last_heartbeat_at": None,
            "reason_code": None,
            "updated_at": "2026-02-11T20:32:00+00:00",
        }

        validate_payload("heartbeat_status", payload, contracts_dir=CONTRACTS_DIR)


if __name__ == "__main__":
    unittest.main()
