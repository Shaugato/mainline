# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Severity appraisal — the decision the Archivist does not make.

ARCHITECTURE.md §8.4, row 1, states this agent's abstention in one line: **severity comes
from a coded field, a regulator classification, or a signed human. A model-rated severity
never arms the gate.** Migration 0033 turns that line into a plain-column CHECK on
``mainline.event``::

    CONSTRAINT model_cannot_arm CHECK (severity_gate < 4 OR severity_basis <> 'model_rated')

This module is the arithmetic that makes a row satisfying that CHECK the only row this
package can build — and, more usefully, it is the arithmetic that makes the *disagreement*
visible instead of discarding it.

**Three severities, three different sentences** (0033's own words):

===================== ============================================================
``severity_actual``   what happened. A coded consequence. A model may never state it.
``severity_potential`` what could reasonably have happened. Hindsight and model
                      inference live here, and this is deliberately **not** the gate.
``severity_gate``     what this system will act on.
===================== ============================================================

**The ceiling, and why it is 3 rather than 0.** A model rating contributes to the gate up
to :data:`MODEL_GATE_CEILING`, one below the arming threshold. Migration 0033 spells out
the case the ceiling exists for: *"Rated 5 by a model, the event still sits in the record
at severity_gate = 3 with severity_potential = 5, which is a visible, quotable
disagreement between what the machine thought and what the gate did. That row is a better
exhibit than a green test suite."* Zeroing the model's reading instead would delete the
disagreement, and the deletion would be invisible.

**The downgrade is a row, not a shrug.** Every capped claim produces a :class:`Downgrade`,
and :func:`downgrade_silence_rows` renders those as ``mainline_meas.silence_ledger`` rows
with ``source='severity_downgrade'`` and ``reason='cap_exceeded'`` — invariant I13, silence
is logged. This package **builds** those rows and never writes them: ``agent_ingestor``
holds no INSERT on ``silence_ledger`` (see the README's *Grants I do not hold*).

**Promotion is the escape hatch, and it costs a name.** 0033 permits a model rating to be
promoted by *"a person who puts their name on it"*. :func:`promote` is that, and it demands
a person id and a signing-credential id, because a promotion nobody signed is the original
problem with a different ``severity_basis`` string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, Literal

from .errors import (
    ModelRatedCannotArm,
    SeverityOutOfRange,
    SeverityWithoutBasis,
    SeverityWithoutSpan,
    UnsignedPromotion,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .verbatim import VerbatimSpan

__all__ = [
    "ARMING_THRESHOLD",
    "MAX_SEVERITY",
    "MODEL_GATE_CEILING",
    "SEVERITY_BASIS_VOCABULARY",
    "Basis",
    "Dimension",
    "Downgrade",
    "SeverityAppraisal",
    "SeverityClaim",
    "appraise",
    "downgrade_silence_rows",
    "promote",
]

#: The gate class boundary. ``blocking_check`` arms at 4; 0-3 is advisory. Mirrored here
#: rather than imported so that this module has no dependency on the gate's own package —
#: and asserted against the kernel's value by the integration suite, not by a comment.
ARMING_THRESHOLD: Final[int] = 4

#: The ceiling a ``model_rated`` claim may push ``severity_gate`` to. One below the
#: arming threshold, and the whole of MI14's client-side half.
MODEL_GATE_CEILING: Final[int] = ARMING_THRESHOLD - 1

#: ``CHECK severity_*_in_range`` on ``mainline.event``.
MAX_SEVERITY: Final[int] = 5

#: ``CHECK severity_basis_closed`` on ``mainline.event``, in the migration's own order.
SEVERITY_BASIS_VOCABULARY: Final[tuple[str, ...]] = (
    "coded_field",
    "regulator_class",
    "human_rated",
    "model_rated",
)


class Basis(StrEnum):
    """Who says so. The closed vocabulary of ``event.severity_basis``."""

    CODED_FIELD = "coded_field"
    REGULATOR_CLASS = "regulator_class"
    HUMAN_RATED = "human_rated"
    MODEL_RATED = "model_rated"

    @property
    def admitted(self) -> bool:
        """Whether a claim on this basis may push the gate past the ceiling.

        Three of the four are admitted. The fourth is the product.
        """
        return self is not Basis.MODEL_RATED


#: Which of the three severities a claim speaks to.
Dimension = Literal["actual", "potential"]


@dataclass(frozen=True, slots=True)
class SeverityClaim:
    """One statement about how bad this event was, and who is behind it.

    A claim is never a bare integer. It carries its basis, the dimension it speaks to,
    the span of the source that says it, and an attribution — the coded field's name, the
    regulator's scheme and code, the person's id, or the call profile that produced it.
    Everything a reader needs in order to disagree with it is on the claim.

    Attributes:
        basis: who says so.
        value: 0-5.
        dimension: ``"actual"`` (what happened) or ``"potential"`` (what could have).
        span: where in the extracted text this reading was taken from. Required for any
            non-zero value.
        attributed_to: the field, scheme, person or profile behind the claim.
        evidence: extra key/value pairs carried into the ledger. Sorted pairs rather than
            a mapping so the claim stays hashable and comparable.
    """

    basis: Basis
    value: int
    dimension: Dimension
    attributed_to: str
    span: VerbatimSpan | None = None
    evidence: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Refuse a claim the ``event`` CHECKs would refuse, and one they would not.

        Raises:
            SeverityOutOfRange: outside 0-5.
            SeverityWithoutSpan: non-zero and unquoted.
            ModelRatedCannotArm: a model claiming ``severity_actual``.
            ValueError: an unattributed claim.
        """
        if not 0 <= self.value <= MAX_SEVERITY:
            raise SeverityOutOfRange(
                f"severity {self.value} from {self.attributed_to!r} is outside 0-{MAX_SEVERITY}; "
                f"mainline.event has three range CHECKs and would refuse the row"
            )
        if not self.attributed_to.strip():
            raise ValueError(
                "a severity claim must name what is behind it: the coded field, the "
                "regulator scheme and code, the person id, or the call profile"
            )
        if self.value > 0 and self.span is None:
            raise SeverityWithoutSpan(
                f"severity {self.value} from {self.attributed_to!r} carries no source "
                f"span. Migration 0033: a severity with no span is a number somebody "
                f"typed, and this one will be read aloud when a permit is refused."
            )
        if self.basis is Basis.MODEL_RATED and self.dimension == "actual":
            raise ModelRatedCannotArm(
                f"{self.attributed_to!r} is a model and claimed severity_actual="
                f"{self.value}. A model may state what could reasonably have happened; "
                f"what did happen comes from a coded field, a regulator classification, "
                f"or a signed human (ARCHITECTURE.md §8.4)."
            )

    @classmethod
    def coded(
        cls,
        value: int,
        *,
        field_name: str,
        dimension: Dimension = "actual",
        span: VerbatimSpan | None = None,
        evidence: Mapping[str, str] | None = None,
    ) -> SeverityClaim:
        """Build a claim from a consequence code out of the buyer's own system."""
        return cls(
            basis=Basis.CODED_FIELD,
            value=value,
            dimension=dimension,
            attributed_to=field_name,
            span=span,
            evidence=_pairs(evidence),
        )

    @classmethod
    def regulator(
        cls,
        value: int,
        *,
        scheme: str,
        code: str,
        dimension: Dimension = "actual",
        span: VerbatimSpan | None = None,
        evidence: Mapping[str, str] | None = None,
    ) -> SeverityClaim:
        """Build a claim from a statutory classification: a notifiable-incident class."""
        return cls(
            basis=Basis.REGULATOR_CLASS,
            value=value,
            dimension=dimension,
            attributed_to=f"{scheme}:{code}",
            span=span,
            evidence=_pairs({**dict(evidence or {}), "scheme": scheme, "code": code}),
        )

    @classmethod
    def human(
        cls,
        value: int,
        *,
        person_id: str,
        credential_id: str,
        dimension: Dimension = "actual",
        span: VerbatimSpan | None = None,
        evidence: Mapping[str, str] | None = None,
    ) -> SeverityClaim:
        """Build a claim from a named human's rating, with the credential it is bound to.

        Raises:
            UnsignedPromotion: no credential. An unsigned human rating is an opinion in a
                column the gate reads.
        """
        if not credential_id.strip():
            raise UnsignedPromotion(
                f"human rating by {person_id!r} carries no signing credential; "
                f"mainline.signing_credential is what binds a name to a key, and a "
                f"severity nobody signed cannot be attributed under oath"
            )
        return cls(
            basis=Basis.HUMAN_RATED,
            value=value,
            dimension=dimension,
            attributed_to=person_id,
            span=span,
            evidence=_pairs(
                {**dict(evidence or {}), "person_id": person_id, "credential_id": credential_id}
            ),
        )

    @classmethod
    def model(
        cls,
        value: int,
        *,
        profile_id: str,
        prompt_version: str,
        output_sha256: str,
        span: VerbatimSpan | None = None,
        evidence: Mapping[str, str] | None = None,
    ) -> SeverityClaim:
        """Build a capped claim from a model's reading: always ``potential``, never ``actual``.

        The replayability quad travels on the claim (§8.2), so the row that records the
        downgrade names the exact call whose reading was capped.
        """
        return cls(
            basis=Basis.MODEL_RATED,
            value=value,
            dimension="potential",
            attributed_to=profile_id,
            span=span,
            evidence=_pairs(
                {
                    **dict(evidence or {}),
                    "profile_id": profile_id,
                    "prompt_version": prompt_version,
                    "output_sha256": output_sha256,
                }
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        """Ledger-shaped form: everything a reader needs to disagree with the claim."""
        return {
            "basis": str(self.basis),
            "value": self.value,
            "dimension": self.dimension,
            "attributed_to": self.attributed_to,
            "span": list(self.span.pair) if self.span else None,
            "quote_sha256": self.span.sha256 if self.span else None,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class Downgrade:
    """One claim the ceiling refused to admit in full. Evidence, not an exception.

    Attributes:
        claim: the capped claim, with its attribution and its span.
        proposed: what the claim said.
        admitted: what the gate took, which is :data:`MODEL_GATE_CEILING` or less.
        reason: the ``silence_ledger`` reason vocabulary term.
    """

    claim: SeverityClaim
    proposed: int
    admitted: int
    reason: str = "cap_exceeded"

    def to_mapping(self) -> dict[str, Any]:
        """Ledger-shaped form."""
        return {
            "reason": self.reason,
            "proposed": self.proposed,
            "admitted": self.admitted,
            "ceiling": MODEL_GATE_CEILING,
            "arming_threshold": ARMING_THRESHOLD,
            "claim": self.claim.to_mapping(),
        }


@dataclass(frozen=True, slots=True)
class SeverityAppraisal:
    """The three severities, the basis, the span, and what was refused on the way.

    :meth:`to_columns` is the only way :mod:`mainline_archivist.emit` obtains severity
    values, so there is no path from a hand-typed integer to ``mainline.event``.
    """

    severity_actual: int
    severity_potential: int
    severity_gate: int
    severity_basis: Basis
    severity_span: tuple[int, int] | None
    determined_by: SeverityClaim
    claims: tuple[SeverityClaim, ...]
    downgrades: tuple[Downgrade, ...]

    @property
    def arms_gate(self) -> bool:
        """Whether this severity reaches the blocking band."""
        return self.severity_gate >= ARMING_THRESHOLD

    @property
    def disagrees(self) -> bool:
        """Whether the machine's reading and the gate's answer differ.

        The quotable case: ``severity_potential = 5`` with ``severity_gate = 3``.
        """
        return bool(self.downgrades) or self.severity_potential > self.severity_gate

    def to_columns(self) -> dict[str, Any]:
        """Return the ``mainline.event`` severity columns, exactly as the DDL names them."""
        return {
            "severity_actual": self.severity_actual,
            "severity_potential": self.severity_potential,
            "severity_gate": self.severity_gate,
            "severity_basis": str(self.severity_basis),
            "severity_span": list(self.severity_span) if self.severity_span else None,
        }

    def to_mapping(self) -> dict[str, Any]:
        """Full ledger form, including every claim and every downgrade."""
        return {
            **self.to_columns(),
            "determined_by": self.determined_by.to_mapping(),
            "claims": [claim.to_mapping() for claim in self.claims],
            "downgrades": [downgrade.to_mapping() for downgrade in self.downgrades],
            "model_gate_ceiling": MODEL_GATE_CEILING,
        }


def appraise(claims: Sequence[SeverityClaim]) -> SeverityAppraisal:
    """Reduce a set of claims to the three severities and one basis.

    The arithmetic, in full:

    * ``severity_actual`` — the maximum over **admitted** claims (coded, regulator,
      signed human). A ``model_rated`` claim cannot participate: it is refused at
      construction for even having ``dimension='actual'``.
    * ``severity_potential`` — the maximum over every claim, in either dimension, and at
      least ``severity_actual``. This is where the model's reading is recorded in full,
      uncapped, exactly as it was made.
    * ``severity_gate`` — ``max(admitted_max, min(model_max, MODEL_GATE_CEILING))``.
    * ``severity_basis`` — the basis of the claim that *determined* the gate. Ties resolve
      towards the stronger basis in ``SEVERITY_BASIS_VOCABULARY`` order, so an event that
      a coded field and a model both rate 3 is ``coded_field``: the gate value is the
      coded field's, and attributing it to the model would understate the record.

    No CHECK ties ``severity_gate`` to the other two on the table, and this function does
    not invent one — 0033 explains why at length: ``severity_gate >= severity_potential``
    would make the row that matters most unrepresentable.

    Raises:
        SeverityWithoutBasis: the claim set is empty.
        ModelRatedCannotArm: the result would be ``model_rated`` at or above the arming
            threshold. Unreachable given the ceiling; kept because an assertion that can
            only fire on a bug in this file is exactly where the last line of defence
            belongs.
    """
    if not claims:
        raise SeverityWithoutBasis(
            "appraise() was given no severity claims. mainline.event.severity_basis is "
            "NOT NULL over a closed vocabulary, so an empty claim set would have to "
            "invent one, and an invented 'coded_field' zero is indistinguishable "
            "downstream from a real one."
        )

    admitted = [claim for claim in claims if claim.basis.admitted]
    modelled = [claim for claim in claims if not claim.basis.admitted]

    actual = max((claim.value for claim in admitted if claim.dimension == "actual"), default=0)
    potential = max([claim.value for claim in claims] + [actual])

    admitted_max = max((claim.value for claim in admitted), default=0)
    model_max = max((claim.value for claim in modelled), default=0)
    model_contribution = min(model_max, MODEL_GATE_CEILING)
    gate = max(actual, admitted_max, model_contribution)

    determined_by = _determining_claim(claims, gate=gate, model_contribution=model_contribution)
    downgrades = tuple(
        Downgrade(claim=claim, proposed=claim.value, admitted=min(claim.value, MODEL_GATE_CEILING))
        for claim in modelled
        if claim.value > MODEL_GATE_CEILING
    )

    if determined_by.basis is Basis.MODEL_RATED and gate >= ARMING_THRESHOLD:
        raise ModelRatedCannotArm(
            f"appraisal produced severity_gate={gate} on basis 'model_rated', which "
            f"CHECK model_cannot_arm refuses (mainline.event, migration 0033). The "
            f"ceiling arithmetic in this module makes that unreachable, so this is a "
            f"defect in appraise(), not in the caller."
        )

    return SeverityAppraisal(
        severity_actual=actual,
        severity_potential=potential,
        severity_gate=gate,
        severity_basis=determined_by.basis,
        severity_span=determined_by.span.pair if determined_by.span else None,
        determined_by=determined_by,
        claims=tuple(claims),
        downgrades=downgrades,
    )


def promote(
    claim: SeverityClaim,
    *,
    person_id: str,
    credential_id: str,
    span: VerbatimSpan | None = None,
) -> SeverityClaim:
    """Convert a model rating into a signed human rating.

    0033: a model rating is *"allowed to be promoted by a person who puts their name on
    it"*. The promoted claim keeps the model's evidence — profile, prompt version, output
    digest — beside the promoter's identity, so the record says *this human adopted this
    machine reading* rather than pretending the machine was never involved.

    Args:
        claim: the ``model_rated`` claim being adopted.
        person_id: the adopting person.
        credential_id: their ``mainline.signing_credential``.
        span: the promoter's own span, when they cite a different passage. Defaults to
            the model's.

    Raises:
        UnsignedPromotion: no person, or no credential.
        ValueError: the claim is not ``model_rated`` — promoting a coded field is not a
            thing, and silently returning it unchanged would hide a caller's confusion.
    """
    if claim.basis is not Basis.MODEL_RATED:
        raise ValueError(
            f"promote() adopts a model_rated claim; {claim.attributed_to!r} is "
            f"{claim.basis}. A coded field and a regulator classification are already "
            f"admitted, and a human rating already carries a name."
        )
    if not person_id.strip() or not credential_id.strip():
        raise UnsignedPromotion(
            f"promotion of {claim.attributed_to!r}'s rating needs a person id and a "
            f"signing-credential id. A promotion nobody signed is the original problem "
            f"with a different severity_basis string."
        )
    return SeverityClaim.human(
        claim.value,
        person_id=person_id,
        credential_id=credential_id,
        dimension=claim.dimension,
        span=span or claim.span,
        evidence={**dict(claim.evidence), "promoted_from": str(Basis.MODEL_RATED)},
    )


def downgrade_silence_rows(
    appraisal: SeverityAppraisal,
    *,
    site_id: str,
    subject_kind: str,
    subject_id: str,
    policy_version: str | None = None,
) -> tuple[Any, ...]:
    """Render every capped claim as a ``silence_ledger`` row. I13: silence is logged.

    ``source='severity_downgrade'`` and ``reason='cap_exceeded'`` are both in the CHECK
    vocabularies ``mainline_agentkit.refusal`` transcribes from ARCHITECTURE.md §5.7, and
    :class:`~mainline_agentkit.refusal.SilenceRow` validates them at construction, so a
    vocabulary drift fails here rather than at the database.

    **This package cannot write these rows.** ``GRANTS.yaml`` gives ``INSERT`` on
    ``mainline_meas.silence_ledger`` to ``agent_recaller`` only. The rows are returned for
    a caller that holds the grant; see the README's *Grants I do not hold*.

    Returns:
        A tuple of ``SilenceRow``, one per downgrade, in claim order. Typed ``Any`` at the
        boundary because the row class belongs to agentkit and re-declaring it here would
        be a second definition of one wire shape.
    """
    from mainline_agentkit.refusal import SilenceRow

    return tuple(
        SilenceRow(
            site_id=site_id,
            source="severity_downgrade",
            reason=downgrade.reason,
            subject_kind=subject_kind,
            subject_id=subject_id,
            severity=downgrade.admitted,
            score=float(downgrade.proposed),
            threshold=float(MODEL_GATE_CEILING),
            arithmetic=downgrade.to_mapping(),
            policy_version=policy_version,
        )
        for downgrade in appraisal.downgrades
    )


def _determining_claim(
    claims: Sequence[SeverityClaim], *, gate: int, model_contribution: int
) -> SeverityClaim:
    """Return the claim the gate value came from, preferring the stronger basis.

    An admitted claim whose value equals the gate wins outright. Only when no admitted
    claim reaches the gate is the value the model's contribution, and then the strongest
    model claim is named — capped or not, it is the reading that produced the number.
    """
    ranked = sorted(claims, key=_basis_rank)
    for claim in ranked:
        if claim.basis.admitted and claim.value == gate:
            return claim
    if model_contribution == gate:
        for claim in ranked:
            if not claim.basis.admitted and min(claim.value, MODEL_GATE_CEILING) == gate:
                return claim
    # Every claim is below the gate only if the gate is 0 and every claim is 0, in which
    # case the strongest basis present is the honest attribution for a zero.
    return ranked[0]


def _basis_rank(claim: SeverityClaim) -> tuple[int, int]:
    """Sort key: strongest basis first, then highest value."""
    return (SEVERITY_BASIS_VOCABULARY.index(str(claim.basis)), -claim.value)


def _pairs(mapping: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    """Freeze a mapping into sorted pairs so a claim stays hashable and comparable."""
    if not mapping:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in mapping.items()))
