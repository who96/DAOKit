from __future__ import annotations

import json
from pathlib import Path
import unittest

from contracts.validator import SchemaValidationError, validate_payload


ROOT_DIR = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = ROOT_DIR / "contracts"
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

SCHEMA_NAMES = (
    "pipeline_state",
    "events",
    "heartbeat_status",
    "process_leases",
)

EXPECTED_ENUMS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("pipeline_state", "properties", "status", "enum"): (
        "PLANNING",
        "ANALYSIS",
        "FREEZE",
        "EXECUTE",
        "ACCEPT",
        "DONE",
        "DRAINING",
        "BLOCKED",
        "FAILED",
    ),
    ("events", "properties", "event_type", "enum"): (
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_FAILED",
        "ACCEPTANCE_PASSED",
        "ACCEPTANCE_FAILED",
        "HEARTBEAT_WARNING",
        "HEARTBEAT_STALE",
        "LEASE_TAKEOVER",
        "SYSTEM",
    ),
    ("events", "properties", "severity", "enum"): (
        "INFO",
        "WARN",
        "ERROR",
    ),
    ("heartbeat_status", "properties", "status", "enum"): (
        "IDLE",
        "RUNNING",
        "WARNING",
        "STALE",
        "BLOCKED",
    ),
    ("process_leases", "$defs", "lease_record", "properties", "status", "enum"): (
        "ACTIVE",
        "RELEASED",
        "EXPIRED",
        "TAKEN_OVER",
    ),
}


def _load_schema(schema_name: str) -> dict:
    path = CONTRACTS_DIR / f"{schema_name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _get_nested_value(payload: dict, path: tuple[str, ...]) -> object:
    node: object = payload
    for token in path:
        if not isinstance(node, dict):
            raise AssertionError(f"invalid path traversal at {token}")
        node = node[token]
    return node


class SchemaCompatibilityGuardrailsTests(unittest.TestCase):
    def test_schema_version_is_pinned_to_1_0_0(self) -> None:
        for schema_name in SCHEMA_NAMES:
            schema = _load_schema(schema_name)
            schema_version = schema["properties"]["schema_version"]
            self.assertEqual(schema_version.get("const"), "1.0.0", schema_name)
            self.assertNotIn("enum", schema_version, schema_name)

    def test_critical_enums_are_frozen(self) -> None:
        for path, expected in EXPECTED_ENUMS.items():
            schema_name = path[0]
            schema = _load_schema(schema_name)
            actual = _get_nested_value(schema, path[1:])
            self.assertEqual(tuple(actual), expected, f"{schema_name} enum changed: {'.'.join(path[1:])}")

    def test_validator_rejects_schema_version_drift(self) -> None:
        for schema_name in SCHEMA_NAMES:
            payload = json.loads(
                (SAMPLES_DIR / f"{schema_name}.valid.json").read_text(encoding="utf-8")
            )
            payload["schema_version"] = "1.0.1"
            with self.assertRaises(SchemaValidationError) as ctx:
                validate_payload(schema_name, payload, contracts_dir=CONTRACTS_DIR)
            self.assertIn("$.schema_version", str(ctx.exception))

    def test_validator_rejects_unknown_event_type_enum_values(self) -> None:
        payload = json.loads((SAMPLES_DIR / "events.valid.json").read_text(encoding="utf-8"))
        payload["event_type"] = "OBSERVER_RELAY_SWITCHED"

        with self.assertRaises(SchemaValidationError) as ctx:
            validate_payload("events", payload, contracts_dir=CONTRACTS_DIR)
        self.assertIn("$.event_type", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
