# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Rendering the CAT diff for the model — and everything it is not allowed to say.

Path B is given the two canonical texts, the blame-origin summary and **the CAT
diff** (research §6.3).  The diff is there so the model is answering a question
about a specific pair of obligations rather than about two paragraphs of English.

The hard constraint on this module is negative, and it is the trap the brief
names: *the oracle must never be given the safe_direction registry or the ability
to name a rule id*.  So this renderer emits **field, before, after** and nothing
else.  It does not say which direction is safer for a parameter — that is
DIRECTRIX, worker W2, and a model told the answer would return the answer.  It
does not name ``R1_DEONTIC`` or any other rule id — a model that can name a rule
id can produce output that looks like a Path-A witness, and the whole point of
two paths is that one of them cannot forge the other.

The diff is also *lossy on purpose*: it reports that a field changed and what it
changed to, never what that means.  Meaning is the lattice's, and the lattice
does not consult this file.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from mainline_domain.contracts import CAT, Quantity

__all__ = ["CAT_FIELD_ORDER", "render_cat_diff", "render_quantity"]

#: The field order the diff is rendered in.  Fixed, because a diff whose line
#: order depends on a dict iteration is a different prompt on every run, and the
#: cassette key is a hash of the prompt.
CAT_FIELD_ORDER: Final[tuple[str, ...]] = (
    "actor",
    "deontic",
    "action",
    "object_class",
    "hazard_energy",
    "parameter",
    "comparator",
    "value",
    "conditions",
    "exceptions",
    "verification",
    "frequency",
    "coverage_quantifier",
)

_ABSENT: Final[str] = "(absent)"
_NO_TUPLE: Final[str] = "(no control tuple could be extracted)"


def render_quantity(value: Quantity | None) -> str:
    """Render a quantity with its unit **and its reference class**.

    The reference is never dropped.  ``50 psig`` and ``50 psia`` are two different
    setpoints and one of them is a weakening (decision D5); a renderer that
    printed both as ``50 psi`` would hand the model a pair of clauses that look
    identical and ask it why they differ.
    """
    if value is None:
        return _ABSENT
    magnitude = _decimal_text(value.value)
    reference = "" if value.reference == "none" else f", {value.reference}"
    return f"{magnitude} {value.unit} ({value.dimension}{reference})"


def _decimal_text(value: Decimal) -> str:
    """Render a Decimal without exponent notation and without trailing noise."""
    if not value.is_finite():
        return str(value)
    normalised = value.normalize()
    sign, digits, exponent = normalised.as_tuple()
    if isinstance(exponent, int) and exponent > 0:
        normalised = normalised.quantize(Decimal(1))
    text = format(normalised, "f")
    _ = (sign, digits)
    return text


def _render_field(name: str, cat: CAT) -> str:
    raw = getattr(cat, name)
    if raw is None:
        return _ABSENT
    if name in ("value", "frequency"):
        return render_quantity(raw)
    if isinstance(raw, tuple):
        return "[" + "; ".join(str(item) for item in raw) + "]" if raw else "[]"
    text = str(raw)
    return text if text else _ABSENT


def render_cat_diff(ancestor: CAT | None, descendant: CAT | None) -> str:
    """Render the field-by-field difference between two control tuples.

    Both sides absent, one side absent, or an identical pair are all rendered
    explicitly rather than as an empty string: a blank section in a prompt reads
    as an omission, and the model would be entitled to infer one.
    """
    if ancestor is None and descendant is None:
        return f"A: {_NO_TUPLE}\nB: {_NO_TUPLE}"
    if ancestor is None:
        return f"A: {_NO_TUPLE}\nB: a control tuple was extracted; no field-level diff is possible."
    if descendant is None:
        return f"B: {_NO_TUPLE}\nA: a control tuple was extracted; no field-level diff is possible."

    lines: list[str] = []
    for name in CAT_FIELD_ORDER:
        before = _render_field(name, ancestor)
        after = _render_field(name, descendant)
        if before != after:
            lines.append(f"{name}: A={before} -> B={after}")
    if not lines:
        return "No field of the control tuple differs between A and B."
    return "\n".join(lines)
