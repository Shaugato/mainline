# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Reconstructing the ``safe_direction`` registry as it stood at one commit.

``load_registry(source, site_id=…, as_of_commit=…)`` and nothing else.  Every
way an entry can fail to answer ends in an :class:`AbstentionReason`, and every
abstention resolves to ``ControlDelta.weaken`` in
:mod:`mainline_domain.registry.resolve`.

**NO CACHE.  ANYWHERE.  ON PURPOSE.**
There is no module-level dictionary in this file, no ``functools.lru_cache``, and
no memo on the registry object.  The obvious optimisation — key a cache on
``(site_id, as_of_commit)`` — is *almost* safe, and "almost" is the problem.  A
commit id is content-addressed, so the same key really does mean the same
history; but the rows the loader reads are also written by the same transaction
that creates a commit, and a cache populated mid-transaction, or populated
before a branch was merged, hands the gate an answer from a history that no
longer describes the database.  The failure it produces is the worst one
available in this system: a *stale direction*, which does not raise, does not
abstain, and silently classifies a weakening as a tightening.  Re-reading a few
hundred clauses is cheaper than being unable to say, under oath, which registry
a verdict was computed against.

The committed test that keeps this honest mutates the source between two loads
at the *same* commit and asserts the second load sees the mutation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from .doc import DOC_CODE
from .encoding import ENCODING_VERSION, decode
from .errors import RegistryEncodingError
from .model import (
    AbstentionReason,
    EntryStatus,
    RegistryEntry,
    Resolution,
    SafeDirection,
    SafeDirectionRegistry,
)
from .source import ClauseVersionRow, ClauseVersionSource

__all__ = ["load_registry"]


def _abstain(
    parameter: str,
    reason: AbstentionReason,
    detail: str,
    entry: RegistryEntry | None = None,
) -> Resolution:
    return Resolution(
        parameter=parameter,
        direction=SafeDirection.ABSTAIN,
        reason=reason,
        entry=entry,
        detail=detail,
    )


