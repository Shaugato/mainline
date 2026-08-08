# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""L3, the silence conservation law, enforced in code before anything is written.

``candidates_conserved`` (MI17) is a database ``CHECK``::

    n_candidates = n_blocking + n_advisory + n_silenced + n_deduped

and it will refuse a run row whose arithmetic does not hold. So why is the same law here?

**Because the conservation law must never be the first thing that notices.** A ``23514``
arriving at ``INSERT INTO recall_run`` says one integer disagrees with four others. It does
not say *which candidate went missing*, and by then the candidate is out of scope, the
retrieval has been discarded and the only available diagnosis is to run it again. Enforcing
here, over the rows themselves, means the failure names the event id and the stage that lost
it — and the CHECK remains exactly what it was: the thing that makes the claim true for every
writer, including a future one that skips this module.

Three further laws are enforced here for the same reason, each with its database counterpart:

* **MI16** — every bonded severity-5 event is blocking. The database derives bonded-ness from
  ``event_bond join event`` in ``fn_bonded_sev5`` and the CHECK
  ``bonded_fatalities_all_blocking`` refuses the run row otherwise. Here it is checked against
  the channel-B result, so a fatality that channel B found and admission lost is named.
* **The probabilistic cap** (recall lead D2) — at most three blocking checks of probabilistic
  origin, with channels A and B **uncapped**, because a cap that could suppress a bonded
  fatality would make MI16 and the cap contradictory constraints.
* **Distinctness** — ``recall_candidate`` is keyed ``(run_id, event_id)``. A candidate found
  by three channels is one candidate; counting it more than once inflates ``n_candidates``
  against a partition that cannot follow.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from mainline_recall_agent.run.errors import ConservationViolated

__all__ = [
    "BLOCKING_CAP_PROBABILISTIC",
    "OUTCOMES",
    "CandidateRow",
    "ConservationReport",
    "enforce_conservation",
]

#: ``mainline_meas.recall_candidate.outcome``'s closed vocabulary.
OUTCOMES: Final[tuple[str, ...]] = ("blocking", "advisory", "silenced", "deduped")

#: Recall lead D2. Scoped to ``origin = 'recall_probabilistic'``; A and B are uncapped.
BLOCKING_CAP_PROBABILISTIC: Final = 3

_DETERMINISTIC_ORIGINS: Final[frozenset[str]] = frozenset(
    {"deterministic_ancestry", "bonded"}
)


@dataclass(frozen=True, slots=True)
class CandidateRow:
    """One ``mainline_meas.recall_candidate`` row, as the orchestrator assembled it."""

    event_id: UUID
    rank: int
    severity: int
    p_relevant: float
    tau_applied: float
    outcome: str
    origin: str
    features: Mapping[str, Any]

    @property
    def is_probabilistic(self) -> bool:
        """Whether the probabilistic blocking cap applies to this row."""
        return self.origin not in _DETERMINISTIC_ORIGINS


@dataclass(frozen=True, slots=True)
class ConservationReport:
    """The five integers ``recall_run`` will store, and the proof that they add up."""

    n_candidates: int
    n_blocking: int
    n_advisory: int
    n_silenced: int
    n_deduped: int

    @property
    def partition(self) -> int:
        """The sum the CHECK compares against ``n_candidates``."""
        return self.n_blocking + self.n_advisory + self.n_silenced + self.n_deduped

    @property
    def conserved(self) -> bool:
        """Whether L3 holds."""
        return self.n_candidates == self.partition

    def as_dict(self) -> dict[str, int]:
        """The counters, for a run row or a log line."""
        return {
            "n_candidates": self.n_candidates,
            "n_blocking": self.n_blocking,
            "n_advisory": self.n_advisory,
            "n_silenced": self.n_silenced,
            "n_deduped": self.n_deduped,
        }


def enforce_conservation(
    rows: Sequence[CandidateRow],
    *,
    bonded_event_ids: Iterable[UUID] = (),
    cap: int = BLOCKING_CAP_PROBABILISTIC,
) -> ConservationReport:
    """Check every conservation law over the assembled candidate rows.

    Args:
        rows: the ``recall_candidate`` rows about to be written.
        bonded_event_ids: the severity-5 bonded events channel B found. Every one of them
            must appear as ``blocking``.
        cap: the probabilistic blocking cap.

    Returns:
        The counters ``recall_run`` will store.

    Raises:
        ConservationViolated: naming the offending event id and the law it broke.
    """
    seen: set[UUID] = set()
    for row in rows:
        if row.event_id in seen:
            raise ConservationViolated(
                f"{row.event_id} appears twice among the candidate rows. "
                "mainline_meas.recall_candidate is keyed (run_id, event_id): a candidate "
                "found by three channels is one candidate, and counting it twice inflates "
                "n_candidates against a partition that cannot follow."
            )
        seen.add(row.event_id)
        if row.outcome not in OUTCOMES:
            raise ConservationViolated(
                f"{row.event_id}: outcome {row.outcome!r} is outside {OUTCOMES}; the "
                "database CHECK would refuse it and the partition would not close"
            )
        if not 0 <= row.severity <= 5:
            raise ConservationViolated(
                f"{row.event_id}: severity {row.severity} is outside 0..5"
            )
        if not 0.0 <= row.p_relevant <= 1.0:
            raise ConservationViolated(
                f"{row.event_id}: p_relevant {row.p_relevant} is not a probability. "
                "Admission compares a calibrated probability against tau; a raw distance "
                "here would be compared against a threshold that means something else."
            )
        if not 0.0 <= row.tau_applied <= 1.0:
            raise ConservationViolated(
                f"{row.event_id}: tau_applied {row.tau_applied} is outside [0, 1]"
            )

    tally = dict.fromkeys(OUTCOMES, 0)
    for row in rows:
        tally[row.outcome] += 1
    report = ConservationReport(
        n_candidates=len(rows),
        n_blocking=tally["blocking"],
        n_advisory=tally["advisory"],
        n_silenced=tally["silenced"],
        n_deduped=tally["deduped"],
    )
    if not report.conserved:
        raise ConservationViolated(
            "candidates_conserved (MI17) fails in code: "
            f"n_candidates={report.n_candidates} but "
            f"blocking+advisory+silenced+deduped={report.partition}. "
            f"{report.as_dict()}"
        )

    by_id = {row.event_id: row for row in rows}
    for bonded in bonded_event_ids:
        row = by_id.get(bonded)
        if row is None:
            raise ConservationViolated(
                f"channel B found bonded severity-5 event {bonded} and it is absent from the "
                "candidate rows. MI16 (bonded_fatalities_all_blocking) exists because a "
                "fatality never decays; losing one between retrieval and accounting is the "
                "exact defect the invariant is written against."
            )
        if row.outcome != "blocking":
            raise ConservationViolated(
                f"bonded severity-5 event {bonded} was recorded as {row.outcome!r}. "
                "Channel B is admitted unconditionally: no threshold, no cap, no rerank."
            )

    blocking_probabilistic = sum(
        1 for row in rows if row.outcome == "blocking" and row.is_probabilistic
    )
    if blocking_probabilistic > cap:
        raise ConservationViolated(
            f"{blocking_probabilistic} blocking checks of probabilistic origin exceed the "
            f"cap of {cap} (recall lead D2). Overflow becomes advisory with a "
            "silence_ledger(reason='cap_exceeded') row carrying its score and its tau; it is "
            "never dropped."
        )
    return report
