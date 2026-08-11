# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The contract every retrieval implementation is judged against.

This module defines *what the harness is allowed to know* about a retriever. It
deliberately implements no retrieval, no embedding, no SQL and no model call: the
harness must be able to score an implementation it did not write and cannot inspect.

Two protocols, and the difference matters
------------------------------------------
:class:`RetrievalBackend` is the minimum: given a permit, return scored candidates.
:class:`ConservingBackend` additionally publishes the run counters that
``mainline_meas.recall_run`` would carry. The silence conservation law (L3) compares
the *declared* counters against the *enumerated* candidates, which is only a real
check if the two come from different places. A backend that cannot publish counters
makes the law unverifiable, and unverifiable is a failure, not a pass.

What the harness trusts, and what it does not
----------------------------------------------
The harness trusts a backend's ``outcome`` and ``p_relevant`` because those are the
decisions under evaluation. It does **not** trust a backend's claim about which
severity-5 events were bonded to the permit: that is corpus ground truth
(:attr:`~trappoint_recall.eval.corpus.EvalQuery.bonded_sev5`), and MI16 is checked
against the corpus. Projections are enforced, never trusted — the same rule the
kernel applies to a trigger applies here to a metric.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast, runtime_checkable

from trappoint_recall.eval.corpus import EvalQuery

__all__ = [
    "BLOCKING_CAP_PROBABILISTIC",
    "Channel",
    "ConservingBackend",
    "NullBackend",
    "Origin",
    "Outcome",
    "QueryResult",
    "RetrievalBackend",
    "RunTally",
    "ScoredCandidate",
    "declared_tally_of",
]

Outcome = Literal["blocking", "advisory", "silenced", "deduped"]
"""The exact partition of ``mainline_meas.recall_candidate.outcome`` (ARCHITECTURE 5.7)."""

Channel = Literal["A", "B", "C", "C_sweep", "D"]
"""A: deterministic ancestry. B: bonded severity-5. C: prefix-constrained ANN.
C_sweep: 256-d coarse sweep. D: lexical BM25."""

Origin = Literal["deterministic_ancestry", "bonded", "recall_probabilistic", "lexical"]
"""``recall_probabilistic`` is the only origin the cap and P@block apply to (lead D2)."""

BLOCKING_CAP_PROBABILISTIC = 3
"""Hard cap on blocking checks of origin ``recall_probabilistic``. Channels A and B are
uncapped, because a cap that could suppress a bonded fatality would contradict MI16."""

_BLOCKING_ELIGIBLE_ORIGINS: frozenset[str] = frozenset(
    {"deterministic_ancestry", "bonded", "recall_probabilistic", "lexical"}
)


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """One retrieved event, with the decision the retriever made about it.

    Attributes:
        doc_id: Event identifier, matched against the qrels.
        rank: 1-based position in the score-sorted candidate set.
        p_relevant: Calibrated probability of relevance. A raw cosine must never reach
            a human, so the harness scores whatever the backend calibrated.
        tau_applied: The severity-graded admission threshold this candidate was tested
            against. Recorded so a report can show the arithmetic, not just the verdict.
        outcome: Which cell of the conservation partition this candidate landed in.
        severity: Severity of the retrieved event, 1..5.
        channel: Which retrieval channel produced it.
        origin: Coarser classification used by the cap and by ``P@block``.
        features: Optional per-candidate diagnostics (rrf score, bm25 score, ...).
    """

    doc_id: str
    rank: int
    p_relevant: float
    tau_applied: float
    outcome: Outcome
    severity: int
    channel: Channel
    origin: Origin
    features: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError(f"{self.doc_id}: rank is 1-based, got {self.rank}")
        if not (0.0 <= self.p_relevant <= 1.0):
            raise ValueError(
                f"{self.doc_id}: p_relevant must be a calibrated probability in [0, 1], "
                f"got {self.p_relevant}. If this is a raw cosine, calibrate it first."
            )
        if not (0.0 <= self.tau_applied <= 1.0):
            raise ValueError(f"{self.doc_id}: tau_applied must be in [0, 1]")
        if not (1 <= self.severity <= 5):
            raise ValueError(f"{self.doc_id}: severity must be 1..5, got {self.severity}")
        if self.origin not in _BLOCKING_ELIGIBLE_ORIGINS:
            raise ValueError(f"{self.doc_id}: unknown origin {self.origin!r}")

    @property
    def is_blocking(self) -> bool:
        return self.outcome == "blocking"

    @property
    def is_probabilistic(self) -> bool:
        return self.origin == "recall_probabilistic"


