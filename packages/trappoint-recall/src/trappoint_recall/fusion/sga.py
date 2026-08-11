# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Severity-Graded Admission: severity lowers the evidence bar, and never touches the score.

The distinction this module exists to preserve is one sentence long and is the difference
between a defensible gate and a rigged one:

> We did not claim these were more similar. We required less evidence before raising a fatal
> precedent.

A system that multiplies a similarity by severity has *changed what it claims about the
world* — it now asserts a stronger resemblance than it measured, and every downstream number
inherits the lie, including the calibrated probability shown to a supervisor and quoted in a
deposition. A system that lowers ``tau`` has changed only its own decision rule, in a
direction it can name and defend. So ``p_relevant`` is computed with no knowledge of
severity at all (severity has no slot in
:data:`~trappoint_recall.fusion.featurespec.FEATURE_SPEC`), and severity enters exactly once
— here — as the choice of threshold. ``tests/unit/recall_fusion`` asserts both halves: that
no expression in this package multiplies by severity, and that changing a candidate's
severity changes its ``tau_applied`` and nothing else.

Three further rulings are implemented here rather than described:

**The cap is scoped to probabilistic origins (recall lead D2).** At most three blocking
checks of origin ``recall_probabilistic``. Channels A (deterministic ancestry) and B (bonded
severity-5) are uncapped, because a cap that could suppress a bonded fatality would
contradict ``bonded_fatalities_all_blocking`` (MI16) and make the gate unsatisfiable on a
fonds with four fatalities. Overflow becomes advisory *and* a
``silence_ledger(reason='cap_exceeded')`` row carrying its score and its tau.

**tau is composed, not chosen (recall lead D9).** ``tau = max(LTT_tau, precision_floor_tau)``.
Learn-then-Test gives the recall-side bound; the precision floor is derived from the nuisance
ceiling. Taking the maximum means a recall-driven threshold can never breach the nuisance
ceiling — *"a rule that breaches the ceiling is rejected rather than tuned"* stops being a
promise and becomes arithmetic.

**The conformal guarantee assumes exchangeability, and says so in the record.** Conformal
risk control is distribution-free but not shift-free, and safety corpora drift: new
equipment, new commodities, a new regulator taxonomy. :data:`EXCHANGEABILITY_ASSUMPTION` is
carried in every :class:`LttResult` and :class:`ComposedTau` so the assumption travels with
the number instead of living in a paper nobody reads.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from trappoint_recall.eval.measurement import DEFAULT_CONFIDENCE, wilson_interval

__all__ = [
    "BLOCKING_CAP_PROBABILISTIC",
    "CANONICAL_SILENCE_REASONS",
    "DEFAULT_NUISANCE_CEILING",
    "DEFAULT_TAU",
    "EXCHANGEABILITY_ASSUMPTION",
    "PROBABILISTIC_ORIGIN",
    "SEVERITY_LEVELS",
    "UNCAPPED_ORIGINS",
    "AdmissionCandidate",
    "AdmissionRefused",
    "AdmissionResult",
    "AdmittedCheck",
    "ComposedTau",
    "LttResult",
    "PrecisionFloorResult",
    "SilenceRecord",
    "TauTable",
    "admit",
    "compose_tau",
    "compose_tau_table",
    "default_tau_grid",
    "hoeffding_bentkus_pvalue",
    "learn_then_test_tau",
    "precision_floor_tau",
]

SEVERITY_LEVELS: Final[tuple[int, ...]] = (1, 2, 3, 4, 5)

DEFAULT_TAU: Final[Mapping[int, float]] = {5: 0.35, 4: 0.45, 3: 0.60, 2: 0.75, 1: 0.85}
"""ARCHITECTURE 6.4's initial calibrated defaults. Monotone *downward* in severity: the more
serious the precedent, the less evidence is required before raising it. These are a starting
point for :func:`compose_tau_table`, not a setting — the shipped table is a calibration
artefact in a signed ``recall_policy`` row."""

BLOCKING_CAP_PROBABILISTIC: Final = 3
"""Hard cap on blocking checks of probabilistic origin, per permit. From the alarm-management
arithmetic: ~250 permits/week at ~4 minutes of supervisor attention per disposition."""

PROBABILISTIC_ORIGIN: Final = "recall_probabilistic"

UNCAPPED_ORIGINS: Final[frozenset[str]] = frozenset({"deterministic_ancestry", "bonded"})
"""Channels A and B. Graph truth and fatality bonds: admitted unconditionally, never capped,
never thresholded."""