def load_registry(
    source: ClauseVersionSource,
    *,
    site_id: UUID,
    as_of_commit: bytes,
    doc_code: str = DOC_CODE,
    require_signature: bool = True,
) -> SafeDirectionRegistry:
    """Build the registry in force at ``as_of_commit``.

    :param require_signature: whether an entry whose ratifying commit carries no
        signature answers.  Defaults to ``True`` and should stay there.  It is a
        parameter only so that the seeding path — which builds a document before
        anything has been signed — can construct a registry to validate its own
        output against, and so that a test can demonstrate the difference the
        signature makes rather than asserting it.  A caller passing ``False`` on
        the gate path has removed the ratification requirement from DIRECTRIX,
        which is the whole mechanism.

    Reachability, generation, retirement, encoding, status, signature and
    uniqueness are each checked, and each failure is recorded against the
    parameter it belongs to rather than dropped.
    """
    reachable = source.ancestry(as_of_commit)
    rows = source.registry_versions(site_id=site_id, doc_code=doc_code)

    visible = [row for row in rows if row.commit_id in reachable]
    document_present = bool(visible)

    by_clause: defaultdict[UUID, list[ClauseVersionRow]] = defaultdict(list)
    for row in visible:
        by_clause[row.clause_uuid].append(row)

    entries: dict[str, RegistryEntry] = {}
    abstentions: dict[str, Resolution] = {}
    #: parameter -> clause that already claimed it, so a duplicate is detectable
    claimed_by: dict[str, UUID] = {}

    for clause_uuid, versions in sorted(by_clause.items(), key=lambda kv: kv[0].bytes):
        head, ambiguity = _head_version(versions)
        if head is None:
            # Ambiguity is keyed by clause, but the caller asks by parameter, so
            # the parameter has to be recovered from *some* candidate.  All the
            # tied candidates are recorded when they disagree about which
            # parameter they even are.
            for parameter in _candidate_parameters(versions):
                abstentions[parameter] = _abstain(
                    parameter,
                    AbstentionReason.AMBIGUOUS_AT_COMMIT,
                    ambiguity
                    or (
                        f"clause {clause_uuid} has two versions at the same generation "
                        f"reachable from {as_of_commit.hex()[:12]}"
                    ),
                )
            continue

        try:
            decoded = decode(head.canon_text)
        except RegistryEncodingError as exc:
            # A malformed clause has no parameter key to be filed under, so it is
            # filed under the clause id.  It still blocks: the parameter it was
            # meant to cover falls through to NOT_IN_REGISTRY, and this row is
            # what tells an operator which clause to fix.
            abstentions[f"clause:{clause_uuid}"] = _abstain(
                f"clause:{clause_uuid}",
                AbstentionReason.MALFORMED_CLAUSE,
                str(exc),
            )
            continue

        parameter = decoded.parameter

        if head.retired_commit is not None and head.retired_commit in reachable:
            abstentions[parameter] = _abstain(
                parameter,
                AbstentionReason.RETIRED,
                f"the {parameter!r} entry was retired in commit "
                f"{head.retired_commit.hex()[:12]}, which is reachable from "
                f"{as_of_commit.hex()[:12]}",
            )
            continue

        previous = claimed_by.get(parameter)
        if previous is not None:
            # Two live clauses ratifying the same parameter.  Neither wins, and
            # the one that was already accepted is withdrawn: a registry that
            # answered from whichever clause happened to sort first would be
            # answering from an arbitrary choice between two signed statements.
            entries.pop(parameter, None)
            abstentions[parameter] = _abstain(
                parameter,
                AbstentionReason.DUPLICATE_PARAMETER,
                f"{parameter!r} is ratified by two live clauses ({previous} and "
                f"{clause_uuid}) at commit {as_of_commit.hex()[:12]}; neither answers",
            )
            continue
        claimed_by[parameter] = clause_uuid

        entry = RegistryEntry(
            parameter=parameter,
            dimension_label=decoded.dimension_label,
            dimensionality=decoded.dimensionality,
            direction=decoded.direction,
            status=decoded.status,
            rationale=decoded.rationale,
            clause_uuid=clause_uuid,
            ratification_commit=head.commit_id,
            ratified_by_sub=head.ratified_by_sub,
            ratification_signed=head.ratification_signed,
            gen=head.gen,
            canon_sha256=head.canon_sha256,
        )

        if decoded.status is EntryStatus.WITHDRAWN:
            abstentions[parameter] = _abstain(
                parameter,
                AbstentionReason.WITHDRAWN,
                f"{parameter!r} was withdrawn in commit {head.commit_id.hex()[:12]}",
                entry,
            )
            continue
        if decoded.status is not EntryStatus.RATIFIED:
            abstentions[parameter] = _abstain(
                parameter,
                AbstentionReason.NOT_RATIFIED,
                f"{parameter!r} is {decoded.status.value}, not RATIFIED. A proposed "
                "direction is a suggestion; ratifying it is a signed commit, and "
                "until then a move in this parameter cannot be classified",
                entry,
            )
            continue
        if require_signature and not head.ratification_signed:
            abstentions[parameter] = _abstain(
                parameter,
                AbstentionReason.UNSIGNED_RATIFICATION,
                f"{parameter!r} is marked RATIFIED but commit "
                f"{head.commit_id.hex()[:12]} carries no signature. The clause says "
                "somebody decided; the commit does not say who",
                entry,
            )
            continue

        entries[parameter] = entry

    return SafeDirectionRegistry(
        site_id=site_id,
        as_of_commit=as_of_commit,
        doc_code=doc_code,
        entries=entries,
        abstentions=abstentions,
        encoding_version=ENCODING_VERSION,
        document_present=document_present,
    )


def _head_version(
    versions: Sequence[ClauseVersionRow],
) -> tuple[ClauseVersionRow | None, str | None]:
    """The version in force, or ``(None, why-not)`` when the history is ambiguous.

    Two rows at the same maximum generation are only ambiguous if they *say
    different things*: the same clause version can legitimately be recorded
    against two commits of equal generation on two branches that were both
    merged, and if their ``canon_sha256`` agree there is nothing to resolve.
    Comparing the digest rather than the text is deliberate — it is the same
    equality the rest of the system uses for clause identity.
    """
    top = max(row.gen for row in versions)
    candidates = [row for row in versions if row.gen == top]
    digests = {row.canon_sha256 for row in candidates}
    if len(digests) > 1:
        commits = ", ".join(sorted(row.commit_id.hex()[:12] for row in candidates))
        return None, (
            f"generation {top} carries {len(digests)} different texts for this clause "
            f"(commits {commits}); the registry does not break the tie"
        )
    # Same text; pick deterministically so the reported ratification commit is
    # stable across runs.  This is not a tie-break between two answers — there is
    # one answer — it is a tie-break between two equally valid citations of it.
    return min(candidates, key=lambda row: row.commit_id), None


def _candidate_parameters(versions: Sequence[ClauseVersionRow]) -> frozenset[str]:
    """Parameter keys mentioned by any candidate version, for reporting only."""
    found: set[str] = set()
    for row in versions:
        try:
            found.add(decode(row.canon_text).parameter)
        except RegistryEncodingError:
            continue
    return frozenset(found)
