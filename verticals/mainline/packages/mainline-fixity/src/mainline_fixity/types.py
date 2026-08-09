# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The rows the fixity patrol reads and the rows it proposes.

Every type here mirrors a table in ARCHITECTURE.md §5.8 exactly, field for field,
in the order the DDL declares them. Where the DDL carries a `CHECK`, the Python
type carries the same predicate in ``__post_init__`` — not because Python
agreeing is worth anything on its own, but because a caller then learns which of
their inputs was wrong instead of reading a constraint name out of a `23514`.

Three rules hold everywhere in here.

**Frozen and slotted.** A finding that can be edited after it is built is a
finding whose contents at write time are not the contents that were reasoned
about.

**No floats in an evidentiary payload.** ``confidence`` is an integer in
milli-units and setpoints are :class:`~decimal.Decimal`, because ``0.1 + 0.2``
appearing in a document a regulator reads is not a rounding problem, it is a
credibility problem. The single conversion to the DDL's ``FLOAT8`` happens once,
at the SQL parameter boundary in :mod:`mainline_fixity.emit`, and nowhere else.

**Aware datetimes only.** A naive timestamp in a record about *when a control was
true in the plant* is an unanswerable question in cross-examination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from mainline_domain.cat.preimage import canonical_decimal
from mainline_domain.contracts import CAT, ControlDelta, Quantity

from .errors import UndeterminedWouldBlock, UnstartedPatrol

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "BLOCKING_SEVERITY_FLOOR",
    "FIXITY_CLASSES",
    "SOURCE_KINDS",
    "WARRANT_CLASSES",
    "BisectOutcome",
    "ClauseBinding",
    "DriftFinding",
    "ErrorBar",
    "FindingStatus",
    "FixityClass",
    "GateClass",
    "ObservedAssertion",
    "PatrolAccount",
    "PatrolRun",
    "PatrolScope",
    "SourceKind",
    "TimeWitness",
    "WarrantClass",
    "cat_json",
    "require_aware",
]

#: ``observed_assertion.source_kind``'s `CHECK`, verbatim (§5.8).
SOURCE_KINDS: Final[tuple[str, ...]] = (
    "dcs_export",
    "madb",
    "historian",
    "cmms",
    "inspection",
    "bypass",
    "lms",
    "isolation_register",
)
SourceKind = Literal[
    "dcs_export",
    "madb",
    "historian",
    "cmms",
    "inspection",
    "bypass",
    "lms",
    "isolation_register",
]

#: L0 as-designed · L1 as-configured · L2 as-operated. The patrol class and the
#: finding class are the same vocabulary because a finding inherits the depth of
#: the scan that found it.
FIXITY_CLASSES: Final[tuple[str, ...]] = ("L0", "L1", "L2")
FixityClass = Literal["L0", "L1", "L2"]

GateClass = Literal["blocking", "advisory"]
FindingStatus = Literal["open", "disposed", "withdrawn", "superseded"]

#: ``CONSTRAINT gate_derived CHECK (gate_class <> 'blocking' OR severity_inherited >= 4)``.
BLOCKING_SEVERITY_FLOOR: Final[int] = 4

#: ``discordance_warrant.warrant_class``'s `CHECK` (§5.8, A6 added by S27).
WARRANT_CLASSES: Final[tuple[str, ...]] = ("A1", "A2", "A3", "A4", "A5", "A6")
WarrantClass = Literal["A1", "A2", "A3", "A4", "A5", "A6"]

#: SHA-256 is 32 bytes. Named so a length check reads as an assertion about the
#: digest algorithm rather than as an unexplained integer in a validator.
_SHA256_BYTES: Final[int] = 32

#: Confidences are carried as integers in milli-units so no float ever reaches an
#: evidentiary payload. 1000 milli = 1.0.
_MILLI_FULL: Final[int] = 1000

#: Only the source kinds whose values pass through lossy archival compression.
#: An inspection record or an isolation register is a discrete assertion by a
#: person; a historian tag is a corridor. Only the second needs an error bar.
_CORRIDOR_SOURCES: Final[frozenset[str]] = frozenset({"historian", "dcs_export"})


