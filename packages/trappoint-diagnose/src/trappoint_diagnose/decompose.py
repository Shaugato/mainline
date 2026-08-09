# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""DECLARATIVE DECOMPOSITION — the primary algorithm, and the reference model of the UDF.

The refused constraint maps to the projected counter behind it, and that counter's
witness rows ARE the minimal unsatisfiable subset. No probe, no search, no oracle: for a
single-counter refusal the answer is already in the rows, and computing it any other way
would be slower and less certain.

This module is the PURE form of what ``trappoint.explain_refusal()`` does in SQL
(migration ``0119a``). Having both is not duplication, it is the differential:

* the SQL form is authoritative at run time, because it is evaluated by the same engine
  that produced the refusal and therefore cannot disagree with it;
* this form is authoritative in TESTS, because it needs no database, so the minimality
  property can be asserted before any schema exists — which is what `PL-2` demands of a
  product whose deliverable is a refusal;
* and where they differ, the difference is a bug in one of them, which is a far better
  position than having one implementation nobody can cross-check.

**One place where this form is strictly better, and it is not an accident.** The render
context that feeds the SQL template carries a counter's ``column``, ``constraint`` and
``polarity``, but not its ``offset_column``. So the SQL decomposition of an
offset-allowed constraint can name the counter and not its companion. This module reads
``vertical.toml`` directly, so it names both — and the reason set for such a refusal is
genuinely TWO atoms: the counter is non-zero AND the offset is absent, and removing
either one restores admissibility. That is what irreducible means, and a one-atom answer
would be a subset that is not unsatisfiable.

**This module never fabricates.** If a projected counter is non-zero and the witness set
behind it is empty, that is drift between a projection and its source, and it raises. The
whole value of a diagnosis produced by the constraint engine is lost the moment the
diagnoser is willing to guess.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from .binding import CounterBinding, GateBinding
from .errors import NotDiagnosable
from .model import (
    CapabilityGap,
    DisposeObligations,
    ForkSubject,
    MusAtom,
    Naa,
    Obligation,
    SubstituteKind,
    SupplyEvidence,
)

__all__ = [
    "EPOCH_PIN_PREFIX",
    "Decomposition",
    "OpenObligation",
    "Witnesses",
    "decompose",
]

# The pin constraint is named per subject kind (`epoch_pin_permit`, `epoch_pin_cr`), and
# the binding does not carry those names, so both this module and the UDF match on the
# prefix. Stated as a constant because two implementations must agree on it exactly.
EPOCH_PIN_PREFIX = "epoch_pin_"

_CLEARANCE_CONSTRAINT = "fk_clearance"


@dataclass(frozen=True, slots=True)
class OpenObligation:
    """One undischarged obligation, as the witness query returns it."""

    obligation_id: str
    origin: str | None = None
    clause_id: str | None = None
    event_id: str | None = None
    severity: int | None = None
    virulence: str | None = None


@dataclass(frozen=True, slots=True)
class Witnesses:
    """The rows behind the refusal, as read from the subject and its obligation table.

    ``open_obligations`` is ``None`` when the substrate could not enumerate the witnesses
    — the counter is fed by a relation the VERTICAL declares, and the substrate does not
    invent rows for tables it does not own. An empty LIST is a different statement: the
    substrate looked, and found nothing, while the counter says otherwise. The first
    degrades to a counter atom; the second is drift and refuses.
    """

    counter_values: Mapping[str, int] = field(default_factory=dict)
    open_obligations: Sequence[OpenObligation] | None = None
    legal_kinds: Sequence[str] = ()
    subject_state: str | None = None


@dataclass(frozen=True, slots=True)
class Decomposition:
    """What the declarative pass concluded."""

    diagnosis: Literal["declarative", "none"]
    mus: tuple[MusAtom, ...]
    naa: Naa | None
    naa_reason: str | None

    @property
    def covered(self) -> bool:
        """True when the decomposition produced a proven-minimal reason set."""
        return self.diagnosis == "declarative"


def _counter_value(witnesses: Witnesses, column: str) -> int:
    value = witnesses.counter_values.get(column)
    if value is None or value <= 0:
        raise NotDiagnosable(
            "TRAPPOINT: the projected counter is zero — this refusal is not reproducible "
            "against the current row"
        )
    return value


