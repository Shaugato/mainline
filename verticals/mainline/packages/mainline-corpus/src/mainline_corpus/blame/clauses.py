# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The clause universe: which obligations exist, and which revision touched each one.

Stage 1 scheduled documents and their revision cadence.  It did **not** schedule clauses, and it
was right not to: a blame edge points at a ``clause_uuid``, every one of the eight realism
injectors is a statement about clauses, and the worker that authors causality is the worker that
must decide what the causes acted on.  So the clause universe is built here, from stage 1's
documents, revisions, people and gazetteer — deterministically, with no text and no model.

── IDENTITY ──────────────────────────────────────────────────────────────────────────────────

``clause_key`` is ``"<site>/<origin doc>/<birth label>"`` — ``MRD/PRO-MEC-014/7.3`` — and the
uuid is ``rng.sid("clause", clause_key)``.  The key names **where the obligation was born**, not
where it lives: in 2026 that clause sits in ``STD-ISO-006`` under the label ``5.2.1`` and its key
and its uuid are unchanged.  That is the ``@wId`` discipline (ARCHITECTURE.md §5.3), and it
means any worker can recompute a clause id from a natural key printed in ``anchors.yaml``
without reading a byte of this output.

── WHAT MAKES A NEW VERSION ──────────────────────────────────────────────────────────────────

A clause gets a row in ``clause_revision.jsonl`` when a revision **touched** it: it was born
there, its content changed there, or its printed label changed there because the document
reflowed (a retypeset, or a split renumbering).  A pure ordinal shift — clause 12 becoming
clause 13 because something was inserted above it — does not mint a version, because nothing
about the obligation or its label changed.  That rule is what keeps the version count in the
thousands rather than in the hundreds of thousands, and it is the same rule a real document
control system runs on.

── THE SPINE IS PLANTED, AND THE PLANT IS ASSERTED ───────────────────────────────────────────

``anchors.yaml`` declares that the film's clause is ``PRO-MEC-014 §7.3``, introduced 2011-03-14,
setpoint 150, lowered to 135 on 2013-08-04, reflowed to ``5.2.1`` in 2016 and migrated to
``STD-ISO-006`` in 2019.  Every one of those is planted here and then **checked** — the builder
raises if the layout it computed disagrees with the gazetteer, so a change to the numbering
scheme goes red in this module instead of on capture day.

── WHAT IS DELIBERATELY ABSENT ───────────────────────────────────────────────────────────────

``raw_text``, ``canon_text``, ``canon_sha256``, ``anchor_set``, ``cat_json`` — no prose exists
yet, and a digest of something that is not the text is a lie in a column offsets are taken into.
``sev_max``, ``blood_root``, ``blood_peaks``, ``blood_size`` — the M2 BLOODLINE group is
PROJECTED from the blame ancestry by a trigger, and a corpus that supplied it would make the
gate read a number the writer chose.  The emitter refuses those names outright.

``delta_basis`` never takes the value ``'lattice+model'``.  That value means a model resolved an
inconclusive lattice verdict, and ``model_named_when_model_used`` would then require a model id.
**No model ran.**  Writing one down would be a false provenance claim in the audit trail of how
the delta was reached, which is the one thing that trail exists to prevent.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from ..injectors import retypeset as retypeset_injector
from ..injectors.split import SplitPlan
from ..skeleton import clock
from ..skeleton.build import Skeleton
from ..skeleton.model import Doc, DocRevision
from . import params
from .model import Clause

__all__ = ["ClauseUniverse", "build_universe"]

#: The spine document's outline is fixed rather than drawn, because ``anchors.yaml`` says the
#: film's clause is ``7.3`` and a drawn outline might not produce a section 7 with three
#: positions in it.  Thirty-four clauses in sections of four puts section 7 at slots 25-28, so
#: ``7.3`` is slot 27.  Everything else about the document is drawn exactly as its peers are.
_SPINE_CLAUSE_COUNT: int = 34
_SPINE_SECTION_SIZE: int = 4
_SPINE_SECTION: int = 7
_SPINE_POSITION: int = 3


@dataclass(frozen=True, slots=True)
class _Slot:
    """One position in a generation-1 document outline, before it becomes a clause."""

    section: int
    position: int
    sub: int | None
    item: int | None

    @property
    def sort_key(self) -> tuple[int, int, int, int]:
        return (self.section, self.position, self.sub or 0, self.item or 0)


