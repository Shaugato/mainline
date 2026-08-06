# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Backends used to prove the G4-alpha suite is neither vacuous nor unsatisfiable.

Two of them, and both are load-bearing:

* :class:`OracleBackend` reads the corpus ground truth and returns the right answer.
  It exists to prove the five gates are **satisfiable** — that they are a gate and not
  a wall. If a perfect retriever could not pass them, the floors would be wrong.
* :class:`ShoutingBackend` blocks on everything it can see. It exists to prove the
  noise gates **bite** — a retriever that maximises recall by blocking indiscriminately
  must fail ``P@block``, the nuisance rate and the mean, not sail through them.

Neither is a retrieval implementation and neither may be imported by product code. They
read ``EvalQuery.truth_doc_id`` directly, which no real backend can do.
"""

from __future__ import annotations

from trappoint_recall.eval.backend import RunTally, ScoredCandidate
from trappoint_recall.eval.corpus import EvalQuery


def _tally(candidates: list[ScoredCandidate]) -> RunTally:
    counts = {"blocking": 0, "advisory": 0, "silenced": 0, "deduped": 0}
    bonded = 0
    bonded_blocking = 0
    for c in candidates:
        counts[c.outcome] += 1
        if c.origin == "bonded" and c.severity == 5:
            bonded += 1
            if c.outcome == "blocking":
                bonded_blocking += 1
    return RunTally(
        n_candidates=len(candidates),
        n_blocking=counts["blocking"],
        n_advisory=counts["advisory"],
        n_silenced=counts["silenced"],
        n_deduped=counts["deduped"],
        n_bonded_sev5=bonded,
        n_bonded_sev5_blocking=bonded_blocking,
    )


class OracleBackend:
    """Returns the authored truth, blocks on it, and accounts for everything it saw.

    Shape of a run against a retro permit:

    * the truth precursor, rank 1, ``blocking`` / ``recall_probabilistic``
    * every corpus-bonded severity-5 event, ``blocking`` / ``bonded`` (channel B is
      unconditional, so these never depend on a score)
    * the grade-2 near miss as ``advisory``
    * the grade-1 neighbours as ``silenced`` and ``deduped``

    Against a routine permit it returns the two distractors as ``silenced`` and
    ``advisory`` and blocks on neither, which is what an uneventful permit should do.
    """

    name = "oracle"

    def __init__(self, *, name: str = "oracle") -> None:
        self.name = name
        self._last: dict[str, RunTally] = {}

    def _build(self, query: EvalQuery, k: int) -> list[ScoredCandidate]:
        candidates: list[ScoredCandidate] = []
        rank = 1
        if query.kind == "retro" and query.truth_doc_id is not None:
            severity = query.severity or 3
            tau = {5: 0.35, 4: 0.45, 3: 0.60, 2: 0.75, 1: 0.85}[severity]
            candidates.append(
                ScoredCandidate(
                    doc_id=query.truth_doc_id,
                    rank=rank,
                    p_relevant=0.93,
                    tau_applied=tau,
                    outcome="blocking",
                    severity=severity,
                    channel="C",
                    origin="recall_probabilistic",
                    features={"rrf": 0.031, "bm25": 14.2},
                )
            )
            rank += 1
            for doc in query.bonded_sev5:
                candidates.append(
                    ScoredCandidate(
                        doc_id=doc,
                        rank=rank,
                        p_relevant=1.0,
                        tau_applied=0.0,
                        outcome="blocking",
                        severity=5,
                        channel="B",
                        origin="bonded",
                        features={},
                    )
                )
                rank += 1
            suffix = query.query_id.split("-")[-1]
            candidates.append(
                ScoredCandidate(
                    doc_id=f"E-NEAR-{suffix}",
                    rank=rank,
                    p_relevant=0.41,
                    tau_applied=tau,
                    outcome="advisory",
                    severity=3,
                    channel="C",
                    origin="recall_probabilistic",
                )
            )
            rank += 1
            candidates.append(
                ScoredCandidate(
                    doc_id=f"E-RELATED-{suffix}-a",
                    rank=rank,
                    p_relevant=0.12,
                    tau_applied=tau,
                    outcome="silenced",
                    severity=2,
                    channel="D",
                    origin="lexical",
                )
            )
            rank += 1
            candidates.append(
                ScoredCandidate(
                    doc_id=f"E-RELATED-{suffix}-b",
                    rank=rank,
                    p_relevant=0.09,
                    tau_applied=tau,
                    outcome="deduped",
                    severity=2,
                    channel="C_sweep",
                    origin="recall_probabilistic",
                )
            )
        else:
            suffix = query.query_id.split("-")[-1]
            candidates.append(
                ScoredCandidate(
                    doc_id=f"E-DISTRACTOR-{suffix}-a",
                    rank=rank,
                    p_relevant=0.08,
                    tau_applied=0.60,
                    outcome="silenced",
                    severity=2,
                    channel="C",
                    origin="recall_probabilistic",
                )
            )
            rank += 1
            candidates.append(
                ScoredCandidate(
                    doc_id=f"E-DISTRACTOR-{suffix}-b",
                    rank=rank,
                    p_relevant=0.21,
                    tau_applied=0.60,
                    outcome="advisory",
                    severity=2,
                    channel="D",
                    origin="lexical",
                )
            )
        return candidates[:k]

    async def retrieve(self, query: EvalQuery, k: int) -> list[ScoredCandidate]:
        candidates = self._build(query, k)
        self._last[query.query_id] = _tally(candidates)
        return candidates

    async def declared_tally(self, query: EvalQuery) -> RunTally:
        return self._last.get(
            query.query_id,
            RunTally(n_candidates=0, n_blocking=0, n_advisory=0, n_silenced=0, n_deduped=0),
        )


class ShoutingBackend:
    """Blocks on every candidate it produces, including on routine permits.

    The maximum-recall degenerate. It finds every precursor, so the recall gate passes;
    it also blocks on routine work, so the nuisance rate, the mean and ``P@block`` must
    all refuse it. If they do not, the noise gates are decorative.
    """

    name = "shouting"

    def __init__(self, *, name: str = "shouting") -> None:
        self.name = name
        self._last: dict[str, RunTally] = {}

    def _build(self, query: EvalQuery, k: int) -> list[ScoredCandidate]:
        suffix = query.query_id.split("-")[-1]
        docs: list[tuple[str, int]] = []
        if query.kind == "retro" and query.truth_doc_id is not None:
            docs.append((query.truth_doc_id, query.severity or 3))
            docs.extend((d, 5) for d in query.bonded_sev5)
            docs.extend(
                [
                    (f"E-NEAR-{suffix}", 3),
                    (f"E-RELATED-{suffix}-a", 2),
                    (f"E-RELATED-{suffix}-b", 2),
                    (f"E-IRRELEVANT-{suffix}", 1),
                ]
            )
        else:
            docs.extend([(f"E-DISTRACTOR-{suffix}-a", 2), (f"E-DISTRACTOR-{suffix}-b", 2)])
        candidates: list[ScoredCandidate] = []
        for rank, (doc, severity) in enumerate(docs[:k], start=1):
            bonded = doc in query.bonded_sev5
            candidates.append(
                ScoredCandidate(
                    doc_id=doc,
                    rank=rank,
                    p_relevant=0.99,
                    tau_applied=0.10,
                    outcome="blocking",
                    severity=severity,
                    channel="B" if bonded else "C",
                    origin="bonded" if bonded else "recall_probabilistic",
                )
            )
        return candidates

    async def retrieve(self, query: EvalQuery, k: int) -> list[ScoredCandidate]:
        candidates = self._build(query, k)
        self._last[query.query_id] = _tally(candidates)
        return candidates

    async def declared_tally(self, query: EvalQuery) -> RunTally:
        return self._last.get(
            query.query_id,
            RunTally(n_candidates=0, n_blocking=0, n_advisory=0, n_silenced=0, n_deduped=0),
        )


class DroppingBackend(OracleBackend):
    """An oracle whose declared counters under-report by one candidate per run.

    Models the failure the conservation law exists to catch: a candidate that was seen,
    scored and then lost between the run counters and the candidate set. The law must
    notice; nothing else in the suite would.
    """

    name = "dropping"

    def __init__(self, *, name: str = "dropping") -> None:
        super().__init__(name=name)

    async def declared_tally(self, query: EvalQuery) -> RunTally:
        honest = await super().declared_tally(query)
        if honest.n_candidates == 0:
            return honest
        return RunTally(
            n_candidates=honest.n_candidates - 1,
            n_blocking=honest.n_blocking,
            n_advisory=honest.n_advisory,
            n_silenced=max(0, honest.n_silenced - 1),
            n_deduped=honest.n_deduped,
            n_bonded_sev5=honest.n_bonded_sev5,
            n_bonded_sev5_blocking=honest.n_bonded_sev5_blocking,
        )