def _obligation_atoms(rows: Sequence[OpenObligation], detail: str) -> tuple[MusAtom, ...]:
    return tuple(
        Obligation(
            obligation_id=row.obligation_id,
            origin=row.origin,
            clause_id=row.clause_id,
            event_id=row.event_id,
            severity=row.severity,
            virulence=row.virulence,
            detail=detail,
        )
        for row in sorted(rows, key=lambda row: row.obligation_id)
    )


def _decompose_obligation_counter(
    binding: GateBinding, witnesses: Witnesses, rows: Sequence[OpenObligation]
) -> Decomposition:
    if not rows:
        raise NotDiagnosable(
            "TRAPPOINT: projected counter disagrees with the re-derived witness set — "
            "refusing on drift"
        )
    atoms = _obligation_atoms(rows, "open on this subject; no live disposition")
    ids = [row.obligation_id for row in sorted(rows, key=lambda row: row.obligation_id)]
    legal = tuple(witnesses.legal_kinds) or None
    del binding
    return Decomposition(
        diagnosis="declarative",
        mus=atoms,
        naa=DisposeObligations(
            obligation_ids=ids,
            cardinality=len(ids),
            legal_kinds=legal,
            description=(
                f"{len(ids)} obligation(s) remain open on this subject; disposing of "
                "exactly those restores admissibility"
            ),
        ),
        naa_reason=None,
    )


def _decompose_counter_without_witnesses(
    binding: GateBinding,
    subject_table: str,
    counter: CounterBinding,
    witnesses: Witnesses,
    value: int,
) -> Decomposition:
    qualified = f"{binding.schema}.{subject_table}.{counter.column}"
    source = binding.relation_for(counter.column)
    detail = (
        f"projected counter is non-zero; it is fed by {source}"
        if source
        else "projected counter is non-zero and no source relation is declared for it"
    )
    counter_atom = CapabilityGap(
        capability=qualified,
        required_value=0,
        observed_value=value,
        detail=detail,
    )
    if not counter.offset_allowed or counter.offset_column is None:
        return Decomposition(
            diagnosis="declarative",
            mus=(counter_atom,),
            naa=SupplyEvidence(
                required=[qualified],
                cardinality=value,
                description=(
                    f"{value} obligation(s) feed this counter; resolving exactly those "
                    "restores admissibility"
                ),
            ),
            naa_reason=None,
        )

    # The offset-allowed shape. The CHECK is `counter = 0 OR offset > 0`, so BOTH facts
    # are needed to refuse and removing EITHER restores admissibility. A one-atom answer
    # here would be a subset that is not unsatisfiable, which the wire contract forbids
    # in as many words (M-2).
    offset_qualified = f"{binding.schema}.{subject_table}.{counter.offset_column}"
    offset_value = witnesses.counter_values.get(counter.offset_column, 0)
    offset_atom = CapabilityGap(
        capability=offset_qualified,
        required_value=1,
        observed_value=offset_value,
        detail=(
            "the offsetting companion is absent; this constraint is satisfied either by "
            "the counter reaching zero or by this being present"
        ),
    )
    return Decomposition(
        diagnosis="declarative",
        mus=(counter_atom, offset_atom),
        naa=SupplyEvidence(
            required=[offset_qualified],
            cardinality=1,
            description=(
                f"supply one {counter.offset_column}; the constraint admits it as an "
                "alternative to the counter reaching zero"
            ),
        ),
        naa_reason=None,
    )


def _decompose_clearance(
    witnesses: Witnesses, attempt: Mapping[str, Any], schema: str
) -> Decomposition:
    rows = witnesses.open_obligations or ()
    attempted_kind = attempt.get("kind")
    if not rows:
        return Decomposition(
            diagnosis="none",
            mus=(
                CapabilityGap(
                    capability=f"{schema}.clearance_legal",
                    detail=(
                        "no open obligation on this subject carries a classification, so "
                        "the refused verdict cannot be placed in the lattice"
                    ),
                ),
            ),
            naa=None,
            naa_reason="not_computable",
        )

    virulences = sorted({row.virulence for row in rows if row.virulence})
    classification = ", ".join(virulences) if virulences else None
    named = attempted_kind if isinstance(attempted_kind, str) and attempted_kind else "verdict"
    gap = CapabilityGap(
        capability=f"{schema}.clearance_legal.{named}",
        required_value=classification,
        detail=(
            f"no row ({classification or 'unknown'}, "
            f"{attempted_kind or 'the attempted kind'}) exists in the typed clearance table"
        ),
    )
    atoms: tuple[MusAtom, ...] = (
        gap,
        *_obligation_atoms(
            rows, "classification projected from the authority source, not from the inserted row"
        ),
    )
    legal = tuple(witnesses.legal_kinds)
    if not legal:
        # Not a diagnoser failure. At this ancestral severity the verdict set is empty by
        # design: there is no disposition constructor that clears it, and saying so is the
        # sentence the product exists to be able to say.
        return Decomposition(
            diagnosis="declarative", mus=atoms, naa=None, naa_reason="no_legal_verdict_exists"
        )
    return Decomposition(
        diagnosis="declarative",
        mus=atoms,
        naa=SubstituteKind(
            legal_kinds=list(legal),
            cardinality=1,
            description=(
                f"{len(legal)} clearance kind(s) exist at this classification; the "
                "attempted verdict is not one of them"
            ),
        ),
        naa_reason=None,
    )


