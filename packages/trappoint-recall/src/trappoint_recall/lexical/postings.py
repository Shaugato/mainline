# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Posting maintenance: idempotent by construction, site-scoped by every statement.

Two write paths, one analyser.  :func:`upsert_document` maintains a single document's
postings, its length and the document frequencies it moved; :func:`rebuild_site` throws away a
site's index and rebuilds it.  They must agree — a corpus built incrementally and the same
corpus rebuilt from scratch have to produce identical tables, or ``df`` drifts and IDF drifts
with it, silently, changing what the gate recalls.  ``tests/integration/recall_lexical`` asserts
that agreement directly.

**Idempotence is stronger than "running twice is harmless".**  A second ingest of an unchanged
document issues **zero** writes: the writer reads what is there, diffs, and writes only the
difference.  That is what makes :class:`WriteReport` a useful assertion rather than a log line,
and it is why the reported number of writes is part of the completion test rather than a row
digest alone — a digest cannot tell "wrote the same bytes again" from "wrote nothing", and the
first of those is a changefeed event, a range write and an audit entry that should not exist.

**Statement portability is deliberate.**  Every write uses
``INSERT … ON CONFLICT … DO UPDATE SET x = excluded.x`` rather than CockroachDB's shorter
``UPSERT``.  The two are equivalent here, and the Postgres-compatible spelling is the one a
second SQL engine also understands — which is what lets the idempotence and differential
suites run on a laptop with no cluster.  Losing that would make the BM25 arithmetic testable
only where a cluster exists, and an untested-by-default oracle is not an oracle.

``lex_doclen`` carries no ``site_id`` (ARCHITECTURE §5.4), so a document's length row cannot be
scoped and a site's document set has to be recovered from ``lex_posting``.  Every place that
costs something says so.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, TypeVar

from trappoint_recall.lexical.analyser import analyse, is_well_formed_term
from trappoint_recall.lexical.executor import (
    Executor,
    ParamStyle,
    SqlBuilder,
    Statement,
    as_float,
    as_int,
    as_text,
    check_identifier,
)
from trappoint_recall.lexical.reference import LexicalTables

__all__ = [
    "DocumentPostings",
    "WriteReport",
    "build_document_postings",
    "content_digest",
    "delete_document",
    "rebuild_site",
    "snapshot_tables",
    "upsert_document",
]

_T = TypeVar("_T")

#: Rows per INSERT.  Small enough that a retry under SERIALIZABLE is cheap, large enough that a
#: 2 000-document corpus is not 200 000 round trips.
DEFAULT_BATCH_ROWS: Final[int] = 500


@dataclass(frozen=True, slots=True)
class DocumentPostings:
    """One document's contribution to the index."""

    event_id: str
    length: int
    weights: Mapping[str, float]

    def __post_init__(self) -> None:
        bad = [t for t in self.weights if not is_well_formed_term(t)]
        if bad:
            raise ValueError(f"malformed terms from the analyser: {bad[:5]!r}")
        if self.length < 0:
            raise ValueError(f"document length must be >= 0, got {self.length!r}")


@dataclass(slots=True)
class WriteReport:
    """What a write path actually did.  Zero everywhere means "already correct"."""

    postings_inserted: int = 0
    postings_updated: int = 0
    postings_deleted: int = 0
    doclen_written: int = 0
    stats_written: int = 0
    stats_deleted: int = 0
    statements: list[str] = field(default_factory=list)

    @property
    def rows_written(self) -> int:
        return (
            self.postings_inserted
            + self.postings_updated
            + self.postings_deleted
            + self.doclen_written
            + self.stats_written
            + self.stats_deleted
        )

    def merge(self, other: WriteReport) -> None:
        self.postings_inserted += other.postings_inserted
        self.postings_updated += other.postings_updated
        self.postings_deleted += other.postings_deleted
        self.doclen_written += other.doclen_written
        self.stats_written += other.stats_written
        self.stats_deleted += other.stats_deleted
        self.statements.extend(other.statements)