@dataclass(frozen=True, slots=True)
class Migration:
    """A clause's move from its origin document into another, under a change record."""

    plan: SplitPlan
    from_label: str
    to_label: str


class ClauseUniverse:
    """Every clause, both numbering schemes, and the membership changes between them."""

    __slots__ = (
        "_g1",
        "_g2",
        "by_key",
        "clauses",
        "migrations",
        "origin_members",
        "retypeset_docs",
        "spine_clause_key",
    )

    def __init__(
        self,
        clauses: Sequence[Clause],
        g1: Mapping[str, tuple[str, tuple[int, int, int, int]]],
        g2: Mapping[tuple[str, str], tuple[str, tuple[int, int, int]]],
        migrations: Mapping[str, Migration],
        retypeset_docs: frozenset[tuple[str, str]],
        spine_clause_key: str,
    ) -> None:
        self.clauses = tuple(clauses)
        self.by_key = {clause.clause_key: clause for clause in self.clauses}
        self._g1 = dict(g1)
        self._g2 = dict(g2)
        self.migrations = dict(migrations)
        self.retypeset_docs = retypeset_docs
        self.spine_clause_key = spine_clause_key
        members: dict[tuple[str, str], list[Clause]] = {}
        for clause in self.clauses:
            members.setdefault((clause.site_code, clause.origin_doc_code), []).append(clause)
        self.origin_members = {
            key: tuple(sorted(items, key=lambda c: self._g1[c.clause_key][1]))
            for key, items in members.items()
        }

    # ── membership ───────────────────────────────────────────────────────────────────────────

    def doc_code_at(self, clause_key: str, on: dt.date) -> str:
        migration = self.migrations.get(clause_key)
        clause = self.by_key[clause_key]
        if migration is not None and on >= migration.plan.effective_on:
            return migration.plan.target_doc_code
        return clause.origin_doc_code

    def members_at(self, site_code: str, doc_code: str, on: dt.date) -> tuple[Clause, ...]:
        """Clauses that are in ``doc_code`` on ``on`` and had been born by then."""
        out: list[Clause] = []
        for clause in self.clauses:
            if clause.site_code != site_code or clause.birth_on > on:
                continue
            if self.doc_code_at(clause.clause_key, on) == doc_code:
                out.append(clause)
        return tuple(out)

    # ── layout ───────────────────────────────────────────────────────────────────────────────

    def g1_label(self, clause_key: str) -> str:
        return self._g1[clause_key][0]

    def g1_sort(self, clause_key: str) -> tuple[int, int, int, int]:
        return self._g1[clause_key][1]

    def g2_label(self, doc_code: str, clause_key: str) -> str:
        return self._g2[(doc_code, clause_key)][0]

    def g2_sort(self, doc_code: str, clause_key: str) -> tuple[int, int, int]:
        return self._g2[(doc_code, clause_key)][1]

    def has_g2(self, doc_code: str, clause_key: str) -> bool:
        return (doc_code, clause_key) in self._g2

    def label_at(self, clause_key: str, doc_code: str, generation: int) -> str:
        if generation >= 2 and self.has_g2(doc_code, clause_key):
            return self.g2_label(doc_code, clause_key)
        return self.g1_label(clause_key)

    def sort_at(self, clause_key: str, doc_code: str, generation: int) -> tuple[int, ...]:
        if generation >= 2 and self.has_g2(doc_code, clause_key):
            return self.g2_sort(doc_code, clause_key)
        return self.g1_sort(clause_key)


# ── the gazetteer views this module needs ────────────────────────────────────────────────────


def _control_classes() -> tuple[dict[str, Any], ...]:
    return tuple(
        dict(entry)
        for entry in gaz.as_sequence(
            gaz.load("control_classes"), "classes", origin="control_classes.yaml"
        )
    )


def _setpoints() -> tuple[dict[str, Any], ...]:
    return tuple(
        dict(entry)
        for entry in gaz.as_sequence(gaz.load("setpoints"), "parameters", origin="setpoints.yaml")
    )


def _spine_facts() -> Mapping[str, Any]:
    return gaz.as_mapping(gaz.load("anchors"), "spine", origin="anchors.yaml")


# ── outline ──────────────────────────────────────────────────────────────────────────────────


