# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Where registry clauses come from, and the one in-memory implementation.

The loader talks to a :class:`ClauseVersionSource`, never to a database.  That
boundary exists so that the *resolution algorithm* — which version of which
clause is in force at commit ``c`` — lives in exactly one place and is testable
without a cluster.  A SQL implementation that resolved ancestry in its own
``WITH RECURSIVE`` and an in-memory one that resolved it in Python would be two
algorithms, and the one that runs in production would be the one with no unit
tests.  So the source answers two dumb questions (*what commits can commit c
see* and *what rows exist for this document*) and the loader does the deciding.

WHAT "IN FORCE AT COMMIT c" MEANS HERE
--------------------------------------
For each clause of the document, the version written by the highest-generation
commit that is an ancestor of — or is — ``c``.  Full ancestry, not first-parent:
a clause introduced on a branch that was merged into ``c`` is present at ``c``,
which is what a merge means.

``gen`` is ``1 + max(parent.gen)``, so it strictly increases along any path and
is a correct ordering *within* a line of descent.  Across two branches it is
not: two versions of one clause can share a generation and disagree.  That is a
real, representable history — two people edited the same parameter on two
branches and both branches were merged — and this loader does not resolve it.
It records the parameter as ``ambiguous_at_commit``, which abstains, which
resolves to ``weaken``.  Picking the higher ``commit_id`` would be a tie-break,
and decision D4 (stated for the assignment stage, applied here for the same
reason) says a tie-break is an unrecorded decision by a solver whereas a
blocking row is a recorded decision by a human.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from .errors import RegistrySourceError

__all__ = [
    "ClauseVersionRow",
    "ClauseVersionSource",
    "CommitNode",
    "InMemoryClauseVersionSource",
]


@dataclass(frozen=True, slots=True)
class ClauseVersionRow:
    """One ``mainline.clause_version`` row of the registry document, plus its commit.

    ``ratification_signed`` is ``commit_obj.sig IS NOT NULL`` for the commit that
    wrote this version, and ``ratified_by_sub`` is that commit's ``author_sub``.
    Both are properties of the *commit*, joined here rather than copied onto the
    clause, because a clause that carried its own "signed by" field could assert
    a signature it does not have.

    ``retired_commit`` is ``mainline.clause.retired_commit`` — the clause-level
    retirement pointer.  It is carried on every version row because retirement is
    a fact about the clause and the loader has to know whether the retirement is
    itself reachable from ``as_of_commit``: a parameter retired *after* the
    commit being read is still in force at that commit, and reading it as retired
    would make history change under a re-run.
    """

    clause_uuid: UUID
    commit_id: bytes
    gen: int
    canon_text: str
    canon_sha256: bytes
    ratified_by_sub: str
    ratification_signed: bool
    retired_commit: bytes | None = None


class ClauseVersionSource(Protocol):
    """The two questions the loader asks.  Anything that answers them will do."""

    def ancestry(self, as_of_commit: bytes) -> frozenset[bytes]:
        """Every commit reachable from ``as_of_commit``, **including it**.

        :raises RegistrySourceError: if ``as_of_commit`` is not a commit this
            source knows.  Returning an empty set would be indistinguishable
            from a legitimately empty history and would silently produce an
            empty registry.
        """
        ...

    def registry_versions(
        self, *, site_id: UUID, doc_code: str
    ) -> Sequence[ClauseVersionRow]:
        """Every clause version of that document for that site, any commit.

        Unfiltered by commit on purpose: reachability is the loader's decision,
        and a source that pre-filtered would be making it.
        """
        ...


@dataclass(frozen=True, slots=True)
class CommitNode:
    """A commit in a test or seeding DAG.  ``parents`` in ``parent_ord`` order."""

    commit_id: bytes
    parents: tuple[bytes, ...] = ()
    author_sub: str = "sub-unknown"
    signed: bool = False


@dataclass
class InMemoryClauseVersionSource:
    """A source backed by dictionaries.  Used by the seeder and by every unit test.

    Not a mock: it is the same object the seeder builds a document in before
    handing it to a writer, so the unit tests exercise the code path the seeder
    exercises.  A mock would let the tests agree with a fiction.
    """

    commits: dict[bytes, CommitNode] = field(default_factory=dict)
    rows: list[ClauseVersionRow] = field(default_factory=list)
    site_id: UUID | None = None
    doc_code: str | None = None

    def add_commit(
        self,
        commit_id: bytes,
        *,
        parents: Iterable[bytes] = (),
        author_sub: str = "sub-unknown",
        signed: bool = False,
    ) -> CommitNode:
        """Record one commit and its parents, in ``parent_ord`` order."""
        node = CommitNode(
            commit_id=commit_id,
            parents=tuple(parents),
            author_sub=author_sub,
            signed=signed,
        )
        self.commits[commit_id] = node
        return node

    def add_version(self, row: ClauseVersionRow) -> None:
        """Record one clause version.  Order is irrelevant; the loader sorts."""
        self.rows.append(row)

    def ancestry(self, as_of_commit: bytes) -> frozenset[bytes]:
        """Walk every parent edge from ``as_of_commit``; raise on an unknown commit."""
        if as_of_commit not in self.commits:
            raise RegistrySourceError(
                f"commit {as_of_commit.hex()[:12]} is unknown to this source; the "
                "registry as of an unknown commit is unknown, not empty"
            )
        seen: set[bytes] = set()
        stack = [as_of_commit]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            node = self.commits.get(current)
            if node is None:
                raise RegistrySourceError(
                    f"commit {current.hex()[:12]} is referenced as a parent but is not "
                    "in this source; the ancestry cannot be walked"
                )
            stack.extend(node.parents)
        return frozenset(seen)

    def registry_versions(
        self, *, site_id: UUID, doc_code: str
    ) -> Sequence[ClauseVersionRow]:
        """Every recorded version, unfiltered by commit — reachability is the loader's."""
        if self.site_id is not None and site_id != self.site_id:
            return ()
        if self.doc_code is not None and doc_code != self.doc_code:
            return ()
        return tuple(self.rows)

    def commit_metadata(self) -> Mapping[bytes, CommitNode]:
        """A copy of the commit DAG, for a test that wants to assert its shape."""
        return dict(self.commits)
