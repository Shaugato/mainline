# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""As-documented against as-operated, through the **same** lattice the clause pipeline uses.

The single most important sentence in ARCHITECTURE.md §5.8 is this one: *a drift
finding is a ``control_delta`` whose author is the plant.* Everything in this module
follows from it.

The comparison is not a new algorithm. It is
:func:`mainline_domain.lattice.explain` with ``reference = documented_cat`` and
``descendant = observed_cat`` — nine rules, a join, a minimal unsatisfiable subset.
Because the merge gate already auto-materialises a blocking check for ``weaken`` over
severity ≥ 4 ancestry, **a reality-authored weakening fires the existing gate with no
new gate logic**, and the blocking decision reads ``clause_blame_current.max_severity``
rather than the clause's current text — so diachronic gating is preserved for free. A
second comparison implementation here would have been a second answer to a question
that must have exactly one.

Three things this module adds on top of the lattice, and only three.

**The corridor gates the setpoint rule, and only the setpoint rule.** A historian
value differing from a setpoint by less than ``ExcDev + CompDev`` establishes
nothing. But a missing verification step, a widened exception or a downgraded
deontic arrive as *structured fields* from a CMMS or an isolation register and have
no corridor at all. So the downgrade to ``undetermined`` fires only when
``R2_SETPOINT`` is the **only rule contributing a refusal** — see
:func:`_setpoint_is_the_only_reason`, which explains at length why the minimal
unsatisfiable subset is the wrong set to ask, and why asking it was wrong in the
dangerous direction.

**Absence is a first-class outcome, and it is not compliance.** No observation is not
a passing observation. It produces an ``undetermined`` finding — MI21 forbids it from
blocking — *and* an A6 discordance warrant, which is a separate, human-closed
obligation that MI05 makes blocking at merge. The residual risk this leaves is named
in the README rather than mitigated away.

**Confidence is the binding's confidence and nothing else.** The lattice compare is
exact. The only genuinely uncertain step in a drift finding is the SME-reviewed
clause ⇄ asset binding, so that is what ``confidence`` reports. A number that blended
an exact comparison with an uncertain binding would be a number nobody could
interpret, and it would be read as a probability that the finding is true.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from mainline_domain.contracts import CAT, ControlDelta, force
from mainline_domain.lattice import explain
from mainline_domain.registry.model import SafeDirection

from .errorbar import CorridorVerdict, read_against_corridor
from .errors import MissingErrorBar

if TYPE_CHECKING:
    from mainline_domain.contracts import DeltaWitness
    from mainline_domain.lattice import LatticeDecision
    from mainline_domain.registry.model import SafeDirectionRegistry

    from .errorbar import BoundedNegative, Reading
    from .types import ClauseBinding, ObservedAssertion

__all__ = [
    "SETPOINT_ONLY",
    "FixityComparison",
    "Reason",
    "compare_fixity",
]

#: The one rule the compression corridor is allowed to overrule, and it is the only
#: rule whose evidence is an archived scalar rather than a structured field. Every
#: other rule reads a field a person or a CMMS wrote, and those do not compress.
SETPOINT_ONLY: frozenset[str] = frozenset({"R2_SETPOINT"})


class Reason(StrEnum):
    """Why the comparison came out the way it did, in the words the finding uses."""

    #: The lattice found a determinate delta and the evidence can carry it.
    DRIFT = "drift"
    #: Documented and observed agree, under all nine rules.
    NO_DRIFT = "no_drift"
    #: The plant is running a control the document does not contain.
    UNDOCUMENTED_CONTROL = "undocumented_control"
    #: No observation exists for a control that should have produced one — A6.
    EVIDENCE_ABSENT = "evidence_absent"
    #: The only reason this looked like a weakening is a number inside the corridor.
    BELOW_CORRIDOR = "below_corridor"
    #: The control is a tolerance band; one archived vertex cannot show its width.
    BAND_NOT_OBSERVABLE = "band_not_observable"


