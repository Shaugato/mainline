# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Assemble the world stage 2 renders against.

Two sources, and the split is deliberate.

**Stage 1 is rebuilt in memory** by :func:`mainline_corpus.skeleton.build.build_skeleton`,
exactly as ``corpus-blame-key`` does.  It is pure, it takes a couple of seconds, and its output
tree is not committed — a render stage that required somebody else's ``--out`` directory could
not verify itself on a clean checkout, which is the one thing the judge-facing bundle must be
able to do.

**Stages 1b and the MOC stream are read from their committed fixture trees** —
``fixtures/corpus/answer-key/`` and ``fixtures/corpus/moc-stream/``.  Those *are* committed, so
reading them costs nothing and, more importantly, the JSONL rows are the published interface
between workers.  Reaching into ``AnswerKey``'s dataclasses instead would couple this stage to
another worker's internals, which is how two workers end up unable to change anything.

Nothing here writes.  Nothing here draws a random number.  Nothing here reads a clock.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..skeleton.build import build_skeleton

__all__ = ["ANSWER_KEY_RELPATH", "MOC_STREAM_RELPATH", "World", "load_world", "read_jsonl"]

ANSWER_KEY_RELPATH: Final[str] = "verticals/mainline/fixtures/corpus/answer-key"
MOC_STREAM_RELPATH: Final[str] = "verticals/mainline/fixtures/corpus/moc-stream"


