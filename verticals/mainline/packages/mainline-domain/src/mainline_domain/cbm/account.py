# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""CONSERVATION OF BLAME MASS — the arithmetic, in Python, with no database.

    inherited = carried + split_carried + merge_carried + residue_open + residue_disposed

THE DATABASE IS THE AUTHORITY AND THIS MODULE IS NOT
----------------------------------------------------
``mainline.fn_cbm_account_guard`` (migration ``0140a``) re-derives all six
counters from ``clause_blame_current`` / ``identity_assignment`` /
``identity_residue`` and OVERWRITES whatever an inserter supplied, and
``CONSTRAINT cbm_balances`` (migration ``0049c``) refuses the row if they do not
balance.  Nothing in this file can prevent, permit or alter either.

So why does it exist?  Because a projector that could only find out whether its
arithmetic was right by attempting a write would learn it as an exception, in
production, after the fact.  This module lets the projector compute the account
it is about to propose, compare it with what the database derived, and report a
disagreement as a defect in ITSELF rather than as a mysterious ``23514``.
``tests/integration/algorithms/cbm/test_differential_200.py`` proves the two
agree on 200 fixture commits; if they ever disagree, **the SQL is right**,
because the SQL is the one a state transition is conditioned on.

THE BUCKETS PARTITION ANCESTORS, NOT ROWS
-----------------------------------------
``identity_residue``'s unique key is ``(commit_id, ancestor_clause_uuid,
reason)`` — one ancestor may legitimately be both ``ambiguous`` and
``anchor_drop`` — and ``identity_assignment`` is keyed over the descendant too,
so a split writes one row per child.  Counting *rows* would make the right-hand
side exceed the left on ordinary data and the identity would be arithmetic about
nothing.  Each ancestor is therefore placed in exactly ONE bucket by a fixed
precedence, and the precedence is fail-closed at every step:

    residue_open > residue_disposed > split_carried > merge_carried > carried

An ancestor with both a claimed match and an open residue row counts as
``residue_open``, which blocks.  The generous reading is never the one taken.

An ancestor in NONE of the five is UNACCOUNTED.  That is not an error here —
this module reports what it found — and the sum is then strictly less than
``inherited``, so the database refuses the account.  That refusal is the
product: a matcher that quietly under-emits residue cannot produce a clean gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final
from uuid import UUID

from mainline_domain.contracts import CBMAccount

from .version import BLOOD_SEVERITY_THRESHOLD

__all__ = [
    "BLOOD_SEVERITY_THRESHOLD",
    "BUCKET_PRECEDENCE",
    "AncestorFacts",
    "Bucket",
    "CommitFacts",
    "classify",
    "derive_account",
    "unaccounted_ancestors",
]


class Bucket(Enum):
    """The five terms on the right-hand side of the conservation identity.

    The member ORDER is the precedence order and is load-bearing: :func:`classify`
    returns the first member whose predicate holds, and the SQL in ``0140a``
    encodes the same order as five mutually exclusive ``FILTER`` predicates.
    """

    RESIDUE_OPEN = "residue_open"
    RESIDUE_DISPOSED = "residue_disposed"
    SPLIT_CARRIED = "split_carried"
    MERGE_CARRIED = "merge_carried"
    CARRIED = "carried"


@dataclass(frozen=True, slots=True)
class AncestorFacts:
    """Everything the classification needs about ONE blood-bearing ancestor.

    Every field is a fact read from an authoritative relation, never a judgement:
    ``has_*`` are existence answers over ``identity_residue`` and
    ``identity_assignment`` for this (commit, ancestor) pair.

    ``relation='absent'`` is DELIBERATELY not a field.  An absent ancestor is
    exactly the case the conservation law says must be *explicitly* absent with
    a signed disposition, so an ``absent`` assignment with no residue row is an
    assertion with no obligation attached: it classifies as nothing, the account
    fails to balance, and the write is refused.  Declaring an obligation gone is
    not the same as recording that it is gone.
    """

    clause_uuid: UUID
    max_ancestral_severity: int
    has_open_residue: bool
    has_any_residue: bool
    has_split: bool
    has_merge: bool
    has_matched: bool

    def is_blood_bearing(self) -> bool:
        """Severity >= 4.  The universe the conservation law quantifies over."""
        return self.max_ancestral_severity >= BLOOD_SEVERITY_THRESHOLD


