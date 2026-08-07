# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The registry is read AS OF A COMMIT, holds no cache, and refuses to break ties.

Three claims, and each of them is the difference between DIRECTRIX and a lookup
table:

1. **A verdict is re-derivable under the registry that existed when it was
   issued.**  Reading at an earlier commit gives the earlier answer, including
   "that parameter did not exist yet".
2. **No cache.**  A stale direction does not raise and does not abstain; it
   silently classifies a weakening as a tightening, which is the worst failure
   available in this system.  The test mutates the source between two loads at
   the same commit and requires the second to see it.
3. **A same-generation conflict is not resolved.**  Two branches that both edited
   one parameter and both merged produce ``ambiguous_at_commit``, which abstains,
   which blocks.  Picking the higher commit id would be a tie-break — an
   unrecorded decision by a program, where a blocking row is a recorded decision
   by a person (decision D4, applied here for the same reason it is applied to
   the assignment stage).
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from mainline_domain.canon import canon_digest
from mainline_domain.registry import (
    AbstentionReason,
    ClauseVersionRow,
    EntryStatus,
    InMemoryClauseVersionSource,
    RegistrySourceError,
    SafeDirection,
    clause_uuid_for,
    encode,
    load_registry,
)
from mainline_domain.registry.doc import DOC_CODE

SITE = uuid.UUID("9f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f")


def commit(label: str) -> bytes:
    return hashlib.sha256(f"mainline-directrix-test/{label}".encode()).digest()


def entry_row(
    *,
    parameter: str,
    direction: SafeDirection,
    commit_id: bytes,
    gen: int,
    dimension_label: str = "pressure",
    status: EntryStatus = EntryStatus.RATIFIED,
    rationale: str = "stated so that a later reader has something to disagree with",
    signed: bool = True,
    author: str = "sub-principal-engineer",
    retired_commit: bytes | None = None,
) -> ClauseVersionRow:
    text = encode(
        parameter=parameter,
        dimension_label=dimension_label,
        direction=direction,
        status=status,
        rationale=rationale,
    )
    return ClauseVersionRow(
        clause_uuid=clause_uuid_for(SITE, parameter),
        commit_id=commit_id,
        gen=gen,
        canon_text=text,
        canon_sha256=canon_digest(text),
        ratified_by_sub=author,
        ratification_signed=signed,
        retired_commit=retired_commit,
    )


def linear_history() -> tuple[InMemoryClauseVersionSource, bytes, bytes, bytes]:
    """c1 ratifies max_operating_pressure; c2 adds min_ppe_level; c3 retires nothing.

    A deliberately boring three-commit line, because the interesting behaviour is
    what each commit *cannot* see.
    """
    source = InMemoryClauseVersionSource(site_id=SITE, doc_code=DOC_CODE)
    c1, c2, c3 = commit("c1"), commit("c2"), commit("c3")
    source.add_commit(c1, parents=(), author_sub="sub-a", signed=True)
    source.add_commit(c2, parents=(c1,), author_sub="sub-b", signed=True)
    source.add_commit(c3, parents=(c2,), author_sub="sub-c", signed=True)

    source.add_version(
        entry_row(
            parameter="max_operating_pressure",
            direction=SafeDirection.LOWER_IS_SAFER,
            commit_id=c1,
            gen=1,
        )
    )
    source.add_version(
        entry_row(
            parameter="min_ppe_level",
            direction=SafeDirection.HIGHER_IS_SAFER,
            commit_id=c2,
            gen=2,
            dimension_label="ordinal",
        )
    )
    return source, c1, c2, c3


def test_an_earlier_commit_sees_an_earlier_registry() -> None:
    source, c1, c2, _c3 = linear_history()

    early = load_registry(source, site_id=SITE, as_of_commit=c1)
    late = load_registry(source, site_id=SITE, as_of_commit=c2)

    assert early.parameters() == {"max_operating_pressure"}
    assert late.parameters() == {"max_operating_pressure", "min_ppe_level"}

    assert early.safe_direction("min_ppe_level") is SafeDirection.ABSTAIN
    assert early.resolve("min_ppe_level").reason is AbstentionReason.NOT_IN_REGISTRY
    assert late.safe_direction("min_ppe_level") is SafeDirection.HIGHER_IS_SAFER


def test_a_later_edit_is_invisible_to_the_commit_that_predates_it() -> None:
    """The whole point: last March's verdict is re-derivable under last March's registry."""
    source, c1, _c2, c3 = linear_history()
    source.add_version(
        entry_row(
            parameter="max_operating_pressure",
            direction=SafeDirection.HIGHER_IS_SAFER,  # somebody flipped it
            commit_id=c3,
            gen=3,
            rationale="a later and, one hopes, well-argued reversal",
        )
    )

    at_c1 = load_registry(source, site_id=SITE, as_of_commit=c1)
    at_c3 = load_registry(source, site_id=SITE, as_of_commit=c3)

    assert at_c1.safe_direction("max_operating_pressure") is SafeDirection.LOWER_IS_SAFER
    assert at_c3.safe_direction("max_operating_pressure") is SafeDirection.HIGHER_IS_SAFER


