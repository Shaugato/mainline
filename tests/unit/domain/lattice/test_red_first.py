# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""PL-2: the two tests that were RED before one line of the lattice existed.

``docs/leads/algorithms.md`` §3 names worker W4's first failing test:

    ``MUST → SHOULD`` with everything else identical returns ``weaken`` with
    exactly one witness; and a ``weaken`` verdict with an empty witness set
    raises.

For a product whose deliverable is a **refusal**, a suite that has never been red
asserts nothing.  Both tests below were run before ``mainline_domain.lattice``
existed and both failed with ``ModuleNotFoundError: No module named
'mainline_domain.lattice'`` — recorded here because a red nobody witnessed is a
claim, not evidence.

The second test deserves a note on *where the enforcement actually lives*.
``contracts.DeltaVerdict`` is a plain frozen dataclass owned by worker W1 and
this worker may not add a ``__post_init__`` to it, so the raw dataclass will
happily hold a witness-free ``weaken`` — :func:`test_the_raw_dataclass_is_not_the_gate`
demonstrates exactly that, on purpose.  The Python refusal lives in
:func:`mainline_domain.lattice.verdict`, the one sanctioned construction path in
this domain, and the *real* refusal lives in the database:
``fn_delta_witness_guard`` (migration ``0140``, attached to
``mainline.clause_version`` by ``0145``) raises ``P0001`` for every writer,
forever, including one that never imports this package.  Decision D8.

That database refusal is executed, not asserted:
``tests/integration/algorithms/lattice/test_witness_or_refuse.py`` runs the same
INSERT against two schemas differing only in whether ``0145`` was applied.  The
one without the trigger accepts the row; the one with it raises ``P0001``.  That
is the same red-before-green discipline as this file, kept as a fixture rather
than performed once — because "the INSERT was refused" is otherwise equally
consistent with a ``NOT NULL``, a foreign key, or a typo in the test.
"""

from __future__ import annotations

import pytest
from _lattice_fixtures import AS_OF, cat, empty_registry
from mainline_domain.contracts import ControlDelta, DeltaVerdict
from mainline_domain.lattice import WitnesslessWeakenError, decide, verdict


def test_must_to_should_is_one_witness_and_it_is_r1() -> None:
    """(a) Two CATs identical but for the deontic rung.  One reason, and its name.

    Nothing else moves: same actor, same action, same object, no parameter, no
    value, no exceptions, no verification, no frequency.  So the verdict has
    exactly one thing it can be about, and if the lattice returns two witnesses
    it has invented a second reason out of an unchanged tuple.
    """
    reference = cat(actor="operator", deontic="MUST", action="isolate", object_class="vessel")
    descendant = cat(actor="operator", deontic="SHOULD", action="isolate", object_class="vessel")

    result = decide(reference, descendant, empty_registry(), AS_OF)

    assert result.delta is ControlDelta.WEAKEN
    assert result.basis == "lattice"
    assert result.minimal is True
    assert len(result.witnesses) == 1, [w.rule_id for w in result.witnesses]
    assert result.witnesses[0].rule_id == "R1_DEONTIC"
    assert result.witnesses[0].field == "deontic"
    assert result.witnesses[0].from_repr == "MUST"
    assert result.witnesses[0].to_repr == "SHOULD"
    assert result.witnesses[0].note


def test_a_witnessless_lattice_weaken_cannot_be_built() -> None:
    """(b) ``weaken`` + ``basis='lattice'`` + no witnesses raises.  D8, in Python."""
    with pytest.raises(WitnesslessWeakenError) as raised:
        verdict(ControlDelta.WEAKEN, "lattice", (), minimal=True)

    # The message has to name the mechanism, because the person who sees it is
    # debugging a projector, not reading this file.
    assert "witness" in str(raised.value).lower()


def test_a_witnessless_lattice_remove_cannot_be_built_either() -> None:
    """``remove`` is force 3 and is covered by the same clause of D8."""
    with pytest.raises(WitnesslessWeakenError):
        verdict(ControlDelta.REMOVE, "lattice", (), minimal=True)


def test_a_witnessless_abstention_is_legal_because_the_lattice_declined() -> None:
    """``abstain_to_weaken`` has no lattice witness *by construction*.

    The ratchet fires when Path A could not decide, so demanding a lattice
    witness for it would demand an explanation nobody has.  ``fn_delta_witness_guard``
    scopes itself to ``delta_basis='lattice'`` for exactly this reason, and this
    function is the Python half of the same scoping.
    """
    built = verdict(ControlDelta.WEAKEN, "abstain_to_weaken", (), minimal=False)
    assert built.witnesses == ()
    assert built.minimal is False


def test_the_raw_dataclass_is_not_the_gate() -> None:
    """Deliberately demonstrates the bypass, so nobody mistakes Python for the gate.

    ``DeltaVerdict`` is W1's frozen dataclass with no validation, and this worker
    does not own it.  Constructing the forbidden shape directly SUCCEEDS.  That is
    not a defect to be fixed here — it is the reason D8 is a database trigger.
    """
    smuggled = DeltaVerdict(delta=ControlDelta.WEAKEN, basis="lattice", witnesses=(), minimal=True)
    assert smuggled.witnesses == ()
