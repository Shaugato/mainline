# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Frozen shared types for the MAINLINE **algorithms** domain.

This module is a verbatim transcription of ``docs/leads/algorithms.md`` §4.
It is written **once, by worker W1 (`canon-anchors`)**, and imported by every
other worker in the domain.  **No other worker may edit this file.**  A worker
that needs a new shared type defines it inside its own subpackage.

Three rules hold everywhere in here:

* **Frozen, slotted dataclasses.**  Identity-bearing fields carry no defaults —
  a default on an identity field is a silent decision, and this domain does not
  make silent decisions.
* **No model SDK, ever** (decision D1).  ``mainline_domain`` must never import
  ``boto3``/``anthropic``/``strands``.  The LLM path lives in the physically
  separate package ``mainline-delta-oracle`` and reaches this domain only
  through the :class:`DeltaOracle` ``Protocol`` and the :class:`OracleVerdict`
  dataclass below.  The lattice decides a state transition, and P7 forbids any
  component that can decide a state transition from reaching a model.
* **No third-party import at all.**  ``contracts`` is stdlib-only so that the
  offline verifier and the migration runner can depend on it without dragging
  in ``scipy``/``numpy``.

Boundary note carried from §4: :data:`ResidueReason` is exactly the five values
already in the ``mainline.identity_residue`` ``CHECK``.  There is no sixth;
``cat_confidence='opaque'`` maps to ``'opaque_control'``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Final, Literal, Protocol
from uuid import UUID

__all__ = [
    "IDENTITY_ANCHOR_CLASSES",
    "RULE_IDS",
    "CAT",
    "Anchor",
    "AnchorClass",
    "AnchorSet",
    "AssignmentEdge",
    "CATResult",
    "CBMAccount",
    "Candidate",
    "CanonResult",
    "CatConfidence",
    "ControlDelta",
    "DeltaBasis",
    "DeltaOracle",
    "DeltaVerdict",
    "DeltaWitness",
    "OcrRepair",
    "OracleRequest",
    "OracleVerdict",
    "PrefixArmRunner",
    "Quantity",
    "Reference",
    "RelationKind",
    "ResidueReason",
    "ResidueRow",
    "RuleId",
    "Segment",
    "Stage",
    "force",
]


# --------------------------------------------------------------------------- #
# control_delta — mirrors the SQL enum mainline.control_delta                  #
# --------------------------------------------------------------------------- #


class ControlDelta(Enum):
    """Mirrors ``CREATE TYPE mainline.control_delta AS ENUM (...)`` exactly.

    The member *values* are the SQL labels and are the only thing ever written
    to the database.  Member order here matches the SQL declaration order.
    """

    INTRODUCE = "introduce"
    STRENGTHEN = "strengthen"
    RESTATE = "restate"
    WEAKEN = "weaken"
    REMOVE = "remove"


_FORCE: Final[Mapping[str, int]] = {
    "introduce": 0,
    "strengthen": 0,
    "restate": 0,
    "weaken": 2,
    "remove": 3,
}


def force(d: ControlDelta) -> int:
    """Return the *force* of a delta: how loudly the gate must react.

    ``introduce``/``restate``/``strengthen`` = 0, ``weaken`` = 2, ``remove`` = 3.

    Force exists so that the ABSTENTION RATCHET (W5) can state its guarantee as
    arithmetic: the resolution of Path A and Path B is **monotone upward** in
    this codomain, so no oracle output can ever lower the Path-A verdict.  It is
    deliberately not a total order over "severity" of an edit — it is the order
    in which the *database* must refuse.
    """
    return _FORCE[d.value]


# --------------------------------------------------------------------------- #
# CANONHOLD — canonicalisation result                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class OcrRepair:
    """One confusable repair, applied **only inside a numeric token class**.

    ``start``/``end`` are a half-open span into ``CanonResult.canon_text``.
    Repairs are 1:1 character substitutions, so ``end - start == len(before)
    == len(after)`` always holds.
    """

    start: int
    end: int
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class Segment:
    """A content-defined (or layout-defined) segment of ``canon_text``.

    ``start``/``end`` are a half-open span into ``CanonResult.canon_text``;
    ``sha256`` is the SHA-256 of the segment's UTF-8 bytes (no domain prefix —
    the domain-separated digest is ``CanonResult.canon_sha256``, which covers
    the whole clause).
    """

    start: int
    end: int
    sha256: bytes