_KNOWN_ORIGINS: Final[frozenset[str]] = UNCAPPED_ORIGINS | {PROBABILISTIC_ORIGIN, "lexical"}

COARSE_SWEEP_CHANNEL: Final = "C_sweep"
"""The 256-d unpartitioned sweep. Insurance against taxonomy induction error, and never
blocking unless severity is 5 (ARCHITECTURE 6.4)."""

CANONICAL_SILENCE_REASONS: Final[frozenset[str]] = frozenset(
    {
        "below_tau",
        "model_refusal",
        "dedup_sibling",
        "cap_exceeded",
        "truncated",
        "abstained",
        "bounded_negative",
        "unreachable",
    }
)
"""The closed ``mainline_meas.silence_ledger.reason`` vocabulary (ARCHITECTURE 5.7). Held
here as data so this package can refuse to emit a reason the database would reject."""

DEFAULT_NUISANCE_CEILING: Final = 0.03
"""Share of *routine* permits allowed to produce at least one probabilistic blocking check.
EEMUA 191 / ISA-18.2 translated to a permit budget (ARCHITECTURE 6.7)."""

EXCHANGEABILITY_ASSUMPTION: Final = (
    "Learn-then-Test / conformal risk control is distribution-free but assumes the "
    "calibration sample is exchangeable with the population the gate will see. Safety "
    "corpora drift - new equipment, new commodities, a re-induced taxonomy - so this is "
    "disciplined calibration under a stated assumption, not a guarantee that survives "
    "shift. Recalibrate on a schedule and record the calibration commit."
)

CapOrdering = Literal["severity_then_score", "score_only"]


class AdmissionRefused(ValueError):
    """An admission input that cannot be decided. Never silently coerced."""


# --------------------------------------------------------------------------------------
# The threshold table
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TauTable:
    """Severity-graded thresholds, validated to be monotone in the defensible direction.

    The validation is the point. A table where a higher severity carried a *higher* tau
    would be a system demanding more evidence before raising a fatality than before raising
    a near miss, and nothing downstream would notice.
    """

    thresholds: Mapping[int, float]
    policy_version: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = [level for level in SEVERITY_LEVELS if level not in self.thresholds]
        if missing:
            raise AdmissionRefused(
                f"tau table is missing severity level(s) {missing}. A missing level would be "
                "defaulted at admission time, which is a threshold nobody signed."
            )
        extra = sorted(set(self.thresholds) - set(SEVERITY_LEVELS))
        if extra:
            raise AdmissionRefused(f"tau table declares unknown severity level(s) {extra}")
        for level, value in self.thresholds.items():
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise AdmissionRefused(
                    f"tau for severity {level} is {value!r}; a threshold on a calibrated "
                    "probability must lie in [0, 1]"
                )
        for lower_severity, higher_severity in itertools.pairwise(SEVERITY_LEVELS):
            if self.thresholds[higher_severity] > self.thresholds[lower_severity]:
                raise AdmissionRefused(
                    f"tau({higher_severity}) = {self.thresholds[higher_severity]} exceeds "
                    f"tau({lower_severity}) = {self.thresholds[lower_severity]}. Severity "
                    "LOWERS the evidence bar; a table that raises it demands more proof "
                    "before a fatality than before a near miss."
                )

    def tau_for(self, severity: int) -> float:
        try:
            return self.thresholds[severity]
        except KeyError as exc:
            raise AdmissionRefused(
                f"severity {severity!r} is outside the modelled range {SEVERITY_LEVELS}"
            ) from exc

    def to_json(self) -> dict[str, Any]:
        return {
            "tau": {str(level): self.thresholds[level] for level in SEVERITY_LEVELS},
            "policy_version": self.policy_version,
            "rule": "severity lowers the evidence bar; it never inflates the score",
            "provenance": dict(self.provenance),
        }

    @classmethod
    def defaults(cls, policy_version: str = "") -> TauTable:
        return cls(thresholds=dict(DEFAULT_TAU), policy_version=policy_version)


# --------------------------------------------------------------------------------------
# Learn-then-Test / conformal threshold selection
# --------------------------------------------------------------------------------------


def _h1(observed: float, bound: float) -> float:
    """KL divergence between two Bernoullis, the exponent in the Hoeffding term."""
    if observed <= 0.0:
        return -math.log1p(-bound)
    if observed >= 1.0:  # pragma: no cover - guarded by the caller (observed < bound < 1)
        return math.inf
    return observed * math.log(observed / bound) + (1.0 - observed) * math.log(
        (1.0 - observed) / (1.0 - bound)
    )