def _decompose_epoch_pin(
    binding: GateBinding,
    context_subject_kind: str,
    subject_id: str,
    gate_epoch: int,
    witnesses: Witnesses,
    attempt: Mapping[str, Any],
) -> Decomposition:
    subject = binding.subject(context_subject_kind)
    completing = None if subject is None else subject.completing_state
    attempted_epoch = attempt.get("gate_epoch")
    observed = attempted_epoch if isinstance(attempted_epoch, int) else None
    capability = f"{context_subject_kind}.gate_epoch"
    if witnesses.subject_state is not None and witnesses.subject_state == completing:
        return Decomposition(
            diagnosis="declarative",
            mus=(
                CapabilityGap(
                    capability=capability,
                    required_value=gate_epoch,
                    observed_value=observed,
                    detail=(
                        "the completed transition pins this subject at its epoch, and "
                        "ON UPDATE RESTRICT refuses any change to it"
                    ),
                ),
            ),
            naa=ForkSubject(
                parent_subject_id=subject_id,
                cardinality=1,
                description=(
                    "the subject is completed and pinned; the only admissible path is a "
                    "child subject whose gate is cleared afresh"
                ),
            ),
            naa_reason=None,
        )
    return Decomposition(
        diagnosis="declarative",
        mus=(
            CapabilityGap(
                capability=capability,
                required_value=gate_epoch,
                observed_value=observed,
                detail=(
                    "the epoch moved after the completion was prepared; a new obligation bumped it"
                ),
            ),
        ),
        naa=SupplyEvidence(
            required=["gate_epoch"],
            cardinality=1,
            description=(
                "read the subject epoch again and re-attempt the completion against it, "
                "having disposed of what bumped it"
            ),
        ),
        naa_reason=None,
    )


def decompose(
    binding: GateBinding,
    *,
    subject_kind: str,
    subject_id: str,
    gate_epoch: int,
    constraint: str,
    witnesses: Witnesses,
    attempt: Mapping[str, Any] | None = None,
) -> Decomposition:
    """Decompose *constraint* into its irreducible reason set and nearest alternative.

    The four cases, in the order the UDF tries them: a declared counter, the clearance
    lattice, the epoch pin, and everything else. The last is not a failure — it is the
    hand-off to QuickXplain, and it is reported as ``diagnosis="none"`` so that a
    consumer never mistakes a candidate set for a proven-minimal one.

    Raises:
        NotDiagnosable: the counter is zero (the refusal is no longer reproducible) or the
            counter is non-zero with an empty witness set (drift). Neither licences a
            fabricated reason set.
    """
    attempt = dict(attempt or {})
    subject = binding.subject(subject_kind)
    counter = None if subject is None else subject.counter_for(constraint)

    if subject is not None and counter is not None:
        value = _counter_value(witnesses, counter.column)
        if witnesses.open_obligations is not None:
            return _decompose_obligation_counter(binding, witnesses, witnesses.open_obligations)
        return _decompose_counter_without_witnesses(
            binding, subject.table, counter, witnesses, value
        )

    if constraint == _CLEARANCE_CONSTRAINT:
        return _decompose_clearance(witnesses, attempt, binding.schema)

    if constraint.startswith(EPOCH_PIN_PREFIX):
        return _decompose_epoch_pin(
            binding, subject_kind, subject_id, gate_epoch, witnesses, attempt
        )

    return Decomposition(
        diagnosis="none",
        mus=(
            CapabilityGap(
                capability=constraint[:128],
                detail=(
                    "outside the declarative decomposition; the general algorithm is "
                    "QuickXplain over savepoint probes, in a separate transaction and "
                    "never on the completion path"
                ),
            ),
        ),
        naa=None,
        naa_reason="not_computable",
    )
