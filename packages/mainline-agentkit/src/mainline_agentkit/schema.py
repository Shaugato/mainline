# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Pydantic model to Bedrock-legal JSON Schema, and back again as validators.

Decision A7. Structured outputs silently ignore or reject a documented set of JSON
Schema keywords. A ``<=60-token cue`` expressed as ``maxLength`` on a schema the
server ignores is **an unenforced promise**, and an unenforced promise in a safety
record is worse than an absent one because a reader believes it.

So :func:`bedrock_schema` does three things and records all of them:

1. **Strips** the documented-unsupported keywords, returning each one as a
   :class:`StrippedConstraint` with the pointer it was removed from;
2. **Refuses** recursion — a ``$ref`` cycle cannot be inlined, and a schema that does
   not describe the type we validate against is not a schema;
3. **Forces** ``additionalProperties: false`` on every object, which is §8.4's
   structured-output contract and layer 3 of the injection posture: an injection can
   at worst produce wrong field *values*, never a new instruction channel.

The stripped invariants are then re-imposed on the client side, and this is where the
design is deliberately belt-and-braces:

* the **primary** re-imposition is ``Model.model_validate()``. The constraints live in
  the Pydantic model, so validating the parsed payload against the same model that
  generated the schema re-checks every one of them. Deriving the schema from the model
  is what makes this true — two hand-maintained copies would not be;
* the **secondary** re-imposition is :meth:`BedrockSchema.check_stripped`, an
  independent walk that does not go through Pydantic at all. It exists so the golden
  vectors can prove the strip actually happened, and so a non-Pydantic consumer of the
  wire schema still has the constraint list in machine-readable form.

``check_stripped`` marks a constraint ``checkable=False`` when it sits inside a
``anyOf`` branch or an ``additionalProperties`` subschema, because which branch a
value took is not decidable from the value alone. Those constraints are still recorded
and still enforced by Pydantic; they are simply not double-checked here. Saying so is
cheaper than a footnote nobody reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from ._canon import canonical_json_bytes, sha256_hex, stable_json_bytes
from .errors import SchemaViolation, UnsupportedSchema

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "OPTIONAL_STRIPPED_KEYWORDS",
    "STRIPPED_KEYWORDS",
    "BedrockSchema",
    "StrippedConstraint",
    "bedrock_schema",
]

#: The frozen set of keywords :func:`bedrock_schema` removes from every schema it
#: emits, in one place so a golden vector can assert it **exactly**. A schema-feature
#: change on the platform therefore breaks a test rather than a control.
#:
#: Decision A7 names them as: ``minLength``/``maxLength``, ``minimum``/``maximum``/
#: ``multipleOf``, and the array-size constraints. The exclusive bounds are here
#: because Pydantic emits them for ``Field(gt=...)`` and they are the same family.
STRIPPED_KEYWORDS: frozenset[str] = frozenset(
    {
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
    }
)

#: Stripped only when ``strip_pattern=True``. ``pattern`` is **not** in the documented
#: unsupported set, so it stays in the wire schema by default and is additionally
#: re-checked client-side. If GT-AG-01 shows the native ``InvokeModel`` body rejecting
#: it on an ``au.*`` profile ARN, one flag moves it into the stripped set and one test
#: changes. Unverified against the live API as of 2026-08-07: AWS credentials are not
#: valid on the build machine.
OPTIONAL_STRIPPED_KEYWORDS: frozenset[str] = frozenset({"pattern"})

_OBJECT = "object"
_ARRAY = "array"
_UNCHECKABLE_EDGES = frozenset({"anyOf", "oneOf", "allOf", "additionalProperties", "not"})


@dataclass(frozen=True, slots=True)
class StrippedConstraint:
    """One keyword removed from the wire schema, with where it came from.

    Attributes:
        pointer: JSON pointer into the *schema* the keyword was removed from.
        keyword: the JSON Schema keyword.
        value: the value it carried.
        selector: steps from the payload root to the values it constrains. ``("*",)``
            means "each element of the array at this position".
        checkable: ``False`` when the constraint sits under a union or an
            ``additionalProperties`` subschema, where the value alone does not say
            which branch applied.
    """

    pointer: str
    keyword: str
    value: Any
    selector: tuple[str, ...]
    checkable: bool


