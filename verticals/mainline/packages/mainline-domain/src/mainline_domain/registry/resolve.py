# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The fail-closed bridge from a registry answer to a ``control_delta``.

This is the module decision D6 lives in: **unknown parameter ⇒ abstain ⇒
weaken.**  Not "neutral", not "restate", not "skip the rule".

WHY AN UNKNOWN PARAMETER IS NOT NEUTRAL
---------------------------------------
The tempting reading is that if the registry has nothing to say about a
parameter then the system has learned nothing about the edit, so the edit should
be treated as it would have been without rule R2 at all.  That reading is wrong
in this product for a structural reason: **the registry's coverage is under the
author's influence.**  A parameter that is absent from DIRECTRIX is a parameter
whose setpoint can be moved without R2 firing, so "absent ⇒ neutral" makes
*deleting a registry entry* — or simply never adding one — a way to move a
setpoint invisibly.  Under D6 it is the opposite: the way to stop the gate
blocking on a parameter is to **ratify** it, which is a signed commit that binds
the direction publicly before the edit anyone cares about is proposed.

That is the adoption ratchet, and it converts DIRECTRIX's honest weakness
(coverage is hard engineering, a few hundred parameters per site) into nuisance
blocks instead of silent passes — risk R-A4, accepted deliberately.

WHY THE RULING IS A DATACLASS AND NOT AN ENUM
---------------------------------------------
Because worker W4 has to write a :class:`~mainline_domain.contracts.DeltaWitness`
for every ``weaken``, and decision D8 makes a witness-free lattice ``weaken``
physically un-insertable (``fn_delta_witness_guard``, P0001).  A bare
``ControlDelta.weaken`` returned from here would be a verdict with no
explanation, and the database would refuse to store it — correctly.  So the
ruling carries the arithmetic that produced it: the direction, the sign of the
comparison, the resolution with its abstention reason, and the two quantities as
they were compared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..contracts import ControlDelta, Quantity
from ..quantity.algebra import compare
from ..quantity.errors import QuantityError
from .model import AbstentionReason, Resolution, SafeDirection, SafeDirectionRegistry

__all__ = [
    "SetpointRuling",
    "delta_for_abstention",
    "setpoint_delta",
    "tolerance_delta",
]

#: The delta an abstention resolves to.  Named rather than inlined so that a
#: reader looking for "what happens when we do not know" finds one answer in one
#: place, and so that a change to it is a change to a constant somebody has to
#: justify rather than a scattered edit.
ABSTENTION_DELTA: Final[ControlDelta] = ControlDelta.WEAKEN


@dataclass(frozen=True, slots=True)
class SetpointRuling:
    """One R2 decision, with everything needed to write its witness.

    ``comparison`` is ``-1``/``0``/``+1`` for *descendant below / equal to /
    above ancestor*, or ``None`` when no comparison was possible.  ``delta`` is
    never ``None`` and is never ``introduce``: introduction and removal are
    decided by the presence of the CAT, not by the direction of a move, and that
    is W4's call rather than this module's.
    """

    delta: ControlDelta
    direction: SafeDirection
    comparison: int | None
    resolution: Resolution
    ancestor: Quantity | None
    descendant: Quantity | None
    reason: str

    @property
    def abstained(self) -> bool:
        """True when no comparison was made, whatever the reason."""
        return self.resolution.abstained or self.comparison is None


def delta_for_abstention(resolution: Resolution) -> ControlDelta:
    """Return ``weaken`` — the whole of decision D6, as a named function.

    :raises ValueError: if handed a resolution that did not abstain — a caller
        that reaches for the abstention path with an answer in hand has a bug,
        and silently returning ``weaken`` would hide it behind a verdict that
        looks conservative.
    """
    if not resolution.abstained:
        raise ValueError(
            f"{resolution.parameter!r} resolved to {resolution.direction.value}; "
            "there is nothing to abstain to"
        )
    return ABSTENTION_DELTA


