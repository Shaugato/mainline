# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Validate a rendered response against its prompt's tool schema.

Every tier's output goes through here, not just the model's.  A deterministic renderer that
dropped a field is exactly as broken as a model that did, and finding out at load time — four
stages downstream, against a ``NOT NULL`` in CockroachDB — costs a great deal more than finding
out here.

The validator is written out rather than delegated to ``jsonschema`` for two reasons.  The
schemas in ``prompts/*.md`` are a closed subset (object / array / string / integer / number /
boolean, ``enum``, ``required``, ``additionalProperties: false``) that fits in eighty lines; and
the error messages a generic validator produces name a JSON pointer, whereas the messages here
name the node and the field, which is what the person reading CI output needs.  If the schema
subset ever grows, this refuses the unknown construct rather than ignoring it — an unsupported
keyword is a validation gap, and a silent validation gap is worse than no validation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["SchemaViolation", "validate_response"]


class SchemaViolation(RuntimeError):
    """A rendered response does not satisfy its prompt's tool schema."""


_TYPE_CHECKS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


def _check_object(value: Any, schema: Mapping[str, Any], *, where: str) -> None:
    if not isinstance(value, Mapping):
        raise SchemaViolation(f"{where}: expected an object, got {type(value).__name__}")
    properties: Mapping[str, Any] = schema["properties"]
    required = {str(name) for name in schema["required"]}
    missing = sorted(required - set(value))
    if missing:
        raise SchemaViolation(f"{where}: missing required field(s) {missing}")
    extra = sorted(set(value) - set(properties))
    if extra:
        raise SchemaViolation(
            f"{where}: undeclared field(s) {extra}; the schema sets "
            "`additionalProperties: false` and a field nothing declared is a field nothing "
            "downstream reads"
        )
    for name, child in properties.items():
        _check(value[name], child, where=f"{where}.{name}")


def _check_array(value: Any, schema: Mapping[str, Any], *, where: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise SchemaViolation(f"{where}: expected an array, got {type(value).__name__}")
    for position, item in enumerate(value):
        _check(item, schema["items"], where=f"{where}[{position}]")


def _check(value: Any, schema: Mapping[str, Any], *, where: str) -> None:
    node_type = schema.get("type")

    if node_type == "object":
        _check_object(value, schema, where=where)
        return

    if node_type == "array":
        _check_array(value, schema, where=where)
        return

    expected = _TYPE_CHECKS.get(str(node_type))
    if expected is None:
        raise SchemaViolation(
            f"{where}: schema declares unsupported type {node_type!r}. This validator refuses "
            "what it cannot check rather than passing it."
        )
    # `bool` is a subclass of `int`; a boolean where an integer belongs is a real defect.
    if isinstance(value, bool) and node_type != "boolean":
        raise SchemaViolation(f"{where}: expected {node_type}, got boolean")
    if not isinstance(value, expected):
        raise SchemaViolation(f"{where}: expected {node_type}, got {type(value).__name__}")

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        raise SchemaViolation(f"{where}: {value!r} is not one of {list(enum)}")

    if node_type == "string" and isinstance(value, str) and not value.strip():
        raise SchemaViolation(
            f"{where}: empty string. Every string in these schemas is a sentence something "
            "downstream binds, digests or prints; an empty one is an abstention wearing the "
            "costume of an answer."
        )


def validate_response(
    response: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    node_id: str,
    renderer: str,
) -> None:
    """Refuse ``response`` if it does not satisfy ``schema``."""
    try:
        _check(response, schema, where="response")
    except SchemaViolation as exc:
        raise SchemaViolation(f"{renderer} tier, node {node_id}: {exc}") from None