def require_aware(value: datetime, what: str) -> datetime:
    """Return ``value`` if it carries a timezone, else raise.

    A naive datetime in an evidentiary payload cannot be defended: it means
    "some time, in a zone the writer did not record", and the whole point of
    :class:`TimeWitness` is that two clocks from two administrative domains can
    be compared.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{what} is a naive datetime ({value!r}). Every timestamp in a fixity record "
            f"must carry a timezone: the SECOND CLOCK compares witnesses across "
            f"administrative domains and cannot compare a time with no zone"
        )
    return value


def _quantity_json(quantity: Quantity | None) -> dict[str, str] | None:
    """Render a :class:`Quantity` as float-free JSON."""
    if quantity is None:
        return None
    return {
        "value": canonical_decimal(quantity.value),
        "unit": quantity.unit,
        "dimension": quantity.dimension,
        "reference": quantity.reference,
    }


def cat_json(cat: CAT | None) -> dict[str, Any] | None:
    """Render a CAT for the ``documented_cat`` / ``observed_cat`` JSONB columns.

    Field order follows :class:`~mainline_domain.contracts.CAT` and numbers go
    through :func:`~mainline_domain.cat.preimage.canonical_decimal`, so the JSON
    a reviewer reads has one spelling per value and contains no float. This is a
    *rendering*, not an identity: identity is
    :func:`~mainline_domain.cat.preimage.cat_key`, and nothing here should be
    hashed as though it were.
    """
    if cat is None:
        return None
    return {
        "actor": cat.actor,
        "deontic": cat.deontic,
        "action": cat.action,
        "object_class": cat.object_class,
        "hazard_energy": cat.hazard_energy,
        "parameter": cat.parameter,
        "comparator": cat.comparator,
        "value": _quantity_json(cat.value),
        "conditions": list(cat.conditions),
        "exceptions": list(cat.exceptions),
        "verification": list(cat.verification),
        "frequency": _quantity_json(cat.frequency),
        "coverage_quantifier": cat.coverage_quantifier,
    }


@dataclass(frozen=True, slots=True)
class ErrorBar:
    """A historian tag's exception and compression deviations.

    ``exc_dev`` is the deviation applied when the value left the collector;
    ``comp_dev`` is the one applied when it entered the archive. They compose in
    **series**, so :meth:`corridor` sums them rather than root-sum-squaring them.
    Treating them as independent errors would produce a narrower corridor and a
    more confident finding, which is the wrong direction to be wrong in.

    ``unit`` is carried so the corridor cannot be silently compared against a
    setpoint in another unit; :mod:`mainline_fixity.errorbar` refuses that.
    """

    exc_dev: Decimal
    comp_dev: Decimal
    unit: str

    def __post_init__(self) -> None:
        """Refuse a negative or non-finite deviation."""
        for name, value in (("exc_dev", self.exc_dev), ("comp_dev", self.comp_dev)):
            if not value.is_finite() or value < 0:
                raise ValueError(
                    f"{name} must be a finite, non-negative Decimal; got {value!r}. "
                    f"A negative deviation would widen a corridor in the safe direction"
                )

    def corridor(self) -> Decimal:
        """Half-width of the band inside which an excursion is indistinguishable."""
        return self.exc_dev + self.comp_dev

    def to_json(self) -> dict[str, str]:
        """Render for the ``observed_assertion.err_bar`` JSONB column."""
        return {
            "exc_dev": canonical_decimal(self.exc_dev),
            "comp_dev": canonical_decimal(self.comp_dev),
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class ObservedAssertion:
    """One row of ``mainline.observed_assertion`` — what the plant says it is doing.

    ``source_ref`` is the S3 ``versionId`` of the export and is immutable. It is
    the only thing tying this row to an Object-Locked object, so it is required
    even when the export is a fixture: a fixture with an empty provenance field
    trains everyone to accept an empty provenance field.
    """

    obs_id: UUID
    site_id: UUID
    source_kind: SourceKind
    source_ref: str
    asset_tag: str
    observed_cat: CAT | None
    effective_at: datetime
    leaf_hash: bytes
    err_bar: ErrorBar | None = None
    ingested_at: datetime | None = None

    def __post_init__(self) -> None:
        """Hold the DDL's `CHECK` and the corridor rule at construction."""
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(
                f"source_kind {self.source_kind!r} is not one of {SOURCE_KINDS}. "
                f"We never speak OPC UA to a control system: everything arrives as a "
                f"periodic one-way export, and the kind names which one"
            )
        if not self.source_ref:
            raise ValueError(
                "source_ref is empty. It is the S3 versionId of the export and the only "
                "link between this row and an Object-Locked object"
            )
        if len(self.leaf_hash) != _SHA256_BYTES:
            raise ValueError(
                f"leaf_hash must be {_SHA256_BYTES} bytes of SHA-256; got {len(self.leaf_hash)}"
            )
        require_aware(self.effective_at, "observed_assertion.effective_at")
        if self.ingested_at is not None:
            require_aware(self.ingested_at, "observed_assertion.ingested_at")

    @property
    def needs_error_bar(self) -> bool:
        """True when this source kind's values are compression-corridor vertices."""
        return self.source_kind in _CORRIDOR_SOURCES