@dataclass(frozen=True, slots=True)
class RunTally:
    """The counters ``mainline_meas.recall_run`` carries, as declared by the backend.

    Mirrors the two CHECK constraints exactly so the harness can assert offline what
    the database asserts online:

    * ``candidates_conserved``: n_candidates = blocking + advisory + silenced + deduped (MI17)
    * ``bonded_fatalities_all_blocking``: n_bonded_sev5_blocking = n_bonded_sev5 (MI16)
    """

    n_candidates: int
    n_blocking: int
    n_advisory: int
    n_silenced: int
    n_deduped: int
    n_bonded_sev5: int = 0
    n_bonded_sev5_blocking: int = 0
    arms_degraded: bool = False

    def __post_init__(self) -> None:
        for name in (
            "n_candidates",
            "n_blocking",
            "n_advisory",
            "n_silenced",
            "n_deduped",
            "n_bonded_sev5",
            "n_bonded_sev5_blocking",
        ):
            value: int = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(
                    f"{name} must be an int; the conservation law is exact integer "
                    "arithmetic and a float here would make it approximately true"
                )
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")

    @property
    def partition_sum(self) -> int:
        return self.n_blocking + self.n_advisory + self.n_silenced + self.n_deduped

    @property
    def conserved(self) -> bool:
        """MI17 / conservation law L3, exact integer arithmetic."""
        return self.n_candidates == self.partition_sum

    @property
    def bonded_conserved(self) -> bool:
        """MI16 as declared. Still cross-checked against corpus truth by the harness."""
        return self.n_bonded_sev5_blocking == self.n_bonded_sev5

    def to_dict(self) -> dict[str, object]:
        return {
            "n_candidates": self.n_candidates,
            "n_blocking": self.n_blocking,
            "n_advisory": self.n_advisory,
            "n_silenced": self.n_silenced,
            "n_deduped": self.n_deduped,
            "n_bonded_sev5": self.n_bonded_sev5,
            "n_bonded_sev5_blocking": self.n_bonded_sev5_blocking,
            "arms_degraded": self.arms_degraded,
            "conserved": self.conserved,
            "bonded_conserved": self.bonded_conserved,
        }

    @classmethod
    def enumerate_from(
        cls, candidates: Sequence[ScoredCandidate], *, arms_degraded: bool = False
    ) -> RunTally:
        """Derive a tally by counting candidates. Used as the *independent* side of L3."""
        counts = {"blocking": 0, "advisory": 0, "silenced": 0, "deduped": 0}
        bonded = 0
        bonded_blocking = 0
        for c in candidates:
            counts[c.outcome] += 1
            if c.severity == 5 and c.origin == "bonded":
                bonded += 1
                if c.is_blocking:
                    bonded_blocking += 1
        return cls(
            n_candidates=len(candidates),
            n_blocking=counts["blocking"],
            n_advisory=counts["advisory"],
            n_silenced=counts["silenced"],
            n_deduped=counts["deduped"],
            n_bonded_sev5=bonded,
            n_bonded_sev5_blocking=bonded_blocking,
            arms_degraded=arms_degraded,
        )


@dataclass(frozen=True, slots=True)
class QueryResult:
    """What one backend returned for one permit, plus the counters it declared."""

    query: EvalQuery
    candidates: tuple[ScoredCandidate, ...]
    declared_tally: RunTally | None
    latency_ms: float | None = None
    backend_name: str = ""

    @property
    def enumerated_tally(self) -> RunTally:
        return RunTally.enumerate_from(self.candidates)

    @property
    def blocking(self) -> tuple[ScoredCandidate, ...]:
        return tuple(c for c in self.candidates if c.is_blocking)

    @property
    def probabilistic_blocking(self) -> tuple[ScoredCandidate, ...]:
        return tuple(c for c in self.candidates if c.is_blocking and c.is_probabilistic)

    def ranked_doc_ids(self) -> tuple[str, ...]:
        """Candidates in ascending rank order, deduplicated by first appearance."""
        seen: set[str] = set()
        ordered: list[str] = []
        for c in sorted(self.candidates, key=lambda x: x.rank):
            if c.doc_id in seen:
                continue
            seen.add(c.doc_id)
            ordered.append(c.doc_id)
        return tuple(ordered)


@runtime_checkable
class RetrievalBackend(Protocol):
    """The minimum a retrieval implementation must offer the harness."""

    name: str

    async def retrieve(self, query: EvalQuery, k: int) -> list[ScoredCandidate]:
        """Return up to ``k`` scored candidates for ``query``, decisions included.

        Implementations must honour the query's time wall themselves; the harness
        cannot enforce it inside a backend it did not write, and says so in the report.
        """
        ...


@runtime_checkable
class ConservingBackend(RetrievalBackend, Protocol):
    """A backend that also publishes its run counters, so L3 can be checked."""

    async def declared_tally(self, query: EvalQuery) -> RunTally:
        """Counters for the run that produced the last :meth:`retrieve` for ``query``."""
        ...


async def declared_tally_of(backend: RetrievalBackend, query: EvalQuery) -> RunTally | None:
    """Fetch the declared tally if the backend publishes one, else ``None``.

    ``None`` is propagated rather than substituted. Deriving the declared counters from
    the enumerated candidates would make the conservation law tautologically true, which
    is the one thing it must never be.
    """
    fetch = getattr(backend, "declared_tally", None)
    if fetch is None:
        return None
    typed = cast(Callable[[EvalQuery], Awaitable[RunTally]], fetch)
    return await typed(query)


class NullBackend:
    """A complete, honest backend that retrieves nothing.

    This is not a stub and not a mock. It implements the full contract, it declares its
    counters truthfully, and every one of those counters is zero. Its purpose is to make
    the G4-alpha suite **red for a substantive reason on day one**: a system that never
    blocks has a nuisance rate of zero, a mean of zero blocking checks per permit and a
    conservation law that holds over nothing at all. If those three facts were allowed to
    read as passes, the suite would certify silence. They are not, and it does not.
    """

    name = "null"

    def __init__(self, *, name: str = "null") -> None:
        self.name = name

    async def retrieve(self, query: EvalQuery, k: int) -> list[ScoredCandidate]:
        del query, k
        return []

    async def declared_tally(self, query: EvalQuery) -> RunTally:
        del query
        return RunTally(
            n_candidates=0,
            n_blocking=0,
            n_advisory=0,
            n_silenced=0,
            n_deduped=0,
            n_bonded_sev5=0,
            n_bonded_sev5_blocking=0,
            arms_degraded=False,
        )
