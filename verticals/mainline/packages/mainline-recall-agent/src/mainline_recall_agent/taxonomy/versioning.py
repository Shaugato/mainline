# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The taxonomy version is a commit, and the diff is a first-class artefact.

``diachronic-recall.md`` §3 ends on the sentence this module exists to make true: *"The
taxonomy version is a commit and every bond records it: a re-induction silently changes what
the gate would have recalled, and that must be attributable."*

Read that failure mode carefully, because it is the one MAINLINE cannot detect after the
fact.  Suppose a 2019 fatality was filed under a level-3 activity, and a 2027 re-induction
merges that activity into a broader one.  Every arm the gate generates is derived from the
*current* taxonomy.  The 2019 event is still in the archive, still severity 5, still bonded
— to a scope that the new arm set no longer visits in the same way.  Nothing errors.  The
permit merges.  The only artefact that can ever explain it is a record that says: at version
N the label was this, at version N+1 it is that, here is who ran it, on what model, under
what prompt, and here is what the holdout said.

So :class:`TaxonomyVersion` is emitted by every induction run whether or not anything
changed, ``mainline.event_bond.taxonomy_ver`` and ``mainline.event_cue.taxonomy_ver`` pin
every row to one, and :class:`LabelDiff` is computed rather than described.

Renames are only claimed when they can be shown.  Without document assignments, a removed
label and an added label are two facts and *"it was renamed"* is a story; with assignments,
an overlap of the document sets is evidence, and the threshold that was applied is recorded
in the diff.  A version record that overclaims is worse than one that says less.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from mainline_recall_agent.providers.canonical import canonical_json, sha256_hex

from .errors import TaxonomyVersionError
from .models import TaxonomySnapshot

__all__ = [
    "DEFAULT_RENAME_OVERLAP",
    "LabelDiff",
    "TaxonomyVersion",
    "diff_labels",
    "diff_snapshots",
    "emit_version",
]

#: Jaccard overlap of assigned document sets above which a (removed, added) pair at the
#: same level and parent is reported as a rename rather than as a deletion plus an
#: insertion.  Recorded in the diff so the number is arguable rather than assumed.
DEFAULT_RENAME_OVERLAP: Final[float] = 0.5

_LabelKey = tuple[int, str, str]


@dataclass(frozen=True, slots=True)
class LabelDiff:
    """What changed between two taxonomy snapshots.

    Identity is ``(level, activity_root, label)``.  Deliberately *not* ``scope_id``: scope
    ids are derived from the label path, so every rename would otherwise present as a
    delete plus an insert with no way to tell it from a genuine one.
    """

    added: tuple[_LabelKey, ...] = ()
    removed: tuple[_LabelKey, ...] = ()
    renamed: tuple[tuple[_LabelKey, _LabelKey], ...] = ()
    reparented: tuple[tuple[_LabelKey, str, str], ...] = ()
    unchanged: int = 0
    rename_overlap: float = DEFAULT_RENAME_OVERLAP
    rename_evidence: str = "none: no document assignments were supplied"

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.renamed or self.reparented)

    def summary(self) -> str:
        return (
            f"+{len(self.added)} -{len(self.removed)} ~{len(self.renamed)} renamed "
            f"^{len(self.reparented)} reparented ={self.unchanged} unchanged"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": [list(key) for key in self.added],
            "removed": [list(key) for key in self.removed],
            "renamed": [[list(before), list(after)] for before, after in self.renamed],
            "reparented": [
                [list(key), before, after] for key, before, after in self.reparented
            ],
            "unchanged": self.unchanged,
            "rename_overlap_threshold": self.rename_overlap,
            "rename_evidence": self.rename_evidence,
            "summary": self.summary(),
        }


def _parent_label(snapshot: TaxonomySnapshot, scope_id: str) -> str:
    node = snapshot.by_scope(scope_id)
    if node is None or node.parent_scope is None:
        return ""
    parent = snapshot.by_scope(node.parent_scope)
    return parent.label if parent else ""


def _assignments_by_key(
    snapshot: TaxonomySnapshot, assignments: Mapping[str, str]
) -> dict[_LabelKey, set[str]]:
    out: dict[_LabelKey, set[str]] = {}
    for doc_id, scope_id in assignments.items():
        node = snapshot.by_scope(scope_id)
        if node is None:
            continue
        out.setdefault((node.level, node.activity_root, node.label), set()).add(doc_id)
    return out