def test_the_loader_holds_no_cache() -> None:
    """Two loads at the SAME commit, with the source mutated in between.

    A cache keyed on ``(site, commit)`` is almost safe — commit ids are
    content-addressed — and "almost" is the problem: the rows are written by the
    same transaction that creates the commit, so a cache populated mid-write, or
    before a branch merged, hands the gate a direction from a history that no
    longer describes the database.
    """
    source, c1, _c2, _c3 = linear_history()

    first = load_registry(source, site_id=SITE, as_of_commit=c1)
    assert first.parameters() == {"max_operating_pressure"}

    source.add_version(
        entry_row(
            parameter="isolation_point_count",
            direction=SafeDirection.HIGHER_IS_SAFER,
            commit_id=c1,
            gen=1,
            dimension_label="count",
        )
    )

    second = load_registry(source, site_id=SITE, as_of_commit=c1)
    assert second.parameters() == {"max_operating_pressure", "isolation_point_count"}, (
        "the second load returned the first load's answer; a cache has been "
        "introduced and a stale direction is now possible"
    )


def test_a_merge_makes_a_branch_entry_visible() -> None:
    """Reachability is over ALL parents, not first-parent, because that is what merging means."""
    source = InMemoryClauseVersionSource(site_id=SITE, doc_code=DOC_CODE)
    base, branch, merge = commit("base"), commit("branch"), commit("merge")
    source.add_commit(base, parents=(), signed=True)
    source.add_commit(branch, parents=(base,), signed=True)
    source.add_commit(merge, parents=(base, branch), signed=True)
    source.add_version(
        entry_row(
            parameter="min_escape_route_count",
            direction=SafeDirection.HIGHER_IS_SAFER,
            commit_id=branch,
            gen=2,
            dimension_label="count",
        )
    )

    assert load_registry(source, site_id=SITE, as_of_commit=base).parameters() == frozenset()
    assert load_registry(source, site_id=SITE, as_of_commit=merge).parameters() == {
        "min_escape_route_count"
    }


def test_two_branches_that_disagree_abstain_rather_than_being_tie_broken() -> None:
    """The same clause, same generation, two texts, both merged. Nobody wins."""
    source = InMemoryClauseVersionSource(site_id=SITE, doc_code=DOC_CODE)
    base, left, right, merge = commit("b"), commit("l"), commit("r"), commit("m")
    source.add_commit(base, parents=(), signed=True)
    source.add_commit(left, parents=(base,), signed=True)
    source.add_commit(right, parents=(base,), signed=True)
    source.add_commit(merge, parents=(left, right), signed=True)

    source.add_version(
        entry_row(
            parameter="max_operating_pressure",
            direction=SafeDirection.LOWER_IS_SAFER,
            commit_id=left,
            gen=2,
        )
    )
    source.add_version(
        entry_row(
            parameter="max_operating_pressure",
            direction=SafeDirection.HIGHER_IS_SAFER,
            commit_id=right,
            gen=2,
            rationale="the other branch, arguing the opposite and equally sincerely",
        )
    )

    registry = load_registry(source, site_id=SITE, as_of_commit=merge)
    assert registry.parameters() == frozenset()
    resolution = registry.resolve("max_operating_pressure")
    assert resolution.direction is SafeDirection.ABSTAIN
    assert resolution.reason is AbstentionReason.AMBIGUOUS_AT_COMMIT


def test_the_same_text_on_two_branches_is_not_ambiguous() -> None:
    """Ambiguity is disagreement, not duplication.

    Two commits of equal generation recording the *identical* clause is an
    ordinary consequence of merging, and blocking on it would make the registry
    unusable on any repository where two people made the same edit.
    """
    source = InMemoryClauseVersionSource(site_id=SITE, doc_code=DOC_CODE)
    base, left, right, merge = commit("b2"), commit("l2"), commit("r2"), commit("m2")
    for cid, parents in ((base, ()), (left, (base,)), (right, (base,)), (merge, (left, right))):
        source.add_commit(cid, parents=parents, signed=True)
    for cid in (left, right):
        source.add_version(
            entry_row(
                parameter="max_operating_pressure",
                direction=SafeDirection.LOWER_IS_SAFER,
                commit_id=cid,
                gen=2,
            )
        )

    registry = load_registry(source, site_id=SITE, as_of_commit=merge)
    assert registry.safe_direction("max_operating_pressure") is SafeDirection.LOWER_IS_SAFER


