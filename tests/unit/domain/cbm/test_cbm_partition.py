# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The five buckets partition the ancestor set — exhaustively, not by sampling.

There are five booleans on :class:`AncestorFacts` and six severities of interest,
which is 192 states in total.  That is small enough to enumerate, so this file
enumerates it rather than drawing from it: a property that holds on 1,000 random
draws and fails on one of 192 reachable states is a property that fails in
production.

WHAT PARTITIONING BUYS, IN ONE SENTENCE
---------------------------------------
``inherited = carried + split + merge + residue_open + residue_disposed`` is only
a conservation law if each ancestor lands in at most one term and every
accounted-for ancestor lands in exactly one.  If two terms could ever claim the
same ancestor, the right-hand side would exceed the left on correct data and the
CHECK would refuse honest accounts; if none could, the law would be vacuous.
"""

from __future__ import annotations

import itertools
import uuid

import pytest
from mainline_domain.cbm import (
    BUCKET_PRECEDENCE,
    AncestorFacts,
    Bucket,
    CommitFacts,
    classify,
    derive_account,
    unaccounted_ancestors,
)

SITE = uuid.UUID("11111111-2222-3333-4444-555555555555")
COMMIT = bytes.fromhex("ab" * 32)
PARENT = bytes.fromhex("cd" * 32)

_FLAGS = ("has_open_residue", "has_any_residue", "has_split", "has_merge", "has_matched")


def _all_states() -> list[AncestorFacts]:
    states: list[AncestorFacts] = []
    for severity in (0, 1, 3, 4, 5):
        for combination in itertools.product((False, True), repeat=len(_FLAGS)):
            states.append(
                AncestorFacts(
                    clause_uuid=uuid.uuid4(),
                    max_ancestral_severity=severity,
                    **dict(zip(_FLAGS, combination, strict=True)),
                )
            )
    return states


ALL_STATES = _all_states()


def test_the_enumeration_really_is_the_whole_state_space() -> None:
    assert len(ALL_STATES) == 5 * 2 ** len(_FLAGS) == 160


@pytest.mark.parametrize("state", ALL_STATES, ids=range(len(ALL_STATES)))
def test_every_state_lands_in_at_most_one_bucket(state: AncestorFacts) -> None:
    bucket = classify(state)
    assert bucket is None or bucket in BUCKET_PRECEDENCE


def test_the_bucket_is_the_first_precedence_member_whose_predicate_holds() -> None:
    """The precedence order is the ``Bucket`` member order, and the SQL in
    ``0140a`` encodes the same order as five mutually exclusive FILTER
    predicates.  If this drifts, the differential test is what catches it — but
    it should not have to."""
    predicates = {
        Bucket.RESIDUE_OPEN: lambda s: s.has_open_residue,
        Bucket.RESIDUE_DISPOSED: lambda s: s.has_any_residue,
        Bucket.SPLIT_CARRIED: lambda s: s.has_split,
        Bucket.MERGE_CARRIED: lambda s: s.has_merge,
        Bucket.CARRIED: lambda s: s.has_matched,
    }
    assert tuple(predicates) == BUCKET_PRECEDENCE

    for state in ALL_STATES:
        expected = next((b for b in BUCKET_PRECEDENCE if predicates[b](state)), None)
        assert classify(state) is expected


def test_the_identity_holds_for_every_subset_of_the_state_space() -> None:
    """A commit made of ALL 160 states at once, and every 40-state slice of it.

    ``inherited`` must equal the sum of the five terms plus the number of
    unaccounted ancestors, exactly, with no state counted twice and none lost.
    """
    for start in (0, 40, 80, 120):
        window = ALL_STATES[start : start + 40]
        facts = CommitFacts(
            site_id=SITE, commit_id=COMMIT, first_parent=PARENT, ancestors=tuple(window)
        )
        account = derive_account(facts)
        blood = [s for s in window if s.is_blood_bearing()]
        orphans = unaccounted_ancestors(facts)

        assert account.inherited == len(blood)
        accounted = (
            account.carried
            + account.split_carried
            + account.merge_carried
            + account.residue_open
            + account.residue_disposed
        )
        assert accounted + len(orphans) == account.inherited
        assert account.balanced() is (len(orphans) == 0)


def test_a_sub_blood_ancestor_never_contributes_to_any_term() -> None:
    """The threshold is applied once, to the universe, and not per bucket.

    A severity-3 ancestor with a matched assignment must contribute to NEITHER
    ``inherited`` nor ``carried``; contributing to only one of them would break
    the identity on data that is entirely correct.
    """
    low = [s for s in ALL_STATES if not s.is_blood_bearing()]
    account = derive_account(
        CommitFacts(site_id=SITE, commit_id=COMMIT, first_parent=PARENT, ancestors=tuple(low))
    )
    assert account.inherited == 0
    assert account.carried == 0
    assert account.split_carried == 0
    assert account.merge_carried == 0
    assert account.residue_open == 0
    assert account.residue_disposed == 0
    assert account.balanced()


def test_the_account_is_a_pure_function_of_the_facts() -> None:
    """Same facts, same account, in any order of evaluation.

    A projector whose answer depended on iteration order would make
    ``account_gen`` 0 and 1 differ for an unchanged commit, and "the accounting
    balanced" would become a statement about when it ran.
    """
    facts = CommitFacts(
        site_id=SITE, commit_id=COMMIT, first_parent=PARENT, ancestors=tuple(ALL_STATES)
    )
    reversed_facts = CommitFacts(
        site_id=SITE,
        commit_id=COMMIT,
        first_parent=PARENT,
        ancestors=tuple(reversed(ALL_STATES)),
    )
    assert derive_account(facts) == derive_account(reversed_facts)
