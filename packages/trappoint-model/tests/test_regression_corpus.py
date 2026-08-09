# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Every recorded counterexample, replayed deterministically, on every run.

``.hypothesis-corpus/counterexamples.jsonl`` is the durable half of the corpus. Hypothesis
prunes its own directory the moment an example stops failing — measured: three shrunk
counterexamples were on disk while the model was wrong and the directory was empty on the
first green run — so the histories that found real bugs are recorded here instead, with
the verdict each step must produce written down.

That written-down verdict is stronger than the differential it came from. The differential
asserts *agreement*; two implementations that made the same mistake agree perfectly. These
assert the answer.

Two arms:

* **the oracle arm** always runs, needs no cluster, and catches a model regression;
* **the cluster arm** runs both sides and additionally catches a substrate regression —
  and asserts the oracle and the cluster still agree, which is the differential pinned to
  one history instead of generated.
"""

from __future__ import annotations

from typing import Any

import pytest
from trappoint_model.adapter import Adapter
from trappoint_model.invariants import check_all
from trappoint_model.refschema import Fixture
from trappoint_model.replay import Counterexample, load_corpus, replay

CORPUS = load_corpus()


def _ids(entries: list[Counterexample]) -> list[str]:
    return [entry.id for entry in entries]


def test_the_corpus_is_not_empty() -> None:
    """A committed corpus that lost its entries is a deleted regression suite."""
    assert CORPUS, (
        "counterexamples.jsonl parsed to nothing. The corpus is part of the assurance "
        "case; an empty one must fail rather than pass quietly."
    )


@pytest.mark.parametrize("entry", CORPUS, ids=_ids(CORPUS))
def test_the_oracle_still_answers_as_recorded(entry: Counterexample) -> None:
    """Replay against the model alone. No cluster; always runs."""
    for index, (step, want, _) in enumerate(replay(entry)):
        assert want == step.expect, (
            f"{entry.id} step {index} ({step.op} {step.args}): the ORACLE now answers "
            f"{want}, but {step.expect} was recorded on {entry.found}.\n{entry.summary}\n"
            f"{entry.diagnosis}"
        )


@pytest.mark.requires_cluster
@pytest.mark.parametrize("entry", CORPUS, ids=_ids(CORPUS))
def test_the_cluster_still_answers_as_recorded(
    entry: Counterexample, conn: Any, fixture: Fixture
) -> None:
    """Replay against both. The recorded verdict AND the agreement, per step."""
    adapter = Adapter(conn, fixture)
    for index, (step, want, got) in enumerate(replay(entry, adapter=adapter)):
        where = f"{entry.id} step {index} ({step.op} {step.args})"
        assert got == step.expect, (
            f"{where}: the CLUSTER now answers {got}, but {step.expect} was recorded on "
            f"{entry.found}.\n{entry.summary}\n{entry.diagnosis}"
        )
        assert want == got, (
            f"{where}: oracle {want} vs cluster {got}. This history is in the corpus "
            "BECAUSE the two once disagreed here; they are disagreeing again."
        )
    violations, _ = check_all(conn)
    assert not violations, (
        f"{entry.id} left the database in a state the laws forbid:\n"
        + "\n".join(str(v) for v in violations)
    )


@pytest.mark.requires_cluster
def test_a_replay_uses_fresh_handles_each_time(conn: Any, fixture: Fixture) -> None:
    """Two replays of one entry must not collide.

    Handles are minted per replay, so running the corpus twice against one tenancy writes
    two independent histories. Without that, the second run would meet the first run's
    rows — ``UNIQUE (site_id, external_ref)`` on ``permit``, the ``dedupe_key`` digest on
    ``blocking_check`` — and every entry would fail with a refusal that has nothing to do
    with the bug it records.
    """
    entry = CORPUS[0]
    adapter = Adapter(conn, fixture)
    first = [str(got) for _, _, got in replay(entry, adapter=adapter)]
    second = [str(got) for _, _, got in replay(entry, adapter=adapter)]
    assert first == second, (
        "the same history produced different verdicts on its second replay, so the two "
        f"runs collided:\n  first : {first}\n  second: {second}"
    )


def test_every_entry_carries_a_diagnosis() -> None:
    """An entry with no diagnosis is a file nobody can act on.

    The corpus is read by people who were not here. ``summary`` says what broke;
    ``diagnosis`` says WHICH SIDE was wrong, which is the sentence that stops the next
    reader from 'fixing' the model to match the cluster.
    """
    for entry in CORPUS:
        assert entry.summary.strip(), f"{entry.id} has no summary"
        assert entry.diagnosis.strip(), f"{entry.id} has no diagnosis"
        assert entry.found.strip(), f"{entry.id} does not say when it was found"
        assert entry.steps, f"{entry.id} records no steps"