def build_document_postings(
    event_id: str,
    fields: Mapping[str, str] | str,
    *,
    field_weights: Mapping[str, float] | None = None,
) -> DocumentPostings:
    """Analyse a document into ``term → weight`` plus its length.

    ``weight`` here is a field-weighted term frequency.  It is the **only** thing the BM25
    statement reads out of ``lex_posting``, which is what makes the query weight-source
    agnostic: replacing this function with a learned-sparse impact model changes the numbers
    in the column and nothing else in the system.

    ``length`` is the field-weighted token count, rounded, because ``lex_doclen.len`` is
    ``INT8``.  Weighting length as well as frequency keeps ``tf/|d|`` coherent: boosting a
    title without lengthening the document would make short-titled documents score as though
    they were shorter than they are.
    """
    if isinstance(fields, str):
        fields = {"_": fields}
    weights_by_field = dict(field_weights or {})
    weighted: dict[str, float] = {}
    length = 0.0
    for name in sorted(fields):
        weight = float(weights_by_field.get(name, 1.0))
        if weight < 0.0:
            raise ValueError(f"field weight for {name!r} must be >= 0, got {weight!r}")
        tokens = analyse(fields[name])
        length += weight * len(tokens)
        counts = Counter(token.text for token in tokens)
        for term, count in counts.items():
            weighted[term] = weighted.get(term, 0.0) + weight * count
    # Deterministic key order so that batched INSERT text is a function of the document.
    ordered = {term: weighted[term] for term in sorted(weighted)}
    return DocumentPostings(event_id=event_id, length=round(length), weights=ordered)


# ── statement text ───────────────────────────────────────────────────────────────────────────

_SELECT_DOC_POSTINGS: Final[str] = """\
-- The document's current postings. lex_posting's primary key is (site_id, term, event_id), so
-- this is a constrained scan of the SITE's key space filtered on event_id, not a point read.
-- It is the one read in this module that costs more than it looks like it should; see the
-- cross-domain note about a (site_id, event_id) index.
SELECT p.term AS term, p.weight AS weight
  FROM {schema}.lex_posting AS p
 WHERE p.site_id = {site_id} AND p.event_id = {event_id}
 ORDER BY p.term"""

_INSERT_POSTINGS: Final[str] = """\
INSERT INTO {schema}.lex_posting (site_id, term, event_id, weight)
VALUES {rows}
ON CONFLICT (site_id, term, event_id) DO UPDATE SET weight = excluded.weight"""

_DELETE_POSTINGS: Final[str] = """\
DELETE FROM {schema}.lex_posting
 WHERE site_id = {site_id} AND event_id = {event_id} AND term IN ({terms})"""

_DELETE_SITE_POSTINGS: Final[str] = """\
DELETE FROM {schema}.lex_posting WHERE site_id = {site_id}"""

_READ_DOCLEN: Final[str] = """\
SELECT d.len AS len FROM {schema}.lex_doclen AS d WHERE d.event_id = {event_id}"""

_WRITE_DOCLEN: Final[str] = """\
INSERT INTO {schema}.lex_doclen (event_id, len)
VALUES {rows}
ON CONFLICT (event_id) DO UPDATE SET len = excluded.len"""

_DELETE_DOCLEN: Final[str] = """\
DELETE FROM {schema}.lex_doclen WHERE event_id IN ({events})"""

_COUNT_DF: Final[str] = """\
SELECT p.term AS term, count(*) AS df
  FROM {schema}.lex_posting AS p
 WHERE p.site_id = {site_id} AND p.term IN ({terms})
 GROUP BY p.term"""

_WRITE_STATS: Final[str] = """\
INSERT INTO {schema}.lex_stats (site_id, term, df)
VALUES {rows}
ON CONFLICT (site_id, term) DO UPDATE SET df = excluded.df"""

_DELETE_STATS: Final[str] = """\
DELETE FROM {schema}.lex_stats WHERE site_id = {site_id} AND term IN ({terms})"""

_DELETE_SITE_STATS: Final[str] = """\
DELETE FROM {schema}.lex_stats WHERE site_id = {site_id}"""

_REBUILD_STATS: Final[str] = """\
-- df recomputed from the posting list itself, in one statement, so that a full rebuild cannot
-- disagree with the incremental writer about what df means.
INSERT INTO {schema}.lex_stats (site_id, term, df)
SELECT p.site_id, p.term, count(*)
  FROM {schema}.lex_posting AS p
 WHERE p.site_id = {site_id}
 GROUP BY p.site_id, p.term"""

_SNAPSHOT_POSTINGS: Final[str] = """\
SELECT p.site_id AS site_id, p.term AS term, p.event_id AS event_id, p.weight AS weight
  FROM {schema}.lex_posting AS p
 WHERE p.site_id = {site_id}
 ORDER BY p.term, p.event_id"""