def diff_snapshots(
    before: TaxonomySnapshot | None,
    after: TaxonomySnapshot,
    *,
    before_assignments: Mapping[str, str] | None = None,
    after_assignments: Mapping[str, str] | None = None,
    rename_overlap: float = DEFAULT_RENAME_OVERLAP,
) -> LabelDiff:
    """Diff two snapshots by label identity, promoting pairs to renames when shown.

    ``before=None`` is the first induction: everything is an addition, which is a true and
    useful thing for a version record to say.
    """
    after_keys = after.label_keys()
    if before is None:
        return LabelDiff(
            added=tuple(sorted(after_keys)),
            unchanged=0,
            rename_overlap=rename_overlap,
            rename_evidence="none: this is the first taxonomy version",
        )
    before_keys = before.label_keys()
    added = set(after_keys - before_keys)
    removed = set(before_keys - after_keys)
    common = before_keys & after_keys

    reparented: list[tuple[_LabelKey, str, str]] = []
    for key in sorted(common):
        node_before = next(
            n for n in before.nodes if (n.level, n.activity_root, n.label) == key
        )
        node_after = next(
            n for n in after.nodes if (n.level, n.activity_root, n.label) == key
        )
        parent_before = _parent_label(before, node_before.scope_id)
        parent_after = _parent_label(after, node_after.scope_id)
        if parent_before != parent_after:
            reparented.append((key, parent_before, parent_after))

    renamed: list[tuple[_LabelKey, _LabelKey]] = []
    evidence = "none: no document assignments were supplied"
    if before_assignments and after_assignments:
        evidence = (
            f"document-set Jaccard >= {rename_overlap} between the removed and added label"
        )
        before_docs = _assignments_by_key(before, before_assignments)
        after_docs = _assignments_by_key(after, after_assignments)
        claimed_added: set[_LabelKey] = set()
        for old in sorted(removed):
            old_docs = before_docs.get(old, set())
            if not old_docs:
                continue
            best_key: _LabelKey | None = None
            best_score = rename_overlap
            for new in sorted(added - claimed_added):
                if new[0] != old[0] or new[1] != old[1]:
                    continue
                new_docs = after_docs.get(new, set())
                if not new_docs:
                    continue
                score = len(old_docs & new_docs) / len(old_docs | new_docs)
                if score >= best_score:
                    best_score = score
                    best_key = new
            if best_key is not None:
                renamed.append((old, best_key))
                claimed_added.add(best_key)
        for old, new in renamed:
            removed.discard(old)
            added.discard(new)

    return LabelDiff(
        added=tuple(sorted(added)),
        removed=tuple(sorted(removed)),
        renamed=tuple(sorted(renamed)),
        reparented=tuple(sorted(reparented)),
        unchanged=len(common) - len(reparented),
        rename_overlap=rename_overlap,
        rename_evidence=evidence,
    )