def _outline(count: int, stream: rng.Stream, *, is_spine: bool) -> tuple[_Slot, ...]:
    """Lay ``count`` clauses out across numbered sections in the generation-1 house style."""
    slots: list[_Slot] = []
    section = 1
    position = 0
    low, high = params.SECTION_SIZE
    size = _SPINE_SECTION_SIZE if is_spine else low + int(rng.unit(stream) * (high - low + 1))
    for _ in range(count):
        if position >= size:
            section += 1
            position = 0
            size = (
                _SPINE_SECTION_SIZE if is_spine else low + int(rng.unit(stream) * (high - low + 1))
            )
        position += 1
        deep = (not is_spine) and rng.unit(stream) < params.P_DEEP_LABEL
        sub = 1 + int(rng.unit(stream) * 3) if deep else None
        # A deep generation-1 label ALWAYS carries its bracketed item, so it is `7.3.2(b)` and
        # never a bare `7.3.2`.  Without the bracket a three-component generation-1 label can
        # collide with a generation-2 `chapter.barrier.item`, and a clause whose printed label
        # came out of the 2016 reflow unchanged would make the reflow look like a formatting
        # tweak in exactly the shot that has to prove it was not.
        item = int(rng.unit(stream) * 4) if deep else None
        slots.append(_Slot(section=section, position=position, sub=sub, item=item))
    return tuple(slots)


def _classes_for(
    doc: Doc, classes: Sequence[Mapping[str, Any]]
) -> tuple[Mapping[str, Any], ...]:
    matched = tuple(
        entry for entry in classes if doc.activity_root in {str(item) for item in entry["mue"]}
    )
    if not matched:
        raise gaz.GazetteerError(
            f"control_classes.yaml declares no class for fonds {doc.activity_root!r}, so every "
            f"clause of {doc.doc_code} would assert nothing and the mechanism join key would be "
            "empty for the whole document"
        )
    return tuple(sorted(matched, key=lambda entry: str(entry["key"])))


def _resolve_role(entry: Mapping[str, Any], stream: rng.Stream) -> str:
    role = str(entry["barrier_role"])
    return rng.pick(stream, ("preventive", "recovery")) if role == "either" else role


def _setpoint_for(
    doc: Doc, control_class: str, setpoints: Sequence[Mapping[str, Any]], stream: rng.Stream
) -> str | None:
    """Choose a setpoint this clause could be written about, or ``None``.

    A setpoint is what makes ``control_delta`` decidable without prose judgement — lowering an
    alarm threshold is unambiguously a strengthening — so a corpus needs enough of them for the
    lattice to have work to do, and not so many that every clause is a number.
    """
    candidates = [
        entry
        for entry in setpoints
        if str(entry["control_class"]) == control_class
        and {str(item) for item in entry["applies_to_classes"]} & set(doc.asset_classes)
    ]
    if not candidates or rng.unit(stream) >= 0.42:
        return None
    return str(rng.pick(stream, sorted(candidates, key=lambda e: str(e["key"])))["key"])


def _birth_revision(revisions: Sequence[DocRevision], stream: rng.Stream) -> DocRevision:
    """Which revision introduced this clause.

    Most clauses are in the document from first issue; the rest arrive later, which is what
    gives ``control_delta = 'introduce'`` a real population and gives an orphan clause — one the
    record never explains — somewhere to be born.
    """
    if len(revisions) == 1 or rng.unit(stream) < params.P_BORN_AT_FIRST_ISSUE:
        return revisions[0]
    return revisions[1 + int(rng.unit(stream) * (len(revisions) - 1))]


# ── generation-2 layout ──────────────────────────────────────────────────────────────────────


def _g2_start(revisions: Sequence[DocRevision]) -> dt.date | None:
    """Return the date this document begins using the generation-2 numbering, or ``None``."""
    for revision in revisions:
        if revision.template_generation >= 2:
            return revision.effective_on
    return None


