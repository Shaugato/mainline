# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""A deliberately small JSON Schema 2020-12 validator.

Scope is exactly the keyword set used by ``spec/binding/vertical.schema.json`` and
nothing else:

``type`` (including a list of types) · ``enum`` · ``const`` · ``pattern`` ·
``minLength`` / ``maxLength`` · ``required`` · ``properties`` ·
``additionalProperties`` (boolean or schema) · ``minProperties`` · ``items`` ·
``minItems`` / ``maxItems`` · ``uniqueItems`` · ``allOf`` · ``if`` / ``then`` /
``else`` · ``$ref`` into ``#/$defs`` · ``$defs``.

**Why not the `jsonschema` package.** This module decides whether a vertical is allowed
to emit gate SQL. Every dependency on that path is another package an opposing expert
must trust in order to trust the refusal. The schema uses eleven keywords; eleven
keywords is a file and a test suite, not a supply chain. The trade is stated plainly in
`pyproject.toml` and the limitation is stated here: **an unknown keyword is refused,
never ignored.** A schema that grew a keyword this module does not implement must not
validate vacuously, so ``validate`` raises on it. That is the only safe direction for a
validator whose "yes" is a licence to generate a schema.

Errors carry a JSON Pointer to the offending location, because the reader is looking at
a TOML file with forty keys and needs to know which one.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["SchemaViolation", "UnsupportedKeyword", "validate"]

# Keywords this module understands. Anything else in a schema object is a refusal:
# see the module docstring for why silence is not an option here.
_SUPPORTED: frozenset[str] = frozenset(
    {
        "$comment",
        "$defs",
        "$id",
        "$ref",
        "$schema",
        "additionalProperties",
        "allOf",
        "const",
        "default",
        "description",
        "else",
        "enum",
        "if",
        "items",
        "maxItems",
        "maxLength",
        "minItems",
        "minLength",
        "minProperties",
        "pattern",
        "properties",
        "required",
        "then",
        "title",
        "type",
        "uniqueItems",
    }
)

_DEFS_PREFIX = "#/$defs/"


class SchemaViolation(Exception):
    """The instance does not satisfy the schema.

    ``pointer`` is a JSON Pointer into the *instance*, so the message can be pasted
    straight into a conversation about which line of ``vertical.toml`` is wrong.
    """

    def __init__(self, pointer: str, message: str) -> None:
        """Record the JSON Pointer and render it into the exception's own message."""
        self.pointer = pointer or "/"
        self.message = message
        super().__init__(f"{self.pointer}: {message}")


class UnsupportedKeyword(Exception):
    """The schema uses a keyword this validator does not implement.

    Raised rather than ignored. A validator that silently skips a keyword reports
    success for an instance it never checked, which is worse than having no validator.
    """


def _type_name(value: object) -> str:  # noqa: PLR0911
    # One return per JSON type. A dispatch table would satisfy the return-count metric
    # and would read as indirection over a list of seven facts that never change.
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__


def _matches_type(value: object, expected: str) -> bool:  # noqa: PLR0911
    # As `_type_name`: one branch per JSON type, deliberately flat.
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    raise UnsupportedKeyword(f"unknown type name {expected!r} in schema")


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref is None:
        return schema
    if not isinstance(ref, str) or not ref.startswith(_DEFS_PREFIX):
        raise UnsupportedKeyword(
            f"$ref {ref!r} is not a local #/$defs/ reference; remote references are "
            "refused because resolving one would put a network fetch on the path that "
            "decides whether a vertical may generate a schema"
        )
    name = ref[len(_DEFS_PREFIX) :]
    defs = root.get("$defs")
    if not isinstance(defs, dict) or name not in defs:
        raise UnsupportedKeyword(f"$ref {ref!r} does not resolve in this document")
    target = defs[name]
    if not isinstance(target, dict):
        raise UnsupportedKeyword(f"$defs/{name} is not a schema object")
    return _resolve(target, root)


def _check_keywords(schema: dict[str, Any]) -> None:
    unknown = sorted(set(schema) - _SUPPORTED)
    if unknown:
        raise UnsupportedKeyword(
            f"schema uses keyword(s) {', '.join(unknown)} which this validator does not "
            "implement. Refusing rather than ignoring: a skipped keyword is an unchecked "
            "instance reported as valid."
        )


def _validate_string(value: str, schema: dict[str, Any], pointer: str) -> None:
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and re.search(pattern, value) is None:
        raise SchemaViolation(pointer, f"{value!r} does not match /{pattern}/")
    min_length = schema.get("minLength")
    if isinstance(min_length, int) and len(value) < min_length:
        raise SchemaViolation(pointer, f"shorter than minLength {min_length}")
    max_length = schema.get("maxLength")
    if isinstance(max_length, int) and len(value) > max_length:
        raise SchemaViolation(pointer, f"longer than maxLength {max_length}")


