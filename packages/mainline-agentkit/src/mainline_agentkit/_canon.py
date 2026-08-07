# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""A deliberately small RFC 8785 (JCS) serialiser for cassette and schema digests.

**Why this is not** ``trappoint_jcs``. The custody ledger's canonicaliser is
``packages/trappoint-jcs``, and it is the authority for every hash that a signature
covers. This module is not that. It covers two digests that never leave the build:
the cassette key and the schema version. Taking a workspace dependency for them would
put a second package on the import path of the one component in the Cognition plane
whose import graph a residency reviewer has to read in full.

The two implementations must agree, and that is asserted rather than assumed:
``tests/test_cassette.py::test_agrees_with_trappoint_jcs`` cross-checks this module
against ``trappoint_jcs.canonicalise`` over a shared vector set whenever that package
is importable — which it always is inside the uv workspace, and which skips with a
reason in a bare checkout of this distribution alone.

Scope, stated so the limits are visible:

* objects, arrays, strings, integers, booleans and null — the closed set of types a
  model *input* can contain in this system;
* member names sorted by UTF-16 code-unit order, per RFC 8785 §3.2.3;
* **floats are refused.** A cassette key that depends on IEEE-754 formatting is a
  cassette key that changes with a Python release. Model inputs in MAINLINE carry
  quantities as integers plus a unit, or as strings; there is no third case.
"""

from __future__ import annotations

from typing import Any

__all__ = ["CanonError", "canonical_json_bytes", "sha256_hex", "stable_json_bytes"]

import hashlib
import json

#: RFC 8785 §3.2.2.2 short escapes, plus the two mandatory ones.
_SHORT_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}

_MAX_DEPTH = 64
_CONTROL_CEILING = 0x20


class CanonError(ValueError):
    """A value cannot be canonicalised under this profile."""


def _escape(value: str) -> str:
    out: list[str] = ['"']
    for ch in value:
        code = ord(ch)
        short = _SHORT_ESCAPES.get(code)
        if short is not None:
            out.append(short)
        elif code < _CONTROL_CEILING:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _sort_key(name: str) -> bytes:
    """Member-name ordering is over UTF-16 code units, not code points (RFC 8785)."""
    return name.encode("utf-16-be", errors="surrogatepass")


def _serialise(value: Any, out: list[str], depth: int) -> None:  # noqa: PLR0911
    # One return per JSON type. Collapsing them into a dispatch table would hide the
    # closed set of types this profile accepts, which is the point of the module.
    if depth > _MAX_DEPTH:
        raise CanonError(f"nesting deeper than {_MAX_DEPTH} refused")
    if value is None:
        out.append("null")
        return
    if value is True:
        out.append("true")
        return
    if value is False:
        out.append("false")
        return
    if isinstance(value, str):
        out.append(_escape(value))
        return
    if isinstance(value, int):
        out.append(str(value))
        return
    if isinstance(value, float):
        raise CanonError(
            "float refused: a digest whose bytes depend on IEEE-754 formatting is not a "
            "stable key. Carry quantities as an integer plus a unit, or as a string."
        )
    if isinstance(value, dict):
        _serialise_object(value, out, depth)
        return
    if isinstance(value, (list, tuple)):
        _serialise_array(value, out, depth)
        return
    raise CanonError(f"type {type(value).__name__!r} has no canonical JSON form here")


def _serialise_object(value: dict[Any, Any], out: list[str], depth: int) -> None:
    names: list[str] = []
    for name in value:
        if not isinstance(name, str):
            raise CanonError(f"non-string member name {name!r}")
        names.append(name)
    names.sort(key=_sort_key)
    out.append("{")
    for index, name in enumerate(names):
        if index:
            out.append(",")
        out.append(_escape(name))
        out.append(":")
        _serialise(value[name], out, depth + 1)
    out.append("}")


def _serialise_array(value: list[Any] | tuple[Any, ...], out: list[str], depth: int) -> None:
    out.append("[")
    for index, item in enumerate(value):
        if index:
            out.append(",")
        _serialise(item, out, depth + 1)
    out.append("]")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the RFC 8785 canonical UTF-8 form of ``value``.

    Raises:
        CanonError: on a float, a non-string member name, an unsupported type, or
            nesting beyond the depth ceiling.
    """
    out: list[str] = []
    _serialise(value, out, 0)
    return "".join(out).encode("utf-8")


def stable_json_bytes(value: Any) -> bytes:
    """Serialise a value this system did **not** author: model output.

    :func:`canonical_json_bytes` refuses floats, and that refusal is correct for inputs
    we construct — a cassette key that moves with a Python release is not a key. It is
    the *wrong* rule for a payload the model produced: a model can return ``19.5``, and
    a digest routine that raised on it would turn a schema violation into a crash three
    frames from the retry that was supposed to handle it.

    So received payloads are hashed with sorted-key compact JSON instead. Deterministic
    for a given object graph, tolerant of anything ``json`` can serialise, and never
    used for anything a signature covers.
    """
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


def sha256_hex(*parts: bytes) -> str:
    """Hash a domain-separated concatenation of byte strings.

    The ``0x1f`` unit separator between parts is not decoration: without it
    ``("ab", "c")`` and ``("a", "bc")`` produce the same digest, and a cassette key
    built from ``profile_id`` and ``prompt_version`` is exactly that shape.
    """
    digest = hashlib.sha256()
    for index, part in enumerate(parts):
        if index:
            digest.update(b"\x1f")
        digest.update(part)
    return digest.hexdigest()
