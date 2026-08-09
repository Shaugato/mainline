# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""May this lesson travel, and where did it not — decided without a model.

ARCHITECTURE.md §8.4 row 7 names the decision the cherry-pick worker does **not**
make: *Applicability.* This module is where that decision actually lives, and the
whole point is that it is not made here either. It is made by the **envelope** —
a predicate the originating site declared, in data, in ``lesson.envelope`` — and
this module only evaluates it.

Three separate things, kept separate on purpose.

**Eligibility** is ``only_tightenings_travel``. A total function of the lesson's
own ``control_delta``, mirroring MI23. Weakenings are site-local trade-offs and
must be re-earned locally: a setpoint that is right at one plant can be an
unrevealed hazard at another, so a relaxation one site justified with its own
evidence must not arrive at a sister site carrying that justification.

**Applicability** is the envelope predicate, evaluated over a set of site facts.
The predicate language is six forms, total, and has no ``eval``: an envelope is
data a site wrote, and data a site wrote is untrusted input.

**Priority** is the score, and it is the one people misread. The DDL column beside
it is called ``model_version``, and **no model produces this score.** It is
:func:`applicability_score`, an integer function with published weights, and the
column is filled with :data:`SCORER_VERSION`. A column named for a model that
holds a deterministic value is a far smaller lie than a model in the propagation
path — and the propagation path ends at a site safety superintendent's queue,
which is a place a model's opinion has no business ordering silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from .errors import WeakeningWouldTravel
from .types import TRAVELLING_DELTAS, require_aware

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from .types import Lesson

__all__ = [
    "DEFAULT_SLA_DAYS",
    "SCORER_VERSION",
    "SCORE_WEIGHTS",
    "SiteFacts",
    "TravelVerdict",
    "applicability_score",
    "due_by",
    "evaluate_envelope",
    "may_travel",
]

#: The version string written into ``propagation.model_version``. It names a
#: deterministic scorer. Bumped by any change to :data:`SCORE_WEIGHTS`, because a
#: score whose weights changed without the version changing is a queue that
#: reordered itself for no recorded reason.
SCORER_VERSION: Final[str] = "fleet-applicability-scorer-1.0.0"

#: The scorer's published weights, in milli-units summing to 1000. These order a
#: superintendent's queue; they do not decide anything. They are here, as data,
#: because a priority order derived from an unpublished formula is a priority order
#: nobody can argue with.
SCORE_WEIGHTS: Final[Mapping[str, int]] = {
    "hazard_energy_match": 400,
    "control_class_overlap": 300,
    "anchor_overlap": 200,
    "severity_weight": 100,
}

#: Default severity-scaled SLA windows, in days.
#:
#: **These numbers are carried in data and are not derived from any standard.**
#: No regulation this project has read prescribes a fleet-propagation response
#: window, and inventing one and presenting it as best practice would be exactly
#: the kind of unearned authority this product exists to refuse. They are a
#: starting table for a customer's own escalation policy, and :func:`due_by` takes
#: the table as an argument so a site can supply its own without editing code.
DEFAULT_SLA_DAYS: Final[Mapping[int, int]] = {5: 7, 4: 14, 3: 30, 2: 60, 1: 90}

#: A site's facts, as normalised ``namespace:value`` tokens — for example
#: ``hazard_energy:h2s``, ``control_class:energy_isolation``, ``asset:P-101A``.
#: A set of strings rather than a nested document, because the envelope predicate
#: has to be total and a nested query language would not be.
SiteFacts = frozenset[str]

_MAX_ENVELOPE_DEPTH: Final[int] = 8


@dataclass(frozen=True, slots=True)
class TravelVerdict:
    """Whether a lesson may travel to one site, and why or why not.

    ``eligible`` and ``applicable`` are separate fields because they fail for
    different reasons and are answered by different parties: eligibility is the
    fleet's rule about the lesson, applicability is the originating site's claim
    about where the lesson holds. Collapsing them into one boolean would make a
    "no" unattributable.
    """

    eligible: bool
    applicable: bool
    reasons: tuple[str, ...]

    @property
    def travels(self) -> bool:
        """True only when both halves say yes."""
        return self.eligible and self.applicable


def may_travel(lesson: Lesson, facts: SiteFacts) -> TravelVerdict:
    """Decide whether ``lesson`` may be offered to a site with these facts.

    Never raises for an ordinary "no": a lesson that does not apply is an
    expected, recorded outcome, and turning it into an exception would make the
    caller's happy path the only path that produces a record.

    :class:`~mainline_cherrypick.errors.WeakeningWouldTravel` is raised only by
    :class:`~mainline_cherrypick.types.Lesson`'s own constructor, so a lesson
    object that exists is already eligible — the ``eligible`` check here is
    defence in depth against a future constructor that forgets.
    """
    reasons: list[str] = []
    eligible = lesson.control_delta in TRAVELLING_DELTAS
    if not eligible:
        reasons.append(f"control_delta={lesson.control_delta.value!r} is not a tightening (MI23)")

    applicable, envelope_reasons = evaluate_envelope(lesson.envelope, facts)
    reasons.extend(envelope_reasons)
    return TravelVerdict(eligible=eligible, applicable=applicable, reasons=tuple(reasons))


