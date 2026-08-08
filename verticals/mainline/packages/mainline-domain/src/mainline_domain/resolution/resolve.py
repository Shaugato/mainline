# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The pure resolution function, and the four things it refuses to be given.

``resolve`` is the only place in MAINLINE where a model output meets a
deterministic verdict.  It is a pure function — no clock, no I/O, no globals, no
model — over ``(DeltaVerdict, OracleVerdict | None, theta)``, and it returns a
``DeltaVerdict`` whose ``basis`` records honestly which path decided.

**What ``basis`` means here, exactly.**  ``'lattice+model'`` is written *only*
when the model's label raised the force above Path A's.  A model that merely
agreed does not get to appear in the basis, because ``delta_basis`` is read by
people asking "was a model load-bearing for this refusal", and answering "yes"
where the honest answer is "the lattice found it and the model concurred" is
inflation in the direction that costs us credibility.  Concurrence is recorded in
the silence arithmetic, which is where it belongs.

**Four refusals, all on the way in.**  Every one of them is a state that cannot
be resolved correctly, and each raises rather than degrading:

* a Path-A verdict whose ``basis`` is already ``'human'`` — a signed human
  disposition is an input to the record, never something a table re-decides
  (:class:`HumanVerdictNotResolvable`);
* a Path-A verdict already carrying ``'lattice+model'`` or
  ``'abstain_to_weaken'`` — resolution is not composable, and resolving twice
  would let a second model call ratchet a verdict that a first one already
  raised (:class:`AlreadyResolved`);
* a lattice ``weaken``/``remove`` with an empty witness set — decision D8 makes
  an unexplainable weakening unrepresentable, and the database refuses it with
  ``P0001``; refusing it here as well is the second layer, not the only one
  (:class:`WitnesslessWeakening`);
* an ``OracleVerdict`` whose confidence is not a real number in ``[0, 1]``, or a
  theta outside the same interval (:class:`MalformedOracleVerdict`,
  :class:`ThetaOutOfRange`).

**A missing Path B is an abstention.**  ``oracle=None`` — the call never ran,
the transport was down, the queue drained — resolves through the abstention
floor, not through "nothing to add".  P3: absence of evidence resolves toward
the block, and it writes its arithmetic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from ..contracts import ControlDelta, DeltaVerdict, force
from .table import TABLE_SHA256, TABLE_VERSION, ResolutionCell, cell_for

if TYPE_CHECKING:
    from ..contracts import DeltaWitness, OracleVerdict

__all__ = [
    "AlreadyResolved",
    "HumanVerdictNotResolvable",
    "MalformedOracleVerdict",
    "Resolution",
    "ResolutionRefused",
    "ThetaOutOfRange",
    "WitnesslessWeakening",
    "explain",
    "resolve",
]

#: The label used in place of the oracle's when Path B did not run at all.  It is
#: never read as a label — ``absent=True`` routes straight to the abstention
#: floor — but the table is keyed on a total domain and a lookup needs a member.
_ABSENT_LABEL: Final[ControlDelta] = ControlDelta.WEAKEN


class ResolutionRefused(Exception):
    """Base class for every input this function will not resolve."""


class HumanVerdictNotResolvable(ResolutionRefused):
    """A signed human verdict was handed to the machine resolution."""


class AlreadyResolved(ResolutionRefused):
    """A verdict that has already been through the ratchet was handed back to it."""


class WitnesslessWeakening(ResolutionRefused):
    """A lattice weakening arrived with no witness set (decision D8)."""


class MalformedOracleVerdict(ResolutionRefused):
    """The oracle's confidence is not a real number in ``[0, 1]``."""


class ThetaOutOfRange(ResolutionRefused):
    """theta is not a real number in ``[0, 1]``."""


@dataclass(frozen=True, slots=True)
class Resolution:
    """The resolved verdict plus everything needed to explain it.

    ``verdict`` is what :func:`resolve` returns and what a caller stores.  The
    rest is the arithmetic: :mod:`mainline_domain.resolution.silence` turns it
    into a ledger row, and nothing else in the domain reads it.
    """

    verdict: DeltaVerdict
    cell: ResolutionCell
    path_a_delta: ControlDelta
    path_a_witnesses: tuple[DeltaWitness, ...]
    oracle_label: ControlDelta | None
    oracle_confidence: float | None
    oracle_model_id: str | None
    oracle_prompt_version: str | None
    oracle_rationale: str | None
    theta: float
    confident: bool
    abstained: bool
    oracle_present: bool
    table_version: str
    table_sha256: str

    @property
    def raised_by_model(self) -> bool:
        """Whether Path B is the reason this verdict is more forceful than Path A."""
        return self.cell.rule == "MODEL_RAISES"

    @property
    def is_zero_force(self) -> bool:
        """Whether the resolution asserts that nothing was weakened."""
        return force(self.verdict.delta) == 0