@dataclass(frozen=True, slots=True)
class ClauseBinding:
    """One row of ``mainline.clause_binding`` — clause ⇄ plant.

    §5.8 calls this "the expensive part; SME-reviewed", and ``bind_kind``
    records how expensive: ``explicit`` is a person naming the tag in the clause,
    ``hard_anchor`` is the anchor extractor finding it, ``proposed`` is neither
    and must not be patrolled as though it were a fact.
    """

    clause_uuid: UUID
    asset_tag: str
    site_id: UUID
    bind_kind: Literal["explicit", "hard_anchor", "proposed"]
    bound_by: str
    confidence_milli: int

    def __post_init__(self) -> None:
        """Refuse a confidence outside 0…1000 milli-units."""
        if not 0 <= self.confidence_milli <= _MILLI_FULL:
            raise ValueError(
                f"confidence_milli must be 0…{_MILLI_FULL}; got {self.confidence_milli}. "
                f"Confidence is carried in milli-units so no float reaches an "
                f"evidentiary payload"
            )

    @property
    def patrollable(self) -> bool:
        """A ``proposed`` binding is a hypothesis and is counted, never checked."""
        return self.bind_kind in ("explicit", "hard_anchor")


@dataclass(frozen=True, slots=True)
class PatrolScope:
    """What one scheduled occurrence was asked to cover.

    ``occurrence_ts`` is the scheduler's occurrence, not ``now()``. EventBridge
    Scheduler is at-least-once, and ``UNIQUE (site_id, schedule_id,
    occurrence_ts)`` is what makes a redelivery a no-op rather than a second run
    with a second set of findings.
    """

    site_id: UUID
    patrol_class: FixityClass
    schedule_id: str
    occurrence_ts: datetime
    scope_pred: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Hold the class `CHECK` and the aware-timestamp rule."""
        if self.patrol_class not in FIXITY_CLASSES:
            raise ValueError(f"patrol_class {self.patrol_class!r} is not one of {FIXITY_CLASSES}")
        if not self.schedule_id:
            raise ValueError("schedule_id is empty; it is half of the idempotency key")
        require_aware(self.occurrence_ts, "patrol_scope.occurrence_ts")


@dataclass(frozen=True, slots=True)
class PatrolAccount:
    """The patrol's conservation law: ``in_scope = checked + not_checked``.

    This is the fixity analogue of L3 (``candidates = blocking + advisory +
    silenced + deduped``). It exists so that *"the patrol found no drift"* is a
    bounded statement about a stated denominator rather than an impression.
    """

    n_in_scope: int
    n_checked: int
    n_not_checked: int

    def __post_init__(self) -> None:
        """Refuse a negative count; balance is checked separately and explicitly."""
        for name, value in (
            ("n_in_scope", self.n_in_scope),
            ("n_checked", self.n_checked),
            ("n_not_checked", self.n_not_checked),
        ):
            if value < 0:
                raise ValueError(f"{name} is negative ({value})")

    def balanced(self) -> bool:
        """``n_in_scope == n_checked + n_not_checked``, exactly."""
        return self.n_in_scope == self.n_checked + self.n_not_checked


@dataclass(frozen=True, slots=True)
class BisectOutcome:
    """Where a bisect stopped, and whether it stopped at an answer.

    ``culprit`` is populated **only** when the search converged on a single
    element that was actually probed. If it terminated against a skipped region
    the answer is the pair ``(lo, hi)`` and ``culprit`` is ``None``. §5.8:
    *fabricating a named culprit from an unobservable interval is how this
    product gets a customer sued.*
    """

    culprit: UUID | None
    lo: UUID | None
    hi: UUID | None
    probes: int
    skipped: int

    def __post_init__(self) -> None:
        """Refuse an outcome that is both a culprit and a range."""
        if self.culprit is not None and (self.lo is not None or self.hi is not None):
            raise ValueError(
                "a bisect outcome is either a culprit or a range, never both: a named "
                "culprit beside a range invites a reader to believe the culprit and "
                "ignore the width"
            )

    @property
    def is_range(self) -> bool:
        """True when the honest answer is an interval rather than an element."""
        return self.culprit is None


@dataclass(frozen=True, slots=True)
class DriftFinding:
    """One row of ``mainline.drift_finding`` — a `control_delta` authored by the plant.

    Two fields are **not** decided here and must not be: ``severity_inherited``
    is projected from ``clause_blame_current`` and ``gate_class`` is derived from
    it. :mod:`mainline_fixity.emit` supplies a placeholder that is a pure function
    of ``(direction, undetermined)`` and of nothing else; the trigger overwrites
    both. That is the same discipline CF-07 tests on ``blocking_check``.
    """

    finding_id: UUID
    run_id: UUID
    site_id: UUID
    clause_uuid: UUID
    fixity_class: FixityClass
    documented_cat: CAT | None
    observed_cat: CAT | None
    direction: ControlDelta | None
    undetermined: bool
    confidence_milli: int
    asset_tag: str | None = None
    bisect: BisectOutcome | None = None
    status: FindingStatus = "open"

    def __post_init__(self) -> None:
        """Hold MI21 and the DDL's `CHECK`s at construction."""
        if self.fixity_class not in FIXITY_CLASSES:
            raise ValueError(f"fixity_class {self.fixity_class!r} is not one of {FIXITY_CLASSES}")
        if not 0 <= self.confidence_milli <= _MILLI_FULL:
            raise ValueError(
                f"confidence_milli must be 0…{_MILLI_FULL}; got {self.confidence_milli}"
            )
        # Deliberately NOT `self.would_block`: that property already answers False
        # for an undetermined finding, so asking it here would make the check
        # vacuous — which is what the first version of this line did. The condition
        # is the contradiction itself: a direction the gate reacts to, carried on a
        # finding that admits it cannot tell.
        if self.undetermined and self.direction in (ControlDelta.WEAKEN, ControlDelta.REMOVE):
            raise UndeterminedWouldBlock(str(self.clause_uuid))
        if self.documented_cat is None and self.observed_cat is None:
            raise ValueError(
                "a drift finding with neither a documented nor an observed control "
                "describes nothing. An ABSENCE finding carries documented_cat and a "
                "NULL observed_cat"
            )

    @property
    def is_absence(self) -> bool:
        """True when the expected evidence is missing — warrant class A6."""
        return self.observed_cat is None

    @property
    def would_block(self) -> bool:
        """Report whether this finding would block at a projected severity of 4 or more.

        This is the patrol's **proposal**, not the gate's answer. The gate's
        answer is ``gate_class`` after the projection trigger has run, and it can
        only ever be weaker than this.
        """
        if self.undetermined or self.direction is None:
            return False
        return self.direction in (ControlDelta.WEAKEN, ControlDelta.REMOVE)


