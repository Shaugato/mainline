# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``canon_v1`` — RFC 8785 JSON Canonicalization Scheme, plus the evidentiary payload profile.

Why this file exists at all
---------------------------
A hash of bytes nobody can reproduce is not evidence. CockroachDB cannot produce the
bytes: ``sha256()`` returns hex *text* rather than ``BYTES`` (cockroach#73896) and
``JSONB`` normalises and reorders keys, so ``sha256(payload::STRING)`` is a number only
we can compute. Canonicalisation is therefore **client-side, versioned, and frozen** —
this module is the thing an opposing expert re-implements in Rust, and the thing whose
SHA-256 is written into every checkpoint as ``canon_src_sha256``.

Two entry points, deliberately different
----------------------------------------
``canonicalise(obj)``
    Strict RFC 8785. Every number is serialised exactly as ECMAScript
    ``Number.prototype.toString`` would, including the ES6 exponent thresholds. This
    function exists so that conformance against the published cyberphone test vectors is
    a fact rather than a claim.

``canonicalise_payload(obj)``
    The **evidentiary profile** (custody ruling CU-5). It walks the structure first and
    refuses any ``float`` with :exc:`NonEvidentiaryNumber`, then delegates to
    ``canonicalise``. No evidentiary quantity is a binary float: a setpoint is a decimal
    string, a severity is an integer, a timestamp is RFC 3339 text. The ES6 number path
    (exponential below 1e-6 and at or above 1e21, versus Python's own thresholds at 1e-4
    and 1e16) is the single largest interoperability risk in a scheme whose entire value
    is that a stranger reproduces our bytes. We keep the conformance and remove evidence's
    dependence on the riskiest path.

Frozen by construction
----------------------
This module imports **only** the standard library and has **no package-relative
imports**, because a byte-identical copy of it is vendored into ``trappoint-verify`` —
whose dependency floor is ``cryptography`` and nothing else. ``scripts/custody/
check_vendored_canon.py`` asserts the two copies are byte-equal and that every
canonicaliser ever shipped still matches its pin in ``spec/custody/canon-registry.yaml``.
Removing or modifying a shipped ``canon_v*`` is a breaking change to *evidence*, not to
code, and CI refuses it.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Final

__all__ = [
    "CANON_VERSION",
    "MAX_DEPTH",
    "MAX_SAFE_INTEGER",
    "CanonicalisationError",
    "DepthExceeded",
    "DuplicateKey",
    "InvalidString",
    "NonEvidentiaryNumber",
    "NonFiniteNumber",
    "NonInteroperableNumber",
    "NonStringKey",
    "UnsupportedType",
    "canon_src_sha256",
    "canonicalise",
    "canonicalise_json",
    "canonicalise_payload",
    "es6_number",
]

#: The value written to ``ledger_intake.payload_ver``. The verifier dispatches on it.
CANON_VERSION: Final[int] = 1

#: Structural depth limit. Evidentiary payloads are shallow; unbounded recursion inside a
#: verifier a stranger runs on a hostile bundle is a denial-of-service surface, not a
#: feature. 64 is far above anything the MAINLINE payload profile emits.
MAX_DEPTH: Final[int] = 64

#: ``2**53 - 1``. Above this an IEEE-754 double no longer represents every integer, so a
#: conforming ECMAScript implementation and an exact-integer implementation disagree.
MAX_SAFE_INTEGER: Final[int] = 9007199254740991


class CanonicalisationError(ValueError):
    """Base class. Every refusal in this module is one of these."""


class UnsupportedType(CanonicalisationError):
    """A value that is not a JSON value reached the serialiser."""


class NonStringKey(CanonicalisationError):
    """An object member name was not a ``str``."""


class DuplicateKey(CanonicalisationError):
    """The source JSON text carried the same member name twice (RFC 8785 §3.1)."""


class InvalidString(CanonicalisationError):
    """A ``str`` contained an unpaired surrogate and has no UTF-8 encoding."""


class NonFiniteNumber(CanonicalisationError):
    """``NaN`` or an infinity reached the serialiser. JSON has no such literals."""


class NonInteroperableNumber(CanonicalisationError):
    """An integer outside ``±(2**53 - 1)``; ES6 and exact-integer output disagree."""


class NonEvidentiaryNumber(CanonicalisationError):
    """CU-5: an IEEE-754 ``float`` appeared in a payload destined for the ledger."""


class DepthExceeded(CanonicalisationError):
    """The structure nested deeper than :data:`MAX_DEPTH`."""


# --------------------------------------------------------------------------------------
# RFC 8785 §3.2.2.3 — ECMAScript number serialisation
# --------------------------------------------------------------------------------------

def es6_number(value: float) -> str:
    """Serialise *value* exactly as ECMAScript ``Number.prototype.toString`` does.

    Python's ``repr`` already yields the **shortest round-tripping** decimal digits, which
    is the hard half. The remaining half is layout, and it is where every naive port of
    this function is wrong:

    ==================  ==============================  ===========================
    decimal exponent    ECMAScript (this function)      Python ``repr``
    ==================  ==============================  ===========================
    ``n < -6``          exponential  ``1e-7``           exponential from ``n < -4``
    ``-6 <= n < 21``    positional   ``0.000001``       positional
    ``n >= 21``         exponential  ``1e+21``          exponential from ``n >= 16``
    ==================  ==============================  ===========================

    So ``1e-5`` is ``"0.00001"`` here and ``'1e-05'`` in Python, and ``1e17`` is
    ``"100000000000000000"`` here and ``'1e+17'`` in Python. That mismatch is the classic
    JCS interoperability bug. It is written out below as an explicit conversion rather
    than left to string formatting.

    ``-0.0`` serialises as ``"0"``; ``NaN`` and the infinities raise
    :exc:`NonFiniteNumber`.
    """
    if math.isnan(value):
        raise NonFiniteNumber("NaN has no JSON serialisation")
    if math.isinf(value):
        raise NonFiniteNumber(f"{value!r} has no JSON serialisation")
    if value == 0.0:
        return "0"  # collapses -0.0, per RFC 8785 §3.2.2.3.

    sign = "-" if value < 0.0 else ""
    text = repr(abs(value))

    # Decompose the shortest round-trip repr into (digits, n) such that
    #     |value| == 0.<digits> * 10**n
    # with `digits` carrying no leading and no trailing zero.
    mantissa, _, exponent_text = text.partition("e")
    exponent = int(exponent_text) if exponent_text else 0
    integer_part, _, fraction_part = mantissa.partition(".")
    digits = integer_part + fraction_part
    n = len(integer_part) + exponent

    without_leading = digits.lstrip("0")
    n -= len(digits) - len(without_leading)
    digits = without_leading.rstrip("0")
    k = len(digits)

    if k <= n <= 21:
        # 100 -> "100": all significant digits, then the trailing zeros.
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        # 1.5 -> "1.5": the point falls inside the digit run.
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        # 0.000001 -> "0.000001": the ECMAScript lower threshold, not Python's.
        return sign + "0." + "0" * (-n) + digits
    # Exponential. ECMAScript writes the exponent with a sign and no zero padding, so
    # 1e-7 is "1e-7" and not "1e-07".
    e = n - 1
    suffix = ("e+" if e >= 0 else "e-") + str(abs(e))
    if k == 1:
        return sign + digits + suffix
    return sign + digits[0] + "." + digits[1:] + suffix


# --------------------------------------------------------------------------------------
# RFC 8785 §3.2.2.2 — string serialisation
# --------------------------------------------------------------------------------------

#: The seven short escapes RFC 8785 §3.2.2.2 permits, keyed by code point. ``\/`` is
#: deliberately absent — a solidus is emitted literally — and ``\v`` is not a JSON escape at
#: all, so U+000B falls through to the ``\u000b`` branch below.
_SHORT_ESCAPES: Final[dict[int, str]] = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def _validate_string(value: str) -> None:
    """Refuse a ``str`` that has no UTF-8 encoding.

    Python permits unpaired surrogates inside ``str``; UTF-8, UTF-16 and JSON do not. This
    runs **before** member names reach the sort, because ``str.encode("utf-16-be")`` would
    otherwise raise a bare ``UnicodeEncodeError`` from inside ``list.sort`` — an
    unmodelled exception escaping a canonicaliser is exactly the shape of defect this
    package exists to not have.
    """
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:  # unpaired surrogate
        raise InvalidString(
            "string contains an unpaired surrogate and has no UTF-8 encoding"
        ) from exc


def _serialise_string(value: str, out: list[str]) -> None:
    _validate_string(value)
    out.append('"')
    for character in value:
        code_point = ord(character)
        escape = _SHORT_ESCAPES.get(code_point)
        if escape is not None:
            out.append(escape)
        elif code_point < 0x20:
            # Lower-case hex, four digits, per RFC 8785 §3.2.2.2.
            out.append(f"\\u{code_point:04x}")
        else:
            # Everything else is literal, including U+007F (DEL, which JSON does not
            # require escaping) and every astral character.
            out.append(character)
    out.append('"')


def _member_sort_key(name: str) -> bytes:
    """RFC 8785 §3.2.3: sort by the **UTF-16 code unit** sequence of the member name.

    This is not Python's ``str`` ordering. ``"\\U0001f602"`` (a smiley) is code point
    U+1F602, which compares *above* U+FB33 in Python, but its UTF-16 encoding begins with
    the surrogate U+D83D, which compares *below* U+FB33. The cyberphone ``weird.json``
    vector exists to catch exactly this, and sorting on the encoded bytes is what passes
    it.
    """
    return name.encode("utf-16-be")


# --------------------------------------------------------------------------------------
# The serialiser
# --------------------------------------------------------------------------------------

def _serialise(value: Any, out: list[str], depth: int) -> None:
    if depth > MAX_DEPTH:
        raise DepthExceeded(f"structure nests deeper than MAX_DEPTH={MAX_DEPTH}")

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
        _serialise_string(value, out)
        return
    if isinstance(value, bool):  # a bool subclass; True/False are handled above.
        out.append("true" if value else "false")
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise NonInteroperableNumber(
                f"integer {value} exceeds ±(2**53-1); an ECMAScript canonicaliser would "
                "round it, so no two implementations would agree on the bytes"
            )
        # Within the safe range float(value) is exact and es6_number(float(value)) is the
        # decimal expansion, so this is both the RFC 8785 answer and the exact one.
        out.append(es6_number(float(value)))
        return
    if isinstance(value, float):
        out.append(es6_number(value))
        return
    if isinstance(value, (list, tuple)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _serialise(item, out, depth + 1)
        out.append("]")
        return
    if isinstance(value, dict):
        names: list[str] = []
        for name in value:
            if not isinstance(name, str):
                raise NonStringKey(f"object member name {name!r} is not a str")
            _validate_string(name)
            names.append(name)
        names.sort(key=_member_sort_key)
        out.append("{")
        for index, name in enumerate(names):
            if index:
                out.append(",")
            _serialise_string(name, out)
            out.append(":")
            _serialise(value[name], out, depth + 1)
        out.append("}")
        return

    raise UnsupportedType(
        f"{type(value).__name__} is not a JSON value; convert it before canonicalising"
    )


def canonicalise(value: Any) -> bytes:
    """Return the RFC 8785 canonical UTF-8 bytes of *value*.

    Accepts ``dict``, ``list``, ``tuple``, ``str``, ``int``, ``float``, ``bool`` and
    ``None``. Anything else raises :exc:`UnsupportedType` — silently coercing a
    ``Decimal`` or a ``datetime`` would produce bytes whose meaning depends on which
    library the reader happens to have.
    """
    out: list[str] = []
    _serialise(value, out, 0)
    return "".join(out).encode("utf-8")


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for name, member in pairs:
        if name in seen:
            raise DuplicateKey(f"object member {name!r} appears more than once")
        seen[name] = member
    return seen


def canonicalise_json(text: str | bytes) -> bytes:
    """Parse JSON *text* and return its RFC 8785 canonical bytes.

    Duplicate member names raise :exc:`DuplicateKey` rather than resolving last-wins:
    RFC 8785 §3.1 requires the input to be free of them, and a canonicaliser that quietly
    picks one has just chosen, on the writer's behalf, which of two records was signed.
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return canonicalise(json.loads(text, object_pairs_hook=_reject_duplicate_members))


# --------------------------------------------------------------------------------------
# CU-5 — the evidentiary payload profile
# --------------------------------------------------------------------------------------

def _assert_evidentiary(value: Any, depth: int) -> None:
    if depth > MAX_DEPTH:
        raise DepthExceeded(f"structure nests deeper than MAX_DEPTH={MAX_DEPTH}")
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, float):
        raise NonEvidentiaryNumber(
            f"IEEE-754 float {value!r} is not an evidentiary quantity (CU-5). Carry the "
            "value as an exact integer in its smallest unit, or as a decimal string."
        )
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise NonInteroperableNumber(
                f"integer {value} exceeds ±(2**53-1) and is not reproducible by a "
                "conforming ECMAScript canonicaliser; carry it as a decimal string"
            )
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_evidentiary(item, depth + 1)
        return
    if isinstance(value, dict):
        for name, member in value.items():
            if not isinstance(name, str):
                raise NonStringKey(f"object member name {name!r} is not a str")
            _assert_evidentiary(member, depth + 1)
        return
    raise UnsupportedType(
        f"{type(value).__name__} is not a JSON value; convert it before canonicalising"
    )


def canonicalise_payload(value: Any) -> bytes:
    """Return the canonical bytes of a **ledger payload**, refusing binary floats.

    This is the function the sequencer, the intake client and every agent call. The whole
    structure is checked before a single byte is produced, so the refusal names the
    offending value rather than arriving half-way through a serialisation.
    """
    _assert_evidentiary(value, 0)
    return canonicalise(value)


# --------------------------------------------------------------------------------------
# The scheme's own code, inside the scheme (verifier check 10)
# --------------------------------------------------------------------------------------

def canon_src_sha256() -> bytes:
    """SHA-256 of this module's own source, over **LF-normalised** bytes.

    Written into every checkpoint as ``canon_src_sha256`` so that a verifier can prove the
    leaves it is checking were produced by the canonicaliser it is running. Normalising
    CRLF to LF before hashing makes the value identical on a Windows checkout with
    ``core.autocrlf=true`` and on a Linux CI runner; without it the pin would be a
    platform fingerprint rather than a code fingerprint. The normalisation is stated
    normatively in ``spec/wire/checkpoint.md`` so a third-party implementer reproduces it.
    """
    source = Path(__file__).resolve().read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(source).digest()