def evaluate_envelope(  # noqa: PLR0911, PLR0912
    envelope: Mapping[str, Any],
    facts: SiteFacts,
    *,
    depth: int = 0,
) -> tuple[bool, tuple[str, ...]]:
    """Evaluate a transport envelope against a site's facts.

    Six forms, and no others:

    ==================  ==================================================
    ``{}``              vacuously true — the originating site declared no
                        restriction, which is a claim it is making
    ``{"all": [...]}``  every sub-predicate holds
    ``{"any": [...]}``  at least one sub-predicate holds
    ``{"not": {...}}``  the sub-predicate does not hold
    ``{"has": "t"}``    the site carries fact token ``t``
    ``{"absent": "t"}`` the site does not carry fact token ``t``
    ==================  ==================================================

    An unrecognised key evaluates to **false with a reason**, never to true. An
    envelope this code does not understand is an envelope whose author meant
    something, and defaulting to "applies everywhere" would propagate a lesson
    into plants its author was trying to exclude.

    One ``return`` per form plus one per malformation, and that branch count is
    why ``PLR0911``/``PLR0912`` are silenced here rather than the function being
    split: a total evaluator over six forms **is** a wide dispatch, and factoring
    it into helpers would hide the exhaustiveness that makes "an unrecognised
    operator is refused" checkable by reading.

    Returns:
        ``(applies, reasons)``. ``reasons`` is empty when the answer is yes; a
        "yes" needs no explanation and a "no" always does.

    Raises:
        ValueError: the envelope nests deeper than eight levels. An envelope is
            data a site wrote, and unbounded recursion over untrusted input is a
            denial of service with a safety justification attached.
    """
    if depth > _MAX_ENVELOPE_DEPTH:
        raise ValueError(
            f"transport envelope nests deeper than {_MAX_ENVELOPE_DEPTH} levels. An "
            f"envelope is untrusted input from another site; unbounded recursion over it "
            f"is a denial of service"
        )
    if not envelope:
        return True, ()

    if len(envelope) != 1:
        detail = (
            f"envelope node carries {sorted(envelope)}: exactly one operator per node, "
            f"so that a reader cannot mistake an implicit conjunction for a disjunction"
        )
        return False, (detail,)

    ((operator, operand),) = envelope.items()

    if operator == "has":
        token = str(operand)
        if token in facts:
            return True, ()
        return False, (f"site does not carry {token!r}",)

    if operator == "absent":
        token = str(operand)
        if token not in facts:
            return True, ()
        return False, (f"site carries {token!r}, which the envelope excludes",)

    if operator == "not":
        if not isinstance(operand, dict):
            return False, ("'not' takes one envelope node",)
        holds, _ = evaluate_envelope(operand, facts, depth=depth + 1)
        if holds:
            return False, ("the excluded condition holds at this site",)
        return True, ()

    if operator in ("all", "any"):
        if not isinstance(operand, list) or not operand:
            return False, (f"{operator!r} takes a non-empty list of envelope nodes",)
        results = [
            evaluate_envelope(node if isinstance(node, dict) else {}, facts, depth=depth + 1)
            for node in operand
        ]
        if operator == "all":
            failures = tuple(
                reason for holds, reasons in results if not holds for reason in reasons
            )
            return (not failures), failures
        if any(holds for holds, _ in results):
            return True, ()
        return False, tuple(reason for _, reasons in results for reason in reasons)

    unknown = (
        f"unrecognised envelope operator {operator!r}. An envelope this code does not "
        f"understand is refused, never assumed to apply everywhere"
    )
    return False, (unknown,)


def applicability_score(
    lesson: Lesson,
    facts: SiteFacts,
    *,
    lesson_facts: SiteFacts,
) -> int:
    """Return a priority score in milli-units; no model produces this number.

    Args:
        lesson: the lesson being offered; only ``max_severity`` is read.
        facts: the receiving site's fact tokens.
        lesson_facts: the originating site's fact tokens for this lesson —
            the hazard energies, control classes and anchors the change touched.

    Returns:
        ``0…1000``. It orders a superintendent's queue and decides nothing. A site
        that receives a lesson scoring 12 still owes the fleet an answer, because
        DEP-3's content is a *mandated response*, not mandated conformity.

    The weights are :data:`SCORE_WEIGHTS`, published, and the version written into
    ``propagation.model_version`` is :data:`SCORER_VERSION`.
    """
    score = 0
    for namespace, weight_key in (
        ("hazard_energy", "hazard_energy_match"),
        ("control_class", "control_class_overlap"),
        ("asset", "anchor_overlap"),
    ):
        theirs = {token for token in lesson_facts if token.startswith(f"{namespace}:")}
        mine = {token for token in facts if token.startswith(f"{namespace}:")}
        if not theirs:
            continue
        overlap = len(theirs & mine)
        score += (SCORE_WEIGHTS[weight_key] * overlap) // len(theirs)

    score += (SCORE_WEIGHTS["severity_weight"] * lesson.max_severity) // 5
    return min(score, 1000)


def due_by(
    proposed_at: datetime,
    max_severity: int,
    *,
    sla_days: Mapping[int, int] = DEFAULT_SLA_DAYS,
) -> datetime:
    """Return the severity-scaled SLA deadline for a propagation.

    ``sla_days`` is an argument, not a constant, because :data:`DEFAULT_SLA_DAYS`
    is a starting table rather than a standard — see its docstring. A site that
    supplies its own escalation policy changes a value, not this function.

    Raises:
        KeyError: the severity has no window in the supplied table. Defaulting
            would silently give an unmapped severity the loosest deadline in the
            table, which is the wrong direction to guess in.
    """
    require_aware(proposed_at, "propagation.proposed_at")
    return proposed_at + timedelta(days=sla_days[max_severity])


def assert_may_travel(lesson: Lesson) -> None:
    """Raise unless ``lesson`` is eligible to travel at all, and return otherwise.

    Redundant with :class:`~mainline_cherrypick.types.Lesson`'s constructor by
    design: the emitter calls this immediately before building the ``INSERT``, so
    the check runs against the object that is about to be written rather than
    against the object that was once built.
    """
    if lesson.control_delta not in TRAVELLING_DELTAS:
        raise WeakeningWouldTravel(str(lesson.lesson_id), lesson.control_delta.value)