def _abstain_ruling(
    resolution: Resolution,
    ancestor: Quantity | None,
    descendant: Quantity | None,
    reason: str,
) -> SetpointRuling:
    return SetpointRuling(
        delta=ABSTENTION_DELTA,
        direction=SafeDirection.ABSTAIN,
        comparison=None,
        resolution=resolution,
        ancestor=ancestor,
        descendant=descendant,
        reason=reason,
    )


def _forced_abstention(parameter: str, reason: AbstentionReason, detail: str) -> Resolution:
    return Resolution(
        parameter=parameter,
        direction=SafeDirection.ABSTAIN,
        reason=reason,
        entry=None,
        detail=detail,
    )


def setpoint_delta(
    registry: SafeDirectionRegistry,
    parameter: str,
    *,
    ancestor: Quantity | None,
    descendant: Quantity | None,
) -> SetpointRuling:
    """Rule R2: did this setpoint move against the safe direction?

    Five ways to get ``weaken`` without a comparison ever happening, and each of
    them is a real thing that occurs in a corpus:

    1. the parameter is not in the registry, or is proposed, withdrawn,
       duplicated, retired or ambiguous — :func:`delta_for_abstention`;
    2. one of the two quantities is missing, i.e. the extractor could not read a
       value on one side.  A setpoint that became unreadable is not a setpoint
       that stayed the same;
    3. the two quantities are not comparable — different dimensionality, or a
       gauge reading against an unstated-frame one (decision D5).  This is the
       case the whole quantity package exists to produce, and it lands here;
    4. the registry entry's declared dimension disagrees with what the clause
       measures — the parameter's meaning moved under its own name;
    5. the parameter is governed by ``TIGHTER_TOLERANCE_IS_SAFER``, for which a
       move in the value is not the control.  Use :func:`tolerance_delta`.
    """
    dimensionality = None
    if descendant is not None:
        dimensionality = descendant.dimension
    elif ancestor is not None:
        dimensionality = ancestor.dimension

    resolution = registry.resolve(parameter, dimensionality=dimensionality)

    if resolution.abstained:
        return _abstain_ruling(
            resolution,
            ancestor,
            descendant,
            f"registry abstained ({resolution.reason.value if resolution.reason else '?'}): "
            f"{resolution.detail}",
        )

    if ancestor is None or descendant is None:
        missing = "ancestor" if ancestor is None else "descendant"
        return _abstain_ruling(
            _forced_abstention(
                parameter,
                AbstentionReason.NOT_IN_REGISTRY,
                f"no {missing} value to compare",
            ),
            ancestor,
            descendant,
            f"the {missing} clause carries no readable value for {parameter!r}; a "
            "setpoint that became unreadable is not a setpoint that stayed put",
        )

    if resolution.direction is SafeDirection.TIGHTER_TOLERANCE_IS_SAFER:
        return _abstain_ruling(
            _forced_abstention(
                parameter,
                AbstentionReason.DIMENSION_MISMATCH,
                f"{parameter!r} is governed by tolerance width, not by the value",
            ),
            ancestor,
            descendant,
            f"{parameter!r} is ratified TIGHTER_TOLERANCE_IS_SAFER: the control is the "
            "band, not the target. Call tolerance_delta with the two bands",
        )

    try:
        comparison = compare(descendant, ancestor)
    except QuantityError as exc:
        return _abstain_ruling(
            _forced_abstention(
                parameter,
                AbstentionReason.DIMENSION_MISMATCH,
                str(exc),
            ),
            ancestor,
            descendant,
            f"the two values are not comparable: {exc}",
        )

    delta = _delta_from_sign(resolution.direction, comparison)
    return SetpointRuling(
        delta=delta,
        direction=resolution.direction,
        comparison=comparison,
        resolution=resolution,
        ancestor=ancestor,
        descendant=descendant,
        reason=_explain(parameter, resolution.direction, comparison, delta),
    )