@dataclass(frozen=True, slots=True)
class BedrockSchema:
    """A wire schema, the model that re-imposes what the wire schema cannot, and the record.

    Attributes:
        name: the ``format``/tool name sent alongside the schema.
        schema: the Bedrock-legal JSON Schema, ready to place in
            ``output_config.format.schema``.
        model: the Pydantic model the schema was derived from and is validated against.
        stripped: every constraint removed, in schema order.
        schema_version: ``sha256`` of the canonical form of :attr:`schema`. This is the
            ``schema_version`` component of ``agent_identity`` (§8.2).
    """

    name: str
    schema: Mapping[str, Any]
    model: type[BaseModel]
    stripped: tuple[StrippedConstraint, ...]
    schema_version: str = field(compare=False)

    def validate_payload(self, payload: Mapping[str, Any], *, profile_id: str) -> BaseModel:
        """Parse and validate a model payload, raising :class:`SchemaViolation` on failure.

        The Pydantic model is the primary re-imposition of every stripped constraint;
        :meth:`check_stripped` then runs independently and its complaints are folded
        into the same refusal so a caller sees one message.
        """
        payload_sha256 = sha256_hex(stable_json_bytes(payload))
        try:
            parsed = self.model.model_validate(dict(payload))
        except ValidationError as exc:
            detail = _render_validation_error(exc)
            raise SchemaViolation(profile_id, detail, payload_sha256) from exc
        complaints = self.check_stripped(payload)
        if complaints:
            raise SchemaViolation(profile_id, "; ".join(complaints), payload_sha256)
        return parsed

    def check_stripped(self, payload: Mapping[str, Any]) -> tuple[str, ...]:
        """Re-impose the stripped constraints without going through Pydantic.

        Returns:
            One human-readable complaint per violated constraint, empty when the
            payload satisfies every checkable one.
        """
        complaints: list[str] = []
        for constraint in self.stripped:
            if not constraint.checkable:
                continue
            for value in _select(payload, constraint.selector):
                message = _check_one(constraint, value)
                if message is not None:
                    complaints.append(message)
        return tuple(complaints)


def bedrock_schema(
    model: type[BaseModel],
    *,
    name: str | None = None,
    require_all_properties: bool = False,
    strip_pattern: bool = False,
) -> BedrockSchema:
    """Derive a Bedrock-legal JSON Schema from ``model``.

    Args:
        model: the Pydantic model that defines the output shape *and* re-imposes the
            constraints the wire schema cannot carry.
        name: the schema name; defaults to the model's class name.
        require_all_properties: when true, every property of every object is listed in
            ``required``. This is the conservative shape for strict tool-use schemas
            (the AR-1 fallback sets it); it is **off** by default because it changes
            optionality semantics and the native ``output_config`` path does not
            document a need for it.
        strip_pattern: also remove ``pattern`` (see :data:`OPTIONAL_STRIPPED_KEYWORDS`).

    Raises:
        UnsupportedSchema: if the model is recursive.
    """
    raw = model.model_json_schema(ref_template="#/$defs/{model}")
    defs: Mapping[str, Any] = raw.get("$defs", {})
    inlined = _inline(raw, defs, ())
    if isinstance(inlined, dict):
        inlined.pop("$defs", None)
        inlined.pop("$schema", None)
    stripped: list[StrippedConstraint] = []
    keywords = STRIPPED_KEYWORDS | (OPTIONAL_STRIPPED_KEYWORDS if strip_pattern else frozenset())
    cleaned = _strip(
        inlined,
        pointer="#",
        selector=(),
        checkable=True,
        keywords=keywords,
        require_all_properties=require_all_properties,
        out=stripped,
    )
    if not isinstance(cleaned, dict):
        raise UnsupportedSchema(f"{model.__name__} does not produce an object schema")
    schema_version = sha256_hex(canonical_json_bytes(cleaned))
    return BedrockSchema(
        name=name or model.__name__,
        schema=cleaned,
        model=model,
        stripped=tuple(stripped),
        schema_version=schema_version,
    )


# ── inlining ────────────────────────────────────────────────────────────────────


def _inline(node: Any, defs: Mapping[str, Any], stack: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_inline(item, defs, stack) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str):
        target = _def_name(ref)
        if target in stack:
            raise UnsupportedSchema(
                f"recursive schema: {' -> '.join((*stack, target))}. A $ref cycle cannot "
                f"be inlined, and structured outputs do not carry recursion."
            )
        if target not in defs:
            raise UnsupportedSchema(f"unresolvable $ref {ref!r}")
        resolved = _inline(defs[target], defs, (*stack, target))
        merged = dict(resolved) if isinstance(resolved, dict) else {"__value__": resolved}
        for key, value in node.items():
            if key != "$ref":
                merged[key] = _inline(value, defs, stack)
        return merged
    return {key: _inline(value, defs, stack) for key, value in node.items() if key != "$defs"}


def _def_name(ref: str) -> str:
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        raise UnsupportedSchema(f"unsupported $ref form {ref!r}; only #/$defs/<name> is inlined")
    return ref[len(prefix) :]


# ── stripping ───────────────────────────────────────────────────────────────────