@dataclass(frozen=True, slots=True)
class CanonResult:
    """Output of ``canon(v)``.  Every offset in the system is into ``canon_text``.

    ``furniture_spans`` is the exception and is documented as such: those are
    half-open spans into the **raw input**, because the furniture they name has
    by definition been removed from ``canon_text``.

    ``numbering_prefix`` is the raw excised prefix (e.g. ``'7.3.2 (b)   '``);
    ``printed_label`` is its normalised form (``'7.3.2(b)'``) and is the
    Akoma-Ntoso ``@eId`` analogue — stored, never identity.
    """

    canon_text: str
    canon_sha256: bytes
    canon_version: int
    numbering_prefix: str | None
    printed_label: str | None
    furniture_spans: tuple[tuple[int, int], ...]
    ocr_repairs: tuple[OcrRepair, ...]
    segments: tuple[Segment, ...]


# --------------------------------------------------------------------------- #
# ANCHORLOCK — hard anchors                                                    #
# --------------------------------------------------------------------------- #


class AnchorClass(Enum):
    """The seven model-free hard-anchor classes (clause-identity research §5)."""

    EQUIPMENT_TAG = "equipment_tag"
    SETPOINT = "setpoint"
    REGULATORY_CITATION = "regulatory_citation"
    CAS = "cas"
    NAMED_ROLE = "named_role"
    INSTRUMENT_LOOP = "instrument_loop"
    ISOLATION_POINT_ID = "isolation_point_id"


IDENTITY_ANCHOR_CLASSES: Final[frozenset[AnchorClass]] = frozenset(
    {
        AnchorClass.EQUIPMENT_TAG,
        AnchorClass.ISOLATION_POINT_ID,
        AnchorClass.CAS,
        AnchorClass.REGULATORY_CITATION,
        AnchorClass.INSTRUMENT_LOOP,
    }
)
"""Classes over which anchor *conflict* is decided.

``setpoint`` is deliberately **not** an identity class: a moved setpoint is the
lattice's job (rule R2), not the matcher's.  If ``setpoint`` were an identity
class, every legitimate setpoint change would present as a non-match and the
weakening it represents would be hidden behind an ``unmatched`` residue row
instead of being adjudicated as the weakening it is.
"""


@dataclass(frozen=True, slots=True)
class Anchor:
    """One extracted anchor.

    ``raw`` is the surface form as it appears in ``canon_text``; ``norm`` is the
    **identity form** (what equality is decided on); ``span`` is a half-open
    span into ``canon_text``.
    """

    cls: AnchorClass
    raw: str
    norm: str
    span: tuple[int, int]


@dataclass(frozen=True, slots=True)
class AnchorSet:
    """A set of anchors extracted from one clause version."""

    items: frozenset[Anchor]

    def by_class(self) -> Mapping[AnchorClass, frozenset[Anchor]]:
        """Group the anchors by class.  **All seven keys are always present**
        (possibly mapping to an empty set), so callers never need ``.get``."""
        grouped: dict[AnchorClass, set[Anchor]] = {c: set() for c in AnchorClass}
        for anchor in self.items:
            grouped[anchor.cls].add(anchor)
        return {c: frozenset(v) for c, v in grouped.items()}

    def norms(self, cls: AnchorClass) -> frozenset[str]:
        """The normalised identity forms of one class."""
        return frozenset(a.norm for a in self.items if a.cls is cls)

    def identity_norms(self) -> frozenset[str]:
        """Normalised forms across :data:`IDENTITY_ANCHOR_CLASSES` only."""
        return frozenset(a.norm for a in self.items if a.cls in IDENTITY_ANCHOR_CLASSES)

    def conflicting_classes(self, other: AnchorSet) -> frozenset[AnchorClass]:
        """Identity classes in which the two sets *conflict*.

        A class conflicts when **both** sides carry at least one anchor of that
        class and they share **none**.  Both-sides-non-empty is what makes this
        a conflict rather than a drop: an anchor that simply disappears is
        handled by :mod:`mainline_domain.anchors.drop`, which raises a
        ``weaken`` candidate on its own.  Requiring disjointness (rather than
        inequality) means a descendant that *adds* ``P-101B`` alongside
        ``P-101A`` is still the same clause — an extension, not a swap.
        """
        conflicts: set[AnchorClass] = set()
        for cls in IDENTITY_ANCHOR_CLASSES:
            mine = self.norms(cls)
            theirs = other.norms(cls)
            if mine and theirs and not (mine & theirs):
                conflicts.add(cls)
        return frozenset(conflicts)

    def compatible_with(self, other: AnchorSet) -> bool:
        """``False`` iff the two sets conflict in any identity class.

        This is the **veto over cosine**: a semantic candidate scoring 0.97 with
        a different equipment tag is rejected, not accepted.  The relation is
        symmetric and reflexive; it is *not* transitive, and nothing in the
        cascade may assume that it is.
        """
        return not self.conflicting_classes(other)


