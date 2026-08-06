# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""RFC 8785 (JCS) canonical JSON and the request digest used to key cassettes.

Scope note — this is *test/replay infrastructure*, not the custody canonicaliser.  The
authoritative JCS implementation for anything that reaches the ledger is
``packages/trappoint-jcs`` (custody domain).  This module exists so that the providers
package has no dependency on a package outside its own licence boundary and can key a
cassette with nothing but the standard library.  The two must agree; a conformance test
comparing them belongs to whichever of the two lands second.

Why JCS and not ``json.dumps(sort_keys=True)``: ``json.dumps`` sorts by Python code point
(not UTF-16 code units), emits ``NaN``/``Infinity`` happily, and formats floats with
``repr`` rather than the ECMAScript ``Number::toString`` algorithm.  Each of those is a
silent digest divergence, and a digest that diverges silently is a cassette that misses
in CI for reasons nobody can reproduce.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any, Final

from .errors import CanonicalisationError

__all__ = ["canonical_json", "es6_number", "request_digest", "sha256_hex"]

_ESCAPES: Final[dict[int, str]] = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}

#: 2**53 - 1.  Beyond this an integer is not exactly representable as an IEEE-754 double,
#: so JCS (which is defined over doubles) can no longer round-trip it.
_MAX_SAFE_INTEGER: Final[int] = 9007199254740991


def es6_number(value: float | int) -> str:
    """Format a number exactly as ECMAScript ``Number::toString`` would.

    Implements ECMA-262 7.1.12.1 steps 5-10 over the shortest round-tripping decimal
    representation, which is what ``repr()`` produces in CPython.
    """
    if isinstance(value, bool):  # bool is an int subclass; JCS treats it as a literal
        raise CanonicalisationError("bool must be emitted as a JSON literal, not a number")
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise CanonicalisationError(
                "integer exceeds IEEE-754 exact range; JCS cannot canonicalise it",
                value=value,
            )
        return str(value)
    if value != value or value in (float("inf"), float("-inf")):  # noqa: PLR0124 - NaN test
        raise CanonicalisationError("NaN and Infinity have no JSON serialisation")
    if value == 0.0:
        return "0"  # JCS: -0 canonicalises to "0"

    negative = value < 0.0
    dec = Decimal(repr(abs(value)))
    sign, digits, exponent = dec.as_tuple()
    assert sign == 0
    assert isinstance(exponent, int)

    digit_list = list(digits)
    while len(digit_list) > 1 and digit_list[-1] == 0:
        digit_list.pop()
        exponent += 1
    s = "".join(str(d) for d in digit_list)
    k = len(s)
    n = exponent + k  # value == 0.s * 10**n

    if k <= n <= 21:
        out = s + "0" * (n - k)
    elif 0 < n <= 21:
        out = s[:n] + "." + s[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + s
    else:
        e = n - 1
        mantissa = s if k == 1 else s[0] + "." + s[1:]
        out = f"{mantissa}e{'+' if e >= 0 else '-'}{abs(e)}"
    return "-" + out if negative else out


def _emit_string(text: str, out: list[str]) -> None:
    out.append('"')
    for ch in text:
        code = ord(ch)
        escape = _ESCAPES.get(code)
        if escape is not None:
            out.append(escape)
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')


def _sort_key(key: str) -> tuple[int, ...]:
    """JCS sorts member names by UTF-16 code unit, not by Unicode code point."""
    raw = key.encode("utf-16-be")
    return tuple(int.from_bytes(raw[i : i + 2], "big") for i in range(0, len(raw), 2))


def _emit(value: Any, out: list[str], depth: int) -> None:
    if depth > 64:
        raise CanonicalisationError("canonicalisation depth limit exceeded")
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        _emit_string(value, out)
    elif isinstance(value, (int, float)):
        out.append(es6_number(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _emit(item, out, depth + 1)
        out.append("]")
    elif isinstance(value, dict):
        keys = list(value.keys())
        for key in keys:
            if not isinstance(key, str):
                raise CanonicalisationError(
                    "JCS object member names must be strings", key_type=type(key).__name__
                )
        out.append("{")
        for i, key in enumerate(sorted(keys, key=_sort_key)):
            if i:
                out.append(",")
            _emit_string(key, out)
            out.append(":")
            _emit(value[key], out, depth + 1)
        out.append("}")
    else:
        raise CanonicalisationError(
            "value has no JCS serialisation", python_type=type(value).__name__
        )


def canonical_json(value: Any) -> bytes:
    """Serialise ``value`` to RFC 8785 canonical JSON as UTF-8 bytes."""
    out: list[str] = []
    _emit(value, out, 0)
    return "".join(out).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_digest(request: Any) -> str:
    """``sha256(JCS(request))`` in lowercase hex — the cassette key."""
    return sha256_hex(canonical_json(request))