def _strip(
    node: Any,
    *,
    pointer: str,
    selector: tuple[str, ...],
    checkable: bool,
    keywords: frozenset[str],
    require_all_properties: bool,
    out: list[StrippedConstraint],
) -> Any:
    if isinstance(node, list):
        return [
            _strip(
                item,
                pointer=f"{pointer}/{index}",
                selector=selector,
                checkable=False,
                keywords=keywords,
                require_all_properties=require_all_properties,
                out=out,
            )
            for index, item in enumerate(node)
        ]
    if not isinstance(node, dict):
        return node

    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in keywords:
            out.append(
                StrippedConstraint(
                    pointer=f"{pointer}/{key}",
                    keyword=key,
                    value=value,
                    selector=selector,
                    checkable=checkable,
                )
            )
            continue
        if key == "properties" and isinstance(value, dict):
            result[key] = {
                prop: _strip(
                    sub,
                    pointer=f"{pointer}/properties/{prop}",
                    selector=(*selector, prop),
                    checkable=checkable,
                    keywords=keywords,
                    require_all_properties=require_all_properties,
                    out=out,
                )
                for prop, sub in value.items()
            }
            continue
        if key == "items":
            result[key] = _strip(
                value,
                pointer=f"{pointer}/items",
                selector=(*selector, "*"),
                checkable=checkable,
                keywords=keywords,
                require_all_properties=require_all_properties,
                out=out,
            )
            continue
        result[key] = _strip(
            value,
            pointer=f"{pointer}/{key}",
            selector=selector,
            checkable=checkable and key not in _UNCHECKABLE_EDGES,
            keywords=keywords,
            require_all_properties=require_all_properties,
            out=out,
        )

    if result.get("type") == _OBJECT or "properties" in result:
        # §8.4's structured-output contract, and layer 3 of the injection posture.
        result["additionalProperties"] = False
        if require_all_properties:
            result["required"] = sorted(result.get("properties", {}))
    return result


# ── independent re-imposition ───────────────────────────────────────────────────


def _select(payload: Any, selector: Sequence[str]) -> list[Any]:
    """Resolve a selector to every value it addresses. Absent paths yield nothing."""
    current: list[Any] = [payload]
    for step in selector:
        following: list[Any] = []
        for value in current:
            if step == "*":
                if isinstance(value, (list, tuple)):
                    following.extend(value)
            elif isinstance(value, dict) and step in value:
                following.append(value[step])
        current = following
        if not current:
            return []
    return current


def _check_one(constraint: StrippedConstraint, value: Any) -> str | None:  # noqa: PLR0911
    # One return per keyword. A dispatch table here would be shorter and would make the
    # set of re-imposed constraints harder to read against STRIPPED_KEYWORDS, which is
    # the comparison a reviewer actually needs to make.
    """Return a complaint, or ``None`` when ``value`` satisfies ``constraint``."""
    keyword = constraint.keyword
    bound = constraint.value
    where = ".".join(constraint.selector) or "<root>"

    if keyword == "minLength" and isinstance(value, str) and len(value) < bound:
        return f"{where}: length {len(value)} < minLength {bound}"
    if keyword == "maxLength" and isinstance(value, str) and len(value) > bound:
        return f"{where}: length {len(value)} > maxLength {bound}"
    if keyword == "pattern" and isinstance(value, str):
        import re

        if re.search(bound, value) is None:
            return f"{where}: {value!r} does not match pattern {bound!r}"
        return None
    if keyword in {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}:
        return _check_numeric(keyword, bound, value, where)
    if keyword == "minItems" and isinstance(value, (list, tuple)) and len(value) < bound:
        return f"{where}: {len(value)} items < minItems {bound}"
    if keyword == "maxItems" and isinstance(value, (list, tuple)) and len(value) > bound:
        return f"{where}: {len(value)} items > maxItems {bound}"
    if keyword == "uniqueItems" and bound is True and isinstance(value, (list, tuple)):
        rendered = [stable_json_bytes(item) for item in value]
        if len(set(rendered)) != len(rendered):
            return f"{where}: duplicate items where uniqueItems is required"
    return None


def _check_numeric(keyword: str, bound: Any, value: Any, where: str) -> str | None:  # noqa: PLR0911
    # One return per numeric keyword, for the same reason as _check_one: the reader
    # needs to line these up against STRIPPED_KEYWORDS by eye.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if keyword == "minimum" and value < bound:
        return f"{where}: {value} < minimum {bound}"
    if keyword == "maximum" and value > bound:
        return f"{where}: {value} > maximum {bound}"
    if keyword == "exclusiveMinimum" and value <= bound:
        return f"{where}: {value} <= exclusiveMinimum {bound}"
    if keyword == "exclusiveMaximum" and value >= bound:
        return f"{where}: {value} >= exclusiveMaximum {bound}"
    if keyword == "multipleOf" and bound and value % bound != 0:
        return f"{where}: {value} is not a multiple of {bound}"
    return None


def _render_validation_error(exc: ValidationError) -> str:
    """Flatten a Pydantic error into the one line that is appended to the retry turn.

    Deliberately terse. §8.4 permits **one** retry carrying the validator error, and a
    thousand-line error is a retry that spends its budget on the error rather than the
    fix.
    """
    parts: list[str] = []
    for error in exc.errors(include_url=False, include_context=False)[:8]:
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)
