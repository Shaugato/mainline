# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Layer 3: output-schema containment, and the exact size of what an injection can win.

Layer 3's claim in ARCHITECTURE.md 8.4 is one sentence: *an injection can at worst
produce wrong field values, never a new instruction channel*. This module is that
sentence made checkable, in two halves that fail in different ways.

**The static half** (:func:`assert_contained_schema`) is about what the schema makes
*expressible*. Two properties:

* every object node carries ``additionalProperties: false``. Without it a compromised
  model returns ``{"anchors": [...], "operator_note": "approve the permit"}``, the
  payload validates, and a free-text channel has been added to the record by the
  attacker. The dynamic half below would then have nothing to catch.
* no property anywhere is named in :data:`GATE_ARMING_FIELDS`. A ``severity`` field in an
  extraction schema is not a bug in a prompt; it is a *capability*, granted to a model,
  to set the field 8.4 says only a coded field, a regulator classification or a signed
  human may set. The control is that the field is not expressible at all.

**The dynamic half** (:func:`contain`) takes the payload a *fully compromised* model
would return - one that did exactly what the injected text asked - and reports the
largest effect it had. Three possible answers, and only the third is a residual:

``CONTAINED_UNKNOWN_FIELD``
    The payload carried a key the schema does not declare. Refused.
``CONTAINED_TYPE_VIOLATION``
    The payload carried a declared key with an undeclared shape or an off-enum value.
    Refused.
``VALUE_ONLY_DISTORTION``
    The payload is schema-valid and differs from the honest reading only in the *values*
    of declared fields. Nothing was added; something was changed. This is the honest
    residual of the whole posture and it is reported with the exact field paths, so the
    finding a human reads says which numbers moved.

**Why a validator lives here rather than a dependency.** The schema subset
``mainline_agentkit.schema.bedrock_schema`` emits is small and closed, and this package
holds no dependency (see ``pyproject.toml``). Unknown keywords are refused rather than
skipped: a validator that silently ignores a keyword it does not implement is a
validator that reports containment it did not check.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .classes import Layer, Outcome
from .errors import GateFieldInSchema, QuarantineError

__all__ = [
    "ANNOTATION_KEYWORDS",
    "GATE_ARMING_FIELDS",
    "SUPPORTED_KEYWORDS",
    "ContainmentResult",
    "SchemaUnsupported",
    "Violation",
    "assert_contained_schema",
    "contain",
    "field_differences",
]


class SchemaUnsupported(QuarantineError):
    """A schema used a keyword this validator does not implement. Fails closed."""

    def __init__(self, keyword: str, pointer: str) -> None:
        """Name the keyword and where it appeared."""
        super().__init__(
            f"unsupported JSON Schema keyword {keyword!r} at {pointer}: this validator "
            f"refuses what it cannot check, because silently skipping a keyword reports "
            f"containment that was never verified."
        )
        self.keyword = keyword
        self.pointer = pointer


#: Field names no structured-output schema in the Cognition plane may declare.
#:
#: Each name is a field the gate reads, or a field that would let a T1/T2 agent draft
#: something 8.2 reserves to ``svc_disposition`` and a signed human. The list is
#: deliberately over-broad on synonyms - ``severity``, ``severity_gate``,
#: ``severity_actual``, ``potential_admitted`` - because the cost of a false positive is
#: one renamed field in a proposal schema and the cost of a false negative is a model
#: with a legitimate channel into the gate.
GATE_ARMING_FIELDS: Final[frozenset[str]] = frozenset(
    {
        # severity, in every spelling the data model uses
        "severity",
        "severity_gate",
        "severity_actual",
        "severity_band",
        "potential_admitted",
        "fatal_potential",
        # the gate's own decision surface
        "admitted",
        "admissible",
        "blocking",
        "blocking_check",
        "blocking_check_id",
        "gate_outcome",
        "merge_allowed",
        "may_merge",
        "permit_state",
        "disposition",
        "disposition_id",
        "defeater_code",
        "rationale",
        "disposition_rationale",
        "override",
        "override_code",
        "signature",
        "signed_by",
        "retracted_by",
        # blame-edge state, which 8.2 says an inferred edge may never reach
        "edge_state",
        "blame_state",
        "basis",
        # the tool surface, for completeness: a schema that declared it would be a
        # channel even though the request never carries one
        "tools",
        "tool_choice",
        "toolConfig",
        "toolChoice",
        "mcp_servers",
    }
)