def _assign_g2(
    universe_clauses: Sequence[Clause],
    *,
    docs_by_key: Mapping[tuple[str, str], Doc],
    revisions_by_doc: Mapping[tuple[str, str], tuple[DocRevision, ...]],
    migrations: Mapping[str, Migration],
    g1: Mapping[str, tuple[str, tuple[int, int, int, int]]],
    roles: Mapping[str, str],
) -> dict[tuple[str, str], tuple[str, tuple[int, int, int]]]:
    """Compute ``chapter.barrier.item`` for every clause in every document that reaches gen 2.

    Membership is taken at the moment the document starts using the new scheme, plus everything
    that arrives afterwards — a clause born later, or migrated in by a split, takes the next
    item number in its (chapter, barrier) group and renumbers nobody.  Numbering that stayed
    stable between reissues and moved only at a reflow is the behaviour of every document
    control system that has ever worked; renumbering on every issue is the behaviour of none.
    """
    by_doc: dict[tuple[str, str], list[Clause]] = {}
    for clause in universe_clauses:
        migration = migrations.get(clause.clause_key)
        origin_key = (clause.site_code, clause.origin_doc_code)
        by_doc.setdefault(origin_key, []).append(clause)
        if migration is not None:
            target_key = (clause.site_code, migration.plan.target_doc_code)
            by_doc.setdefault(target_key, []).append(clause)

    layout: dict[tuple[str, str], tuple[str, tuple[int, int, int]]] = {}
    for doc_key in sorted(by_doc):
        _site_code, doc_code = doc_key
        doc = docs_by_key.get(doc_key)
        revisions = revisions_by_doc.get(doc_key)
        if doc is None or not revisions:
            continue
        start = _g2_start(revisions)
        if start is None:
            continue

        members: list[Clause] = []
        for clause in by_doc[doc_key]:
            migration = migrations.get(clause.clause_key)
            # It leaves this document; it is only numbered here while it is still present.
            if (
                migration is not None
                and migration.plan.source_doc_code == doc_code
                and migration.plan.effective_on <= start
            ):
                continue
            members.append(clause)

        def _arrival(clause: Clause, doc_code: str = doc_code) -> dt.date:
            migration = migrations.get(clause.clause_key)
            if migration is not None and migration.plan.target_doc_code == doc_code:
                return max(clause.birth_on, migration.plan.effective_on)
            return clause.birth_on

        classes_present = sorted({clause.control_class for clause in members})
        order = retypeset_injector.chapter_order(doc.activity_root, classes_present)
        chapter_of = {name: index + 1 for index, name in enumerate(order)}

        core = sorted(
            (clause for clause in members if _arrival(clause) <= start),
            key=lambda c: g1[c.clause_key][1],
        )
        late = sorted(
            (clause for clause in members if _arrival(clause) > start),
            key=lambda c: (_arrival(c), c.clause_key),
        )

        counters: dict[tuple[int, int], int] = {}
        for clause in [*core, *late]:
            chapter = chapter_of[clause.control_class]
            barrier = params.RETYPESET_BARRIER_INDEX[roles[clause.clause_key]]
            item = counters.get((chapter, barrier), 0) + 1
            counters[(chapter, barrier)] = item
            layout[(doc_code, clause.clause_key)] = (
                retypeset_injector.g2_label(chapter, barrier, item),
                (chapter, barrier, item),
            )
    return layout


# ── the builder ──────────────────────────────────────────────────────────────────────────────