@dataclass(frozen=True, slots=True)
class CommitFacts:
    """The three relations, resolved for one commit, as the projector saw them.

    ``ancestors`` must ALREADY be filtered to the blood-bearing set A(c) defined
    in ``0140a``'s header — clause versions in the first-parent commit whose
    document the commit touched and whose closure severity is >= 4.  Whoever
    builds this object is asserting that filter; :func:`derive_account` re-checks
    it with :meth:`AncestorFacts.is_blood_bearing` rather than trusting it,
    because a caller that forgot would silently inflate ``inherited``.

    ``closure_missing`` is the count of first-parent clause versions with no
    ``clause_blame_current`` row.  It is carried rather than raised at
    construction so that a caller can inspect the whole picture before deciding;
    :func:`derive_account` refuses on it.
    """

    site_id: UUID
    commit_id: bytes
    first_parent: bytes | None
    ancestors: tuple[AncestorFacts, ...]
    closure_missing: int = 0


#: Precedence order, written once so the tests can iterate it.
BUCKET_PRECEDENCE: Final[tuple[Bucket, ...]] = (
    Bucket.RESIDUE_OPEN,
    Bucket.RESIDUE_DISPOSED,
    Bucket.SPLIT_CARRIED,
    Bucket.MERGE_CARRIED,
    Bucket.CARRIED,
)


def classify(facts: AncestorFacts) -> Bucket | None:
    """Place one ancestor in exactly one bucket, or ``None`` if unaccounted.

    ``None`` is not an error and is not an exception.  It is the finding that
    makes ``inherited`` exceed the sum of the five terms, which is what
    ``CONSTRAINT cbm_balances`` refuses.  A function that raised here would move
    the refusal into the projector, which is precisely where it must not be.
    """
    if facts.has_open_residue:
        return Bucket.RESIDUE_OPEN
    if facts.has_any_residue:
        return Bucket.RESIDUE_DISPOSED
    if facts.has_split:
        return Bucket.SPLIT_CARRIED
    if facts.has_merge:
        return Bucket.MERGE_CARRIED
    if facts.has_matched:
        return Bucket.CARRIED
    return None


def unaccounted_ancestors(facts: CommitFacts) -> tuple[UUID, ...]:
    """Return the blood-bearing ancestors this commit accounts for in no way at all.

    This is the diagnostic the ``23514`` cannot carry.  A refusal says the
    account did not balance; this says *which obligations went missing*, which is
    what an operator needs and what the console renders beside the refusal.
    """
    return tuple(
        a.clause_uuid for a in facts.ancestors if a.is_blood_bearing() and classify(a) is None
    )


def derive_account(facts: CommitFacts) -> CBMAccount:
    """Compute the account exactly as ``0140a`` computes it.

    :raises ClosureNotMaterialised: when any first-parent clause version in a
        touched document has no closure row.  Fail closed: a severity nobody has
        projected yet is not a severity of zero, and a zero would shrink
        ``inherited``, which is a gate that opens.

    The returned account is NOT guaranteed to balance — call
    :meth:`CBMAccount.balanced` to find out, and :func:`unaccounted_ancestors`
    to find out why not.  Returning an unbalanced account rather than raising is
    deliberate: the projector's job is to report what it found, and the database's
    job is to refuse it.
    """
    from .errors import ClosureNotMaterialised  # local: keeps the import graph acyclic

    if facts.closure_missing > 0:
        raise ClosureNotMaterialised(facts.first_parent or b"", facts.closure_missing)

    counts: dict[Bucket, int] = dict.fromkeys(BUCKET_PRECEDENCE, 0)
    inherited = 0
    for ancestor in facts.ancestors:
        if not ancestor.is_blood_bearing():
            continue
        inherited += 1
        bucket = classify(ancestor)
        if bucket is not None:
            counts[bucket] += 1

    return CBMAccount(
        site_id=facts.site_id,
        commit_id=facts.commit_id,
        inherited=inherited,
        carried=counts[Bucket.CARRIED],
        split_carried=counts[Bucket.SPLIT_CARRIED],
        merge_carried=counts[Bucket.MERGE_CARRIED],
        residue_open=counts[Bucket.RESIDUE_OPEN],
        residue_disposed=counts[Bucket.RESIDUE_DISPOSED],
    )