def _validate_array(
    value: list[Any], schema: dict[str, Any], root: dict[str, Any], pointer: str
) -> None:
    min_items = schema.get("minItems")
    if isinstance(min_items, int) and len(value) < min_items:
        raise SchemaViolation(pointer, f"{len(value)} item(s), minItems is {min_items}")
    max_items = schema.get("maxItems")
    if isinstance(max_items, int) and len(value) > max_items:
        raise SchemaViolation(pointer, f"{len(value)} item(s), maxItems is {max_items}")
    if schema.get("uniqueItems") is True:
        seen: list[Any] = []
        for index, item in enumerate(value):
            if item in seen:
                raise SchemaViolation(f"{pointer}/{index}", f"duplicate item {item!r}")
            seen.append(item)
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            _validate(item, item_schema, root, f"{pointer}/{index}")


def _validate_object(
    value: dict[str, Any], schema: dict[str, Any], root: dict[str, Any], pointer: str
) -> None:
    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if key not in value:
                raise SchemaViolation(pointer, f"required key {key!r} is missing")
    min_properties = schema.get("minProperties")
    if isinstance(min_properties, int) and len(value) < min_properties:
        raise SchemaViolation(pointer, f"needs at least {min_properties} key(s)")

    properties = schema.get("properties")
    known: set[str] = set()
    if isinstance(properties, dict):
        known = set(properties)
        for key in sorted(value):
            if key in properties:
                _validate(value[key], properties[key], root, f"{pointer}/{key}")

    extra = sorted(set(value) - known)
    additional = schema.get("additionalProperties", True)
    if additional is False and extra:
        raise SchemaViolation(
            pointer,
            f"unexpected key(s) {', '.join(repr(k) for k in extra)}. "
            "In TOML this is most often a bare top-level key written after a [table] "
            "header, which silently belongs to that table.",
        )
    if isinstance(additional, dict):
        for key in extra:
            _validate(value[key], additional, root, f"{pointer}/{key}")


def _validate(  # noqa: PLR0912
    instance: object, schema: object, root: dict[str, Any], pointer: str
) -> None:
    # One branch per supported keyword, in the order the module docstring lists them.
    # Collapsing them behind a dispatch table would hide which keywords are implemented,
    # and this validator's whole safety argument is that an unimplemented keyword is
    # REFUSED rather than ignored — a claim a reader has to be able to check by reading.
    if schema is True:
        return
    if schema is False:
        raise SchemaViolation(pointer, "schema is `false`: nothing is valid here")
    if not isinstance(schema, dict):
        raise UnsupportedKeyword(f"schema at {pointer} is neither an object nor a boolean")

    schema = _resolve(schema, root)
    _check_keywords(schema)

    declared = schema.get("type")
    if isinstance(declared, str) and not _matches_type(instance, declared):
        raise SchemaViolation(pointer, f"expected {declared}, got {_type_name(instance)}")
    if isinstance(declared, list) and not any(_matches_type(instance, name) for name in declared):
        raise SchemaViolation(
            pointer, f"expected one of {', '.join(declared)}, got {_type_name(instance)}"
        )

    if "const" in schema and instance != schema["const"]:
        raise SchemaViolation(
            pointer, f"must be {schema['const']!r} (got {instance!r}); there is no second value"
        )
    choices = schema.get("enum")
    if isinstance(choices, list) and instance not in choices:
        raise SchemaViolation(
            pointer, f"{instance!r} is not one of {', '.join(repr(c) for c in choices)}"
        )

    if isinstance(instance, str):
        _validate_string(instance, schema, pointer)
    elif isinstance(instance, list):
        _validate_array(instance, schema, root, pointer)
    elif isinstance(instance, dict):
        _validate_object(instance, schema, root, pointer)

    for sub in schema.get("allOf", []):
        _validate(instance, sub, root, pointer)

    condition = schema.get("if")
    if condition is not None:
        try:
            _validate(instance, condition, root, pointer)
        except SchemaViolation:
            branch = schema.get("else")
        else:
            branch = schema.get("then")
        if branch is not None:
            _validate(instance, branch, root, pointer)


def validate(instance: object, schema: dict[str, Any]) -> None:
    """Validate *instance* against *schema*, raising on the first violation.

    First violation, not all of them. A binding with two errors is fixed one error at a
    time anyway, and a single precise sentence is read where a list of nine is skimmed.

    Raises:
        SchemaViolation: the instance is invalid; ``pointer`` locates it.
        UnsupportedKeyword: the schema uses a keyword this validator does not implement.
    """
    _validate(instance, schema, schema, "")