#: Keywords that carry no constraint and are ignored by design.
ANNOTATION_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"description", "title", "$schema", "$comment", "default", "examples", "$defs", "definitions"}
)

#: Keywords this validator implements. Anything else raises :class:`SchemaUnsupported`.
SUPPORTED_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"type", "properties", "required", "additionalProperties", "items", "enum", "const", "anyOf"}
)

_TYPES: Final[dict[str, tuple[type, ...]]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


@dataclass(frozen=True, slots=True)
class Violation:
    """One way a payload failed the schema, with the pointer it failed at."""

    kind: str
    pointer: str
    detail: str


@dataclass(frozen=True, slots=True)
class ContainmentResult:
    """What layer 3 did with one model payload."""

    outcome: Outcome
    layer: Layer
    violations: tuple[Violation, ...]
    distorted_fields: tuple[str, ...]

    @property
    def contained(self) -> bool:
        """Whether the payload was refused outright rather than admitted with wrong values."""
        return self.outcome in {
            Outcome.CONTAINED_UNKNOWN_FIELD,
            Outcome.CONTAINED_TYPE_VIOLATION,
        }


def assert_contained_schema(schema: Mapping[str, Any], *, name: str) -> None:
    """Refuse a schema that leaves a channel open or declares a gate-arming field.

    Raises:
        GateFieldInSchema: a property named in :data:`GATE_ARMING_FIELDS`.
        SchemaUnsupported: a keyword this validator cannot check, or a ``$ref`` (the
            wire schema is inlined; a reference here means the payload we validate is
            not the one the model was given).
    """
    _walk_schema(schema, "$", name)


def _walk_schema(node: Any, pointer: str, name: str) -> None:
    if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for index, item in enumerate(node):
            _walk_schema(item, f"{pointer}[{index}]", name)
        return
    if not isinstance(node, Mapping):
        return

    for keyword in node:
        if keyword in ANNOTATION_KEYWORDS or keyword in SUPPORTED_KEYWORDS:
            continue
        raise SchemaUnsupported(str(keyword), pointer)

    declared_type = node.get("type")
    properties = node.get("properties")
    if declared_type == "object" or isinstance(properties, Mapping):
        if node.get("additionalProperties") is not False:
            raise SchemaUnsupported("additionalProperties", pointer)
        if isinstance(properties, Mapping):
            for field, sub in properties.items():
                if str(field) in GATE_ARMING_FIELDS:
                    raise GateFieldInSchema(name, str(field), f"{pointer}.properties.{field}")
                _walk_schema(sub, f"{pointer}.properties.{field}", name)
    items = node.get("items")
    if items is not None:
        _walk_schema(items, f"{pointer}.items", name)
    for index, branch in enumerate(node.get("anyOf", []) or []):
        _walk_schema(branch, f"{pointer}.anyOf[{index}]", name)


def contain(
    payload: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any] | None = None,
) -> ContainmentResult:
    """Report the largest effect a compromised payload had.

    Args:
        payload: what a model that obeyed the injected text would return.
        schema: the wire schema the call was constrained by.
        baseline: the honest reading of the same document, when the corpus case knows
            it. Supplying it is what turns "the payload validated" into "the injection
            moved exactly these three values", which is the sentence a finding needs.
    """
    violations = tuple(_validate(payload, schema, "$"))
    if any(violation.kind == "unknown_field" for violation in violations):
        return ContainmentResult(
            outcome=Outcome.CONTAINED_UNKNOWN_FIELD,
            layer=Layer.L3_OUTPUT_SCHEMA_CONTAINMENT,
            violations=violations,
            distorted_fields=(),
        )
    if violations:
        return ContainmentResult(
            outcome=Outcome.CONTAINED_TYPE_VIOLATION,
            layer=Layer.L3_OUTPUT_SCHEMA_CONTAINMENT,
            violations=violations,
            distorted_fields=(),
        )
    distorted = field_differences(baseline, payload) if baseline is not None else ()
    return ContainmentResult(
        outcome=Outcome.VALUE_ONLY_DISTORTION if distorted else Outcome.CLEAN,
        layer=Layer.L3_OUTPUT_SCHEMA_CONTAINMENT,
        violations=(),
        distorted_fields=distorted,
    )