def test_two_live_clauses_claiming_one_parameter_both_lose() -> None:
    """Neither answers, because answering from whichever sorted first is an arbitrary choice."""
    source = InMemoryClauseVersionSource(site_id=SITE, doc_code=DOC_CODE)
    c1 = commit("dup")
    source.add_commit(c1, parents=(), signed=True)

    first = entry_row(
        parameter="max_operating_pressure",
        direction=SafeDirection.LOWER_IS_SAFER,
        commit_id=c1,
        gen=1,
    )
    second = ClauseVersionRow(
        clause_uuid=uuid.uuid4(),  # a DIFFERENT clause saying the same parameter
        commit_id=c1,
        gen=1,
        canon_text=first.canon_text,
        canon_sha256=first.canon_sha256,
        ratified_by_sub=first.ratified_by_sub,
        ratification_signed=True,
    )
    source.add_version(first)
    source.add_version(second)

    registry = load_registry(source, site_id=SITE, as_of_commit=c1)
    assert registry.parameters() == frozenset()
    assert (
        registry.resolve("max_operating_pressure").reason
        is AbstentionReason.DUPLICATE_PARAMETER
    )


def test_a_retirement_reachable_from_the_commit_abstains_and_a_later_one_does_not() -> None:
    source = InMemoryClauseVersionSource(site_id=SITE, doc_code=DOC_CODE)
    c1, c2 = commit("live"), commit("retire")
    source.add_commit(c1, parents=(), signed=True)
    source.add_commit(c2, parents=(c1,), signed=True)

    source.add_version(
        entry_row(
            parameter="max_operating_pressure",
            direction=SafeDirection.LOWER_IS_SAFER,
            commit_id=c1,
            gen=1,
            retired_commit=c2,
        )
    )

    at_c1 = load_registry(source, site_id=SITE, as_of_commit=c1)
    assert at_c1.safe_direction("max_operating_pressure") is SafeDirection.LOWER_IS_SAFER, (
        "a parameter retired AFTER the commit being read is still in force at that "
        "commit; reading it as retired would make history change under a re-run"
    )

    at_c2 = load_registry(source, site_id=SITE, as_of_commit=c2)
    assert at_c2.resolve("max_operating_pressure").reason is AbstentionReason.RETIRED


def test_a_malformed_clause_blocks_instead_of_crashing_the_gate() -> None:
    source = InMemoryClauseVersionSource(site_id=SITE, doc_code=DOC_CODE)
    c1 = commit("garbled")
    source.add_commit(c1, parents=(), signed=True)
    source.add_version(
        ClauseVersionRow(
            clause_uuid=clause_uuid_for(SITE, "max_operating_pressure"),
            commit_id=c1,
            gen=1,
            canon_text="SAFE-DIRECTION REGISTRY ENTRY. Parameter: max_operating_pressure.",
            canon_sha256=canon_digest("garbled"),
            ratified_by_sub="sub-a",
            ratification_signed=True,
        )
    )

    registry = load_registry(source, site_id=SITE, as_of_commit=c1)
    assert registry.parameters() == frozenset()
    malformed = [
        resolution
        for resolution in registry.abstentions.values()
        if resolution.reason is AbstentionReason.MALFORMED_CLAUSE
    ]
    assert len(malformed) == 1
    # The parameter it was meant to cover still blocks, via the ordinary route.
    assert registry.safe_direction("max_operating_pressure") is SafeDirection.ABSTAIN


def test_an_unknown_commit_raises_rather_than_returning_an_empty_registry() -> None:
    """An unknown history is unknown, not empty.

    An empty registry abstains on everything, which blocks everything, which
    looks like a policy decision.  A raise looks like what it is.
    """
    source, _c1, _c2, _c3 = linear_history()
    with pytest.raises(RegistrySourceError):
        load_registry(source, site_id=SITE, as_of_commit=commit("never-happened"))


def test_the_registry_is_immutable_once_loaded() -> None:
    source, c1, _c2, _c3 = linear_history()
    registry = load_registry(source, site_id=SITE, as_of_commit=c1)
    with pytest.raises(TypeError):
        registry.entries["max_operating_pressure"] = None  # type: ignore[index]


def test_a_document_that_does_not_exist_says_so() -> None:
    source = InMemoryClauseVersionSource(site_id=SITE, doc_code=DOC_CODE)
    c1 = commit("empty")
    source.add_commit(c1, parents=(), signed=True)
    registry = load_registry(source, site_id=SITE, as_of_commit=c1)
    assert registry.resolve("anything").reason is AbstentionReason.DOCUMENT_ABSENT