def _log_binomial_pmf(k: int, n: int, p: float) -> float:
    if k < 0 or k > n:
        return -math.inf
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:  # pragma: no cover - alpha is validated to be strictly inside (0, 1)
        return 0.0 if k == n else -math.inf
    log_choose = math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    return log_choose + k * math.log(p) + (n - k) * math.log1p(-p)


def _binomial_cdf(k: int, n: int, p: float) -> float:
    """P(Bin(n, p) <= k), summed in log space so large n does not underflow to nonsense."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    terms = [_log_binomial_pmf(index, n, p) for index in range(k + 1)]
    finite = [value for value in terms if value > -math.inf]
    if not finite:  # pragma: no cover - only reachable for degenerate p
        return 0.0
    peak = max(finite)
    total = sum(math.exp(value - peak) for value in finite)
    return min(1.0, math.exp(peak) * total)


def hoeffding_bentkus_pvalue(risk_hat: float, n: int, alpha: float) -> float:
    """Compute the Hoeffding-Bentkus p-value for ``H0: R(lambda) > alpha``.

    Bates, Angelopoulos, Lei, Malik and Jordan (2021); used by Learn-then-Test
    (`arXiv:2208.02814 <https://arxiv.org/pdf/2208.02814>`_). Small ``p`` is evidence that
    the true risk is at or below ``alpha``.

    Args:
        risk_hat: Empirical risk in ``[0, 1]``.
        n: Number of calibration observations behind ``risk_hat``.
        alpha: The risk level being tested against.

    Raises:
        AdmissionRefused: on a non-finite risk, an empty sample, or an alpha outside (0, 1).
    """
    if n <= 0:
        raise AdmissionRefused("a p-value over an empty calibration sample is not a number")
    if not 0.0 <= risk_hat <= 1.0 or not math.isfinite(risk_hat):
        raise AdmissionRefused(f"empirical risk must lie in [0, 1], got {risk_hat!r}")
    if not 0.0 < alpha < 1.0:
        raise AdmissionRefused(f"alpha must lie strictly inside (0, 1), got {alpha!r}")
    if risk_hat >= alpha:
        return 1.0
    hoeffding = math.exp(-n * _h1(risk_hat, alpha))
    bentkus = math.e * _binomial_cdf(math.ceil(n * risk_hat), n, alpha)
    return min(1.0, hoeffding, bentkus)


def default_tau_grid(step: float = 0.01) -> tuple[float, ...]:
    """Build a fixed ascending grid on ``[0, 1]``.

    Fixed, and fixed *before* the run: an LTT grid chosen after seeing the risk curve is a
    multiple-comparisons problem wearing a guarantee's clothes.
    """
    if not 0.0 < step <= 0.5:
        raise AdmissionRefused(f"grid step must lie in (0, 0.5], got {step!r}")
    count = round(1.0 / step)
    return tuple(round(index * step, 10) for index in range(count + 1))


@dataclass(frozen=True, slots=True)
class LttResult:
    """The recall-side threshold, and everything needed to argue with it."""

    tau: float
    alpha: float
    delta: float
    n: int
    risk_at_tau: float
    p_value_at_tau: float
    certified: bool
    grid_step: float
    severity: int | None = None
    assumption: str = EXCHANGEABILITY_ASSUMPTION

    def to_json(self) -> dict[str, Any]:
        return {
            "method": "learn_then_test_fixed_sequence_hoeffding_bentkus",
            "tau": self.tau,
            "alpha": self.alpha,
            "delta": self.delta,
            "n": self.n,
            "risk_at_tau": self.risk_at_tau,
            "p_value_at_tau": self.p_value_at_tau,
            "certified": self.certified,
            "grid_step": self.grid_step,
            "severity": self.severity,
            "risk_definition": "share of true precursors whose calibrated p_relevant falls "
            "below tau, i.e. the miss rate the threshold would have produced",
            "assumption": self.assumption,
        }


def learn_then_test_tau(
    precursor_scores: Sequence[float],
    *,
    alpha: float,
    delta: float = 0.05,
    grid: Sequence[float] | None = None,
    severity: int | None = None,
) -> LttResult:
    """Select the largest threshold whose miss rate is certified at level ``alpha``.

    The risk is the miss rate: the share of *true* precursors (as adjudicated on a
    temporally-blocked calibration fold) whose calibrated ``p_relevant`` falls below the
    threshold. It is non-decreasing in the threshold, so a fixed-sequence test walking the
    grid upward and stopping at the first non-rejection controls the family-wise error rate
    without any correction term.

    Args:
        precursor_scores: Calibrated ``p_relevant`` for every known true precursor in the
            calibration fold.
        alpha: Tolerated miss rate.
        delta: Error probability for the guarantee. Rejection requires ``p <= delta``.
        grid: Ascending candidate thresholds. Defaults to :func:`default_tau_grid`.
        severity: Recorded on the result, for the per-severity table. Never multiplied by
            anything.

    Returns:
        An :class:`LttResult`. When no grid point is certified, ``tau`` is 0.0 and
        ``certified`` is False: the safe direction is to admit everything and let the
        precision floor and the cap absorb the noise, never to invent a threshold.

    Raises:
        AdmissionRefused: on an empty score list, a bad alpha or delta, or a non-ascending
            grid.
    """
    if not precursor_scores:
        raise AdmissionRefused(
            "Learn-then-Test needs at least one known precursor; a threshold certified on "
            "an empty sample is a certificate of nothing"
        )
    if not 0.0 < alpha < 1.0:
        raise AdmissionRefused(f"alpha must lie strictly inside (0, 1), got {alpha!r}")
    if not 0.0 < delta < 1.0:
        raise AdmissionRefused(f"delta must lie strictly inside (0, 1), got {delta!r}")
    for score in precursor_scores:
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise AdmissionRefused(
                f"precursor score {score!r} is not a calibrated probability; LTT runs on "
                "p_relevant, never on a raw fusion score"
            )
    candidates = tuple(grid) if grid is not None else default_tau_grid()
    if not candidates:
        raise AdmissionRefused("the tau grid is empty")
    for index in range(len(candidates) - 1):
        if not candidates[index] < candidates[index + 1]:
            raise AdmissionRefused(
                "the tau grid must be strictly ascending: fixed-sequence testing depends on "
                "the order, and a shuffled grid silently voids the guarantee"
            )

    n = len(precursor_scores)
    step = candidates[1] - candidates[0] if len(candidates) > 1 else 0.0
    best_tau = 0.0
    best_risk = 0.0
    best_p = 1.0
    certified = False

    for candidate in candidates:
        misses = sum(1 for score in precursor_scores if score < candidate)
        risk = misses / n
        p_value = 1.0 if risk >= alpha else hoeffding_bentkus_pvalue(risk, n, alpha)
        if p_value > delta:
            break
        best_tau = candidate
        best_risk = risk
        best_p = p_value
        certified = True

    if not certified:
        # Nothing on the grid clears the bound. Returning 0.0 admits everything: the miss
        # rate is minimised and the nuisance is left to the precision floor and the cap.
        # Returning the smallest *uncertified* grid point instead would be a threshold
        # wearing a guarantee it does not have.
        return LttResult(
            tau=0.0,
            alpha=alpha,
            delta=delta,
            n=n,
            risk_at_tau=0.0,
            p_value_at_tau=1.0,
            certified=False,
            grid_step=step,
            severity=severity,
        )

    return LttResult(
        tau=best_tau,
        alpha=alpha,
        delta=delta,
        n=n,
        risk_at_tau=best_risk,
        p_value_at_tau=best_p,
        certified=True,
        grid_step=step,
        severity=severity,
    )


@dataclass(frozen=True, slots=True)
class PrecisionFloorResult:
    """The nuisance-side threshold: the least selective tau the alarm budget can afford."""

    tau: float
    ceiling: float
    n_routine_permits: int
    nuisance_rate: float
    nuisance_upper: float
    feasible: bool
    confidence: float = DEFAULT_CONFIDENCE
    bounded: bool = True
    severity: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "method": "nuisance_ceiling_inversion",
            "tau": self.tau,
            "ceiling": self.ceiling,
            "n_routine_permits": self.n_routine_permits,
            "nuisance_rate": self.nuisance_rate,
            "nuisance_upper": self.nuisance_upper,
            "confidence": self.confidence,
            "bounded": self.bounded,
            "feasible": self.feasible,
            "severity": self.severity,
            "definition": "share of routine permits producing at least one probabilistic "
            "blocking check at this tau, measured on the uneventful-permit replay",
        }


def precision_floor_tau(
    routine_permit_max_scores: Sequence[float],
    *,
    ceiling: float = DEFAULT_NUISANCE_CEILING,
    grid: Sequence[float] | None = None,
    confidence: float = DEFAULT_CONFIDENCE,
    bounded: bool = True,
    severity: int | None = None,
) -> PrecisionFloorResult:
    """Invert the nuisance ceiling: the smallest tau the alarm budget tolerates.

    Args:
        routine_permit_max_scores: For each routine permit in the negative-control replay,
            the highest calibrated ``p_relevant`` any probabilistic candidate reached. A
            permit is a nuisance at tau exactly when this value is at or above tau.
        ceiling: Maximum tolerable nuisance rate.
        grid: Ascending candidate thresholds. Defaults to :func:`default_tau_grid`.
        confidence: Confidence for the Wilson bound.
        bounded: Compare the Wilson *upper* bound against the ceiling rather than the point
            estimate. A ceiling cleared only by a point estimate is a ceiling cleared by
            sampling luck.

    Returns:
        A :class:`PrecisionFloorResult`. When no grid point clears the ceiling,
        ``feasible`` is False and ``tau`` is 1.0 — the rule is rejected rather than tuned.

    Raises:
        AdmissionRefused: on an empty replay or a ceiling outside (0, 1].
    """
    if not routine_permit_max_scores:
        raise AdmissionRefused(
            "the nuisance ceiling cannot be inverted without a routine-permit replay; a "
            "precision floor derived from no negative control is not a floor"
        )
    if not 0.0 < ceiling <= 1.0:
        raise AdmissionRefused(f"the nuisance ceiling must lie in (0, 1], got {ceiling!r}")
    for score in routine_permit_max_scores:
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise AdmissionRefused(
                f"routine-permit score {score!r} is not a calibrated probability"
            )
    candidates = tuple(grid) if grid is not None else default_tau_grid()
    n = len(routine_permit_max_scores)

    for candidate in candidates:
        alarms = sum(1 for score in routine_permit_max_scores if score >= candidate)
        rate = alarms / n
        upper = wilson_interval(alarms, n, confidence=confidence)[1]
        measured = upper if bounded else rate
        if measured <= ceiling:
            return PrecisionFloorResult(
                tau=candidate,
                ceiling=ceiling,
                n_routine_permits=n,
                nuisance_rate=rate,
                nuisance_upper=upper,
                feasible=True,
                confidence=confidence,
                bounded=bounded,
                severity=severity,
            )

    alarms = sum(1 for score in routine_permit_max_scores if score >= 1.0)
    return PrecisionFloorResult(
        tau=1.0,
        ceiling=ceiling,
        n_routine_permits=n,
        nuisance_rate=alarms / n,
        nuisance_upper=wilson_interval(alarms, n, confidence=confidence)[1],
        feasible=False,
        confidence=confidence,
        bounded=bounded,
        severity=severity,
    )


@dataclass(frozen=True, slots=True)
class ComposedTau:
    """``tau = max(LTT_tau, precision_floor_tau)`` with both inputs kept in the record."""

    severity: int
    tau: float
    ltt_tau: float
    precision_floor_tau: float
    binding: Literal["learn_then_test", "precision_floor", "equal"]
    ltt_certified: bool
    floor_feasible: bool
    assumption: str = EXCHANGEABILITY_ASSUMPTION

    def to_json(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "tau": self.tau,
            "ltt_tau": self.ltt_tau,
            "precision_floor_tau": self.precision_floor_tau,
            "binding": self.binding,
            "ltt_certified": self.ltt_certified,
            "floor_feasible": self.floor_feasible,
            "rule": "tau = max(LTT_tau, precision_floor_tau): a recall-driven threshold can "
            "never breach the nuisance ceiling",
            "assumption": self.assumption,
        }


def compose_tau(ltt: LttResult, floor: PrecisionFloorResult, *, severity: int) -> ComposedTau:
    """Compose the two thresholds. The result is never below either input."""
    if severity not in SEVERITY_LEVELS:
        raise AdmissionRefused(f"severity {severity!r} is outside {SEVERITY_LEVELS}")
    tau = max(ltt.tau, floor.tau)
    if ltt.tau > floor.tau:
        binding: Literal["learn_then_test", "precision_floor", "equal"] = "learn_then_test"
    elif floor.tau > ltt.tau:
        binding = "precision_floor"
    else:
        binding = "equal"
    return ComposedTau(
        severity=severity,
        tau=tau,
        ltt_tau=ltt.tau,
        precision_floor_tau=floor.tau,
        binding=binding,
        ltt_certified=ltt.certified,
        floor_feasible=floor.feasible,
    )


def compose_tau_table(
    per_severity: Mapping[int, tuple[LttResult, PrecisionFloorResult]],
    *,
    policy_version: str = "",
) -> tuple[TauTable, tuple[ComposedTau, ...]]:
    """Compose a full severity-graded table, and validate its monotonicity.

    The monotonicity check in :class:`TauTable` is doing real work here: the two selectors
    are fitted independently per severity, and nothing about their arithmetic guarantees the
    composed table slopes the defensible way. If it does not, the table is refused rather
    than sorted into shape — a table that had to be reordered to be legal was measuring
    something other than what it claims.
    """
    composed = tuple(
        compose_tau(ltt, floor, severity=severity)
        for severity, (ltt, floor) in sorted(per_severity.items())
    )
    table = TauTable(
        thresholds={record.severity: record.tau for record in composed},
        policy_version=policy_version,
        provenance={
            "composition": [record.to_json() for record in composed],
            "assumption": EXCHANGEABILITY_ASSUMPTION,
        },
    )
    return table, composed


# --------------------------------------------------------------------------------------
# Admission
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AdmissionCandidate:
    """One scored candidate presented for admission."""

    doc_id: str
    p_relevant: float
    severity: int
    origin: str
    channel: str
    rank: int
    also_matched: tuple[str, ...] = ()
    coarse_only: bool = False

    def __post_init__(self) -> None:
        if not self.doc_id:
            raise AdmissionRefused("doc_id must be non-empty")
        if not math.isfinite(self.p_relevant) or not 0.0 <= self.p_relevant <= 1.0:
            raise AdmissionRefused(
                f"{self.doc_id}: p_relevant is {self.p_relevant!r}. Admission runs on a "
                "calibrated probability; a raw cosine here would be compared against a "
                "threshold that means something else entirely."
            )
        if self.severity not in SEVERITY_LEVELS:
            raise AdmissionRefused(f"{self.doc_id}: severity {self.severity!r} is outside 1..5")
        if self.origin not in _KNOWN_ORIGINS:
            raise AdmissionRefused(f"{self.doc_id}: unknown origin {self.origin!r}")
        if self.rank < 1:
            raise AdmissionRefused(f"{self.doc_id}: rank is 1-based, got {self.rank}")

    @property
    def is_probabilistic(self) -> bool:
        return self.origin == PROBABILISTIC_ORIGIN


@dataclass(frozen=True, slots=True)
class AdmittedCheck:
    """A candidate's admission decision, with the arithmetic that produced it."""

    doc_id: str
    outcome: Literal["blocking", "advisory", "silenced"]
    p_relevant: float
    tau_applied: float
    tau_consulted: bool
    severity: int
    origin: str
    channel: str
    also_matched: tuple[str, ...] = ()
    demotion: str = ""

    @property
    def margin(self) -> float:
        """Return how far above the bar this candidate cleared.

        Meaningless when tau was not consulted, which is why :attr:`tau_consulted` is a
        field and not an inference.
        """
        return self.p_relevant - self.tau_applied

    def to_json(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "outcome": self.outcome,
            "p_relevant": self.p_relevant,
            "tau_applied": self.tau_applied,
            "tau_consulted": self.tau_consulted,
            "severity": self.severity,
            "origin": self.origin,
            "channel": self.channel,
            "also_matched": list(self.also_matched),
            "demotion": self.demotion,
        }


