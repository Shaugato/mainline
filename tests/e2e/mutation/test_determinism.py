# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Two runs of one seed produce one artefact, byte for byte.

A residual-risk figure that moves between two runs of the same code is a figure
nobody can act on: a change of 0.02 could be a regression or could be the
generator.  So the whole run is a pure function of the master seed and committed
bytes, and this file asserts it over the rendered document rather than over the
counts — the counts could agree while the per-mutant rows disagreed, and the rows
are what a reader recounts from.
"""

from __future__ import annotations

from mainline_mutation import run, stable_document
from mainline_mutation.model import mutant_id
from mainline_mutation.runner import _rng


def test_two_runs_of_one_seed_render_identically():
    first = stable_document(run(seed=7))
    second = stable_document(run(seed=7))
    assert first == second


def test_a_different_seed_is_a_different_run():
    """Not that the OUTCOMES differ — that the run is genuinely seeded.

    The mutant ids must move with the seed, because a run whose identifiers did
    not depend on the seed would be one whose ``--seed`` flag did nothing.  The
    outcomes may legitimately be identical; most operators are deterministic and
    ignore the generator entirely.
    """
    a = {r.mutant_id for r in run(seed=1).results}
    b = {r.mutant_id for r in run(seed=2).results}
    assert a
    assert b
    assert a.isdisjoint(b)


def test_the_artefact_records_its_seed():
    output = run(seed=42)
    assert output.seed == 42
    assert '"seed": 42' in stable_document(output)


def test_mutant_ids_are_a_pure_function_of_their_inputs():
    first = mutant_id(seed=3, class_id="deontic_downgrade", fixture_id="F01")
    again = mutant_id(seed=3, class_id="deontic_downgrade", fixture_id="F01")
    assert first == again
    assert first != mutant_id(seed=3, class_id="deontic_downgrade", fixture_id="F02")
    assert first != mutant_id(seed=4, class_id="deontic_downgrade", fixture_id="F01")
    assert first != mutant_id(seed=3, class_id="hedge_insertion", fixture_id="F01")


def test_one_class_s_generator_does_not_depend_on_another_s():
    """Adding a class must not move any other class's mutants.

    The per-mutant generator is seeded from ``(seed, class, fixture)`` and not
    from a running counter, so the catalogue can grow without invalidating every
    previously published row.  A counter would make every artefact incomparable
    with every earlier one for a reason that has nothing to do with the system
    under measurement.
    """
    before = _rng(0, "retypeset", "F01").random()
    _ = _rng(0, "a_new_class_that_did_not_exist", "F01").random()
    after = _rng(0, "retypeset", "F01").random()
    assert before == after


def test_the_crippled_arm_is_also_deterministic():
    disabled = frozenset({"R1_DEONTIC", "R7_FREQUENCY"})
    first = stable_document(run(seed=0, disabled_rules=disabled))
    second = stable_document(run(seed=0, disabled_rules=disabled))
    assert first == second
