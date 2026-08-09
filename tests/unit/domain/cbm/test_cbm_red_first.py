# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""PL-2: the three assertions that were red before one line of ``cbm/`` existed.

They are pure and need no cluster, which is the point — the cluster suite is
where the REFUSAL lives, and this file is where the ARITHMETIC lives.  A
conservation law that only holds inside a database is a law nobody can check by
reading.

The first of the three is the whole product in four lines: an ancestor the
matcher accounted for in no way at all makes the account fail to balance.  It was
red with ``ImportError`` before ``mainline_domain.cbm`` existed, red with
``AttributeError`` before :func:`classify` did, and green only once the buckets
partitioned the ancestor set.
"""

from __future__ import annotations

import uuid

import pytest
from mainline_domain.cbm import (
    BLOOD_SEVERITY_THRESHOLD,
    AncestorFacts,
    Bucket,
    ClosureNotMaterialised,
    CommitFacts,
    classify,
    derive_account,
    unaccounted_ancestors,
)

SITE = uuid.UUID("11111111-2222-3333-4444-555555555555")
COMMIT = bytes.fromhex("ab" * 32)
PARENT = bytes.fromhex("cd" * 32)


def _ancestor(
    *,
    severity: int = 5,
    open_residue: bool = False,
    any_residue: bool = False,
    split: bool = False,
    merge: bool = False,
    matched: bool = False,
) -> AncestorFacts:
    return AncestorFacts(
        clause_uuid=uuid.uuid4(),
        max_ancestral_severity=severity,
        has_open_residue=open_residue,
        has_any_residue=any_residue or open_residue,
        has_split=split,
        has_merge=merge,
        has_matched=matched,
    )


def _facts(*ancestors: AncestorFacts, closure_missing: int = 0) -> CommitFacts:
    return CommitFacts(
        site_id=SITE,
        commit_id=COMMIT,
        first_parent=PARENT,
        ancestors=ancestors,
        closure_missing=closure_missing,
    )


def test_an_unaccounted_blood_bearing_ancestor_breaks_the_identity() -> None:
    """The product, in four lines.

    Two obligations went in; one came out.  ``balanced()`` is false, which is
    ``CONSTRAINT cbm_balances`` refusing the write, which is a merge that cannot
    happen.
    """
    account = derive_account(_facts(_ancestor(matched=True), _ancestor()))
    assert account.inherited == 2
    assert account.carried == 1
    assert not account.balanced()


def test_the_orphaned_obligation_is_named_and_not_merely_counted() -> None:
    """A ``23514`` says the account did not balance.  It cannot say WHICH
    obligation went missing, and that is what an operator needs."""
    orphan = _ancestor()
    facts = _facts(_ancestor(matched=True), orphan)
    assert unaccounted_ancestors(facts) == (orphan.clause_uuid,)


def test_writing_the_residue_row_the_law_asks_for_closes_the_account() -> None:
    """The remedy is never "adjust the numbers"; it is "record the doubt"."""
    account = derive_account(_facts(_ancestor(matched=True), _ancestor(open_residue=True)))
    assert (account.inherited, account.carried, account.residue_open) == (2, 1, 1)
    assert account.balanced()


def test_an_ancestor_below_the_blood_threshold_is_outside_the_law() -> None:
    """Severity >= 4 is the universe the conservation law quantifies over.

    Counting everything would make every real commit unbalanced (a gate that
    never opens); counting nothing would make every commit balance (a gate that
    never closes).  Both failures look like the system working.
    """
    assert BLOOD_SEVERITY_THRESHOLD == 4
    account = derive_account(
        _facts(_ancestor(severity=5), _ancestor(severity=3), _ancestor(severity=0))
    )
    assert account.inherited == 1
    assert not account.balanced()


def test_the_precedence_is_fail_closed_at_every_step() -> None:
    """Doubt beats a claim; never the other way round.

    A matcher that emits both a ``matched`` assignment and an open residue row for
    one ancestor has contradicted itself, and the account records the obligation
    as OPEN — which blocks — rather than as carried, which would not.
    """
    assert classify(_ancestor(open_residue=True, matched=True)) is Bucket.RESIDUE_OPEN
    assert classify(_ancestor(any_residue=True, matched=True)) is Bucket.RESIDUE_DISPOSED
    assert classify(_ancestor(split=True, merge=True, matched=True)) is Bucket.SPLIT_CARRIED
    assert classify(_ancestor(merge=True, matched=True)) is Bucket.MERGE_CARRIED
    assert classify(_ancestor(matched=True)) is Bucket.CARRIED
    assert classify(_ancestor()) is None


def test_an_absent_assignment_has_no_bucket_because_it_carries_no_obligation() -> None:
    """``relation='absent'`` is an assertion, not a disposition.

    :class:`AncestorFacts` has no ``has_absent`` field at all, which is the
    strongest way to say it: the conservation law requires an absent ancestor to
    be EXPLICITLY absent with a signed disposition, and the disposition hangs off
    an ``identity_residue`` row.  Declaring an obligation gone is not the same as
    recording that it is gone.
    """
    assert not hasattr(_ancestor(), "has_absent")
    assert classify(_ancestor()) is None


def test_a_missing_closure_row_refuses_rather_than_defaulting_to_zero() -> None:
    """P3, fail closed.  A severity nobody has projected is not a severity of zero.

    A zero would shrink ``inherited``, and a smaller ``inherited`` is a gate that
    opens — the one direction of error this design may not make.
    """
    with pytest.raises(ClosureNotMaterialised) as caught:
        derive_account(_facts(_ancestor(matched=True), closure_missing=3))
    assert caught.value.missing == 3
    assert caught.value.first_parent == PARENT


def test_a_root_commit_inherits_nothing_and_balances() -> None:
    account = derive_account(
        CommitFacts(site_id=SITE, commit_id=COMMIT, first_parent=None, ancestors=())
    )
    assert account.inherited == 0
    assert account.balanced()