class CorpusUnavailable(RuntimeError):
    """A fixture tree stage 2 needs is absent or incomplete."""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file into a list of dicts, refusing a truncated line."""
    if not path.is_file():
        raise CorpusUnavailable(
            f"{path}: absent. Stage 2 renders against the committed answer-key and MOC-stream "
            "trees; without them there is nothing to render and a partial corpus is worse than "
            "no corpus."
        )
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise CorpusUnavailable(f"{path}:{number}: not valid JSON ({exc})") from exc
            if not isinstance(parsed, dict):
                raise CorpusUnavailable(f"{path}:{number}: expected an object")
            rows.append(parsed)
    return rows


def _index(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row[field])
        if key in out:
            raise CorpusUnavailable(f"duplicate {field}={key!r}; the corpus index would be lossy")
        out[key] = dict(row)
    return out


def _group(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row[field]), []).append(dict(row))
    return out


@dataclass(frozen=True, slots=True)
class World:
    """Every row stage 2 reads, indexed the way stage 2 reads it."""

    # ── stage 1, rebuilt ────────────────────────────────────────────────────────────────
    site_by_id: dict[str, dict[str, Any]]
    asset_by_tag: dict[str, dict[str, Any]]
    #: Keyed by ``doc_id``, never by ``doc_code``: the fleet-sibling injector puts the *same*
    #: OEM alert code at three sites deliberately, so a code is not an identity.
    doc_by_id: dict[str, dict[str, Any]]
    doc_registry_by_id: dict[str, dict[str, Any]]
    #: ``"<SITE>/<DOC-CODE>" -> doc_id``, which is how a ``revision_key`` names a document.
    doc_id_by_site_code: dict[str, str]
    doc_revisions: list[dict[str, Any]]
    events: list[dict[str, Any]]
    event_registry_by_id: dict[str, dict[str, Any]]
    control_failures_by_event: dict[str, list[dict[str, Any]]]
    change_request_by_ref: dict[str, dict[str, Any]]

    # ── stage 1b + MOC stream, read from committed fixtures ─────────────────────────────
    clause_registry_by_key: dict[str, dict[str, Any]]
    clause_revisions: list[dict[str, Any]]
    blame_registry: list[dict[str, Any]]
    vocabulary_drift: list[dict[str, Any]]
    moc_dossiers: list[dict[str, Any]]
    spine: dict[str, Any]

    # ── derived ─────────────────────────────────────────────────────────────────────────
    doc_revision_by_key: dict[str, dict[str, Any]]
    clause_revisions_by_revision: dict[str, list[dict[str, Any]]]
    quote_refs_by_revision: dict[str, list[dict[str, Any]]]
    spine_revision_keys: frozenset[str]

    def event_ref_by_id(self) -> dict[str, str]:
        """``event_id -> external_ref``."""
        return {str(row["event_id"]): str(row["external_ref"]) for row in self.events}

    def site_code(self, site_id: str) -> str:
        """Return the upper-case site code for a site id."""
        return str(self.site_by_id[site_id]["code"])

    def iter_events(self) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
        """``(event_row, registry_row)`` in ``external_ref`` order."""
        for row in sorted(self.events, key=lambda item: str(item["external_ref"])):
            yield row, self.event_registry_by_id[str(row["event_id"])]


def load_world(*, repo_root: Path) -> World:
    """Rebuild stage 1 and read the committed stage-1b and MOC trees."""
    skeleton = build_skeleton()
    answer_key = repo_root / ANSWER_KEY_RELPATH
    moc_stream = repo_root / MOC_STREAM_RELPATH

    clause_registry = read_jsonl(answer_key / "clause_registry.jsonl")
    clause_revisions = read_jsonl(answer_key / "clause_revision.jsonl")
    blame_registry = read_jsonl(answer_key / "blame_edge_registry.jsonl")
    vocabulary_drift = read_jsonl(answer_key / "injector_vocabulary_drift.jsonl")
    moc_dossiers = read_jsonl(moc_stream / "moc_dossier.jsonl")

    spine_path = answer_key / "spine.json"
    if not spine_path.is_file():
        raise CorpusUnavailable(f"{spine_path}: absent; the camera-facing set is defined by it")
    spine = json.loads(spine_path.read_text(encoding="utf-8"))

    doc_revisions = skeleton.documents.revision_rows()
    doc_revision_by_key = _index(doc_revisions, "revision_key")

    # Every quote_ref names the revision it lives in: `quote:<revision_key>#<kind>/<event_ref>`.
    # Grouping them here means the renderer for a revision is handed exactly the citation lines
    # it must satisfy, in a fixed order, and can neither invent one nor miss one.
    quote_refs_by_revision: dict[str, list[dict[str, Any]]] = {}
    seen_refs: dict[str, dict[str, Any]] = {}
    for row in blame_registry:
        ref = row.get("quote_ref")
        if not ref:
            continue
        revision_key = str(ref).split(":", 1)[1].split("#", 1)[0]
        if revision_key not in doc_revision_by_key:
            raise CorpusUnavailable(
                f"quote_ref {ref!r} names revision {revision_key!r}, which stage 1 did not "
                "produce. A quote that has no document to live in cannot be bound, and an "
                "unbindable quote_ref is a broken answer key, not a rendering problem."
            )
        if str(ref) in seen_refs:
            continue  # several clauses may cite one line; the line is rendered once
        record = {
            "quote_ref": str(ref),
            "kind": str(row.get("quote_ref_kind") or "revision_history_line"),
            "event_ref": str(row["event_ref"]),
            "severity_gate": row.get("severity_gate"),
            "control_class": row.get("control_class"),
            "hazard_energy": row.get("hazard_energy"),
            "effective_on": row.get("effective_on"),
        }
        seen_refs[str(ref)] = record
        quote_refs_by_revision.setdefault(revision_key, []).append(record)
    for records in quote_refs_by_revision.values():
        records.sort(key=lambda item: (item["kind"], item["event_ref"], item["quote_ref"]))

    spine_revision_keys = frozenset(
        str(item["revision_key"]) for item in spine.get("revisions", ())
    )

    site_by_id = _index(skeleton.sites.registry_rows(), "site_id")
    doc_rows = skeleton.documents.rows()
    doc_id_by_site_code: dict[str, str] = {}
    for row in doc_rows:
        code = f"{site_by_id[str(row['site_id'])]['code']}/{row['doc_code']}"
        if code in doc_id_by_site_code:
            raise CorpusUnavailable(f"two documents share the identity {code!r}")
        doc_id_by_site_code[code] = str(row["doc_id"])

    return World(
        site_by_id=site_by_id,
        asset_by_tag=_index(skeleton.assets.asset_rows(), "tag"),
        doc_by_id=_index(doc_rows, "doc_id"),
        doc_registry_by_id=_index(skeleton.documents.registry_rows(), "doc_id"),
        doc_id_by_site_code=doc_id_by_site_code,
        doc_revisions=doc_revisions,
        events=skeleton.events.rows(),
        event_registry_by_id=_index(skeleton.events.registry_rows(), "event_id"),
        control_failures_by_event=_group(skeleton.events.control_failure_rows(), "event_id"),
        change_request_by_ref=_index(skeleton.mocs.registry_rows(), "external_ref"),
        clause_registry_by_key=_index(clause_registry, "clause_key"),
        clause_revisions=clause_revisions,
        blame_registry=blame_registry,
        vocabulary_drift=vocabulary_drift,
        moc_dossiers=moc_dossiers,
        spine=spine,
        doc_revision_by_key=doc_revision_by_key,
        clause_revisions_by_revision=_group(clause_revisions, "revision_key"),
        quote_refs_by_revision=quote_refs_by_revision,
        spine_revision_keys=spine_revision_keys,
    )