@dataclass(frozen=True, slots=True)
class TaxonomyVersion:
    """One induction run, recorded so that a later reader can attribute a recall change.

    ``version_digest`` is sha256 over the RFC 8785 canonical form of everything except
    itself.  Two runs that produced the same taxonomy under the same model, prompt,
    register and configuration have the same digest; anything else does not.
    """

    taxonomy_ver: int
    site_id: str
    parent_taxonomy_ver: int | None
    induced_at: datetime
    model: str
    model_is_semantic: bool
    prompt_version: str
    register_id: str
    register_sha256: str
    snapshot: TaxonomySnapshot
    diff: LabelDiff
    config: Mapping[str, Any] = field(default_factory=dict)
    holdout: Mapping[str, Any] | None = None
    classifier_digest: str = ""
    rejection_counts: Mapping[str, int] = field(default_factory=dict)
    rejected_labels: tuple[Mapping[str, Any], ...] = ()
    abstained_documents: int = 0
    failed_batches: tuple[str, ...] = ()
    dropped_groups: tuple[str, ...] = ()
    merge_rounds: int = 0
    merge_converged: bool = True
    merge_fell_back: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.taxonomy_ver < 1:
            raise TaxonomyVersionError(
                "taxonomy_ver is a positive integer", taxonomy_ver=self.taxonomy_ver
            )
        if (
            self.parent_taxonomy_ver is not None
            and self.parent_taxonomy_ver >= self.taxonomy_ver
        ):
            raise TaxonomyVersionError(
                "a taxonomy version's parent must precede it",
                taxonomy_ver=self.taxonomy_ver,
                parent=self.parent_taxonomy_ver,
            )
        if self.snapshot.taxonomy_ver != self.taxonomy_ver:
            raise TaxonomyVersionError(
                "version record and snapshot disagree about taxonomy_ver",
                record=self.taxonomy_ver,
                snapshot=self.snapshot.taxonomy_ver,
            )

    def body(self) -> dict[str, Any]:
        """Everything the digest covers, in canonical-JSON-safe types."""
        return {
            "taxonomy_ver": self.taxonomy_ver,
            "site_id": self.site_id,
            "parent_taxonomy_ver": self.parent_taxonomy_ver,
            "induced_at": self.induced_at.isoformat(),
            "model": self.model,
            "model_is_semantic": self.model_is_semantic,
            "prompt_version": self.prompt_version,
            "register_id": self.register_id,
            "register_sha256": self.register_sha256,
            "classifier_digest": self.classifier_digest,
            "config": dict(sorted(self.config.items())),
            "snapshot": self.snapshot.to_dict(),
            "diff": self.diff.to_dict(),
            "holdout": dict(self.holdout) if self.holdout else None,
            "rejection_counts": dict(sorted(self.rejection_counts.items())),
            "rejected_labels": [dict(entry) for entry in self.rejected_labels],
            "abstained_documents": self.abstained_documents,
            "failed_batches": list(self.failed_batches),
            "dropped_groups": list(self.dropped_groups),
            "merge": {
                "rounds": self.merge_rounds,
                "converged": self.merge_converged,
                "fell_back_to_deterministic_clustering": self.merge_fell_back,
            },
            "notes": self.notes,
        }

    @property
    def version_digest(self) -> str:
        return sha256_hex(canonical_json(self.body()))

    def to_dict(self) -> dict[str, Any]:
        payload = self.body()
        payload["version_digest"] = self.version_digest
        return payload

    def render(self) -> str:
        parent = self.parent_taxonomy_ver if self.parent_taxonomy_ver is not None else "-"
        semantic = "model-induced" if self.model_is_semantic else "NOT model-induced"
        return (
            f"taxonomy_ver {self.taxonomy_ver} (parent {parent}) "
            f"{len(self.snapshot.nodes)} nodes  {self.diff.summary()}\n"
            f"  model {self.model} [{semantic}]  prompt {self.prompt_version}\n"
            f"  register {self.register_id} sha256 {self.register_sha256[:16]}...\n"
            f"  digest {self.version_digest}"
        )


def emit_version(
    *,
    taxonomy_ver: int,
    site_id: str,
    parent: TaxonomySnapshot | None,
    snapshot: TaxonomySnapshot,
    induced_at: datetime,
    model: str,
    model_is_semantic: bool,
    prompt_version: str,
    register_id: str,
    register_sha256: str,
    config: Mapping[str, Any] | None = None,
    parent_taxonomy_ver: int | None = None,
    before_assignments: Mapping[str, str] | None = None,
    after_assignments: Mapping[str, str] | None = None,
    **extra: Any,
) -> TaxonomyVersion:
    """Build a version record, computing the diff against ``parent``."""
    diff = diff_snapshots(
        parent,
        snapshot,
        before_assignments=before_assignments,
        after_assignments=after_assignments,
    )
    return TaxonomyVersion(
        taxonomy_ver=taxonomy_ver,
        site_id=site_id,
        parent_taxonomy_ver=(
            parent_taxonomy_ver
            if parent_taxonomy_ver is not None
            else (parent.taxonomy_ver if parent is not None else None)
        ),
        induced_at=induced_at,
        model=model,
        model_is_semantic=model_is_semantic,
        prompt_version=prompt_version,
        register_id=register_id,
        register_sha256=register_sha256,
        snapshot=snapshot,
        diff=diff,
        config=config or {},
        **extra,
    )


def diff_labels(before: Sequence[str], after: Sequence[str]) -> tuple[
    tuple[str, ...], tuple[str, ...]
]:
    """Plain set difference over label strings — used by reports that have no snapshot."""
    left, right = set(before), set(after)
    return tuple(sorted(right - left)), tuple(sorted(left - right))
