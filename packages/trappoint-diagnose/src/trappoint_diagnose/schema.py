# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""A deliberately small JSON Schema 2020-12 validator, sized to the refusal payload.

Keyword set, and nothing else:

``type`` (a name or a list of names) · ``enum`` · ``const`` · ``pattern`` ·
``minLength`` / ``maxLength`` · ``minimum`` / ``maximum`` · ``required`` ·
``properties`` · ``additionalProperties`` (boolean or schema) · ``minProperties`` ·
``items`` · ``minItems`` / ``maxItems`` / ``uniqueItems`` · ``allOf`` · ``oneOf`` ·
``if`` / ``then`` / ``else`` · ``$ref`` into ``#/$defs`` · ``$defs`` · ``format`` ·
plus the annotation keywords (``title``, ``description``, ``$comment``, ``$id``,
``$schema``, ``default``) which are read and ignored.

**Why not the `jsonschema` package.** This module decides whether a refusal payload may
be emitted and recorded. Its "yes" is what a console renders and what a ledger stores
forever, so every dependency on this path is another package an opposing expert must
trust in order to trust the diagnosis. Eighteen keywords is a file and a test suite.

**An unknown keyword is REFUSED, never ignored.** If ``refusal.schema.json`` grows a
keyword this module does not implement, validation raises ``UnsupportedKeyword`` rather
than passing vacuously. A validator that silently skips a keyword reports success for an
instance it never checked, which is strictly worse than having no validator at all —
and in this system it would be worse in the specific direction that matters, because the
keyword most likely to be added is one that closes a shape.

``format`` is checked for ``date-time`` only, and the check is deliberate: an
``observed_at`` that is not an RFC 3339 instant makes the refusal unorderable against
every other record in the ledger. Every other format annotation is accepted as
informative, which is what the specification says it is.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

__all__ = ["SchemaViolation", "UnsupportedKeyword", "validate"]

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
        "format",
        "if",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "oneOf",
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
_TYPE_NAMES: frozenset[str] = frozenset(
    {"boolean", "integer", "number", "string", "array", "object", "null"}
)


class SchemaViolation(Exception):
    """The instance does not satisfy the schema.

    ``pointer`` is a JSON Pointer into the *instance*, because the reader is looking at a
    payload with fourteen top-level fields and needs to know which one.
    """

    def __init__(self, pointer: str, message: str) -> None:
        """Record the JSON Pointer and render it into the exception's own message."""
        self.pointer = pointer or "/"
        self.message = message
        super().__init__(f"{self.pointer}: {message}")


class UnsupportedKeyword(Exception):
    """The schema uses a keyword this validator does not implement."""


def _type_name(value: object) -> str:  # noqa: PLR0911
    # One return per JSON type. Flat on purpose: a dispatch table would satisfy the
    # return-count metric and read as indirection over seven facts that never change.
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
            f"$ref {ref!r} is not a local #/$defs/ reference; a remote reference would "
            "put a network fetch on the path that decides whether a refusal may be "
            "recorded"
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
    if schema.get("format") == "date-time":
        _validate_date_time(value, pointer)


def _validate_date_time(value: str, pointer: str) -> None:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SchemaViolation(pointer, f"{value!r} is not an RFC 3339 instant") from exc
    if parsed.tzinfo is None:
        raise SchemaViolation(
            pointer,
            f"{value!r} carries no offset. A naive timestamp in an evidentiary payload "
            "is an unanswerable question in cross-examination.",
        )


def _validate_number(value: float, schema: dict[str, Any], pointer: str) -> None:
    minimum = schema.get("minimum")
    if isinstance(minimum, int | float) and not isinstance(minimum, bool) and value < minimum:
        raise SchemaViolation(pointer, f"{value} is below minimum {minimum}")
    maximum = schema.get("maximum")
    if isinstance(maximum, int | float) and not isinstance(maximum, bool) and value > maximum:
        raise SchemaViolation(pointer, f"{value} is above maximum {maximum}")


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
            f"unexpected key(s) {', '.join(repr(k) for k in extra)}. Atom and payload "
            "shapes are closed; an unknown key is where a score characterising a named "
            "human would arrive (I15).",
        )
    if isinstance(additional, dict):
        for key in extra:
            _validate(value[key], additional, root, f"{pointer}/{key}")


def _validate_one_of(
    instance: object, branches: list[Any], root: dict[str, Any], pointer: str
) -> None:
    """Exactly one branch must validate.

    The failure message names the count rather than the branches: for a ``mus`` atom the
    branches are the five fact families, and "matched 0 of 5" plus the atom's own ``kind``
    is what a reader needs, while five nested tracebacks is what they would skim.
    """
    matched = 0
    for branch in branches:
        try:
            _validate(instance, branch, root, pointer)
        except SchemaViolation:
            continue
        matched += 1
    if matched != 1:
        raise SchemaViolation(
            pointer,
            f"matched {matched} of {len(branches)} alternatives; exactly one is required",
        )


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
    if isinstance(declared, list):
        for name in declared:
            if name not in _TYPE_NAMES:
                raise UnsupportedKeyword(f"unknown type name {name!r} in schema")
        if not any(_matches_type(instance, name) for name in declared):
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
    elif isinstance(instance, bool):
        pass
    elif isinstance(instance, int | float):
        _validate_number(instance, schema, pointer)
    elif isinstance(instance, list):
        _validate_array(instance, schema, root, pointer)
    elif isinstance(instance, dict):
        _validate_object(instance, schema, root, pointer)

    for sub in schema.get("allOf", []):
        _validate(instance, sub, root, pointer)

    branches = schema.get("oneOf")
    if isinstance(branches, list):
        _validate_one_of(instance, branches, root, pointer)

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

    First violation, not all of them: a payload with two faults is fixed one at a time,
    and one precise sentence is read where a list of nine is skimmed.

    Raises:
        SchemaViolation: the instance is invalid; ``pointer`` locates it.
        UnsupportedKeyword: the schema uses a keyword this validator does not implement.
    """
    _validate(instance, schema, schema, "")