@dataclass(frozen=True, slots=True)
class SilenceRecord:
    """A row the caller writes to ``mainline_meas.silence_ledger``.

    Constructed here rather than by the orchestrator so the score and the threshold that
    produced the silence travel with it. A silence ledger that records *that* something was
    withheld without recording *why* is a list, not a ledger.
    """

    subject_id: str
    reason: str
    severity: int
    score: float | None
    threshold: float | None
    arithmetic: Mapping[str, Any]
    source: str = "recall"

    def __post_init__(self) -> None:
        if self.reason not in CANONICAL_SILENCE_REASONS:
            raise AdmissionRefused(
                f"{self.reason!r} is outside the closed silence vocabulary "
                f"{sorted(CANONICAL_SILENCE_REASONS)}; the database would refuse the row"
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "reason": self.reason,
            "subject_kind": "event",
            "subject_id": self.subject_id,
            "severity": self.severity,
            "score": self.score,
            "threshold": self.threshold,
            "arithmetic": dict(self.arithmetic),
        }


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """The complete partition of an admission run."""

    blocking: tuple[AdmittedCheck, ...]
    advisory: tuple[AdmittedCheck, ...]
    silenced: tuple[AdmittedCheck, ...]
    silence_records: tuple[SilenceRecord, ...]
    tau_table: TauTable
    cap: int
    n_input: int

    def __post_init__(self) -> None:
        total = len(self.blocking) + len(self.advisory) + len(self.silenced)
        if total != self.n_input:
            raise AdmissionRefused(
                f"admission lost {self.n_input - total} candidate(s). Every candidate lands "
                "in exactly one of blocking, advisory or silenced; the conservation law "
                "candidates_conserved (MI17) is checked in the database and here."
            )

    @property
    def n_blocking_probabilistic(self) -> int:
        return sum(1 for check in self.blocking if check.origin == PROBABILISTIC_ORIGIN)

    def to_json(self) -> dict[str, Any]:
        return {
            "blocking": [check.to_json() for check in self.blocking],
            "advisory": [check.to_json() for check in self.advisory],
            "silenced": [check.to_json() for check in self.silenced],
            "silence_records": [record.to_json() for record in self.silence_records],
            "tau_table": self.tau_table.to_json(),
            "cap": self.cap,
            "n_input": self.n_input,
            "n_blocking": len(self.blocking),
            "n_blocking_probabilistic": self.n_blocking_probabilistic,
        }