# --------------------------------------------------------------------------- #
# Quantities and the Control Assertion Tuple                                   #
# --------------------------------------------------------------------------- #

Reference = Literal["absolute", "gauge", "delta", "none"]


@dataclass(frozen=True, slots=True)
class Quantity:
    """A magnitude with a unit, a dimension, and an explicit pressure reference.

    ``reference`` is mandatory and load-bearing (decision D5): ``50 psig`` is
    ``344.7 kPa_g`` and is **not** ``446 kPa(a)``.  Silently treating a gauge
    reading as absolute flips a ``safe_direction`` comparison, which is a
    weakening that reads as a strengthening.  The unit algebra that consumes
    this type (worker W2) raises rather than converting between references.
    """

    value: Decimal
    unit: str
    dimension: str
    reference: Reference


@dataclass(frozen=True, slots=True)
class CAT:
    """Control Assertion Tuple — identity axis 2 (``cat_key`` is its hash)."""

    actor: str
    deontic: str
    action: str
    object_class: str
    hazard_energy: str
    parameter: str
    comparator: str
    value: Quantity | None
    conditions: tuple[str, ...]
    exceptions: tuple[str, ...]
    verification: tuple[str, ...]
    frequency: Quantity | None
    coverage_quantifier: str


CatConfidence = Literal["ok", "low", "opaque"]


@dataclass(frozen=True, slots=True)
class CATResult:
    """A CAT extraction attempt.

    ``confidence='opaque'`` is not a failure to be retried — it is a product
    state.  Any edit to an opaque clause with severity ≥ 4 ancestry defaults to
    ``weaken`` (risk R-A3), and the residue reason is ``'opaque_control'``.
    """

    cat: CAT | None
    confidence: CatConfidence
    evidence_spans: tuple[tuple[int, int], ...]
    extractor_version: str


# --------------------------------------------------------------------------- #
# DELTALATTICE                                                                 #
# --------------------------------------------------------------------------- #

RuleId = Literal[
    "R1_DEONTIC",
    "R2_SETPOINT",
    "R3_COMPARATOR",
    "R4_EXCEPTION",
    "R5_QUANTIFIER",
    "R6_VERIFICATION",
    "R7_FREQUENCY",
    "R8_ANCHOR",
    "R9_COVERAGE",
]

RULE_IDS: Final[tuple[RuleId, ...]] = (
    "R1_DEONTIC",
    "R2_SETPOINT",
    "R3_COMPARATOR",
    "R4_EXCEPTION",
    "R5_QUANTIFIER",
    "R6_VERIFICATION",
    "R7_FREQUENCY",
    "R8_ANCHOR",
    "R9_COVERAGE",
)

DeltaBasis = Literal["lattice", "lattice+model", "abstain_to_weaken", "human"]


@dataclass(frozen=True, slots=True)
class DeltaWitness:
    """One element of the minimal unsatisfiable subset behind a verdict.

    Decision D8: a ``weaken``/``remove`` with ``delta_basis='lattice'`` whose
    witness rows were not written earlier in the same transaction is **refused**
    by ``fn_delta_witness_guard`` (P0001).  An unexplainable weaken verdict does
    not get to exist.
    """

    rule_id: RuleId
    field: str
    from_repr: str
    to_repr: str
    note: str


@dataclass(frozen=True, slots=True)
class DeltaVerdict:
    """The delta of record for one clause version, with its explanation."""

    delta: ControlDelta
    basis: DeltaBasis
    witnesses: tuple[DeltaWitness, ...]
    minimal: bool