def build_universe(skeleton: Skeleton, splits: Sequence[SplitPlan]) -> ClauseUniverse:
    """Build every clause, both layouts, and the split migrations between them."""
    classes = _control_classes()
    setpoints = _setpoints()
    spine = _spine_facts()
    spine_site = str(spine["site"])
    spine_doc = str(spine["document_origin"])
    spine_label = str(spine["clause_label_2011"])
    spine_setpoint = str(spine["setpoint_parameter"])
    spine_control_class = str(
        next(entry for entry in setpoints if str(entry["key"]) == spine_setpoint)["control_class"]
    )
    spine_introduced = clock.coerce_date(
        gaz.as_mapping(spine, "dates", origin="anchors.yaml/spine")["clause_introduced"],
        origin="anchors.yaml/spine/dates/clause_introduced",
    )

    docs_by_key = {(doc.site_code, doc.doc_code): doc for doc in skeleton.documents.docs}
    revisions_by_doc: dict[tuple[str, str], list[DocRevision]] = {}
    for revision in skeleton.documents.revisions:
        site_code = revision.revision_key.split("/", 1)[0]
        revisions_by_doc.setdefault((site_code, revision.doc_code), []).append(revision)
    revisions_frozen = {
        key: tuple(sorted(items, key=lambda r: r.rev_no)) for key, items in revisions_by_doc.items()
    }

    clauses: list[Clause] = []
    g1: dict[str, tuple[str, tuple[int, int, int, int]]] = {}
    roles: dict[str, str] = {}
    spine_clause_key = f"{spine_site}/{spine_doc}/{spine_label}"

    for doc_key in sorted(docs_by_key):
        site_code, doc_code = doc_key
        doc = docs_by_key[doc_key]
        revisions = revisions_frozen.get(doc_key)
        if not revisions:
            raise RuntimeError(
                f"{doc_key} has no revisions; stage 1 emits at least the first issue"
            )
        is_spine_doc = site_code == spine_site and doc_code == spine_doc

        outline_stream = rng.stream(f"clause.outline/{site_code}/{doc_code}")
        detail_stream = rng.stream(f"clause.detail/{site_code}/{doc_code}")
        low, high = params.CLAUSE_COUNT_BY_FAMILY[doc.family]
        count = (
            _SPINE_CLAUSE_COUNT
            if is_spine_doc
            else low + int(rng.unit(outline_stream) * (high - low + 1))
        )
        slots = _outline(count, outline_stream, is_spine=is_spine_doc)
        doc_classes = _classes_for(doc, classes)
        class_keys = [str(entry["key"]) for entry in doc_classes]
        by_class_key = {str(entry["key"]): entry for entry in doc_classes}

        for index, slot in enumerate(slots):
            is_spine = (
                is_spine_doc and slot.section == _SPINE_SECTION and slot.position == _SPINE_POSITION
            )
            if is_spine:
                control_class = spine_control_class
            elif is_spine_doc:
                # Every other clause of the spine document takes one of the remaining classes,
                # round-robin so all of them are present: the generation-2 chapter index is a
                # position among the classes the document actually carries, and a missing class
                # would move the spine's chapter and break `5.2.1`.
                others = [key for key in class_keys if key != spine_control_class]
                control_class = others[index % len(others)]
            else:
                control_class = class_keys[
                    int(rng.unit(detail_stream) * len(class_keys)) % len(class_keys)
                ]
            entry = by_class_key[control_class]
            role = "recovery" if is_spine else _resolve_role(entry, detail_stream)
            setpoint_key = (
                spine_setpoint
                if is_spine
                else _setpoint_for(doc, control_class, setpoints, detail_stream)
            )
            birth = (
                next(
                    (r for r in revisions if r.effective_on == spine_introduced),
                    revisions[0],
                )
                if is_spine
                else _birth_revision(revisions, detail_stream)
            )
            label = retypeset_injector.g1_label(slot.section, slot.position, slot.sub, slot.item)
            clause_key = f"{site_code}/{doc_code}/{label}"
            if clause_key in g1:
                raise RuntimeError(
                    f"clause key {clause_key} is not unique; two obligations were born under one "
                    "printed label, which would collapse two clause_uuids into one"
                )
            g1[clause_key] = (label, slot.sort_key)
            roles[clause_key] = role
            clauses.append(
                Clause(
                    clause_key=clause_key,
                    clause_uuid=str(rng.sid("clause", clause_key)),
                    site_id=doc.site_id,
                    site_code=site_code,
                    origin_doc_code=doc_code,
                    origin_doc_id=doc.doc_id,
                    activity_root=doc.activity_root,
                    control_class=control_class,
                    barrier_role=role,
                    setpoint_key=setpoint_key,
                    section=slot.section,
                    position=slot.position,
                    birth_label=label,
                    birth_revision_key=birth.revision_key,
                    birth_on=birth.effective_on,
                    is_spine=is_spine,
                )
            )

    if spine_clause_key not in g1:
        raise RuntimeError(
            f"the spine clause {spine_clause_key} was not laid out. anchors.yaml declares "
            f"clause_label_2011 = {spine_label!r} and the outline must place it there, because "
            "the film shows that label."
        )

    by_key = {clause.clause_key: clause for clause in clauses}
    migrations = _plan_migrations(clauses, splits, g1, by_key)
    g2 = _assign_g2(
        clauses,
        docs_by_key=docs_by_key,
        revisions_by_doc=revisions_frozen,
        migrations=migrations,
        g1=g1,
        roles=roles,
    )
    _bind_migration_labels(migrations, g2, g1)

    retypeset_docs = frozenset(
        (doc.site_code, doc.doc_code)
        for doc in retypeset_injector.documents_in_scope(skeleton.documents.docs)
    )

    universe = ClauseUniverse(
        clauses=clauses,
        g1=g1,
        g2=g2,
        migrations=migrations,
        retypeset_docs=retypeset_docs,
        spine_clause_key=spine_clause_key,
    )
    _assert_spine(universe, spine)
    return universe


