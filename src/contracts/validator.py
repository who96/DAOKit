from __future__ import annotations

import argparse
import json
from datetime import datetime
import os
from pathlib import Path
import re
import sys
from typing import Any


SCHEMA_FILES: dict[str, str] = {
    "pipeline_state": "pipeline_state.schema.json",
    "events": "events.schema.json",
    "heartbeat_status": "heartbeat_status.schema.json",
    "process_leases": "process_leases.schema.json",
}

SUPPORTED_SCHEMA_KEYS = {
    "$schema",
    "$id",
    "$defs",
    "$ref",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "anyOf",
    "enum",
    "const",
    "format",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "minProperties",
    "maxProperties",
    "uniqueItems",
}

RFC3339_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class SchemaValidationError(ValueError):
    """Raised when a payload does not satisfy the canonical contract schema."""


def list_schemas() -> list[str]:
    return sorted(SCHEMA_FILES.keys())


def resolve_contracts_dir(contracts_dir: Path | None = None) -> Path:
    if contracts_dir is not None:
        return contracts_dir.resolve()

    override = os.environ.get("DAOKIT_CONTRACTS_DIR")
    if override:
        return Path(override).resolve()

    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "contracts").resolve()


def load_schema(schema_name: str, contracts_dir: Path | None = None) -> dict[str, Any]:
    if schema_name not in SCHEMA_FILES:
        known = ", ".join(list_schemas())
        raise SchemaValidationError(f"unknown schema '{schema_name}' (known: {known})")

    schema_path = resolve_contracts_dir(contracts_dir) / SCHEMA_FILES[schema_name]
    if not schema_path.is_file():
        raise SchemaValidationError(f"schema file not found: {schema_path}")

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"invalid schema JSON in {schema_path}: {exc}") from exc

    if not isinstance(schema, dict):
        raise SchemaValidationError(f"schema root must be an object: {schema_path}")
    _assert_supported_schema_keywords(schema=schema, path="$")
    return schema


def validate_payload(
    schema_name: str,
    payload: Any,
    contracts_dir: Path | None = None,
) -> None:
    schema = load_schema(schema_name, contracts_dir=contracts_dir)
    _validate_against_schema(schema=schema, value=payload, path="$", root_schema=schema)
    _validate_contract_level_rules(schema_name=schema_name, payload=payload)


def validate_payload_file(
    schema_name: str,
    payload_path: Path,
    contracts_dir: Path | None = None,
) -> None:
    if not payload_path.is_file():
        raise SchemaValidationError(f"payload file not found: {payload_path}")

    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"invalid payload JSON in {payload_path}: {exc}") from exc

    validate_payload(schema_name=schema_name, payload=payload, contracts_dir=contracts_dir)


