# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The validator itself, including the property that makes it safe to have written.

The interesting test is the last one. A validator that ignores a keyword it does not
implement reports success for an instance it never checked, and the keyword most likely to
be added to a schema like this one is a keyword that CLOSES a shape. So an unknown keyword
must be a refusal, and that has to be asserted or it is just a paragraph in a docstring.
"""

from __future__ import annotations

import pytest

from trappoint_diagnose.schema import SchemaViolation, UnsupportedKeyword, validate


def test_type_string_and_pattern():
    validate("abc", {"type": "string", "pattern": "^a"})
    with pytest.raises(SchemaViolation, match="does not match"):
        validate("zbc", {"type": "string", "pattern": "^a"})


def test_type_union():
    schema = {"type": ["string", "null"]}
    validate("x", schema)
    validate(None, schema)
    with pytest.raises(SchemaViolation, match="expected one of"):
        validate(3, schema)


def test_integer_is_not_boolean():
    with pytest.raises(SchemaViolation):
        validate(True, {"type": "integer"})


def test_minimum_and_maximum():
    validate(5, {"type": "integer", "minimum": 0, "maximum": 5})
    with pytest.raises(SchemaViolation, match="below minimum"):
        validate(-1, {"type": "integer", "minimum": 0})
    with pytest.raises(SchemaViolation, match="above maximum"):
        validate(6, {"type": "integer", "maximum": 5})


def test_length_bounds():
    validate("ab", {"type": "string", "minLength": 1, "maxLength": 2})
    with pytest.raises(SchemaViolation, match="minLength"):
        validate("", {"type": "string", "minLength": 1})
    with pytest.raises(SchemaViolation, match="maxLength"):
        validate("abc", {"type": "string", "maxLength": 2})


def test_const_and_enum():
    validate("gate", {"const": "gate"})
    with pytest.raises(SchemaViolation, match="no second value"):
        validate("retry", {"const": "gate"})
    with pytest.raises(SchemaViolation, match="is not one of"):
        validate("40001", {"enum": ["23514", "23503"]})


def test_required_and_additional_properties():
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "integer"}},
        "additionalProperties": False,
    }
    validate({"a": 1}, schema)
    with pytest.raises(SchemaViolation, match="required key"):
        validate({}, schema)
    with pytest.raises(SchemaViolation, match="unexpected key"):
        validate({"a": 1, "b": 2}, schema)


def test_additional_properties_as_a_schema():
    schema = {"type": "object", "additionalProperties": {"type": "string"}}
    validate({"x": "ok"}, schema)
    with pytest.raises(SchemaViolation):
        validate({"x": 1}, schema)


def test_min_properties():
    with pytest.raises(SchemaViolation, match="at least 1"):
        validate({}, {"type": "object", "minProperties": 1})


def test_array_bounds_items_and_uniqueness():
    schema = {
        "type": "array",
        "minItems": 1,
        "maxItems": 2,
        "uniqueItems": True,
        "items": {"type": "integer"},
    }
    validate([1, 2], schema)
    with pytest.raises(SchemaViolation, match="minItems"):
        validate([], schema)
    with pytest.raises(SchemaViolation, match="maxItems"):
        validate([1, 2, 3], schema)
    with pytest.raises(SchemaViolation, match="duplicate"):
        validate([1, 1], schema)


def test_one_of_requires_exactly_one_match():
    schema = {
        "oneOf": [
            {
                "type": "object",
                "required": ["a"],
                "additionalProperties": False,
                "properties": {"a": {"type": "integer"}},
            },
            {
                "type": "object",
                "required": ["b"],
                "additionalProperties": False,
                "properties": {"b": {"type": "integer"}},
            },
        ]
    }
    validate({"a": 1}, schema)
    with pytest.raises(SchemaViolation, match="matched 0 of 2"):
        validate({"c": 1}, schema)


def test_all_of_requires_every_branch():
    schema = {"allOf": [{"type": "integer"}, {"minimum": 3}]}
    validate(4, schema)
    with pytest.raises(SchemaViolation):
        validate(2, schema)


def test_if_then_else():
    schema = {
        "if": {"properties": {"k": {"const": "x"}}, "required": ["k"]},
        "then": {"required": ["only_when_x"]},
        "else": {"required": ["otherwise"]},
    }
    validate({"k": "x", "only_when_x": 1}, schema)
    validate({"k": "y", "otherwise": 1}, schema)
    with pytest.raises(SchemaViolation, match="only_when_x"):
        validate({"k": "x"}, schema)


def test_local_ref_resolution():
    schema = {"$defs": {"u": {"type": "string", "minLength": 2}}, "$ref": "#/$defs/u"}
    validate("ab", schema)
    with pytest.raises(SchemaViolation):
        validate("a", schema)


def test_a_remote_ref_is_refused():
    with pytest.raises(UnsupportedKeyword, match="network fetch"):
        validate("x", {"$ref": "https://example.invalid/schema.json"})


def test_date_time_format_is_enforced():
    schema = {"type": "string", "format": "date-time"}
    validate("2026-08-04T02:14:07.481Z", schema)
    with pytest.raises(SchemaViolation, match="RFC 3339"):
        validate("last Tuesday", schema)
    with pytest.raises(SchemaViolation, match="no offset"):
        validate("2026-08-04T02:14:07", schema)


def test_a_false_schema_admits_nothing():
    with pytest.raises(SchemaViolation, match="nothing is valid"):
        validate(1, False)


def test_a_true_schema_admits_anything():
    validate({"whatever": [1, 2]}, True)


def test_an_unknown_keyword_is_refused_rather_than_ignored():
    # The property this validator's whole safety argument rests on.
    with pytest.raises(UnsupportedKeyword, match="does not implement"):
        validate({"a": 1}, {"type": "object", "dependentRequired": {"a": ["b"]}})


def test_an_unknown_type_name_is_refused():
    with pytest.raises(UnsupportedKeyword, match="unknown type name"):
        validate("x", {"type": "stringy"})


def test_an_unknown_type_name_inside_a_union_is_refused():
    with pytest.raises(UnsupportedKeyword, match="unknown type name"):
        validate("x", {"type": ["string", "decimal"]})


def test_the_violation_carries_a_pointer_into_the_instance():
    schema = {
        "type": "object",
        "properties": {
            "mus": {
                "type": "array",
                "items": {"type": "object", "properties": {"kind": {"type": "string"}}},
            }
        },
    }
    with pytest.raises(SchemaViolation) as caught:
        validate({"mus": [{"kind": 1}]}, schema)
    assert caught.value.pointer == "/mus/0/kind"