def _plan_migrations(
    clauses: Sequence[Clause],
    splits: Sequence[SplitPlan],
    g1: Mapping[str, tuple[str, tuple[int, int, int, int]]],
    by_key: Mapping[str, Clause],
) -> dict[str, Migration]:
    """Choose which clauses each split moves.

    The spine's clause always moves — that is the anchored fact.  The rest are drawn from the
    source document's clauses that were already in issue when the split landed, preferring
    whichever control classes the target document already covers, because a standard absorbs
    obligations it is already about.
    """
    migrations: dict[str, Migration] = {}
    for plan in splits:
        stream = rng.stream(f"injector.split.clauses/{plan.key}")
        pool = [
            clause
            for clause in clauses
            if clause.site_code == plan.source_site
            and clause.origin_doc_code == plan.source_doc_code
            and clause.birth_on < plan.effective_on
        ]
        if not pool:
            raise RuntimeError(
                f"{plan.key}: the source document had no clauses in issue on "
                f"{plan.effective_on}; a split that moves nothing proves nothing"
            )
        wanted = max(2, round(len(pool) * plan.migration_fraction))
        ordered = sorted(pool, key=lambda c: g1[c.clause_key][1])
        chosen: list[Clause] = []
        if plan.anchored:
            spine = next((clause for clause in ordered if clause.is_spine), None)
            if spine is None:
                raise RuntimeError(
                    f"{plan.key} is the spine's split and its clause is not in the source "
                    "document. The 2019 migration is what proves identity survives a document "
                    "boundary, and the film shows it."
                )
            chosen.append(spine)
        remainder = [clause for clause in ordered if clause not in chosen]
        # Contiguity matters: a split lifts a run of related clauses out of a procedure, it does
        # not cherry-pick one clause from each section.
        if remainder:
            start = int(rng.unit(stream) * max(1, len(remainder) - wanted + 1))
            chosen.extend(remainder[start : start + max(0, wanted - len(chosen))])
        for clause in chosen:
            migrations[clause.clause_key] = Migration(
                plan=plan, from_label=g1[clause.clause_key][0], to_label=""
            )
    del by_key
    return migrations


def _bind_migration_labels(
    migrations: dict[str, Migration],
    g2: Mapping[tuple[str, str], tuple[str, tuple[int, int, int]]],
    g1: Mapping[str, tuple[str, tuple[int, int, int, int]]],
) -> None:
    """Fill each migration's ``from``/``to`` labels once both layouts exist."""
    for clause_key, migration in list(migrations.items()):
        plan = migration.plan
        source_key = (plan.source_doc_code, clause_key)
        target_key = (plan.target_doc_code, clause_key)
        from_label = g2[source_key][0] if source_key in g2 else g1[clause_key][0]
        if target_key not in g2:
            raise RuntimeError(
                f"{clause_key} migrates into {plan.target_doc_code}, which has no generation-2 "
                "layout. A receiving document must reach the post-2016 numbering, or the "
                "migrated clause has no label to be printed under."
            )
        migrations[clause_key] = Migration(
            plan=plan, from_label=from_label, to_label=g2[target_key][0]
        )


def _assert_spine(universe: ClauseUniverse, spine: Mapping[str, Any]) -> None:
    """Check the planted spine against ``anchors.yaml`` rather than assuming it."""
    key = universe.spine_clause_key
    clause = universe.by_key[key]
    expected_2016 = str(spine["clause_label_2016"])
    origin = clause.origin_doc_code
    computed = universe.g2_label(origin, key)
    if computed != expected_2016:
        raise RuntimeError(
            f"the 2016 retypeset numbers the spine clause {computed!r}; anchors.yaml declares "
            f"{expected_2016!r} and the film shows that label. The generation-2 scheme is "
            "chapter.barrier.item — check blame.params.RETYPESET_CHAPTER_ORDER for "
            f"{clause.activity_root} and the barrier role of {clause.control_class}."
        )
    migration = universe.migrations.get(key)
    if migration is None:
        raise RuntimeError(
            "the spine clause does not migrate in 2019. MOC-2019-0221 moving it into "
            "STD-ISO-006 while its uuid holds is the second half of beat 1."
        )
    if migration.plan.target_doc_code != str(spine["document_after_split"]):
        raise RuntimeError(
            f"the spine clause migrates into {migration.plan.target_doc_code}, not "
            f"{spine['document_after_split']}"
        )
    if clause.setpoint_key != str(spine["setpoint_parameter"]):
        raise RuntimeError(
            f"the spine clause asserts setpoint {clause.setpoint_key!r}, not "
            f"{spine['setpoint_parameter']!r}; the 150 -> 135 -> 150 story runs on that parameter"
        )
