# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""RFC 8785 canonicalisation, restricted to the frozen PER leaf profile.

Why this is not ``trappoint_jcs``
---------------------------------
It is the same bytes, and a test proves it (``tests/integration/recall_run/
test_leaf_canon_agrees_with_jcs.py`` canonicalises randomised leaves with both and asserts
byte equality). But the PER verifier has one requirement that outranks code reuse: **a
stranger holding a receipt must be able to check it with a stock Python interpreter and
nothing installed.** A verifier that needs a package from the defendant's own repository is
a verifier the defendant controls, and the whole point of a silence receipt is that it can
be checked by someone who does not trust us.

So this module imports the standard library only, and it is deliberately *narrower* than
RFC 8785 rather than a second full implementation to keep honest: it accepts a flat object
whose members are ``int`` or ``str`` and refuses everything else. That is exactly the leaf
profile (recall lead D10) and nothing more.

The profile, and the reason it holds no floats
----------------------------------------------
::

    {"event_id": <uuid str>, "ord": <int>, "outcome": <str>,
     "score_q": <int>, "tau_applied": <int>}

``score_q`` and ``tau_applied`` are integers in units of 1e-6 (see :mod:`.leaf`). The custody
domain's evidentiary payload profile (ruling CU-5) refuses binary floats in a hashed preimage
for the general reason that ES6 number formatting is the largest interoperability risk in any
scheme whose value is that a stranger reproduces the bytes. Here there is a second, sharper
reason: ``score_q`` is the **sort key of the whole proof**, and a float whose text rendering
differs by one ulp between two implementations would silently reorder the commitment.

Member ordering is by UTF-16 code unit, per RFC 8785 §3.2.3 — implemented as a comparison of
big-endian UTF-16 bytes, which is that ordering exactly.
"""

from __future__ import annotations

from collections.abc import Mapping

from trappoint_recall.per.errors import NotCanonicalisable

__all__ = ["MAX_SAFE_INTEGER", "canonicalise_leaf", "serialise_member"]

#: ``2**53 - 1``. Above this an IEEE-754 double stops representing every integer, so an
#: ECMAScript implementation and an exact-integer implementation would disagree about the
#: text of the number. Refusing here keeps the two in agreement by construction.
MAX_SAFE_INTEGER = 9007199254740991

#: RFC 8785 §3.2.2.2 — the two-character escapes, plus the ``\u00XX`` fallback below 0x20.
_SHORT_ESCAPES: dict[int, str] = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def _escape_string(value: str) -> str:
    """Serialise ``value`` as a JSON string exactly as RFC 8785 §3.2.2.2 requires."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:  # a lone surrogate has no UTF-8 encoding
        raise NotCanonicalisable(
            f"string {value!r} contains an unpaired surrogate and has no UTF-8 encoding, "
            "so no two implementations could agree on its bytes"
        ) from exc
    out = ['"']
    for char in value:
        code = ord(char)
        short = _SHORT_ESCAPES.get(code)
        if short is not None:
            out.append(short)
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def serialise_member(value: int | str) -> str:
    """Serialise one leaf member value. Integers only, or strings; nothing else."""
    if isinstance(value, bool):
        # bool is an int subclass in Python and would silently serialise as 0/1 here while a
        # JSON implementation writes `true`. Refuse rather than diverge.
        raise NotCanonicalisable(
            "bool is not in the PER leaf profile; a boolean serialises as 0/1 through the "
            "integer path and as true/false through JSON, which is a byte divergence"
        )
    if isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise NotCanonicalisable(
                f"integer {value} is outside +/-(2**53 - 1); an ECMAScript implementation "
                "would not render it the same way"
            )
        return str(value)
    if isinstance(value, str):
        return _escape_string(value)
    raise NotCanonicalisable(
        f"{type(value).__name__} is not in the PER leaf profile "
        "(flat object, int or str members only)"
    )


def _member_sort_key(name: str) -> bytes:
    """UTF-16 code-unit ordering, expressed as a byte comparison (RFC 8785 §3.2.3)."""
    try:
        return name.encode("utf-16-be")
    except UnicodeEncodeError as exc:
        raise NotCanonicalisable(
            f"object member name {name!r} is not encodable as UTF-16"
        ) from exc


def canonicalise_leaf(member: Mapping[str, int | str]) -> bytes:
    """Return the RFC 8785 bytes of a flat object of integer and string members.

    Args:
        member: the leaf object. Keys must be ``str``; values must be ``int`` or ``str``.

    Returns:
        UTF-8 encoded canonical JSON.

    Raises:
        NotCanonicalisable: on any key or value outside the frozen leaf profile.
    """
    for name in member:
        if not isinstance(name, str):
            raise NotCanonicalisable(f"object member name {name!r} is not a str")
    names = sorted(member, key=_member_sort_key)
    parts = [f"{_escape_string(name)}:{serialise_member(member[name])}" for name in names]
    return ("{" + ",".join(parts) + "}").encode("utf-8")