@dataclass(frozen=True, slots=True)
class FixityComparison:
    """The verdict on one clause ⇄ asset pair, with everything behind it kept.

    ``direction`` is ``None`` exactly when ``undetermined`` is ``True``: an
    undetermined comparison has no direction, and writing ``weaken`` beside
    ``undetermined = true`` would let a reader take the direction and drop the
    caveat.

    ``witnesses`` is the lattice's **minimal** set. Those rows go to
    ``mainline.delta_witness`` before the finding, in the same transaction, for
    the same reason a ``clause_version`` weakening does: an unexplainable
    weakening verdict does not get to exist.
    """

    direction: ControlDelta | None
    undetermined: bool
    reason: Reason
    confidence_milli: int
    witnesses: tuple[DeltaWitness, ...]
    reading: Reading | None
    bounded_negative: BoundedNegative | None
    registry_abstained: bool
    decision: LatticeDecision | None

    def __post_init__(self) -> None:
        """Hold the direction/undetermined exclusivity at construction."""
        if self.undetermined and self.direction is not None:
            raise ValueError(
                "an undetermined comparison has no direction. Writing one beside "
                "undetermined = true lets a reader keep the direction and drop the caveat"
            )

    @property
    def is_finding(self) -> bool:
        """True when this comparison is worth a ``drift_finding`` row.

        Agreement is *not* worth a row: the patrol's coverage claim is carried by
        ``patrol_run.n_checked``, and a row per agreeing clause would put the
        corpus in every audit view and break the 8 KiB budget within a week.
        """
        return self.reason is not Reason.NO_DRIFT

    @property
    def opens_warrant(self) -> bool:
        """True when this comparison also opens a discordance warrant.

        A2 for a real divergence, A6 for an absence. The bounded-negative case
        opens nothing: *"we looked and the archive cannot resolve it"* is a
        recorded limitation of the instrument, not a discordance of the record.
        """
        return self.reason in (
            Reason.DRIFT,
            Reason.UNDOCUMENTED_CONTROL,
            Reason.EVIDENCE_ABSENT,
        )


def compare_fixity(  # noqa: PLR0911
    documented: CAT | None,
    observed: ObservedAssertion | None,
    registry: SafeDirectionRegistry,
    as_of: bytes,
    *,
    binding: ClauseBinding,
) -> FixityComparison:
    """Compare one documented control against one plant observation.

    Args:
        documented: the CAT of the clause version in force at ``as_of``.
        observed: the plant's assertion, or ``None`` when the expected evidence
            never arrived.
        registry: the DIRECTRIX registry **read at ``as_of``**. The lattice
            refuses a registry read at any other commit, which is what stops a
            finding from being re-derived under a registry that has since moved.
        as_of: the commit the documented side was read at.
        binding: the SME-reviewed clause ⇄ asset link. Its confidence is the
            finding's confidence.

    Returns:
        A :class:`FixityComparison`. Never ``None``, and never an exception for
        an ordinary plant state — the exceptions here are for evidence that is
        malformed, not for evidence that is bad news.

    Seven returns, one per outcome, and that is why ``PLR0911`` is silenced rather
    than the function split: each ``return`` is a named product state that a
    reviewer has to be able to find by reading, and hiding three of them behind a
    helper would make the enumeration of outcomes a thing you infer instead of a
    thing you see.

    Raises:
        MissingErrorBar: a corridor-bearing source supplied no ExcDev/CompDev and
            the comparison turns on a setpoint. A confident answer from an export
            that cannot support one is the failure mode this whole module exists
            to prevent.
    """
    if observed is None:
        return FixityComparison(
            direction=None,
            undetermined=True,
            reason=Reason.EVIDENCE_ABSENT,
            confidence_milli=binding.confidence_milli,
            witnesses=(),
            reading=None,
            bounded_negative=None,
            registry_abstained=False,
            decision=None,
        )

    if documented is None:
        # The plant runs a control the document does not contain. That is drift in
        # the document, not in the plant, and `introduce` is the honest label: the
        # as-documented side is missing a control the as-operated side has.
        return FixityComparison(
            direction=ControlDelta.INTRODUCE,
            undetermined=False,
            reason=Reason.UNDOCUMENTED_CONTROL,
            confidence_milli=binding.confidence_milli,
            witnesses=(),
            reading=None,
            bounded_negative=None,
            registry_abstained=False,
            decision=None,
        )

    observed_cat = observed.observed_cat
    if observed_cat is None:
        # A row arrived, but it asserts nothing about this control. Structurally
        # the same as no row at all, and it must not read as agreement.
        return FixityComparison(
            direction=None,
            undetermined=True,
            reason=Reason.EVIDENCE_ABSENT,
            confidence_milli=binding.confidence_milli,
            witnesses=(),
            reading=None,
            bounded_negative=None,
            registry_abstained=False,
            decision=None,
        )

    decision = explain(documented, observed_cat, registry, as_of)
    resolution = registry.resolve(documented.parameter)
    abstained = resolution.abstained

    if decision.verdict.delta is ControlDelta.RESTATE and not decision.minimal:
        return FixityComparison(
            direction=ControlDelta.RESTATE,
            undetermined=False,
            reason=Reason.NO_DRIFT,
            confidence_milli=binding.confidence_milli,
            witnesses=(),
            reading=None,
            bounded_negative=None,
            registry_abstained=abstained,
            decision=decision,
        )

    reading = _read_setpoint(documented, observed_cat, observed, resolution.direction)

    if reading is not None and _setpoint_is_the_only_reason(decision):
        if reading.verdict is CorridorVerdict.INDISTINGUISHABLE:
            return FixityComparison(
                direction=None,
                undetermined=True,
                reason=Reason.BELOW_CORRIDOR,
                confidence_milli=binding.confidence_milli,
                witnesses=decision.verdict.witnesses,
                reading=reading,
                bounded_negative=reading.bounded_negative,
                registry_abstained=abstained,
                decision=decision,
            )
        if reading.verdict is CorridorVerdict.BAND_NOT_OBSERVABLE:
            return FixityComparison(
                direction=None,
                undetermined=True,
                reason=Reason.BAND_NOT_OBSERVABLE,
                confidence_milli=binding.confidence_milli,
                witnesses=decision.verdict.witnesses,
                reading=reading,
                bounded_negative=None,
                registry_abstained=abstained,
                decision=decision,
            )

    return FixityComparison(
        direction=decision.verdict.delta,
        undetermined=False,
        reason=Reason.DRIFT,
        confidence_milli=binding.confidence_milli,
        witnesses=decision.verdict.witnesses,
        reading=reading,
        bounded_negative=None,
        registry_abstained=abstained,
        decision=decision,
    )


