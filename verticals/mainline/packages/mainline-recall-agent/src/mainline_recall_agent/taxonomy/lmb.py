# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Level-Materialised Bonds: one cue row per archival level, per populated facet.

This is the correction that makes the ancestor walk non-vacuous, and it is worth stating
the failure it corrects before the code that avoids it.

``event_cue_embedding``'s vector index is ``cue_scoped_idx (site_id, scope_id, facet, emb)``
and C-SPANN maintains **a separate K-means tree per distinct prefix value** — verified
verbatim from Cockroach Labs' own C-SPANN post and restated in ARCHITECTURE §5.4.  Two
consequences follow, and they pull in opposite directions:

* If every cue inherits **one** scope — say the level-1 ``activity_root`` — then every
  ancestor shares one prefix value, and *"one constrained ANN arm per ancestor"* collapses
  to one arm.  The multi-level design is then a slogan: the query plan is identical to a
  single-scope search.
* If every cue carries only its **leaf** scope, a fleet with ~2 000 level-3 activities over
  1 M vectors puts ~500 vectors in each tree, which is a region where approximate nearest
  neighbour is pointless and a scan would be faster.

Writing one cue row *per level of the event's archival path* resolves both.  Tree sizes are
graded — the fonds tree is large and behaves like an ANN problem, the file tree is small and
precise — and the **matching level becomes a retrieval feature**: a file-level hit is
stronger evidence than a fonds-level hit, and the fusion layer can see the difference
because it is in the row.  This is ISAD(G) multi-level description implemented as index
partitions.

The arithmetic is therefore load-bearing: an event at depth 3 with 4 populated facets emits
exactly 12 rows, and a level-1-only event emits exactly 4.  Under-emitting is not a
performance regression, it is an incident that a whole class of arms can no longer reach.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mainline_recall_agent.providers.types import FACETS

from .errors import CueEmissionError
from .models import ArchivalPath, CueRow, EventRef, FacetValue
from .sources import ActivityNodeSource, resolve_path

__all__ = [
    "NARRATIVE_FACET",
    "LevelMaterialisedBondWriter",
    "LmbEmission",
    "build_cue_rows",
]

#: The one facet whose text is the event's own words rather than a synthesis.  It is the
#: safety net ARCHITECTURE §5.4 describes ("so nothing depends solely on cue quality"), and
#: it is the only facet written with ``is_derived = false``: the other four are a model's
#: paraphrase of a real workplace death and may never be quoted without their event.
NARRATIVE_FACET: str = "narrative"


@dataclass(frozen=True, slots=True)
class LmbEmission:
    """The rows, plus what was left out and why.

    ``unindexed`` is the case worth naming: every facet took ``insufficient_evidence``, so
    the event is in the archive and in no vector tree at all.  That is a legitimate
    outcome of cue synthesis and a terrible one to discover silently, so it is a field on
    the result rather than an empty list the caller may or may not notice.
    """

    rows: tuple[CueRow, ...]
    path: ArchivalPath
    populated_facets: tuple[str, ...]
    skipped_facets: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def unindexed(self) -> bool:
        return not self.rows

    @property
    def rows_per_level(self) -> int:
        return len(self.populated_facets)

    def scope_facet_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple((row.scope_id, row.facet) for row in self.rows)


def _ordered_populated(facets: Sequence[FacetValue]) -> tuple[FacetValue, ...]:
    """Filter to populated facets and order them by the closed facet vocabulary.

    Ordering by ``FACETS`` rather than by arrival order makes the emitted row sequence a
    function of the content alone, which is what lets two runs of the writer be compared
    byte for byte.
    """
    seen: set[str] = set()
    for value in facets:
        if value.facet in seen:
            raise CueEmissionError(
                "the same facet was supplied twice for one event; the second would collide "
                "with UNIQUE (event_id, scope_id, facet, prompt_version) at every level",
                facet=value.facet,
            )
        seen.add(value.facet)
    order = {facet: index for index, facet in enumerate(FACETS)}
    return tuple(sorted((f for f in facets if f.populated), key=lambda f: order[f.facet]))


def build_cue_rows(
    *,
    event: EventRef,
    path: ArchivalPath,
    facets: Sequence[FacetValue],
    gen_model: str,
    prompt_version: str,
) -> LmbEmission:
    """Emit exactly ``depth x populated_facets`` rows of ``mainline.event_cue``.

    The path is taken as a validated :class:`~...models.ArchivalPath`, which can only have
    been produced by :func:`~...sources.resolve_path` against the node table.  A caller
    cannot pass a hand-assembled scope list here, and that is the point: choosing the
    prefix is choosing the K-means tree.
    """
    if not gen_model.strip() or not prompt_version.strip():
        raise CueEmissionError(
            "gen_model and prompt_version are mandatory: a cue whose provenance is blank "
            "cannot be re-embedded when the model changes, and re-embedding is a commit",
            gen_model=gen_model,
            prompt_version=prompt_version,
        )
    if path.site_id != event.site_id:
        raise CueEmissionError(
            "the resolved archival path belongs to another site; a cue filed under a "
            "foreign site's scope is unreachable by this site's arms forever",
            event_site=event.site_id,
            path_site=path.site_id,
        )

    populated = _ordered_populated(facets)
    skipped = tuple(
        value.facet
        for value in sorted(facets, key=lambda f: FACETS.index(f.facet))
        if not value.populated
    )

    rows: list[CueRow] = []
    emitted: set[tuple[str, str]] = set()
    for node in path:
        for value in populated:
            key = (node.scope_id, value.facet)
            if key in emitted:
                raise CueEmissionError(
                    "duplicate (scope_id, facet) pair; one incident would be counted twice "
                    "inside a single graded arm",
                    scope_id=node.scope_id,
                    facet=value.facet,
                )
            emitted.add(key)
            rows.append(
                CueRow(
                    event_id=event.event_id,
                    site_id=event.site_id,
                    scope_id=node.scope_id,
                    scope_level=node.level,
                    facet=value.facet,
                    taxonomy_ver=node.taxonomy_ver,
                    cue_text=value.text.strip(),
                    source_span=value.source_span,
                    is_derived=value.facet != NARRATIVE_FACET,
                    gen_model=gen_model,
                    prompt_version=prompt_version,
                )
            )

    expected = path.depth * len(populated)
    if len(rows) != expected:  # pragma: no cover - guards the loop above against edits
        raise CueEmissionError(
            "LMB row count does not equal depth x populated facets",
            emitted=len(rows),
            expected=expected,
            depth=path.depth,
            populated=len(populated),
        )
    return LmbEmission(
        rows=tuple(rows),
        path=path,
        populated_facets=tuple(value.facet for value in populated),
        skipped_facets=skipped,
    )


class LevelMaterialisedBondWriter:
    """Resolve an event's archival path from the node table and emit its cue rows.

    Holds the provenance (``gen_model``, ``prompt_version``) because those two strings go
    on every row and a writer that took them per call is a writer that can emit a corpus
    with two different provenances in it.
    """

    def __init__(
        self,
        *,
        source: ActivityNodeSource,
        gen_model: str,
        prompt_version: str,
    ) -> None:
        self._source = source
        self._gen_model = gen_model
        self._prompt_version = prompt_version

    @property
    def gen_model(self) -> str:
        return self._gen_model

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def emit(self, *, event: EventRef, scope_id: str, facets: Sequence[FacetValue]) -> LmbEmission:
        path = resolve_path(self._source, scope_id)
        return build_cue_rows(
            event=event,
            path=path,
            facets=facets,
            gen_model=self._gen_model,
            prompt_version=self._prompt_version,
        )