_SNAPSHOT_STATS: Final[str] = """\
SELECT s.site_id AS site_id, s.term AS term, s.df AS df
  FROM {schema}.lex_stats AS s
 WHERE s.site_id = {site_id}
 ORDER BY s.term"""

_SNAPSHOT_DOCLEN: Final[str] = """\
SELECT d.event_id AS event_id, d.len AS len
  FROM {schema}.lex_doclen AS d
 WHERE d.event_id IN (SELECT DISTINCT p.event_id
                        FROM {schema}.lex_posting AS p
                       WHERE p.site_id = {site_id})
 ORDER BY d.event_id"""


def _chunks(items: Sequence[_T], size: int) -> Iterable[Sequence[_T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


#: How many statement texts a report keeps.  A full rebuild of a fleet-sized corpus issues
#: thousands; keeping them all turns a maintenance job into a memory leak, and keeping none
#: makes a failing test unreadable.
_MAX_RECORDED_STATEMENTS: Final[int] = 64


def _run(
    execute: Executor, statement: Statement, report: WriteReport
) -> Sequence[Sequence[object]]:
    if len(report.statements) < _MAX_RECORDED_STATEMENTS:
        report.statements.append(statement.sql)
    return execute(statement.sql, statement.params)


# ── the incremental path ─────────────────────────────────────────────────────────────────────


def upsert_document(
    execute: Executor,
    *,
    site_id: str,
    document: DocumentPostings,
    style: ParamStyle = ParamStyle.NUMERIC,
    schema: str = "mainline",
    batch_rows: int = DEFAULT_BATCH_ROWS,
) -> WriteReport:
    """Bring one document's postings, length and document frequencies to their correct values.

    Returns a :class:`WriteReport` whose ``rows_written`` is ``0`` when nothing had to change.
    """
    schema = check_identifier(schema, what="schema")
    report = WriteReport()

    qb = SqlBuilder(style)
    sql = _SELECT_DOC_POSTINGS.format(
        schema=schema,
        site_id=qb.bind(site_id, key="site"),
        event_id=qb.bind(document.event_id, key="event"),
    )
    existing = {
        as_text(row[0]): as_float(row[1])
        for row in _run(execute, Statement(sql, qb.params, style), report)
    }

    wanted = dict(document.weights)
    removed = sorted(set(existing) - set(wanted))
    added = sorted(set(wanted) - set(existing))
    changed = sorted(t for t in wanted if t in existing and existing[t] != wanted[t])

    if removed:
        for chunk in _chunks(removed, batch_rows):
            qb = SqlBuilder(style)
            sql = _DELETE_POSTINGS.format(
                schema=schema,
                site_id=qb.bind(site_id, key="site"),
                event_id=qb.bind(document.event_id, key="event"),
                terms=", ".join(qb.bind(t, key=f"term:{t}") for t in chunk),
            )
            _run(execute, Statement(sql, qb.params, style), report)
        report.postings_deleted += len(removed)

    writes = added + changed
    if writes:
        writes.sort()
        for chunk in _chunks(writes, batch_rows):
            qb = SqlBuilder(style)
            rows = ", ".join(
                "("
                + qb.bind(site_id, key="site")
                + ", "
                + qb.bind(term)
                + ", "
                + qb.bind(document.event_id, key="event")
                + ", "
                + qb.bind(float(wanted[term]))
                + ")"
                for term in chunk
            )
            sql = _INSERT_POSTINGS.format(schema=schema, rows=rows)
            _run(execute, Statement(sql, qb.params, style), report)
        report.postings_inserted += len(added)
        report.postings_updated += len(changed)

    # Read before write.  `ON CONFLICT DO UPDATE` with an unchanged value is still a write: a
    # new MVCC version, a changefeed row and a range write, for no change in meaning. The
    # idempotence claim in this worker's completion test is that a second ingest of an
    # unchanged document issues NO writes at all, and this read is what makes that true.
    qb = SqlBuilder(style)
    sql = _READ_DOCLEN.format(schema=schema, event_id=qb.bind(document.event_id, key="event"))
    current = _run(execute, Statement(sql, qb.params, style), report)
    if not current or as_int(current[0][0]) != document.length:
        _write_doclen(execute, [(document.event_id, document.length)], style, schema, report)

    # Only membership changes move df; a changed weight does not.
    _refresh_stats(execute, site_id, removed + added, style, schema, report, batch_rows)
    return report


def delete_document(
    execute: Executor,
    *,
    site_id: str,
    event_id: str,
    style: ParamStyle = ParamStyle.NUMERIC,
    schema: str = "mainline",
    batch_rows: int = DEFAULT_BATCH_ROWS,
) -> WriteReport:
    """Remove a document from the index and repair the document frequencies it leaves behind."""
    schema = check_identifier(schema, what="schema")
    report = WriteReport()
    qb = SqlBuilder(style)
    sql = _SELECT_DOC_POSTINGS.format(
        schema=schema,
        site_id=qb.bind(site_id, key="site"),
        event_id=qb.bind(event_id, key="event"),
    )
    terms = [as_text(row[0]) for row in _run(execute, Statement(sql, qb.params, style), report)]
    if terms:
        for chunk in _chunks(terms, batch_rows):
            qb = SqlBuilder(style)
            sql = _DELETE_POSTINGS.format(
                schema=schema,
                site_id=qb.bind(site_id, key="site"),
                event_id=qb.bind(event_id, key="event"),
                terms=", ".join(qb.bind(t, key=f"term:{t}") for t in chunk),
            )
            _run(execute, Statement(sql, qb.params, style), report)
        report.postings_deleted += len(terms)

    qb = SqlBuilder(style)
    sql = _DELETE_DOCLEN.format(schema=schema, events=qb.bind(event_id, key="event"))
    _run(execute, Statement(sql, qb.params, style), report)
    report.doclen_written += 1
    _refresh_stats(execute, site_id, terms, style, schema, report, batch_rows)
    return report


def _write_doclen(
    execute: Executor,
    rows: Sequence[tuple[str, int]],
    style: ParamStyle,
    schema: str,
    report: WriteReport,
    batch_rows: int = DEFAULT_BATCH_ROWS,
) -> None:
    for row_chunk in _chunks(rows, batch_rows):
        qb = SqlBuilder(style)
        values = ", ".join(
            "(" + qb.bind(event_id) + ", " + qb.bind(int(length)) + ")"
            for event_id, length in row_chunk
        )
        sql = _WRITE_DOCLEN.format(schema=schema, rows=values)
        _run(execute, Statement(sql, qb.params, style), report)
    report.doclen_written += len(rows)


def _refresh_stats(
    execute: Executor,
    site_id: str,
    terms: Sequence[str],
    style: ParamStyle,
    schema: str,
    report: WriteReport,
    batch_rows: int = DEFAULT_BATCH_ROWS,
) -> None:
    """Recount ``df`` for exactly the terms whose membership moved.

    Recounted rather than incremented.  An increment is correct only if every previous write
    was correct, and ``df`` is the sole input to IDF: a drift of one here does not raise, it
    quietly re-ranks the channel whose job is to surface the fatality.
    """
    unique = sorted(set(terms))
    if not unique:
        return
    actual: dict[str, int] = {}
    for chunk in _chunks(unique, batch_rows):
        qb = SqlBuilder(style)
        sql = _COUNT_DF.format(
            schema=schema,
            site_id=qb.bind(site_id, key="site"),
            terms=", ".join(qb.bind(t, key=f"term:{t}") for t in chunk),
        )
        for row in _run(execute, Statement(sql, qb.params, style), report):
            actual[as_text(row[0])] = as_int(row[1])

    present = sorted(t for t in unique if actual.get(t, 0) > 0)
    absent = sorted(t for t in unique if actual.get(t, 0) == 0)

    for chunk in _chunks(present, batch_rows):
        qb = SqlBuilder(style)
        rows = ", ".join(
            "("
            + qb.bind(site_id, key="site")
            + ", "
            + qb.bind(term)
            + ", "
            + qb.bind(int(actual[term]))
            + ")"
            for term in chunk
        )
        sql = _WRITE_STATS.format(schema=schema, rows=rows)
        _run(execute, Statement(sql, qb.params, style), report)
    report.stats_written += len(present)

    for chunk in _chunks(absent, batch_rows):
        qb = SqlBuilder(style)
        sql = _DELETE_STATS.format(
            schema=schema,
            site_id=qb.bind(site_id, key="site"),
            terms=", ".join(qb.bind(t, key=f"term:{t}") for t in chunk),
        )
        _run(execute, Statement(sql, qb.params, style), report)
    report.stats_deleted += len(absent)


# ── the rebuild path ─────────────────────────────────────────────────────────────────────────


def rebuild_site(
    execute: Executor,
    *,
    site_id: str,
    documents: Sequence[DocumentPostings],
    style: ParamStyle = ParamStyle.NUMERIC,
    schema: str = "mainline",
    batch_rows: int = DEFAULT_BATCH_ROWS,
) -> WriteReport:
    """Drop and rebuild one site's index from the given documents.

    Site-scoped in every statement.  A rebuild that reached another site's rows would be a
    cross-tenant data loss triggered by an ordinary maintenance job, which is the sort of
    thing that is discovered late and explained badly.
    """
    schema = check_identifier(schema, what="schema")
    report = WriteReport()

    qb = SqlBuilder(style)
    sql = _DELETE_SITE_POSTINGS.format(schema=schema, site_id=qb.bind(site_id, key="site"))
    _run(execute, Statement(sql, qb.params, style), report)

    qb = SqlBuilder(style)
    sql = _DELETE_SITE_STATS.format(schema=schema, site_id=qb.bind(site_id, key="site"))
    _run(execute, Statement(sql, qb.params, style), report)

    event_ids = [doc.event_id for doc in documents]
    for chunk in _chunks(event_ids, batch_rows):
        qb = SqlBuilder(style)
        sql = _DELETE_DOCLEN.format(schema=schema, events=", ".join(qb.bind(e) for e in chunk))
        _run(execute, Statement(sql, qb.params, style), report)

    rows: list[tuple[str, str, str, float]] = [
        (site_id, term, doc.event_id, float(weight))
        for doc in documents
        for term, weight in sorted(doc.weights.items())
    ]
    for row_chunk in _chunks(rows, batch_rows):
        qb = SqlBuilder(style)
        values = ", ".join(
            "("
            + qb.bind(site, key="site")
            + ", "
            + qb.bind(term)
            + ", "
            + qb.bind(event_id)
            + ", "
            + qb.bind(weight)
            + ")"
            for site, term, event_id, weight in row_chunk
        )
        sql = _INSERT_POSTINGS.format(schema=schema, rows=values)
        _run(execute, Statement(sql, qb.params, style), report)
    report.postings_inserted += len(rows)

    _write_doclen(
        execute,
        [(doc.event_id, doc.length) for doc in documents],
        style,
        schema,
        report,
        batch_rows,
    )

    qb = SqlBuilder(style)
    sql = _REBUILD_STATS.format(schema=schema, site_id=qb.bind(site_id, key="site"))
    _run(execute, Statement(sql, qb.params, style), report)
    report.stats_written += len({term for _s, term, _e, _w in rows})
    return report


# ── reading the index back ───────────────────────────────────────────────────────────────────


def snapshot_tables(
    execute: Executor,
    *,
    site_id: str,
    style: ParamStyle = ParamStyle.NUMERIC,
    schema: str = "mainline",
) -> LexicalTables:
    """Read one site's three tables into the shape the pure-Python oracle consumes.

    Three statements, each single, each site-scoped, each ordered — so a snapshot is a
    function of the data and not of which range answered first.  Not for the gate path: this
    reads the whole index and is for verification and for the differential suite.
    """
    schema = check_identifier(schema, what="schema")

    def _one(template: str) -> Sequence[Sequence[object]]:
        qb = SqlBuilder(style)
        sql = template.format(schema=schema, site_id=qb.bind(site_id, key="site"))
        return execute(sql, qb.params)

    posting = tuple(
        (as_text(r[0]), as_text(r[1]), as_text(r[2]), as_float(r[3]))
        for r in _one(_SNAPSHOT_POSTINGS)
    )
    stats = tuple((as_text(r[0]), as_text(r[1]), as_int(r[2])) for r in _one(_SNAPSHOT_STATS))
    doclen = tuple((as_text(r[0]), as_int(r[1])) for r in _one(_SNAPSHOT_DOCLEN))
    return LexicalTables(posting=posting, stats=stats, doclen=doclen)


def content_digest(tables: LexicalTables) -> str:
    """sha256 over the three tables' content, canonically serialised.

    "Byte-identical after a repeated ingest" is a claim about content, not about MVCC
    timestamps, so it is stated as a digest over sorted rows.  Floats are serialised with
    ``repr``, which round-trips float64 exactly: a digest that used ``str`` would call two
    different weights equal at the seventeenth digit.
    """
    payload = {
        "posting": sorted([s, t, e, repr(w)] for s, t, e, w in tables.posting),
        "stats": sorted([s, t, df] for s, t, df in tables.stats),
        "doclen": sorted([e, n] for e, n in tables.doclen),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