def _setpoint_is_the_only_reason(decision: LatticeDecision) -> bool:
    """Report whether ``R2_SETPOINT`` is the only rule contributing a refusal at all.

    **Not the minimal unsatisfiable subset.** That was the first implementation and
    it was wrong, in the dangerous direction. A minimal set is *irredundant*: when a
    setpoint move and a dropped verification step each independently produce
    ``weaken``, ``{R2}`` is already a MUS and the minimisation discards ``R6``. A
    corridor test keyed on the MUS would therefore have downgraded "the threshold
    moved four points **and** the countersignature requirement vanished" to
    ``undetermined``, because the one rule the MUS happened to keep was the one the
    corridor can excuse.

    So the test is over every finding with non-zero force: the corridor may excuse
    the whole verdict only when there is nothing else in it. ``decision.repair`` —
    the minimal correction set — would answer the same question; the force-filtered
    findings are used because they say it literally.
    """
    contributing = {finding.rule_id for finding in decision.findings if force(finding.delta) > 0}
    return contributing == SETPOINT_ONLY


def _read_setpoint(
    documented: CAT,
    observed_cat: CAT,
    observation: ObservedAssertion,
    direction: SafeDirection,
) -> Reading | None:
    """Read the two setpoints against the corridor, or return ``None``.

    ``None`` means there is no scalar comparison to make — one side or the other
    carries no value — and the corridor therefore has nothing to say about this
    clause. It is *not* a way of skipping the error-bar requirement: the raise
    below fires before this function can return ``None`` for a corridor-bearing
    source that does have two values.
    """
    if documented.value is None or observed_cat.value is None:
        return None
    if observation.needs_error_bar and observation.err_bar is None:
        raise MissingErrorBar(observation.asset_tag, observation.source_ref)
    return read_against_corridor(
        documented.value,
        observed_cat.value,
        direction,
        parameter=documented.parameter,
        err_bar=observation.err_bar,
    )