@dataclass(frozen=True, slots=True)
class PatrolRun:
    """One completed row of ``mainline.patrol_run``.

    ``finished_at`` is mandatory and that is a deliberate consequence of the
    grant matrix: ``agent_patroller`` holds ``INSERT`` on ``patrol_run`` and no
    ``UPDATE``, so an in-flight run is **unrepresentable** under this role. A
    patrol that crashes writes no row, the occurrence is therefore not marked
    done, and at-least-once redelivery re-runs it. That is the correct behaviour
    and it falls out of the grant rather than out of a retry policy.
    """

    run_id: UUID
    scope: PatrolScope
    account: PatrolAccount
    as_of_hlc: Decimal
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        """Refuse an unbalanced account and a run whose clock disagrees with itself."""
        require_aware(self.started_at, "patrol_run.started_at")
        require_aware(self.finished_at, "patrol_run.finished_at")
        if self.finished_at < self.started_at:
            raise UnstartedPatrol(self.started_at.isoformat(), self.finished_at.isoformat())
        if not self.account.balanced():
            from .errors import PatrolAccountUnbalanced

            raise PatrolAccountUnbalanced(
                self.account.n_in_scope,
                self.account.n_checked,
                self.account.n_not_checked,
            )
        if not self.as_of_hlc.is_finite() or self.as_of_hlc <= 0:
            raise ValueError(
                f"as_of_hlc must be a positive finite DECIMAL HLC; got {self.as_of_hlc!r}. "
                f"It is the follower-read timestamp the scan actually used, and a run that "
                f"cannot say when it looked has not witnessed anything"
            )


@dataclass(frozen=True, slots=True)
class TimeWitness:
    """One row of ``mainline.time_witness`` — half of the SECOND CLOCK.

    A fixity patrol is a ``t_ops`` witness: it reports when a control was true in
    the plant according to a system the document's author does not administer.
    §5.8 requires ≥ 2 witnesses from **different administrative domains**, one of
    which is not administered by the party with the motive, so this row is worth
    writing even when the patrol finds nothing.
    """

    subject_kind: str
    subject_id: UUID
    kind: Literal["t_led", "t_doc", "t_ops", "t_anchor"]
    t: datetime
    source_system: str
    ingest_hlc: Decimal
    source_sig: bytes | None = None

    def __post_init__(self) -> None:
        """Hold the aware-timestamp rule and refuse an unnamed source system."""
        require_aware(self.t, "time_witness.t")
        if not self.source_system:
            raise ValueError(
                "source_system is empty. A witness whose administrative domain is unnamed "
                "cannot be shown to be a DIFFERENT domain from the other witness, which is "
                "the entire content of the SECOND CLOCK"
            )
