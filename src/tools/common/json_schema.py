from __future__ import annotations

from typing import Any, Mapping


class JsonSchemaValidationError(ValueError):
    """Raised when a payload does not satisfy a JSON-schema contract."""


def validate_json_schema(*, schema: Mapping[str, Any], payload: Any) -> None:
    if not isinstance(schema, Mapping):
        raise JsonSchemaValidationError("schema must be an object")
    _validate_node(dict(schema), payload, path="$")


def _validate_node(schema: dict[str, Any], value: Any, *, path: str) -> None:
    if "const" in schema and value != schema["const"]:
        raise JsonSchemaValidationError(f"{path} must equal constant value {schema['const']!r}")

    if "enum" in schema and value not in schema["enum"]:
        raise JsonSchemaValidationError(f"{path} must be one of {schema['enum']!r}")

    if "type" in schema:
        _validate_type(path=path, value=value, expected=schema["type"])

    if isinstance(value, dict):
        _validate_object(schema=schema, value=value, path=path)

    if isinstance(value, list):
        _validate_array(schema=schema, value=value, path=path)

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise JsonSchemaValidationError(f"{path} length must be >= {schema['minLength']}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise JsonSchemaValidationError(f"{path} length must be <= {schema['maxLength']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise JsonSchemaValidationError(f"{path} must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise JsonSchemaValidationError(f"{path} must be <= {schema['maximum']}")


def _validate_object(*, schema: dict[str, Any], value: dict[str, Any], path: str) -> None:
    required = schema.get("required", [])
    if required is not None and not isinstance(required, list):
        raise JsonSchemaValidationError(f"{path}.required must be an array")

    for item in required:
        if item not in value:
            raise JsonSchemaValidationError(f"{path} missing required field '{item}'")

    properties = schema.get("properties", {})
    if properties is not None and not isinstance(properties, Mapping):
        raise JsonSchemaValidationError(f"{path}.properties must be an object")

    for key, item in value.items():
        if key in properties:
            property_schema = properties[key]
            if not isinstance(property_schema, Mapping):
                raise JsonSchemaValidationError(
                    f"{path}.properties.{key} must be an object schema"
                )
            _validate_node(dict(property_schema), item, path=f"{path}.{key}")
            continue

        additional = schema.get("additionalProperties", True)
        if additional is False:
            raise JsonSchemaValidationError(f"{path} contains unknown field '{key}'")
        if isinstance(additional, Mapping):
            _validate_node(dict(additional), item, path=f"{path}.{key}")


def _validate_array(*, schema: dict[str, Any], value: list[Any], path: str) -> None:
    if "minItems" in schema and len(value) < int(schema["minItems"]):
        raise JsonSchemaValidationError(f"{path} must contain at least {schema['minItems']} items")
    if "maxItems" in schema and len(value) > int(schema["maxItems"]):
        raise JsonSchemaValidationError(f"{path} must contain at most {schema['maxItems']} items")

    item_schema = schema.get("items")
    if item_schema is not None:
        if not isinstance(item_schema, Mapping):
            raise JsonSchemaValidationError(f"{path}.items must be an object schema")
        for index, item in enumerate(value):
            _validate_node(dict(item_schema), item, path=f"{path}[{index}]")


def _validate_type(*, path: str, value: Any, expected: str | list[str]) -> None:
    if isinstance(expected, list):
        if any(_matches_type(value=value, expected=item) for item in expected):
            return
        raise JsonSchemaValidationError(f"{path} must match one of types {expected!r}")

    if not _matches_type(value=value, expected=expected):
        raise JsonSchemaValidationError(f"{path} must be of type {expected!r}")


def _matches_type(*, value: Any, expected: str) -> bool:
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
    raise JsonSchemaValidationError(f"unsupported JSON schema type {expected!r}")