# --------------------------------------------------------------------------- #
# The oracle boundary (Path B lives in a DIFFERENT distribution)               #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class OracleRequest:
    """What the domain hands across the model boundary.

    §4 names this type without a body; W1 fixes the minimal body here so the
    :class:`DeltaOracle` protocol is typeable.  It carries *text and tuples
    only* — no identifiers, no site context, no commit ids — because the thing
    on the other side of this boundary is a model and P7 keeps it starved of
    anything it could use to decide a state transition.
    """

    ancestor_text: str
    descendant_text: str
    ancestor_cat: CAT | None
    descendant_cat: CAT | None
    parameter_hint: str | None
    prompt_version: str


@dataclass(frozen=True, slots=True)
class OracleVerdict:
    """Path B's output.  It can raise the force of a verdict; it can never lower it."""

    label: ControlDelta
    confidence: float
    rationale: str
    cited_spans: tuple[tuple[int, int], ...]
    model_id: str
    prompt_version: str
    abstained: bool


class DeltaOracle(Protocol):
    """The only shape of a model this domain will speak to."""

    def classify(self, req: OracleRequest) -> OracleVerdict: ...


# --------------------------------------------------------------------------- #
# The identity cascade                                                         #
# --------------------------------------------------------------------------- #

Stage = Literal["S0", "S1", "S2", "S3", "S4", "S5", "S6"]


@dataclass(frozen=True, slots=True)
class Candidate:
    """A cascade candidate.

    Not hashable in practice: ``features`` is a ``Mapping``.  Callers key
    candidates by ``(ancestor_clause_uuid, ancestor_commit)``.
    """

    ancestor_clause_uuid: UUID
    ancestor_commit: bytes
    stage: Stage
    score: float
    features: Mapping[str, float]


class PrefixArmRunner(Protocol):
    """One **fully constrained** C-SPANN arm.

    A vector index in CockroachDB is used only when every prefix column is
    constrained to a specific value, so an ancestry walk cannot be
    ``activity_root IN (...)``.  It is N single-value ANN queries ``UNION
    ALL``'d and re-ranked in the application; this protocol is one of the N.
    """

    def ann(
        self,
        site_id: UUID,
        activity_root: str,
        q: Sequence[float],
        k: int,
    ) -> Sequence[Candidate]: ...


RelationKind = Literal["matched", "split", "merge", "absent"]


@dataclass(frozen=True, slots=True)
class AssignmentEdge:
    """One decided ancestor→descendant relation.

    ``descendant_clause_uuid`` is ``None`` exactly when ``relation='absent'``.
    ``margin`` is the distance to the second-best assignment: degeneracy is
    *detected*, never broken (decision D4).
    """

    ancestor_clause_uuid: UUID
    descendant_clause_uuid: UUID | None
    relation: RelationKind
    stage: Stage
    score: float
    margin: float


ResidueReason = Literal[
    "unmatched",
    "ambiguous",
    "anchor_drop",
    "opaque_control",
    "citation_unresolved",
]


@dataclass(frozen=True, slots=True)
class ResidueRow:
    """A blocking row.  ``features`` is the arithmetic, kept."""

    ancestor_clause_uuid: UUID
    reason: ResidueReason
    match_score: float | None
    features: Mapping[str, float]


# --------------------------------------------------------------------------- #
# CONSERVATION OF BLAME MASS                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CBMAccount:
    """The conservation identity, in Python, for the projector to *propose*.

    The database recomputes every one of these counters from
    ``clause_blame_current``/``identity_assignment``/``identity_residue`` and
    overwrites whatever the inserter supplied (``fn_cbm_account_guard``), so
    this object is never trusted — it exists so the projector can be tested
    without a cluster.
    """

    site_id: UUID
    commit_id: bytes
    inherited: int
    carried: int
    split_carried: int
    merge_carried: int
    residue_open: int
    residue_disposed: int

    def balanced(self) -> bool:
        """``inherited = carried + split + merge + residue_open + residue_disposed``.

        Mirrors the ``STORED`` generated column and ``CONSTRAINT cbm_balances``.
        Python agreeing is worth nothing on its own; the point is that the two
        can be compared, and a disagreement is a bug in the projector that the
        database already refused.
        """
        return self.inherited == (
            self.carried
            + self.split_carried
            + self.merge_carried
            + self.residue_open
            + self.residue_disposed
        )