def tolerance_delta(
    registry: SafeDirectionRegistry,
    parameter: str,
    *,
    ancestor_band: Quantity | None,
    descendant_band: Quantity | None,
) -> SetpointRuling:
    """Rule R2 for a ``TIGHTER_TOLERANCE_IS_SAFER`` parameter.

    The bands are half-widths (``± 2 kPa`` is ``Quantity(2, 'kilopascal')``).  A
    band that **grew** is a weakening; a band that shrank is a strengthening; a
    band that vanished is a weakening, because a specification with no tolerance
    is a specification with an infinite one.
    """
    dimensionality = None
    if descendant_band is not None:
        dimensionality = descendant_band.dimension
    elif ancestor_band is not None:
        dimensionality = ancestor_band.dimension

    resolution = registry.resolve(parameter, dimensionality=dimensionality)

    if resolution.abstained:
        return _abstain_ruling(
            resolution,
            ancestor_band,
            descendant_band,
            f"registry abstained ({resolution.reason.value if resolution.reason else '?'}): "
            f"{resolution.detail}",
        )

    if resolution.direction is not SafeDirection.TIGHTER_TOLERANCE_IS_SAFER:
        return _abstain_ruling(
            _forced_abstention(
                parameter,
                AbstentionReason.DIMENSION_MISMATCH,
                f"{parameter!r} is ratified {resolution.direction.value}, not a "
                "tolerance-governed parameter",
            ),
            ancestor_band,
            descendant_band,
            f"{parameter!r} is not governed by its tolerance; call setpoint_delta",
        )

    if ancestor_band is not None and descendant_band is None:
        return SetpointRuling(
            delta=ControlDelta.WEAKEN,
            direction=resolution.direction,
            comparison=1,
            resolution=resolution,
            ancestor=ancestor_band,
            descendant=None,
            reason=(
                f"the tolerance band on {parameter!r} was removed; a specification "
                "with no stated band has an unbounded one"
            ),
        )
    if ancestor_band is None or descendant_band is None:
        return _abstain_ruling(
            _forced_abstention(
                parameter,
                AbstentionReason.NOT_IN_REGISTRY,
                "one side carries no readable tolerance band",
            ),
            ancestor_band,
            descendant_band,
            f"no readable tolerance band on one side of the edit for {parameter!r}",
        )

    try:
        comparison = compare(descendant_band, ancestor_band)
    except QuantityError as exc:
        return _abstain_ruling(
            _forced_abstention(parameter, AbstentionReason.DIMENSION_MISMATCH, str(exc)),
            ancestor_band,
            descendant_band,
            f"the two tolerance bands are not comparable: {exc}",
        )

    if comparison > 0:
        delta = ControlDelta.WEAKEN
    elif comparison < 0:
        delta = ControlDelta.STRENGTHEN
    else:
        delta = ControlDelta.RESTATE
    return SetpointRuling(
        delta=delta,
        direction=resolution.direction,
        comparison=comparison,
        resolution=resolution,
        ancestor=ancestor_band,
        descendant=descendant_band,
        reason=_explain(parameter, resolution.direction, comparison, delta),
    )


def _delta_from_sign(direction: SafeDirection, comparison: int) -> ControlDelta:
    """The whole of rule R2, in six lines, with no room for a fourth outcome.

    ``comparison`` is the sign of *descendant minus ancestor*.  Multiply it by the
    direction and read off the delta.  ``restate`` for an unmoved value is
    correct and is not a no-op: a clause whose text changed but whose setpoint
    did not is a restatement, and the lattice's other eight rules still get to
    disagree.
    """
    if comparison == 0:
        return ControlDelta.RESTATE
    if direction is SafeDirection.LOWER_IS_SAFER:
        return ControlDelta.WEAKEN if comparison > 0 else ControlDelta.STRENGTHEN
    if direction is SafeDirection.HIGHER_IS_SAFER:
        return ControlDelta.WEAKEN if comparison < 0 else ControlDelta.STRENGTHEN
    raise ValueError(f"{direction.value} is not a value-governed direction")


_MOVED: Final[dict[int, str]] = {-1: "decreased", 0: "did not move", 1: "increased"}


def _explain(parameter: str, direction: SafeDirection, comparison: int, delta: ControlDelta) -> str:
    return (
        f"{parameter} {_MOVED[comparison]}; the registry has it ratified "
        f"{direction.value}, so this edit is {delta.value}"
    )