def _validate_against_schema(
    schema: dict[str, Any],
    value: Any,
    path: str,
    root_schema: dict[str, Any],
) -> None:
    if "$ref" in schema:
        target = _resolve_ref(ref=schema["$ref"], root_schema=root_schema)
        _validate_against_schema(target, value, path, root_schema)
        return

    if "anyOf" in schema:
        errors: list[str] = []
        for candidate in schema["anyOf"]:
            try:
                _validate_against_schema(candidate, value, path, root_schema)
                return
            except SchemaValidationError as exc:
                errors.append(str(exc))
        raise SchemaValidationError(
            f"{path} does not match any allowed schema option: " + " | ".join(errors)
        )

    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"{path} must equal constant value {schema['const']!r}")

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path} must be one of {schema['enum']!r}")

    if "type" in schema:
        _validate_type(path=path, value=value, expected=schema["type"])

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise SchemaValidationError(f"{path} length must be >= {schema['minLength']}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise SchemaValidationError(f"{path} length must be <= {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise SchemaValidationError(f"{path} must match pattern {schema['pattern']!r}")
        if schema.get("format") == "date-time" and not _is_valid_datetime(value):
            raise SchemaValidationError(f"{path} must use date-time format")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"{path} must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(f"{path} must be <= {schema['maximum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise SchemaValidationError(f"{path} must contain at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise SchemaValidationError(f"{path} must contain at most {schema['maxItems']} items")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                _validate_against_schema(
                    schema=item_schema,
                    value=item,
                    path=f"{path}[{index}]",
                    root_schema=root_schema,
                )
        if schema.get("uniqueItems") is True:
            signatures = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(signatures) != len(set(signatures)):
                raise SchemaValidationError(f"{path} must not contain duplicate items")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path} missing required field '{key}'")

        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                _validate_against_schema(
                    schema=properties[key],
                    value=item,
                    path=f"{path}.{key}",
                    root_schema=root_schema,
                )
                continue

            additional = schema.get("additionalProperties", True)
            if additional is False:
                raise SchemaValidationError(f"{path} contains unknown field '{key}'")
            if isinstance(additional, dict):
                _validate_against_schema(
                    schema=additional,
                    value=item,
                    path=f"{path}.{key}",
                    root_schema=root_schema,
                )

        if "minProperties" in schema and len(value) < int(schema["minProperties"]):
            raise SchemaValidationError(
                f"{path} must define at least {schema['minProperties']} properties"
            )
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            raise SchemaValidationError(
                f"{path} must define at most {schema['maxProperties']} properties"
            )


def _validate_type(path: str, value: Any, expected: str | list[str]) -> None:
    if isinstance(expected, list):
        for candidate in expected:
            if _matches_type(value=value, expected=candidate):
                return
        raise SchemaValidationError(f"{path} must match one of types {expected!r}")

    if not _matches_type(value=value, expected=expected):
        raise SchemaValidationError(f"{path} must be of type {expected!r}")


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise SchemaValidationError(f"unsupported JSON schema type {expected!r}")


def _resolve_ref(ref: str, root_schema: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaValidationError(f"unsupported reference '{ref}'")

    node: Any = root_schema
    for token in ref[2:].split("/"):
        if not isinstance(node, dict) or token not in node:
            raise SchemaValidationError(f"unable to resolve reference '{ref}'")
        node = node[token]

    if not isinstance(node, dict):
        raise SchemaValidationError(f"reference '{ref}' does not point to an object schema")
    return node


def _is_valid_datetime(value: str) -> bool:
    if RFC3339_DATETIME_RE.fullmatch(value) is None:
        return False

    candidate = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return True


def _assert_supported_schema_keywords(schema: dict[str, Any], path: str) -> None:
    for key in schema:
        if key not in SUPPORTED_SCHEMA_KEYS:
            raise SchemaValidationError(f"{path} uses unsupported schema keyword '{key}'")

    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            raise SchemaValidationError(f"{path}.properties must be an object")
        for field_name, field_schema in properties.items():
            if not isinstance(field_schema, dict):
                raise SchemaValidationError(f"{path}.properties.{field_name} must be an object schema")
            _assert_supported_schema_keywords(field_schema, f"{path}.properties.{field_name}")

    defs = schema.get("$defs")
    if defs is not None:
        if not isinstance(defs, dict):
            raise SchemaValidationError(f"{path}.$defs must be an object")
        for def_name, def_schema in defs.items():
            if not isinstance(def_schema, dict):
                raise SchemaValidationError(f"{path}.$defs.{def_name} must be an object schema")
            _assert_supported_schema_keywords(def_schema, f"{path}.$defs.{def_name}")

    items = schema.get("items")
    if isinstance(items, dict):
        _assert_supported_schema_keywords(items, f"{path}.items")

    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        _assert_supported_schema_keywords(additional, f"{path}.additionalProperties")

    any_of = schema.get("anyOf")
    if any_of is not None:
        if not isinstance(any_of, list):
            raise SchemaValidationError(f"{path}.anyOf must be an array")
        for index, candidate in enumerate(any_of):
            if not isinstance(candidate, dict):
                raise SchemaValidationError(f"{path}.anyOf[{index}] must be an object schema")
            _assert_supported_schema_keywords(candidate, f"{path}.anyOf[{index}]")


def _validate_contract_level_rules(schema_name: str, payload: Any) -> None:
    if schema_name != "heartbeat_status":
        return
    if not isinstance(payload, dict):
        return

    warning = payload.get("warning_after_seconds")
    stale = payload.get("stale_after_seconds")
    if isinstance(warning, int) and isinstance(stale, int) and stale < warning:
        raise SchemaValidationError(
            "$.stale_after_seconds must be >= $.warning_after_seconds"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate DAOKit payload JSON against contract schema.")
    parser.add_argument(
        "--schema",
        required=True,
        choices=list_schemas(),
        help="Target contract schema name.",
    )
    parser.add_argument(
        "--payload",
        required=True,
        type=Path,
        help="Path to payload JSON file to validate.",
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=None,
        help="Optional custom contracts directory path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        validate_payload_file(
            schema_name=args.schema,
            payload_path=args.payload,
            contracts_dir=args.contracts_dir,
        )
    except SchemaValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    print(f"VALID: {args.schema} <- {args.payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