def _cap_sort_key(
    check: AdmittedCheck, candidate: AdmissionCandidate, ordering: CapOrdering
) -> tuple[float, ...]:
    """Order the probabilistic queue for the cap.

    ``severity_then_score`` puts the graver precedent in front of the scarce three slots.
    Note what this is *not*: no score is altered, no probability is inflated, and the same
    candidate has the same ``p_relevant`` whatever its severity. Severity orders a queue; it
    never changes what the system claims about a resemblance. ``score_only`` is available
    for the ablation, so the choice is measurable rather than merely argued.
    """
    if ordering == "score_only":
        return (-check.p_relevant, float(candidate.rank))
    return (-float(candidate.severity), -check.p_relevant, float(candidate.rank))


def admit(
    candidates: Sequence[AdmissionCandidate],
    *,
    tau_table: TauTable,
    cap: int = BLOCKING_CAP_PROBABILISTIC,
    ordering: CapOrdering = "severity_then_score",
    policy_version: str = "",
) -> AdmissionResult:
    """Apply Severity-Graded Admission, the coarse-sweep rule and the probabilistic cap.

    The rules, in the order they fire:

    1. **Channels A and B are admitted unconditionally.** ``origin`` in
       :data:`UNCAPPED_ORIGINS` blocks with no threshold consulted and no cap applied. This
       is ``bonded_fatalities_all_blocking`` (MI16) expressed in code, and it is why the cap
       below is scoped to a single origin.
    2. **A coarse-sweep hit below severity 5 is advisory.** The 256-d unpartitioned sweep is
       insurance against taxonomy induction error, and its hits are too weak to block on
       their own (ARCHITECTURE 6.4). A ``bounded_negative`` silence row records the demotion.
    3. **Below tau is silence.** ``p_relevant < tau(severity)`` becomes ``silenced`` with a
       ``below_tau`` row carrying the score and the threshold, which is what makes Proof of
       Exhausted Recall possible at all.
    4. **At or above tau blocks, up to the cap.** Overflow past ``cap`` blocking checks of
       probabilistic origin becomes advisory with a ``cap_exceeded`` row.

    Raises:
        AdmissionRefused: on a duplicate candidate or a negative cap.
    """
    if cap < 0:
        raise AdmissionRefused(f"the blocking cap must be non-negative, got {cap}")
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.doc_id in seen:
            raise AdmissionRefused(
                f"{candidate.doc_id!r} presented twice for admission; a candidate admitted "
                "twice would break the conservation law and double-count a check"
            )
        seen.add(candidate.doc_id)

    blocking: list[AdmittedCheck] = []
    advisory: list[AdmittedCheck] = []
    silenced: list[AdmittedCheck] = []
    records: list[SilenceRecord] = []
    provisional: list[tuple[AdmittedCheck, AdmissionCandidate]] = []

    for candidate in candidates:
        tau = tau_table.tau_for(candidate.severity)

        if candidate.origin in UNCAPPED_ORIGINS:
            blocking.append(
                AdmittedCheck(
                    doc_id=candidate.doc_id,
                    outcome="blocking",
                    p_relevant=candidate.p_relevant,
                    tau_applied=0.0,
                    tau_consulted=False,
                    severity=candidate.severity,
                    origin=candidate.origin,
                    channel=candidate.channel,
                    also_matched=candidate.also_matched,
                )
            )
            continue

        if (
            candidate.channel == COARSE_SWEEP_CHANNEL or candidate.coarse_only
        ) and candidate.severity < 5:
            advisory.append(
                AdmittedCheck(
                    doc_id=candidate.doc_id,
                    outcome="advisory",
                    p_relevant=candidate.p_relevant,
                    tau_applied=tau,
                    tau_consulted=True,
                    severity=candidate.severity,
                    origin=candidate.origin,
                    channel=candidate.channel,
                    also_matched=candidate.also_matched,
                    demotion="coarse_sweep_below_severity_5",
                )
            )
            records.append(
                SilenceRecord(
                    subject_id=candidate.doc_id,
                    reason="bounded_negative",
                    severity=candidate.severity,
                    score=candidate.p_relevant,
                    threshold=tau,
                    arithmetic={
                        "rule": "a coarse-sweep hit is never blocking below severity 5; the "
                        "256-d sweep is unpartitioned insurance against taxonomy induction "
                        "error and is too weak to block on its own",
                        "channel": candidate.channel,
                        "policy_version": policy_version,
                    },
                )
            )
            continue

        if candidate.p_relevant < tau:
            silenced.append(
                AdmittedCheck(
                    doc_id=candidate.doc_id,
                    outcome="silenced",
                    p_relevant=candidate.p_relevant,
                    tau_applied=tau,
                    tau_consulted=True,
                    severity=candidate.severity,
                    origin=candidate.origin,
                    channel=candidate.channel,
                    also_matched=candidate.also_matched,
                    demotion="below_tau",
                )
            )
            records.append(
                SilenceRecord(
                    subject_id=candidate.doc_id,
                    reason="below_tau",
                    severity=candidate.severity,
                    score=candidate.p_relevant,
                    threshold=tau,
                    arithmetic={
                        "rule": "p_relevant < tau(severity)",
                        "tau_source": "severity-graded admission table",
                        "severity_effect": "severity selected the threshold; it did not "
                        "alter the score",
                        "policy_version": policy_version,
                    },
                )
            )
            continue

        provisional.append(
            (
                AdmittedCheck(
                    doc_id=candidate.doc_id,
                    outcome="blocking",
                    p_relevant=candidate.p_relevant,
                    tau_applied=tau,
                    tau_consulted=True,
                    severity=candidate.severity,
                    origin=candidate.origin,
                    channel=candidate.channel,
                    also_matched=candidate.also_matched,
                ),
                candidate,
            )
        )

    probabilistic = [pair for pair in provisional if pair[1].is_probabilistic]
    other = [pair for pair in provisional if not pair[1].is_probabilistic]
    probabilistic.sort(key=lambda pair: _cap_sort_key(pair[0], pair[1], ordering))

    for position, (check, _queued) in enumerate(probabilistic):
        if position < cap:
            blocking.append(check)
            continue
        advisory.append(
            AdmittedCheck(
                doc_id=check.doc_id,
                outcome="advisory",
                p_relevant=check.p_relevant,
                tau_applied=check.tau_applied,
                tau_consulted=True,
                severity=check.severity,
                origin=check.origin,
                channel=check.channel,
                also_matched=check.also_matched,
                demotion="cap_exceeded",
            )
        )
        records.append(
            SilenceRecord(
                subject_id=check.doc_id,
                reason="cap_exceeded",
                severity=check.severity,
                score=check.p_relevant,
                threshold=check.tau_applied,
                arithmetic={
                    "rule": f"at most {cap} blocking checks of origin "
                    f"{PROBABILISTIC_ORIGIN!r} per permit",
                    "cap": cap,
                    "position_in_queue": position + 1,
                    "ordering": ordering,
                    "uncapped_origins": sorted(UNCAPPED_ORIGINS),
                    "policy_version": policy_version,
                },
            )
        )

    for check, _ in other:
        blocking.append(check)

    return AdmissionResult(
        blocking=tuple(blocking),
        advisory=tuple(advisory),
        silenced=tuple(silenced),
        silence_records=tuple(records),
        tau_table=tau_table,
        cap=cap,
        n_input=len(candidates),
    )