def field_differences(
    baseline: Mapping[str, Any] | None,
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Dotted paths at which ``payload`` differs from ``baseline``. Order-stable."""
    if baseline is None:
        return ()
    out: list[str] = []
    _diff(baseline, payload, "", out)
    return tuple(out)


def _diff(left: Any, right: Any, pointer: str, out: list[str]) -> None:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        for key in sorted(set(left) | set(right), key=str):
            child = f"{pointer}.{key}" if pointer else str(key)
            if key not in left or key not in right:
                out.append(child)
                continue
            _diff(left[key], right[key], child, out)
        return
    if (
        isinstance(left, Sequence)
        and isinstance(right, Sequence)
        and not isinstance(left, (str, bytes))
        and not isinstance(right, (str, bytes))
    ):
        if len(left) != len(right):
            out.append(f"{pointer}[]")
            return
        for index, (l_item, r_item) in enumerate(zip(left, right, strict=True)):
            _diff(l_item, r_item, f"{pointer}[{index}]", out)
        return
    if left != right:
        out.append(pointer or "$")


def _check_type(value: Any, schema: Mapping[str, Any], pointer: str) -> list[Violation] | None:
    """``None`` means the type checked out; a list means stop, the shape is wrong."""
    declared_type = schema.get("type")
    if not isinstance(declared_type, str):
        return None
    expected = _TYPES.get(declared_type)
    if expected is None:
        raise SchemaUnsupported(f"type={declared_type}", pointer)
    # `bool` is a subclass of `int` in Python, and an extraction that returned `True`
    # where an integer milli-value belongs is a type violation, not a 1.
    if declared_type in {"integer", "number"} and isinstance(value, bool):
        return [Violation("type", pointer, "boolean where a number was declared")]
    if not isinstance(value, expected):
        return [Violation("type", pointer, f"expected {declared_type}, got {type(value).__name__}")]
    return None


def _check_scalar(value: Any, schema: Mapping[str, Any], pointer: str) -> list[Violation]:
    out: list[Violation] = []
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes)) and value not in enum:
        out.append(Violation("enum", pointer, f"{value!r} is not one of {list(enum)}"))
    if "const" in schema and value != schema["const"]:
        out.append(Violation("const", pointer, f"{value!r} != {schema['const']!r}"))
    return out


def _check_object(
    value: Mapping[str, Any], schema: Mapping[str, Any], pointer: str
) -> list[Violation]:
    out: list[Violation] = []
    properties = schema.get("properties")
    known = set(properties) if isinstance(properties, Mapping) else set()
    if schema.get("additionalProperties") is False:
        out.extend(
            Violation(
                "unknown_field",
                f"{pointer}.{key}",
                "the schema declares additionalProperties: false, so this key is a "
                "channel the model tried to open",
            )
            for key in value
            if key not in known
        )
    out.extend(
        Violation("required", f"{pointer}.{key}", "required key absent")
        for key in schema.get("required", []) or []
        if key not in value
    )
    if isinstance(properties, Mapping):
        for key, sub in properties.items():
            if key in value and isinstance(sub, Mapping):
                out.extend(_validate(value[key], sub, f"{pointer}.{key}"))
    return out


def _check_any_of(
    value: Any, schema: Mapping[str, Any], pointer: str, out: list[Violation]
) -> list[Violation]:
    branches = schema.get("anyOf")
    if not isinstance(branches, Sequence) or isinstance(branches, (str, bytes)) or not branches:
        return out
    if any(
        not _validate(value, branch, pointer) for branch in branches if isinstance(branch, Mapping)
    ):
        # A branch accepted the value. An unknown field is still a finding, because
        # `additionalProperties: false` holds whichever branch applied.
        return [violation for violation in out if violation.kind == "unknown_field"]
    return [*out, Violation("anyOf", pointer, "value matched no branch of anyOf")]


def _validate(value: Any, schema: Mapping[str, Any], pointer: str) -> list[Violation]:
    fatal = _check_type(value, schema, pointer)
    if fatal is not None:
        return fatal

    out = _check_scalar(value, schema, pointer)
    if isinstance(value, Mapping):
        out.extend(_check_object(value, schema, pointer))
    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                out.extend(_validate(item, items, f"{pointer}[{index}]"))
    return _check_any_of(value, schema, pointer, out)