def _validate_path_a(path_a: DeltaVerdict) -> None:
    if path_a.basis == "human":
        raise HumanVerdictNotResolvable(
            "resolve() was handed a DeltaVerdict with basis='human'. A signed human "
            "verdict is the end of the argument, not an input to it: re-resolving it "
            "would let a model output move a delta a person put their name to."
        )
    if path_a.basis != "lattice":
        raise AlreadyResolved(
            f"resolve() was handed a DeltaVerdict with basis={path_a.basis!r}. "
            f"Resolution is not composable — running it twice would let a second "
            f"model call ratchet a verdict a first one already raised, and the "
            f"stored basis would no longer say which path decided. Resolve the "
            f"lattice verdict once."
        )
    if force(path_a.delta) >= force(ControlDelta.WEAKEN) and not path_a.witnesses:
        raise WitnesslessWeakening(
            f"a lattice {path_a.delta.value} arrived with an empty witness set. "
            f"Decision D8: a weakening whose minimal unsatisfiable subset was never "
            f"computed cannot be explained at a gate, and fn_delta_witness_guard "
            f"refuses the insert with P0001. This is the same refusal, one layer "
            f"earlier."
        )


def _validate_scalars(theta: float, confidence: float | None) -> None:
    if math.isnan(theta) or not 0.0 <= theta <= 1.0:
        raise ThetaOutOfRange(
            f"theta={theta!r} is not a real number in [0, 1]. theta is a calibration "
            f"artefact read from identity_policy; see "
            f"mainline_domain.resolution.policy."
        )
    if confidence is None:
        return
    if math.isnan(confidence) or not 0.0 <= confidence <= 1.0:
        raise MalformedOracleVerdict(
            f"OracleVerdict.confidence={confidence!r} is not a real number in [0, 1]. "
            f"A confidence that cannot be compared against theta cannot be resolved, "
            f"and silently treating it as zero would hide a broken producer behind a "
            f"nuisance block."
        )


def explain(
    path_a: DeltaVerdict,
    oracle: OracleVerdict | None,
    *,
    theta: float,
) -> Resolution:
    """Resolve, and return the full arithmetic alongside the verdict.

    Args:
        path_a: the deterministic lattice verdict.  Must carry ``basis='lattice'``.
        oracle: Path B's answer, or ``None`` when Path B did not run.
        theta: the confidence floor from ``identity_policy``.  No default exists
            anywhere in this package; see
            :func:`mainline_domain.resolution.policy.load_policy_theta`.

    Returns:
        The :class:`Resolution`, whose ``verdict`` is the delta of record.

    Raises:
        ResolutionRefused: on any of the four unresolvable inputs above.
    """
    _validate_path_a(path_a)
    _validate_scalars(theta, None if oracle is None else oracle.confidence)

    present = oracle is not None
    abstained = oracle.abstained if oracle is not None else True
    label = oracle.label if oracle is not None else _ABSENT_LABEL
    confidence = oracle.confidence if oracle is not None else None
    confident = confidence is not None and confidence >= theta

    cell = cell_for(path_a.delta, label, confident=confident, abstained=abstained)

    verdict = DeltaVerdict(
        delta=cell.delta,
        basis=cell.basis,
        # The model contributes no witnesses, ever. Its rationale and spans are
        # evidence attached to the record; a witness is a rule_id, a field and a
        # from/to pair produced by the lattice, and letting model prose into that
        # tuple is exactly the masquerade P7 exists to prevent.
        witnesses=path_a.witnesses,
        # Minimality is a property of the LATTICE's reasoning about its own
        # verdict. Once the resolution has moved the delta — upward, by the model
        # or by the abstention floor — the witness set no longer explains what
        # was decided, so the claim is withdrawn rather than inherited.
        minimal=path_a.minimal and cell.basis == "lattice",
    )
    return Resolution(
        verdict=verdict,
        cell=cell,
        path_a_delta=path_a.delta,
        path_a_witnesses=path_a.witnesses,
        oracle_label=label if present else None,
        oracle_confidence=confidence,
        oracle_model_id=oracle.model_id if oracle is not None else None,
        oracle_prompt_version=oracle.prompt_version if oracle is not None else None,
        oracle_rationale=oracle.rationale if oracle is not None else None,
        theta=theta,
        confident=confident,
        abstained=abstained,
        oracle_present=present,
        table_version=TABLE_VERSION,
        table_sha256=TABLE_SHA256,
    )


def resolve(
    path_a: DeltaVerdict,
    oracle: OracleVerdict | None,
    *,
    theta: float,
) -> DeltaVerdict:
    """The delta of record for one clause version.

    A thin projection of :func:`explain`.  Callers that write a silence record —
    which is every caller, because every ``neutral`` and every abstention is a
    ledger row (P5) — want :func:`explain` instead.
    """
    return explain(path_a, oracle, theta=theta).verdict
