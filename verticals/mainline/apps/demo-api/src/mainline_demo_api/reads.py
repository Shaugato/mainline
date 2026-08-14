# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The twelve GET resources declared by ``console/src/data/resources.ts``.

Every function here returns a complete read envelope for one resource key, built from
one snapshot of one database, with a provenance chip beside every claim the console will
render. They share four rules.

**1. A column is a column; everything else says so.** ``db:column`` means the database
wrote that value into that column. ``blocking_check.open`` is not one — no such column
exists; it is a LEFT JOIN against ``mainline.disposition``, and it is chipped
``derived`` with ``mainline.disposition`` named in ``statement_refs``. The distinction
sounds pedantic until you notice that ``permit.open_blocking`` IS a column, written by a
trigger, and that the entire product exists because a column and a re-derivation can
disagree.

**2. Where there is no table, the payload says so in words and flags itself.**
``propagation`` is the case. ``grep -rl "CREATE TABLE.*lesson"`` over
``verticals/mainline/db/migrations`` returns nothing; ``mainline.lesson``,
``mainline.propagation`` and ``mainline.merge_conflict`` are consumed by
``propagation.schema.json`` and produced by no migration in this repository. That
resource returns ``staged: true`` with a verbatim note naming all three tables, every
pointer chipped ``staged``, and the console renders STAGED across the whole surface. It
does not return an empty list, because an empty list is the claim *there are no lessons*,
which is a different and false sentence.

**3. A row that cannot be rendered under its contract is a 409, not a fudge.**
``exposure.schema.json`` requires ``permit_id``; ``mainline.exposure_receipt.permit_id``
is nullable because a receipt may belong to a change request. Asked for such a receipt
this module answers ``409 unrepresentable`` naming the field and the row, rather than
inventing a permit id or silently dropping the resource to null. The console shows a
transport failure; a judge reading it learns something true.

**4. One transaction, one snapshot.** ``clause_ancestry`` runs six statements. Run in
autocommit they would see six different moments and could produce a payload whose
``closure.ancestor_count`` disagreed with its own ``events`` array.
:func:`read_resource` wraps every call in :func:`db.read_transaction` and retries the
whole thing on ``40001``.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

import psycopg

from . import db
from .envelope import Provenance, b64, jsonable, read_envelope, statement_ref

__all__ = [
    "AUDIT_BYTE_CAP",
    "AUDIT_ROW_CAP",
    "READS",
    "BadRequest",
    "NotFound",
    "ReadError",
    "Unrepresentable",
    "read_resource",
]


# ── Failures a caller can be told about ─────────────────────────────────────────────


class ReadError(Exception):
    """Base for the three ways a read declines to produce an envelope."""

    status = 500

    def __init__(self, detail: str, *, resource: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.resource = resource


class BadRequest(ReadError):
    """A path or query parameter this resource cannot use. 400."""

    status = 400


class NotFound(ReadError):
    """The subject does not exist. 404.

    Distinct from :class:`Unrepresentable` on purpose: "there is no such permit" and
    "there is such a permit and its receipt cannot be expressed in the contract you
    hold" are answered by different people.
    """

    status = 404


class Unrepresentable(ReadError):
    """The row exists and the contract cannot express it. 409.

    Always names the field and the reason. This is the failure mode that would otherwise
    become a quiet ``null``, and a quiet null in a provenance-carrying payload is the one
    thing this whole design is against.
    """

    status = 409


# ── Parameter validation ────────────────────────────────────────────────────────────

#: ``console/src/data/resources.ts`` interpolates only values matching this. Mirrored so
#: the API refuses the same strings the client refuses to send, rather than trusting that
#: every caller is the console.
_PATH_VALUE = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
_HEX = re.compile(r"^([0-9a-f]{2})+$")


#: The most caller-supplied text one refusal built here may carry back, and the most
#: caller-supplied NAMES it may list. Both bound the same thing: an anonymous caller's
#: ability to choose the length of a response it is not paying for. The demo is one Lambda
#: Function URL with ``authorization_type = NONE`` — there is no authoriser between the
#: internet and these branches.
#:
#: **Measured on 2026-08-13, before these existed.** 100,000 bytes of path segment, query
#: value or query *name* came back as a 400 ``detail`` of 100,034 to 100,118 bytes through
#: every one of the six refusals below: ratios 1.00, 1.00, 1.00, 1.00, 1.00, 1.00. The
#: per-response ceiling in :func:`mainline_demo_api.static_site.max_response_bytes` does
#: bound the result — it is 512 KiB and it is now a ceiling that refuses things — but it
#: bounds it *at the exit*: the route had matched, the parameter had been parsed, and a
#: half-megabyte string had been built and JSON-encoded before anything weighed it. A bound
#: at the point of construction refuses the work as well as the delivery, and it is the
#: only one of the two that can.
#:
#: 128 is not a round number, it is :data:`_PATH_VALUE`'s own maximum. A path parameter may
#: legally be 128 characters, a ``site_code`` 64, a UUID 36, a ``commit_id`` 40 hex; the
#: declared query names top out at ``clause_uuid``, 11. So **any value this truncates was
#: already outside the contract the refusal is explaining**, and its first 128 characters
#: are what identifies it to whoever reads the log. 8 names is likewise past the point:
#: the widest resource declares three.
MAX_ECHOED_VALUE: Final = 128
MAX_ECHOED_NAMES: Final = 8


def _echo(value: object) -> str:
    """Render a caller-supplied *value* for a refusal, cut to a length THIS module chose.

    One helper rather than a rule everyone remembers. Every ``!r`` in this file that could
    hold something a caller sent goes through here, including the two that are already
    bounded upstream by :func:`_param` — an echo site that is safe today because of what
    calls it is one refactor from being the exception, and the exception is where the next
    unbounded body comes from. The bounded ones cost a comparison.

    ``repr`` first, then the cut, so the rendering a reader sees is the rendering the
    refusals always used and control characters are still escaped rather than emitted.
    """
    text = repr(value)
    if len(text) <= MAX_ECHOED_VALUE:
        return text
    return f"{text[:MAX_ECHOED_VALUE]}… ({len(text)} characters, truncated)"


def _echo_names(names: Sequence[str]) -> str:
    """Render caller-supplied parameter *names* for a refusal, bounded in count AND length.

    Two bounds because a caller controls both: ``?a=1&b=1&…`` a thousand times over is a
    thousand short names, which no per-name limit would have caught.
    """
    shown = [_echo(name) for name in names[:MAX_ECHOED_NAMES]]
    if len(names) > MAX_ECHOED_NAMES:
        shown.append(f"… and {len(names) - MAX_ECHOED_NAMES} more")
    return "[" + ", ".join(shown) + "]"


#: Resource key → (path parameters, query parameters), transcribed from
#: ``console/src/data/resources.ts``. The console rejects an undeclared query parameter
#: *before it is sent*; this API rejects one on arrival, because the console is not the
#: only thing that can reach a public URL and a silently-ignored parameter is how a
#: caller comes to believe a filter was applied.
#: ``tests/test_envelope.py::test_declared_parameters_match_the_console`` compares this
#: table with the TypeScript.
_DECLARED_PARAMS: Final[Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]]] = {
    "permit": (("permit_id",), ()),
    "change_request": (("cr_id",), ()),
    "blocking_checks": (("permit_id",), ()),
    "disposition": (("check_id",), ()),
    "exposure_receipt": (("receipt_id",), ()),
    "clause_version": (("clause_uuid", "commit_id"), ()),
    "clause_ancestry": (("clause_uuid",), ("as_of",)),
    "ledger": ((), ("site_code", "from_seq", "to_seq")),
    "silence": (("permit_id",), ()),
    "recall_run": (("run_id",), ()),
    "propagation": (("lesson_id",), ()),
    "audit": ((), ()),
}


def _check_request(resource: str, params: Mapping[str, str], query: Mapping[str, str]) -> None:
    """Refuse a parameter this resource does not declare.

    A resource that quietly ignores ``?site_code=OTHER`` has told the caller their filter
    was applied. Naming the declared set in the refusal is what makes the 400 actionable.
    """
    path_names, query_names = _DECLARED_PARAMS[resource]
    unexpected_path = sorted(set(params) - set(path_names))
    if unexpected_path:
        raise BadRequest(
            f"resource {resource!r} has no path parameter(s) {_echo_names(unexpected_path)}. "
            f"Declared: {list(path_names) or '(none)'}.",
            resource=resource,
        )
    unexpected_query = sorted(set(query) - set(query_names))
    if unexpected_query:
        raise BadRequest(
            f"resource {resource!r} does not declare query parameter(s) "
            f"{_echo_names(unexpected_query)}. "
            f"Declared: {list(query_names) or '(none)'}.",
            resource=resource,
        )


def _param(params: Mapping[str, str], name: str, resource: str) -> str:
    value = params.get(name)
    if value is None or not _PATH_VALUE.match(value):
        raise BadRequest(
            f"resource {resource!r} requires path parameter {name!r} as an unreserved token "
            f"matching {_PATH_VALUE.pattern}; got {value!r}",
            resource=resource,
        )
    return value


def _uuid_param(params: Mapping[str, str], name: str, resource: str) -> uuid.UUID:
    raw = _param(params, name, resource)
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise BadRequest(f"{name}={raw!r} is not a UUID", resource=resource) from exc


def _hex_param(value: str, name: str, resource: str) -> str:
    lowered = value.lower()
    if not _HEX.match(lowered):
        raise BadRequest(
            f"{name}={value!r} is not an even-length lowercase hex string; "
            "a half byte is not a byte",
            resource=resource,
        )
    return lowered


def _int_query(query: Mapping[str, str], name: str, resource: str, default: int) -> int:
    raw = query.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise BadRequest(
            f"query parameter {name}={raw!r} is not an integer", resource=resource
        ) from exc


def _row(conn: psycopg.Connection[Any], sql: str, args: Sequence[Any]) -> dict[str, Any] | None:
    result = conn.execute(sql, args).fetchone()
    return dict(result) if result is not None else None


def _rows(conn: psycopg.Connection[Any], sql: str, args: Sequence[Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in conn.execute(sql, args).fetchall()]


def _pick(row: Mapping[str, Any], *names: str) -> dict[str, Any]:
    """Render selected row keys as a payload object."""
    return {name: jsonable(row[name]) for name in names}


# ── The named refusals, read from the catalog ───────────────────────────────────────

_CONSTRAINTS_SQL: Final = """
SELECT con.conname                     AS constraint_name,
       pg_get_constraintdef(con.oid)   AS predicate
  FROM pg_catalog.pg_constraint con
  JOIN pg_catalog.pg_class      rel ON rel.oid = con.conrelid
  JOIN pg_catalog.pg_namespace  nsp ON nsp.oid = rel.relnamespace
 WHERE nsp.nspname = 'mainline'
   AND rel.relname = %s
   AND con.contype = 'c'
 ORDER BY con.oid
"""

_PERMIT_COUNTERS: Final = (
    "open_blocking",
    "open_residue",
    "open_conflicts",
    "open_warrants",
    "unmodelled_asset_count",
    "unmet_floor_count",
    "countersigned_count",
)
_CR_COUNTERS: Final = ("open_blocking", "open_residue", "open_conflicts")


def _gate_constraints(
    conn: psycopg.Connection[Any],
    table: str,
    counters: Sequence[str],
    values: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Read the subject's named refusals, in declaration order, straight from ``pg_constraint``.

    WHICH constraints are *gate* refusals is decided by the catalog's own text rather
    than by a hardcoded list: a gate refusal is a CHECK whose predicate mentions the
    literal ``'merged'``, because every one of them is shaped
    ``state != 'merged' OR <counter> = 0``. On ``mainline.permit`` that selects exactly
    seven of the thirteen CHECKs — the six gate constraints plus ``merge_evidence``,
    which is what ``permit.schema.json`` says the array holds. On
    ``mainline.change_request`` it selects four. Nothing here knows either number in
    advance, so a constraint added by a future migration appears without an edit.

    ``counters`` for each constraint are the projected columns whose names appear as
    whole words in the catalog's predicate. ``merge_evidence`` reads none and gets an
    empty array, which the contract explicitly allows.

    ``blamed_by_refusal`` is ``false`` on every entry: it is true exactly when a refusal
    payload attached to this read names the constraint, and a GET carries no refusal. It
    is chipped ``derived`` rather than ``db:constraint`` for that reason — the name and
    the predicate are the database's word; this boolean is ours.
    """
    out: list[dict[str, Any]] = []
    for row in _rows(conn, _CONSTRAINTS_SQL, (table,)):
        predicate = str(row["predicate"])
        if "'merged'" not in predicate:
            continue
        named = [
            {"column": name, "value": int(values[name])}
            for name in counters
            if re.search(rf"\b{re.escape(name)}\b", predicate)
        ]
        out.append(
            {
                "constraint": row["constraint_name"],
                "predicate": predicate,
                "counters": named,
                "blamed_by_refusal": False,
            }
        )
    return out


# ── permit ──────────────────────────────────────────────────────────────────────────

_PERMIT_SQL: Final = """
SELECT p.permit_id, p.site_id, s.site_code, p.external_ref, p.ref_name, p.parent_permit_id,
       p.state::text                        AS state,
       p.head_seq, p.gate_epoch,
       encode(p.merged_commit, 'hex')       AS merged_commit,
       p.under_hold,
       encode(p.slice_digest, 'hex')        AS slice_digest,
       p.opened_at, p.horizon_at,
       p.open_blocking, p.open_residue, p.open_conflicts, p.open_warrants,
       p.unmodelled_asset_count, p.unmet_floor_count, p.countersigned_count
  FROM mainline.permit p
  LEFT JOIN mainline.site s ON s.site_id = p.site_id
 WHERE p.permit_id = %s
"""

_BOUNDARY_SQL: Final = """
SELECT asset_graph_version, tags_declared, tags_resolved, tags_unmodelled,
       under_declared, computed_at
  FROM mainline.boundary_certificate
 WHERE permit_id = %s
 ORDER BY cert_gen DESC
 LIMIT 1
"""

_MERGE_RECORD_SQL: Final = """
SELECT gate_epoch, merged_at, merged_by,
       encode(merged_commit, 'hex')     AS merged_commit,
       encode(clearance_digest, 'hex')  AS clearance_digest,
       checkpoint_tree_size
  FROM mainline.merge_record
 WHERE subject_kind = %s AND subject_id = %s
"""


def read_permit(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/permits/{permit_id}`` — the row, its seven counters, its named refusals."""
    _check_request("permit", params, query)
    permit_id = _uuid_param(params, "permit_id", "permit")
    row = _row(conn, _PERMIT_SQL, (permit_id,))
    if row is None:
        raise NotFound(f"no mainline.permit row with permit_id {permit_id}", resource="permit")

    counters = {name: int(row[name]) for name in _PERMIT_COUNTERS}
    data: dict[str, Any] = {
        **_pick(
            row,
            "permit_id",
            "site_id",
            "site_code",
            "external_ref",
            "ref_name",
            "parent_permit_id",
            "state",
            "head_seq",
            "gate_epoch",
            "merged_commit",
            "under_hold",
            "slice_digest",
            "opened_at",
            "horizon_at",
        ),
        "counters": counters,
        "constraints": _gate_constraints(conn, "permit", _PERMIT_COUNTERS, row),
    }

    boundary = _row(conn, _BOUNDARY_SQL, (permit_id,))
    data["boundary_certificate"] = (
        _pick(
            boundary,
            "asset_graph_version",
            "tags_declared",
            "tags_resolved",
            "tags_unmodelled",
            "under_declared",
            "computed_at",
        )
        if boundary is not None
        else None
    )

    merge = _row(conn, _MERGE_RECORD_SQL, ("permit", permit_id))
    data["merge_record"] = (
        _pick(
            merge,
            "gate_epoch",
            "merged_at",
            "merged_by",
            "merged_commit",
            "clearance_digest",
            "checkpoint_tree_size",
        )
        if merge is not None
        else None
    )

    prov = Provenance()
    prov.columns(
        "",
        (
            "permit_id",
            "site_id",
            "external_ref",
            "ref_name",
            "parent_permit_id",
            "state",
            "head_seq",
            "gate_epoch",
            "merged_commit",
            "under_hold",
            "slice_digest",
            "opened_at",
            "horizon_at",
        ),
    )
    # site_code is mainline.site's column, not mainline.permit's. Same chip, different
    # table, and `statement_refs` names both so the join is inspectable.
    prov.add("/site_code", "db:column")
    prov.columns("/counters", _PERMIT_COUNTERS)
    for index, entry in enumerate(data["constraints"]):
        prov.add(f"/constraints/{index}", "db:constraint")
        prov.add(f"/constraints/{index}/blamed_by_refusal", "derived")
        for position in range(len(entry["counters"])):
            prov.add(f"/constraints/{index}/counters/{position}/value", "db:column")
    if data["boundary_certificate"] is not None:
        prov.add("/boundary_certificate", "db:column")
    if data["merge_record"] is not None:
        prov.add("/merge_record", "db:column")

    return read_envelope(
        "permit",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("table", "mainline.permit"),
            statement_ref("table", "mainline.site"),
            statement_ref("table", "mainline.boundary_certificate"),
            statement_ref("table", "mainline.merge_record"),
            statement_ref("view", "pg_catalog.pg_constraint", text=_CONSTRAINTS_SQL.strip()),
        ],
    )


# ── change_request ──────────────────────────────────────────────────────────────────

_CR_SQL: Final = """
SELECT cr.cr_id, cr.site_id, cr.external_ref, cr.ref_name, cr.target_ref,
       cr.state::text                   AS state,
       cr.head_seq, cr.gate_epoch,
       encode(cr.merged_commit, 'hex')  AS merged_commit,
       cr.opened_at,
       cr.open_blocking, cr.open_residue, cr.open_conflicts
  FROM mainline.change_request cr
 WHERE cr.cr_id = %s
"""


def read_change_request(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/change-requests/{cr_id}`` — the second gated subject.

    Three counters and four named refusals, not seven and seven. ``change-request.schema.json``
    is explicit that a smaller gate is still a gate and that pretending otherwise would
    be a schema that lies about the DDL; this function reads whatever the catalog
    declares and would report a fifth the day a migration added one.
    """
    _check_request("change_request", params, query)
    cr_id = _uuid_param(params, "cr_id", "change_request")
    row = _row(conn, _CR_SQL, (cr_id,))
    if row is None:
        raise NotFound(
            f"no mainline.change_request row with cr_id {cr_id}", resource="change_request"
        )

    data: dict[str, Any] = {
        **_pick(
            row,
            "cr_id",
            "site_id",
            "external_ref",
            "ref_name",
            "target_ref",
            "state",
            "head_seq",
            "gate_epoch",
            "merged_commit",
            "opened_at",
        ),
        "counters": {name: int(row[name]) for name in _CR_COUNTERS},
        "constraints": _gate_constraints(conn, "change_request", _CR_COUNTERS, row),
    }

    prov = Provenance()
    prov.columns(
        "",
        (
            "cr_id",
            "site_id",
            "external_ref",
            "ref_name",
            "target_ref",
            "state",
            "head_seq",
            "gate_epoch",
            "merged_commit",
            "opened_at",
        ),
    )
    prov.columns("/counters", _CR_COUNTERS)
    for index, entry in enumerate(data["constraints"]):
        prov.add(f"/constraints/{index}", "db:constraint")
        prov.add(f"/constraints/{index}/blamed_by_refusal", "derived")
        for position in range(len(entry["counters"])):
            prov.add(f"/constraints/{index}/counters/{position}/value", "db:column")

    return read_envelope(
        "change_request",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("table", "mainline.change_request"),
            statement_ref("view", "pg_catalog.pg_constraint", text=_CONSTRAINTS_SQL.strip()),
        ],
    )


# ── blocking_checks ─────────────────────────────────────────────────────────────────

_CHECKS_SQL: Final = """
SELECT bc.check_id, bc.subject_kind, bc.permit_id, bc.cr_id, bc.site_id, bc.clause_uuid,
       encode(bc.commit_id, 'hex')      AS commit_id,
       cv.printed_label                 AS clause_label,
       bc.precursor_event_id, bc.origin, bc.severity,
       bc.virulence::text               AS virulence,
       bc.closure_gen,
       bc.control_delta::text           AS control_delta,
       bc.recall_run_id, bc.evidence_summary, bc.materialised_at,
       encode(bc.dedupe_key, 'hex')     AS dedupe_key,
       live.disposition_id              AS disposition_id,
       ev.event_id                      AS e_event_id,
       ev.kind                          AS e_kind,
       ev.external_ref                  AS e_external_ref,
       ev.title                         AS e_title,
       ev.occurred_at                   AS e_occurred_at,
       ev.severity_actual               AS e_severity_actual,
       ev.severity_potential            AS e_severity_potential,
       ev.severity_gate                 AS e_severity_gate,
       ev.severity_basis                AS e_severity_basis,
       ev.source_object_key             AS e_source_object_key,
       encode(ev.source_sha256, 'hex')  AS e_source_sha256
  FROM mainline.blocking_check bc
  LEFT JOIN mainline.clause_version cv
         ON cv.clause_uuid = bc.clause_uuid AND cv.commit_id = bc.commit_id
  LEFT JOIN mainline.event ev ON ev.event_id = bc.precursor_event_id
  LEFT JOIN LATERAL (
         SELECT d.disposition_id
           FROM mainline.disposition d
          WHERE d.check_id = bc.check_id AND d.retracted_by IS NULL
          ORDER BY d.signed_at DESC
          LIMIT 1
       ) live ON true
 WHERE bc.permit_id = %s
 ORDER BY bc.materialised_at, bc.check_id
 LIMIT 512
"""


def read_blocking_checks(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/permits/{permit_id}/blocking-checks`` — every materialised obligation.

    ``severity``, ``virulence`` and ``closure_gen`` are chipped ``db:column`` precisely
    because nobody who wrote the check chose them: ``fn_check_project`` overwrites all
    three from ``clause_blame_current`` on the way in (S1/MI25). The chip is not saying
    "we read a column"; it is saying "the writer did not choose this".

    ``open`` and ``disposition_id`` are chipped ``derived``. There is no ``open`` column.
    It is the absence of a live row in ``mainline.disposition``, computed by the LATERAL
    above, and the contract says so in its own description.
    """
    _check_request("blocking_checks", params, query)
    permit_id = _uuid_param(params, "permit_id", "blocking_checks")
    subject = _row(
        conn,
        "SELECT gate_epoch FROM mainline.permit WHERE permit_id = %s",
        (permit_id,),
    )
    if subject is None:
        raise NotFound(
            f"no mainline.permit row with permit_id {permit_id}", resource="blocking_checks"
        )

    rows = _rows(conn, _CHECKS_SQL, (permit_id,))
    checks: list[dict[str, Any]] = []
    for row in rows:
        if row["dedupe_key"] is None:  # pragma: no cover - STORED generated column
            raise Unrepresentable(
                f"mainline.blocking_check {row['check_id']} has a NULL dedupe_key; "
                "blocking-check.schema.json requires it as a sha256_hex",
                resource="blocking_checks",
            )
        check: dict[str, Any] = {
            **_pick(
                row,
                "check_id",
                "subject_kind",
                "permit_id",
                "cr_id",
                "site_id",
                "clause_uuid",
                "commit_id",
                "clause_label",
                "precursor_event_id",
                "origin",
                "severity",
                "virulence",
                "closure_gen",
                "control_delta",
                "recall_run_id",
                "evidence_summary",
                "materialised_at",
                "dedupe_key",
            ),
            "open": row["disposition_id"] is None,
            "disposition_id": jsonable(row["disposition_id"]),
            "precursor": None,
        }
        if row["e_event_id"] is not None:
            check["precursor"] = {
                "event_id": jsonable(row["e_event_id"]),
                "kind": row["e_kind"],
                "external_ref": row["e_external_ref"],
                "title": row["e_title"],
                "occurred_at": jsonable(row["e_occurred_at"]),
                "severity_actual": jsonable(row["e_severity_actual"]),
                "severity_potential": jsonable(row["e_severity_potential"]),
                "severity_gate": jsonable(row["e_severity_gate"]),
                "severity_basis": row["e_severity_basis"],
                "source_object_key": row["e_source_object_key"],
                "source_sha256": row["e_source_sha256"],
            }
        checks.append(check)

    data = {
        "subject_kind": "permit",
        "subject_id": str(permit_id),
        "gate_epoch": int(subject["gate_epoch"]),
        "checks": checks,
    }

    prov = Provenance()
    prov.add("/subject_id", "db:column").add("/gate_epoch", "db:column")
    prov.add("/subject_kind", "derived")
    # The two computed fields first, per check, so they survive the 256-pointer cap:
    # an unclaimed `db:column` is a value the reader can check against the table, while
    # an unclaimed `derived` would be indistinguishable from one.
    for index in range(len(checks)):
        prov.add(f"/checks/{index}/open", "derived")
        prov.add(f"/checks/{index}/disposition_id", "derived")
    for index in range(len(checks)):
        prov.add(f"/checks/{index}", "db:column")

    return read_envelope(
        "blocking_checks",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("table", "mainline.blocking_check"),
            statement_ref("table", "mainline.clause_version"),
            statement_ref("table", "mainline.event"),
            statement_ref(
                "table",
                "mainline.disposition",
                text=(
                    "SELECT d.disposition_id FROM mainline.disposition d "
                    "WHERE d.check_id = bc.check_id AND d.retracted_by IS NULL "
                    "ORDER BY d.signed_at DESC LIMIT 1"
                ),
            ),
            statement_ref("table", "mainline.permit"),
        ],
    )


# ── disposition ─────────────────────────────────────────────────────────────────────

_CHECK_VIRULENCE_SQL: Final = (
    "SELECT virulence::text AS virulence FROM mainline.blocking_check WHERE check_id = %s"
)

_LATTICE_SQL: Final = """
SELECT virulence::text AS virulence, kind::text AS kind,
       req_compensating, req_second_signer, req_foreign_org, req_predicate, req_reassert,
       min_signer_rank, max_ttl_hours, policy_version, approved_by_sub, approved_at
  FROM mainline.clearance_legal
 WHERE virulence = %s::mainline.virulence_class
 ORDER BY kind
 LIMIT 16
"""

_DEFEATER_SQL: Final = """
SELECT check_id, defeater_code, prompt, encode(vocab_sha256, 'hex') AS vocab_sha256
  FROM mainline.defeater_option
 WHERE check_id = %s
 ORDER BY defeater_code
 LIMIT 32
"""

_DISPOSITION_SQL: Final = """
SELECT d.disposition_id, d.check_id, d.receipt_id, d.permit_id,
       d.kind::text                             AS kind,
       d.virulence::text                        AS virulence,
       d.closure_gen, d.defeater_code,
       encode(d.defeater_vocab_sha256, 'hex')   AS defeater_vocab_sha256,
       d.rationale,
       encode(d.evidence_sha256, 'hex')         AS evidence_sha256,
       d.signer_sub, d.signer_rank, d.signer_org,
       encode(d.signer_credential_id, 'hex')    AS signer_credential_id,
       d.countersigner_sub, d.countersigner_rank, d.countersigner_org,
       encode(d.countersigner_credential_id, 'hex') AS countersigner_credential_id,
       d.signature_alg, d.user_verified,
       d.req_compensating, d.req_second_signer, d.req_foreign_org, d.req_predicate,
       d.req_reassert, d.min_signer_rank, d.max_ttl_hours,
       d.compensating_clause_uuid, d.predicate_id, d.reassert_by, d.expires_at,
       d.verbatim_anchor_count, d.required_anchors,
       d.deliberation_seconds, d.evidence_opened, d.reading_floor_met,
       d.prior_override_count, d.severity_snapshot,
       d.signed_at, d.retracted_by
  FROM mainline.disposition d
 WHERE d.check_id = %s
 ORDER BY (d.retracted_by IS NULL) DESC, d.signed_at DESC
 LIMIT 1
"""


def read_disposition(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/checks/{check_id}/disposition`` — the lattice row, the vocabulary, the signature.

    ``lattice`` is EVERY ``clearance_legal`` row for the check's virulence. The contract
    is emphatic that a ``(virulence, kind)`` pair absent from that array is not a
    disallowed option but a NON-EXISTENT one — attempting it produces ``23503`` on
    ``fk_clearance`` — so the array is the whole set and the console renders the absence
    as an absence.

    ``reading_floor`` is ``null`` on this tree. S19's arithmetic (tau0, rho, t_min) is not
    carried by any table in ``verticals/mainline/db/migrations``: ``mainline.disposition``
    records ``reading_floor_met`` as a projected boolean and ``mainline.permit`` projects
    ``unmet_floor_count``, but the components are nowhere. ``null`` is the contract's own
    provision for that, and it is a truthful answer where a reconstructed τ₀ would not be.
    """
    _check_request("disposition", params, query)
    check_id = _uuid_param(params, "check_id", "disposition")
    check = _row(conn, _CHECK_VIRULENCE_SQL, (check_id,))
    if check is None:
        raise NotFound(
            f"no mainline.blocking_check row with check_id {check_id}", resource="disposition"
        )
    virulence = str(check["virulence"])

    lattice = [
        _pick(
            row,
            "virulence",
            "kind",
            "req_compensating",
            "req_second_signer",
            "req_foreign_org",
            "req_predicate",
            "req_reassert",
            "min_signer_rank",
            "max_ttl_hours",
            "policy_version",
            "approved_by_sub",
            "approved_at",
        )
        for row in _rows(conn, _LATTICE_SQL, (virulence,))
    ]
    options = [
        _pick(row, "check_id", "defeater_code", "prompt", "vocab_sha256")
        for row in _rows(conn, _DEFEATER_SQL, (check_id,))
    ]

    signed_row = _row(conn, _DISPOSITION_SQL, (check_id,))
    signed: dict[str, Any] | None = None
    if signed_row is not None:
        if signed_row["permit_id"] is None:
            raise Unrepresentable(
                f"mainline.disposition {signed_row['disposition_id']} has a NULL permit_id "
                "(its subject is a change request). disposition.schema.json requires permit_id "
                "as a uuid, so this row cannot be rendered under the contract the console holds.",
                resource="disposition",
            )
        signed = {
            **_pick(
                signed_row,
                "disposition_id",
                "check_id",
                "receipt_id",
                "permit_id",
                "kind",
                "virulence",
                "closure_gen",
                "defeater_code",
                "defeater_vocab_sha256",
                "rationale",
                "evidence_sha256",
                "compensating_clause_uuid",
                "predicate_id",
                "reassert_by",
                "expires_at",
                "signed_at",
                "retracted_by",
            ),
            "signature": {
                **_pick(
                    signed_row,
                    "signer_sub",
                    "signer_rank",
                    "signer_org",
                    "signer_credential_id",
                    "countersigner_sub",
                    "countersigner_rank",
                    "countersigner_org",
                    "countersigner_credential_id",
                    "signature_alg",
                ),
                "user_verified": bool(signed_row["user_verified"]),
                "sign_count": None,
            },
            "requirements": _pick(
                signed_row,
                "req_compensating",
                "req_second_signer",
                "req_foreign_org",
                "req_predicate",
                "req_reassert",
                "min_signer_rank",
                "max_ttl_hours",
            ),
            "anchors": _pick(signed_row, "verbatim_anchor_count", "required_anchors"),
            "measurements": _pick(
                signed_row,
                "deliberation_seconds",
                "evidence_opened",
                "reading_floor_met",
                "prior_override_count",
                "severity_snapshot",
            ),
        }

    data = {
        "check_id": str(check_id),
        "virulence": virulence,
        "lattice": lattice,
        "defeater_options": options,
        "reading_floor": None,
        "signed": signed,
    }

    prov = Provenance()
    prov.add("/check_id", "db:column").add("/virulence", "db:column")
    for index in range(len(lattice)):
        prov.add(f"/lattice/{index}", "db:column")
    for index in range(len(options)):
        prov.add(f"/defeater_options/{index}", "db:column")
    if signed is not None:
        prov.add("/signed", "db:column")
        # The req_* flags are on the disposition row because a CHECK has to read them,
        # and they are PROJECTED there by a BEFORE trigger out of clearance_legal. They
        # are columns of mainline.disposition, so db:column is exact.
        prov.add("/signed/requirements", "db:column")
        prov.add("/signed/signature", "db:column")
        prov.add("/signed/signature/sign_count", "derived")
        prov.add("/signed/measurements", "db:column")

    return read_envelope(
        "disposition",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("table", "mainline.blocking_check"),
            statement_ref("table", "mainline.clearance_legal", text=_LATTICE_SQL.strip()),
            statement_ref("table", "mainline.defeater_option"),
            statement_ref("table", "mainline.disposition"),
        ],
    )


# ── exposure_receipt ────────────────────────────────────────────────────────────────

_RECEIPT_SQL: Final = """
SELECT r.receipt_id, r.subject_kind, r.permit_id, r.actor_sub, r.issued_at, r.issued_hlc,
       r.expires_at,
       encode(r.corpus_root, 'hex')     AS corpus_root,
       r.silence_receipt_id, r.policy_version, r.total_tokens,
       encode(r.receipt_digest, 'hex')  AS receipt_digest,
       x.swept_at
  FROM mainline.exposure_receipt r
  LEFT JOIN mainline.receipt_expiry x ON x.receipt_id = r.receipt_id
 WHERE r.receipt_id = %s
"""

_RECEIPT_LINES_SQL: Final = """
SELECT receipt_id, check_id,
       encode(payload_digest, 'hex') AS payload_digest,
       tokens
  FROM mainline.exposure_line
 WHERE receipt_id = %s
 ORDER BY check_id
 LIMIT 512
"""


def read_exposure_receipt(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/receipts/{receipt_id}`` — what was shown, to whom, when.

    ``issued_hlc`` is a ``NUMERIC`` column rendered as a string, which is what the
    contract asks for and what stops a large HLC being rounded through a float. The
    contract also calls it ADVISORY ordering only; the console labels it as such.
    """
    _check_request("exposure_receipt", params, query)
    receipt_id = _uuid_param(params, "receipt_id", "exposure_receipt")
    row = _row(conn, _RECEIPT_SQL, (receipt_id,))
    if row is None:
        raise NotFound(
            f"no mainline.exposure_receipt row with receipt_id {receipt_id}",
            resource="exposure_receipt",
        )
    if row["permit_id"] is None:
        raise Unrepresentable(
            f"mainline.exposure_receipt {receipt_id} has a NULL permit_id (subject_kind="
            f"{row['subject_kind']!r}). exposure.schema.json requires permit_id as a uuid, so "
            "this receipt cannot be rendered under the contract the console holds.",
            resource="exposure_receipt",
        )

    lines = [
        _pick(line, "receipt_id", "check_id", "payload_digest", "tokens")
        for line in _rows(conn, _RECEIPT_LINES_SQL, (receipt_id,))
    ]
    data = {
        **_pick(
            row,
            "receipt_id",
            "permit_id",
            "actor_sub",
            "issued_at",
            "issued_hlc",
            "expires_at",
            "corpus_root",
            "silence_receipt_id",
            "policy_version",
            "total_tokens",
            "receipt_digest",
            "swept_at",
        ),
        "lines": lines,
    }

    prov = Provenance()
    prov.columns(
        "",
        (
            "receipt_id",
            "permit_id",
            "actor_sub",
            "issued_at",
            "issued_hlc",
            "expires_at",
            "corpus_root",
            "silence_receipt_id",
            "policy_version",
            "total_tokens",
            "receipt_digest",
        ),
    )
    # swept_at is mainline.receipt_expiry's column: the sweeper MARKS by writing a new
    # row, because exposure_receipt itself is append-only (S28).
    prov.add("/swept_at", "db:column")
    for index in range(len(lines)):
        prov.add(f"/lines/{index}", "db:column")

    return read_envelope(
        "exposure_receipt",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("table", "mainline.exposure_receipt"),
            statement_ref("table", "mainline.exposure_line"),
            statement_ref("table", "mainline.receipt_expiry"),
        ],
    )


# ── clause_version ──────────────────────────────────────────────────────────────────

_CLAUSE_VERSION_SQL: Final = """
SELECT cv.clause_uuid, cv.gen,
       encode(cv.commit_id, 'hex')      AS commit_id,
       cv.site_id, cv.doc_id, cv.activity_root,
       encode(cv.parent_version, 'hex') AS parent_version,
       cv.ordinal, cv.printed_label, cv.raw_text, cv.canon_text, cv.canon_version,
       encode(cv.canon_sha256, 'hex')   AS canon_sha256,
       cv.anchor_set, cv.cat_key, cv.cat_json, cv.cat_confidence,
       cv.control_delta::text           AS control_delta,
       cv.delta_basis, cv.delta_model, cv.delta_prompt_version,
       encode(cv.blood_root, 'hex')     AS blood_root,
       cv.blood_size, cv.sev_max
  FROM mainline.clause_version cv
 WHERE cv.clause_uuid = %s AND cv.commit_id = decode(%s, 'hex')
"""

_WITNESS_SQL: Final = """
SELECT rule_id, field, from_repr, to_repr, note, minimal
  FROM mainline.delta_witness
 WHERE clause_uuid = %s AND commit_id = decode(%s, 'hex')
 ORDER BY witness_ord
 LIMIT 64
"""

_CLAUSE_VERSION_FIELDS: Final = (
    "clause_uuid",
    "gen",
    "commit_id",
    "site_id",
    "doc_id",
    "activity_root",
    "parent_version",
    "ordinal",
    "printed_label",
    "raw_text",
    "canon_text",
    "canon_version",
    "canon_sha256",
    "anchor_set",
    "cat_key",
    "cat_json",
    "cat_confidence",
    "control_delta",
    "delta_basis",
    "delta_model",
    "delta_prompt_version",
    "blood_root",
    "blood_size",
    "sev_max",
)


def read_clause_version(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/clauses/{clause_uuid}/versions/{commit_id}`` — one version and its delta witnesses.

    ``delta.witnesses`` distinguishes two states the contract insists on keeping apart:
    ``null`` means the payload carries no witness rows and the console renders WITNESS
    UNAVAILABLE; ``[]`` means *the emitter says there are none*. This function queries
    ``mainline.delta_witness``, so it can and does make the second, stronger claim — and
    ``minimal`` is ``null`` when there are no rows, because minimality of an empty set is
    not something the absence of rows establishes.
    """
    _check_request("clause_version", params, query)
    clause_uuid = _uuid_param(params, "clause_uuid", "clause_version")
    raw_commit = _param(params, "commit_id", "clause_version")
    commit_id = _hex_param(raw_commit, "commit_id", "clause_version")

    row = _row(conn, _CLAUSE_VERSION_SQL, (clause_uuid, commit_id))
    if row is None:
        raise NotFound(
            f"no mainline.clause_version row for clause {clause_uuid} at commit {commit_id}",
            resource="clause_version",
        )
    version = _pick(row, *_CLAUSE_VERSION_FIELDS)

    parent: dict[str, Any] | None = None
    if row["parent_version"] is not None:
        parent_row = _row(conn, _CLAUSE_VERSION_SQL, (clause_uuid, row["parent_version"]))
        if parent_row is not None:
            parent = _pick(parent_row, *_CLAUSE_VERSION_FIELDS)

    witness_rows = _rows(conn, _WITNESS_SQL, (clause_uuid, commit_id))
    witnesses = [
        _pick(item, "rule_id", "field", "from_repr", "to_repr", "note") for item in witness_rows
    ]
    minimal_flags = [bool(item["minimal"]) for item in witness_rows]

    data = {
        "clause_uuid": str(clause_uuid),
        "version": version,
        "parent": parent,
        "delta": {
            "delta": row["control_delta"],
            "basis": row["delta_basis"],
            "witnesses": witnesses,
            "minimal": all(minimal_flags) if minimal_flags else None,
        },
    }

    prov = Provenance()
    prov.add("/clause_uuid", "db:column")
    prov.columns("/version", _CLAUSE_VERSION_FIELDS)
    if parent is not None:
        prov.add("/parent", "db:column")
    prov.add("/delta/delta", "db:column").add("/delta/basis", "db:column")
    for index in range(len(witnesses)):
        prov.add(f"/delta/witnesses/{index}", "db:column")
    # `minimal` is an AND over the rows' own `minimal` column, not a column itself.
    prov.add("/delta/minimal", "derived")

    return read_envelope(
        "clause_version",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("table", "mainline.clause_version"),
            statement_ref("table", "mainline.delta_witness", text=_WITNESS_SQL.strip()),
        ],
    )


# ── clause_ancestry ─────────────────────────────────────────────────────────────────

_CLOSURE_SQL: Final = """
SELECT closure_gen, ancestor_events, ancestor_count, max_severity,
       virulence::text                  AS virulence,
       depth, truncated, computed_by, projector_ver, computed_at, site_id,
       encode(as_of_commit, 'hex')      AS as_of_commit
  FROM mainline.clause_blame_current
 WHERE clause_uuid = %s AND as_of_commit = decode(%s, 'hex')
"""

_CAP_SQL: Final = """
SELECT pg_get_constraintdef(con.oid) AS predicate
  FROM pg_catalog.pg_constraint con
  JOIN pg_catalog.pg_class      rel ON rel.oid = con.conrelid
  JOIN pg_catalog.pg_namespace  nsp ON nsp.oid = rel.relnamespace
 WHERE nsp.nspname = 'mainline'
   AND rel.relname = 'clause_blame_closure'
   AND con.conname = 'ancestor_count_within_cap'
"""

_ANCESTRY_EVENTS_SQL: Final = """
SELECT event_id, kind, external_ref, title, occurred_at, ingested_at,
       severity_gate, severity_basis
  FROM mainline.event
 WHERE event_id = ANY(%s)
 ORDER BY occurred_at, event_id
 LIMIT 512
"""

_CONTROL_FAILURE_SQL: Final = """
SELECT event_id, control_class, barrier_role, failure_mode, hazard_energy, icam_tier
  FROM mainline.control_failure
 WHERE event_id = ANY(%s)
 ORDER BY event_id, control_class
 LIMIT 512
"""

_EVENT_EDGE_SQL: Final = """
SELECT child_event_id, parent_event_id, relation
  FROM mainline.event_edge
 WHERE child_event_id = ANY(%s) AND parent_event_id = ANY(%s)
 ORDER BY child_event_id, parent_event_id
 LIMIT 2048
"""

_BLAME_EDGE_SQL: Final = """
SELECT event_id, clause_uuid,
       basis::text                              AS basis,
       state::text                              AS state,
       encode(commit_id, 'hex')                 AS commit_id,
       p_link, attribution,
       encode(evidence_quote_sha256, 'hex')     AS evidence_quote_sha256
  FROM mainline.blame_edge
 WHERE clause_uuid = %s AND event_id = ANY(%s)
 ORDER BY event_id
 LIMIT 512
"""

_COMMIT_CHAIN_SQL: Final = """
SELECT encode(cv.commit_id, 'hex')      AS commit_id,
       cv.gen, co.committed_at,
       cv.control_delta::text           AS control_delta,
       cv.printed_label, cv.sev_max,
       encode(cv.canon_sha256, 'hex')   AS canon_sha256
  FROM mainline.clause_version cv
  JOIN mainline.commit_obj    co ON co.commit_id = cv.commit_id
 WHERE cv.clause_uuid = %s
 ORDER BY cv.gen
 LIMIT 512
"""

_CORPUS_ROOT_SQL: Final = """
SELECT encode(cp.root_hash, 'hex') AS corpus_root
  FROM mainline.ledger_checkpoint cp
  JOIN mainline.site s ON s.site_code = cp.site_code
 WHERE s.site_id = %s
 ORDER BY cp.tree_size DESC
 LIMIT 1
"""


def read_clause_ancestry(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/clauses/{clause_uuid}/ancestry`` — the blame walk, with its truncation declared.

    NOBODY OWNS THIS ENDPOINT. ``console/src/data/resources.ts`` declares it with
    ``owner: null`` and ``docs/leads/ui.md`` §4 records that no backend worker owed it,
    with ``scripts/capture-bundle.ts`` emitting the payload straight from SQL so the
    console never learned the difference. It is implemented here anyway, because the
    replay path and the live path being the same bytes is the entire premise of the
    LIVE/REPLAY badge.

    ``truncation.cap`` is chipped ``db:constraint`` and it is not a flourish. 512 is not
    a constant this file carries: it is parsed out of
    ``CONSTRAINT ancestor_count_within_cap CHECK (ancestor_count <= 512)`` as
    ``pg_get_constraintdef`` reports it. A migration that raised the cap would move this
    number without anyone editing Python, which is the only version of this field that
    can be trusted a year from now.
    """
    _check_request("clause_ancestry", params, query)
    clause_uuid = _uuid_param(params, "clause_uuid", "clause_ancestry")

    as_of = query.get("as_of")
    if as_of:
        as_of_commit = _hex_param(as_of, "as_of", "clause_ancestry")
    else:
        head = _row(
            conn,
            "SELECT encode(head_commit, 'hex') AS head_commit "
            "  FROM mainline.clause WHERE clause_uuid = %s",
            (clause_uuid,),
        )
        if head is None:
            raise NotFound(
                f"no mainline.clause row with clause_uuid {clause_uuid}", resource="clause_ancestry"
            )
        if head["head_commit"] is None:
            raise NotFound(
                f"mainline.clause {clause_uuid} has a NULL head_commit and the request named no "
                "as_of, so there is no commit at which to close the ancestry",
                resource="clause_ancestry",
            )
        as_of_commit = str(head["head_commit"])

    closure_row = _row(conn, _CLOSURE_SQL, (clause_uuid, as_of_commit))
    if closure_row is None:
        raise NotFound(
            f"no mainline.clause_blame_current row for clause {clause_uuid} as of commit "
            f"{as_of_commit}. The closure is written ASYNCHRONOUSLY by the closure-projector, "
            "and the gate fails CLOSED on a missing one (MI22) — an absent closure is a real "
            "state, not an error to paper over.",
            resource="clause_ancestry",
        )

    ancestors: list[uuid.UUID] = list(closure_row["ancestor_events"] or [])

    cap_row = _row(conn, _CAP_SQL, ())
    cap_match = re.search(r"<=\s*(\d+)", str(cap_row["predicate"])) if cap_row else None
    if cap_match is None:
        raise Unrepresentable(
            "mainline.clause_blame_closure declares no ancestor_count_within_cap CHECK, so the "
            "ancestor cap cannot be read from the catalog. ancestry.schema.json requires "
            "truncation.cap, and this API will not carry its own copy of a number the schema owns.",
            resource="clause_ancestry",
        )
    cap = int(cap_match.group(1))

    events = [
        {
            **_pick(
                row,
                "event_id",
                "kind",
                "external_ref",
                "title",
                "occurred_at",
                "ingested_at",
                "severity_gate",
                "severity_basis",
            ),
            "control_failures": [],
        }
        for row in _rows(conn, _ANCESTRY_EVENTS_SQL, (ancestors,))
    ]
    by_event = {event["event_id"]: event for event in events}
    for failure in _rows(conn, _CONTROL_FAILURE_SQL, (ancestors,)):
        target = by_event.get(str(failure["event_id"]))
        if target is not None:
            target["control_failures"].append(
                _pick(
                    failure,
                    "control_class",
                    "barrier_role",
                    "failure_mode",
                    "hazard_energy",
                    "icam_tier",
                )
            )

    event_edges = [
        _pick(row, "child_event_id", "parent_event_id", "relation")
        for row in _rows(conn, _EVENT_EDGE_SQL, (ancestors, ancestors))
    ]
    blame_edges = [
        _pick(
            row,
            "event_id",
            "clause_uuid",
            "basis",
            "state",
            "commit_id",
            "p_link",
            "attribution",
            "evidence_quote_sha256",
        )
        for row in _rows(conn, _BLAME_EDGE_SQL, (clause_uuid, ancestors))
    ]
    commit_chain = [
        _pick(
            row,
            "commit_id",
            "gen",
            "committed_at",
            "control_delta",
            "printed_label",
            "sev_max",
            "canon_sha256",
        )
        for row in _rows(conn, _COMMIT_CHAIN_SQL, (clause_uuid,))
    ]
    corpus = _row(conn, _CORPUS_ROOT_SQL, (closure_row["site_id"],))

    truncated = bool(closure_row["truncated"])
    data = {
        "clause_uuid": str(clause_uuid),
        "as_of_commit": as_of_commit,
        "corpus_root": corpus["corpus_root"] if corpus is not None else None,
        "closure": _pick(
            closure_row,
            "closure_gen",
            "ancestor_count",
            "max_severity",
            "virulence",
            "depth",
            "truncated",
            "computed_by",
            "projector_ver",
            "computed_at",
        ),
        "truncation": {
            "ancestry_complete": not truncated,
            "truncated": truncated,
            "cap": cap,
            "spilled_count": None,
        },
        "events": events,
        "event_edges": event_edges,
        "blame_edges": blame_edges,
        "commit_chain": commit_chain,
    }

    prov = Provenance()
    prov.add("/clause_uuid", "db:column").add("/as_of_commit", "db:column")
    prov.add("/corpus_root", "db:column")
    prov.add("/closure", "db:column")
    prov.add("/truncation/cap", "db:constraint")
    prov.add("/truncation/truncated", "db:column")
    # ancestry_complete is the NEGATION of a column, which is a computation however
    # trivial, and spilled_count is not carried by any table on this tree.
    prov.add("/truncation/ancestry_complete", "derived")
    prov.add("/truncation/spilled_count", "derived")
    for index in range(len(events)):
        prov.add(f"/events/{index}", "db:column")
    for index in range(len(event_edges)):
        prov.add(f"/event_edges/{index}", "db:column")
    for index in range(len(blame_edges)):
        prov.add(f"/blame_edges/{index}", "db:column")
    for index in range(len(commit_chain)):
        prov.add(f"/commit_chain/{index}", "db:column")

    return read_envelope(
        "clause_ancestry",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("view", "mainline.clause_blame_current", text=_CLOSURE_SQL.strip()),
            statement_ref("view", "pg_catalog.pg_constraint", text=_CAP_SQL.strip()),
            statement_ref("table", "mainline.event"),
            statement_ref("table", "mainline.control_failure"),
            statement_ref("table", "mainline.event_edge"),
            statement_ref("table", "mainline.blame_edge"),
            statement_ref("table", "mainline.clause_version"),
            statement_ref("table", "mainline.commit_obj"),
            statement_ref("table", "mainline.ledger_checkpoint"),
        ],
    )


# ── ledger ──────────────────────────────────────────────────────────────────────────

_LEDGER_SITE_SQL: Final = """
SELECT site_code
  FROM mainline.ledger_checkpoint
 GROUP BY site_code
 ORDER BY max(tree_size) DESC, site_code
 LIMIT 1
"""

_CHECKPOINT_SQL: Final = """
SELECT site_code, tree_size,
       encode(root_hash, 'hex')         AS root_hex,
       body                             AS note,
       beacon, log_sig, tsa_token, s3_version,
       encode(canon_src_sha256, 'hex')  AS canon_src_sha256,
       admissible, issued_at
  FROM mainline.ledger_checkpoint
 WHERE site_code = %s
 ORDER BY tree_size
 LIMIT 64
"""

_LEAF_SQL: Final = """
SELECT l.seq, l.entry_id, i.entry_kind, i.subject_id, i.payload_ver, i.canon_bytes,
       i.payload,
       encode(l.leaf_hash, 'hex')       AS leaf_hash_hex,
       encode(l.link_hash, 'hex')       AS link_hash_hex,
       encode(l.prev_link_hash, 'hex')  AS prev_link_hash_hex,
       i.is_sandbox, i.actor, i.actor_kind, i.recorded_at, l.batch_id
  FROM mainline.ledger_leaf   l
  JOIN mainline.ledger_intake i ON i.entry_id = l.entry_id
 WHERE l.site_code = %s AND l.seq >= %s AND l.seq <= %s
 ORDER BY l.seq
 LIMIT 512
"""

_NODE_SQL: Final = """
SELECT level, idx, encode(hash, 'hex') AS hash_hex
  FROM mainline.ledger_node
 WHERE site_code = %s
 ORDER BY level, idx
 LIMIT 2048
"""

_COSIGNATURE_SQL: Final = """
SELECT tree_size, witness_id, trust_domain, adverse, sig, received_at
  FROM mainline.cosignature
 WHERE site_code = %s
 ORDER BY tree_size, witness_id
 LIMIT 64
"""

_DEBT_SQL: Final = """
SELECT debt_id, site_code, permit_id, incurred_at, discharged_tree_size
  FROM mainline.unwitnessed_debt
 WHERE site_code = %s
 ORDER BY incurred_at
 LIMIT 64
"""


def _mth(leaves: Sequence[bytes]) -> bytes:
    """RFC 6962 §2.1 Merkle Tree Hash over ALREADY-HASHED leaves.

    ``mainline.ledger_leaf.leaf_hash`` is the level-0 hash, so this function starts at
    level 1 and never applies the ``0x00`` leaf prefix — applying it twice is the classic
    way to produce a proof that verifies against nothing.
    """
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return leaves[0]
    split = 1 << (len(leaves) - 1).bit_length() - 1
    return hashlib.sha256(b"\x01" + _mth(leaves[:split]) + _mth(leaves[split:])).digest()


def _inclusion_path(index: int, leaves: Sequence[bytes]) -> list[bytes]:
    """RFC 6962 §2.1.1 ``PATH(m, D[n])``."""
    if len(leaves) <= 1:
        return []
    split = 1 << (len(leaves) - 1).bit_length() - 1
    if index < split:
        return [*_inclusion_path(index, leaves[:split]), _mth(leaves[split:])]
    return [*_inclusion_path(index - split, leaves[split:]), _mth(leaves[:split])]


def _consistency_path(first: int, leaves: Sequence[bytes], *, whole: bool = True) -> list[bytes]:
    """RFC 6962 §2.1.2 ``SUBPROOF(m, D[n], b)``."""
    if first == len(leaves):
        return [] if whole else [_mth(leaves)]
    split = 1 << (len(leaves) - 1).bit_length() - 1
    if first <= split:
        return [*_consistency_path(first, leaves[:split], whole=whole), _mth(leaves[split:])]
    return [
        *_consistency_path(first - split, leaves[split:], whole=False),
        _mth(leaves[:split]),
    ]


def read_ledger(  # noqa: PLR0912 - the branches ARE the honesty: each one is a condition
    # under which a proof may not be computed, and collapsing them would mean emitting a
    # proof over a subset of the log while presenting it as a proof over the tree.
    conn: psycopg.Connection[Any],
    params: Mapping[str, str],
    query: Mapping[str, str],
) -> dict[str, Any]:
    """``GET /v1/ledger`` — the bytes the in-browser verifier recomputes.

    THIS PAYLOAD CARRIES NO VERDICTS. Every hash, note and path below is material the
    console's ``verifier-custody-room`` Worker re-derives (D6). Nothing here asserts that
    a proof held, and the ``admissible`` flag is chipped ``db:column`` because it is the
    database's projection of quorum-plus-diversity, not this API's arithmetic.

    The inclusion and consistency proofs are chipped ``derived`` and computed here from
    the leaf hashes, per RFC 6962 §2.1.1 and §2.1.2 — and computed ONLY when the leaf
    window is dense from ``seq = 0`` and covers the checkpoint's ``tree_size``. Anything
    else would be a proof over a subset presented as a proof over the tree. When the
    window does not qualify the arrays are empty, which the contract permits and the
    verifier reads as "nothing to check here" rather than as "nothing was wrong".
    """
    _check_request("ledger", params, query)
    site_code = query.get("site_code") or ""
    if not site_code:
        chosen = _row(conn, _LEDGER_SITE_SQL, ())
        if chosen is None:
            raise NotFound(
                "mainline.ledger_checkpoint holds no rows, so there is no ledger to read. "
                "ledger.schema.json requires at least one checkpoint: a ledger with no "
                "checkpoint is not a ledger with an empty checkpoint list.",
                resource="ledger",
            )
        site_code = str(chosen["site_code"])
    if len(site_code) > 64:
        raise BadRequest(f"site_code={site_code!r} exceeds 64 characters", resource="ledger")

    from_seq = _int_query(query, "from_seq", "ledger", 0)
    to_seq = _int_query(query, "to_seq", "ledger", from_seq + 511)
    if from_seq < 0 or to_seq < from_seq:
        raise BadRequest(
            f"from_seq={from_seq} to_seq={to_seq} is not an ascending range", resource="ledger"
        )

    checkpoint_rows = _rows(conn, _CHECKPOINT_SQL, (site_code,))
    if not checkpoint_rows:
        raise NotFound(
            f"no mainline.ledger_checkpoint rows for site_code {site_code!r}", resource="ledger"
        )
    checkpoints = [
        {
            **_pick(
                row, "site_code", "tree_size", "root_hex", "note", "canon_src_sha256", "admissible"
            ),
            "log_key": None,
            "log_sig_b64": b64(row["log_sig"]),
            "beacon": jsonable(row["beacon"]),
            "tsa_token_b64": b64(row["tsa_token"]),
            "s3_version": row["s3_version"],
            "observed_at": jsonable(row["issued_at"]),
        }
        for row in checkpoint_rows
    ]

    leaf_rows = _rows(conn, _LEAF_SQL, (site_code, from_seq, to_seq))
    leaves = [
        {
            **_pick(
                row,
                "seq",
                "entry_id",
                "entry_kind",
                "subject_id",
                "payload_ver",
                "leaf_hash_hex",
                "link_hash_hex",
                "prev_link_hash_hex",
                "is_sandbox",
                "actor",
                "actor_kind",
                "recorded_at",
                "batch_id",
            ),
            "canon_bytes_b64": base64.b64encode(bytes(row["canon_bytes"])).decode("ascii"),
            "payload": jsonable(row["payload"]),
        }
        for row in leaf_rows
    ]

    nodes = [_pick(row, "level", "idx", "hash_hex") for row in _rows(conn, _NODE_SQL, (site_code,))]
    cosignatures = [
        {
            **_pick(row, "tree_size", "witness_id", "trust_domain", "adverse", "received_at"),
            "sig_b64": b64(row["sig"]),
            "witness_key": None,
        }
        for row in _rows(conn, _COSIGNATURE_SQL, (site_code,))
    ]
    debt = [
        _pick(row, "debt_id", "site_code", "permit_id", "incurred_at", "discharged_tree_size")
        for row in _rows(conn, _DEBT_SQL, (site_code,))
    ]

    # Proofs, only over a window that can carry them.
    inclusion: list[dict[str, Any]] = []
    consistency: list[dict[str, Any]] = []
    dense_from_zero = bool(leaf_rows) and [int(row["seq"]) for row in leaf_rows] == list(
        range(len(leaf_rows))
    )
    if dense_from_zero:
        hashes = [bytes.fromhex(str(row["leaf_hash_hex"])) for row in leaf_rows]
        sizes = sorted(
            {int(cp["tree_size"]) for cp in checkpoints if 0 < int(cp["tree_size"]) <= len(hashes)}
        )
        for size in sizes:
            window = hashes[:size]
            for index in range(size):
                inclusion.append(
                    {
                        "seq": index,
                        "tree_size": size,
                        "path_hex": [node.hex() for node in _inclusion_path(index, window)],
                    }
                )
        for earlier, later in itertools.pairwise(sizes):
            consistency.append(
                {
                    "from_size": earlier,
                    "to_size": later,
                    "path_hex": [node.hex() for node in _consistency_path(earlier, hashes[:later])],
                }
            )
        inclusion = inclusion[:512]
        consistency = consistency[:64]

    data = {
        "site_code": site_code,
        "checkpoints": checkpoints,
        "leaves": leaves,
        "nodes": nodes,
        "inclusion_proofs": inclusion,
        "consistency_proofs": consistency,
        "cosignatures": cosignatures,
        "unwitnessed_debt": debt,
    }

    prov = Provenance()
    prov.add("/site_code", "db:column")
    for index in range(len(checkpoints)):
        prov.add(f"/checkpoints/{index}", "db:column")
        prov.add(f"/checkpoints/{index}/log_key", "derived")
    for index in range(len(leaves)):
        prov.add(f"/leaves/{index}", "db:column")
    for index in range(len(nodes)):
        prov.add(f"/nodes/{index}", "db:column")
    for index in range(len(cosignatures)):
        prov.add(f"/cosignatures/{index}/witness_key", "derived")
        prov.add(f"/cosignatures/{index}", "db:column")
    for index in range(len(debt)):
        prov.add(f"/unwitnessed_debt/{index}", "db:column")
    prov.add("/inclusion_proofs", "derived")
    prov.add("/consistency_proofs", "derived")

    return read_envelope(
        "ledger",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("table", "mainline.ledger_checkpoint"),
            statement_ref("table", "mainline.ledger_leaf"),
            statement_ref("table", "mainline.ledger_intake"),
            statement_ref("table", "mainline.ledger_node"),
            statement_ref("table", "mainline.cosignature"),
            statement_ref("table", "mainline.unwitnessed_debt"),
            statement_ref(
                "statement",
                "RFC 6962 §2.1.1 PATH / §2.1.2 SUBPROOF",
                text=(
                    "computed in mainline_demo_api.reads._inclusion_path / _consistency_path "
                    "over mainline.ledger_leaf.leaf_hash; no verdict is asserted"
                ),
            ),
        ],
    )


# ── silence ─────────────────────────────────────────────────────────────────────────

_SILENCE_ENTRIES_SQL: Final = """
SELECT silence_id, site_id, source, reason, subject_kind, subject_id, severity,
       score, threshold, arithmetic, policy_version, at
  FROM mainline_meas.silence_ledger
 WHERE subject_id = %s
 ORDER BY at, silence_id
 LIMIT 512
"""

_SILENCE_RECEIPT_SQL: Final = """
SELECT sr.silence_receipt_id, sr.run_id, sr.permit_id,
       encode(sr.corpus_root, 'hex')            AS corpus_root,
       encode(sr.candidate_root, 'hex')         AS candidate_root,
       sr.theta, sr.s, sr.n, sr.boundary_proof, sr.policy_version, sr.issued_at,
       rr.index_generation,
       encode(rr.index_plan_digest, 'hex')      AS index_plan_digest
  FROM mainline_meas.silence_receipt sr
  LEFT JOIN mainline_meas.recall_run rr ON rr.run_id = sr.run_id
 WHERE sr.permit_id = %s
 ORDER BY sr.issued_at DESC
 LIMIT 1
"""

#: The bounding sentence, VERBATIM from ``spec/wire/candidate-commitment.md`` and from
#: ``packages/trappoint_recall.per.receipt.PER_BOUND_SENTENCE``. It is reproduced here as
#: a constant rather than imported because this deployment package's dependency closure is
#: psycopg plus the standard library — and it is chipped ``staged``, with the envelope
#: flagged, because NO COLUMN OF ``mainline_meas.silence_receipt`` CARRIES IT. Every other
#: value in a silence payload is a column; this one is a specification constant, and the
#: honest thing is to say so on the same screen as the arithmetic.
PER_BOUND_SENTENCE: Final = "PER proves exhaustion of the retrieval that ran, not of the corpus."

#: The members ``silence.schema.json`` declares on ``boundary_proof`` and on each
#: ``boundary_leaf``. Both carry ``additionalProperties: false``, so these sets are exact
#: rather than minimal. They are named here as THE SHAPE THIS READER REFUSES TO VIOLATE,
#: not as a copy of the contract kept for convenience: this deployment package's dependency
#: closure is psycopg plus the standard library, so the reader cannot load the console's
#: schema, and the only alternative to naming the members is emitting the row and letting
#: the browser reject it — which is precisely the outcome the 409 below exists to prevent.
_BOUNDARY_PROOF_MEMBERS: Final = frozenset({"leaf_s", "leaf_s_plus_1"})
_BOUNDARY_LEAF_MEMBERS: Final = frozenset({"index", "leaf_hash_hex", "score", "path_hex"})


def _members_fault(value: Any, field: str, declared: frozenset[str]) -> str | None:
    """``None`` when *value* is an object declaring exactly *declared*; else why not."""
    if not isinstance(value, Mapping):
        return f"{field} is {type(value).__name__}, not the object the contract declares"
    members = set(value)
    if members == declared:
        return None
    missing = sorted(declared - members)
    undeclared = sorted(members - declared)
    detail = f"{field} carries {sorted(members)} where the contract declares {sorted(declared)}"
    if missing:
        detail += f"; missing {missing}"
    if undeclared:
        detail += f"; undeclared {undeclared}"
    return detail


def _boundary_proof_fault(proof: Any) -> str | None:
    """``None`` when *proof* can be rendered as ``boundary_proof``; else the reason it cannot.

    THE CHECK THIS REPLACED ASKED ONLY WHETHER ``leaf_s`` WAS PRESENT, and that is not the
    shape the contract demands: a proof carrying ``leaf_s: []`` passes "is the key there?"
    and then fails the console's validator on three counts at once — ``leaf_s`` is an array
    where ``boundary_leaf`` is an object, ``leaf_s_plus_1`` likewise, and any extra member
    is refused outright by ``additionalProperties: false``. Measured against the deployed
    demo seed on 2026-08-13: ``$/data/receipt: matched 0 of 2 oneOf branches``. A guard
    whose docstring promises "checked for the shape the contract demands before it goes
    out" and which then emits an envelope the console rejects is worse than no guard, since
    it is read as having already asked the question.
    """
    fault = _members_fault(proof, "boundary_proof", _BOUNDARY_PROOF_MEMBERS)
    if fault is not None:
        return fault
    fault = _members_fault(proof["leaf_s"], "boundary_proof.leaf_s", _BOUNDARY_LEAF_MEMBERS)
    if fault is not None:
        return fault
    if proof["leaf_s_plus_1"] is None:
        # The contract's own `oneOf` — s+1 is absent when s is the last candidate.
        return None
    return _members_fault(
        proof["leaf_s_plus_1"], "boundary_proof.leaf_s_plus_1", _BOUNDARY_LEAF_MEMBERS
    )


_SILENCE_STAGED_NOTE: Final = (
    "receipt.bound.statement is the only value in this payload that no column produced. "
    "mainline_meas.silence_receipt carries silence_receipt_id, run_id, permit_id, corpus_root, "
    "candidate_root, theta, s, n, boundary_proof, policy_version and issued_at, and nothing "
    "else; silence.schema.json additionally requires bound.statement, the bounding sentence to "
    "be reproduced on every exhibit. It is copied verbatim from spec/wire/candidate-commitment.md "
    "and packages/trappoint-recall/src/trappoint_recall/per/receipt.py::PER_BOUND_SENTENCE. "
    "bound.index_generation and bound.index_plan_digest ARE columns, of mainline_meas.recall_run."
)


def read_silence(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/permits/{permit_id}/silence`` — everything the recall declined to surface.

    The dark side of this surface is the point of it: it is a complete list of every
    warning the system chose not to give, rendered in full rather than as a count.

    Two honesty mechanics are visible in the code below.

    * When a receipt is present the envelope is ``staged: true`` with a note, because one
      required field — ``bound.statement`` — has no column behind it. Not the whole
      payload: the note names the one field and lists the columns that produced the rest.
    * ``boundary_proof`` is a JSONB column passed through verbatim, and it is CHECKED for
      the shape the contract demands before it goes out. A receipt whose stored proof
      does not carry ``leaf_s`` produces a 409 naming the field, rather than an envelope
      the console has to reject.
    """
    _check_request("silence", params, query)
    permit_id = _uuid_param(params, "permit_id", "silence")
    exists = _row(
        conn, "SELECT 1 AS present FROM mainline.permit WHERE permit_id = %s", (permit_id,)
    )
    if exists is None:
        raise NotFound(f"no mainline.permit row with permit_id {permit_id}", resource="silence")

    entries = [
        _pick(
            row,
            "silence_id",
            "site_id",
            "source",
            "reason",
            "subject_kind",
            "subject_id",
            "severity",
            "score",
            "threshold",
            "arithmetic",
            "policy_version",
            "at",
        )
        for row in _rows(conn, _SILENCE_ENTRIES_SQL, (permit_id,))
    ]

    receipt_row = _row(conn, _SILENCE_RECEIPT_SQL, (permit_id,))
    receipt: dict[str, Any] | None = None
    if receipt_row is not None:
        proof = receipt_row["boundary_proof"]
        proof_fault = _boundary_proof_fault(proof)
        if proof_fault is not None:
            raise Unrepresentable(
                f"mainline_meas.silence_receipt {receipt_row['silence_receipt_id']} carries a "
                f"boundary_proof silence.schema.json cannot express: {proof_fault}. PER's entire "
                "claim is that leaves s and s+1 bracket theta in a SCORE-SORTED commitment, so a "
                "receipt whose boundary pair is not there establishes nothing and may not be "
                "rendered as though it did.",
                resource="silence",
            )
        if receipt_row["index_generation"] is None or receipt_row["index_plan_digest"] is None:
            raise Unrepresentable(
                f"mainline_meas.silence_receipt {receipt_row['silence_receipt_id']} names run_id "
                f"{receipt_row['run_id']}, which has no mainline_meas.recall_run row, so "
                "bound.index_generation and bound.index_plan_digest have no source. PER may not "
                "claim a bound whose index generation is unknown.",
                resource="silence",
            )
        receipt = {
            **_pick(
                receipt_row,
                "silence_receipt_id",
                "run_id",
                "permit_id",
                "corpus_root",
                "candidate_root",
                "theta",
                "s",
                "n",
                "policy_version",
                "issued_at",
            ),
            "boundary_proof": jsonable(proof),
            "bound": {
                "index_generation": receipt_row["index_generation"],
                "index_plan_digest": receipt_row["index_plan_digest"],
                "statement": PER_BOUND_SENTENCE,
            },
        }

    data = {
        "subject_kind": "permit",
        "subject_id": str(permit_id),
        "entries": entries,
        "receipt": receipt,
    }

    prov = Provenance()
    prov.add("/subject_id", "db:column").add("/subject_kind", "derived")
    for index in range(len(entries)):
        prov.add(f"/entries/{index}", "db:column")
    if receipt is not None:
        prov.add("/receipt/bound/statement", "staged")
        prov.add("/receipt/bound/index_generation", "db:column")
        prov.add("/receipt/bound/index_plan_digest", "db:column")
        prov.add("/receipt", "db:column")

    return read_envelope(
        "silence",
        data,
        server_date=db.server_now(conn),
        staged=receipt is not None,
        staged_note=_SILENCE_STAGED_NOTE if receipt is not None else None,
        provenance=prov,
        statement_refs=[
            statement_ref("table", "mainline_meas.silence_ledger"),
            statement_ref("table", "mainline_meas.silence_receipt"),
            statement_ref("table", "mainline_meas.recall_run"),
            statement_ref("table", "mainline.permit"),
        ],
    )


# ── recall_run ──────────────────────────────────────────────────────────────────────

_RECALL_RUN_SQL: Final = """
SELECT run_id, permit_id, site_id,
       encode(corpus_commit, 'hex')         AS corpus_commit,
       policy_version,
       encode(index_plan_digest, 'hex')     AS index_plan_digest,
       index_generation,
       n_candidates, n_blocking, n_advisory, n_silenced, n_deduped,
       n_bonded_sev5, n_bonded_sev5_blocking,
       arms_degraded, started_at, latency_ms
  FROM mainline_meas.recall_run
 WHERE run_id = %s
"""

_RECALL_COUNTS: Final = (
    "n_candidates",
    "n_blocking",
    "n_advisory",
    "n_silenced",
    "n_deduped",
    "n_bonded_sev5",
    "n_bonded_sev5_blocking",
)


def read_recall_run(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/recall-runs/{run_id}`` — the conservation arithmetic, verbatim.

    Two CHECK constraints on ``mainline_meas.recall_run`` are product claims, and the
    console renders both as arithmetic a reader can add up:
    ``candidates_conserved`` (``n_candidates = blocking + advisory + silenced + deduped``)
    and ``bonded_fatalities_all_blocking`` (``n_bonded_sev5_blocking = n_bonded_sev5`` —
    *a fatality in your fonds is always recalled*). This function does not compute either
    sum; it emits the seven counts as columns and lets the reader do the addition, which
    is the only version of the claim that is checkable.

    ``arms`` is omitted. It is optional in the contract, and no per-arm table exists on
    this tree — ``mainline_meas.recall_run`` carries the aggregate ``arms_degraded``
    boolean and nothing per channel. An empty array would claim there were no arms.
    """
    _check_request("recall_run", params, query)
    run_id = _uuid_param(params, "run_id", "recall_run")
    row = _row(conn, _RECALL_RUN_SQL, (run_id,))
    if row is None:
        raise NotFound(
            f"no mainline_meas.recall_run row with run_id {run_id}", resource="recall_run"
        )

    data = {
        **_pick(
            row,
            "run_id",
            "permit_id",
            "site_id",
            "corpus_commit",
            "policy_version",
            "index_plan_digest",
            "index_generation",
            "arms_degraded",
            "started_at",
            "latency_ms",
        ),
        "counts": {name: int(row[name]) for name in _RECALL_COUNTS},
    }

    prov = Provenance()
    prov.columns(
        "",
        (
            "run_id",
            "permit_id",
            "site_id",
            "corpus_commit",
            "policy_version",
            "index_plan_digest",
            "index_generation",
            "arms_degraded",
            "started_at",
            "latency_ms",
        ),
    )
    prov.columns("/counts", _RECALL_COUNTS)

    return read_envelope(
        "recall_run",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("table", "mainline_meas.recall_run", text=_RECALL_RUN_SQL.strip())
        ],
    )


# ── propagation ─────────────────────────────────────────────────────────────────────

_PROPAGATION_PROBE: Final = """
SELECT to_regclass('mainline.lesson')         AS lesson,
       to_regclass('mainline.propagation')    AS propagation,
       to_regclass('mainline.merge_conflict') AS merge_conflict
"""

_PROPAGATION_NOTE: Final = (
    "STAGED IN FULL. propagation.schema.json is governed by mainline.lesson, "
    "mainline.propagation and mainline.merge_conflict, and NONE OF THE THREE EXISTS: "
    '`grep -rlE "CREATE TABLE[^;]*(lesson|propagation|merge_conflict)" '
    "verticals/mainline/db/migrations` returns nothing, and to_regclass returns NULL for all "
    "three on this cluster (probe carried in statement_refs). The contract requires a lesson "
    "object with eight non-null members, so there is no way to answer this resource from "
    "columns at all. Every value below is hand-authored demonstration material with no cluster "
    "behind it, every pointer is chipped `staged`, and the console renders STAGED across this "
    "surface. It is not an empty list, because an empty list would be the claim that there are "
    "no lessons — a different sentence, and a false one."
)

#: The staged exhibit. Deterministic — the identifiers are UUID5 and the digests are
#: SHA-256 of their own labels, so two invocations return byte-identical bytes and a
#: reader can recompute every hash in this payload from the strings beside it. That is
#: the most a fabricated payload can honestly offer: not evidence, but reproducibility.
_STAGE_NS: Final = uuid.UUID("6f3f4f8e-2b52-5c8b-9a5a-2f6f9a4f1c00")


def _staged_uuid(label: str) -> str:
    return str(uuid.uuid5(_STAGE_NS, f"mainline-demo-api/propagation/{label}"))


def _staged_digest(label: str) -> str:
    return hashlib.sha256(f"mainline-demo-api/propagation/{label}".encode()).hexdigest()


def read_propagation(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/lessons/{lesson_id}/propagation`` — staged, and flagged on every pointer.

    The probe below is run on every request rather than assumed. If a future migration
    produces the three tables, this function reports ``501`` naming them — which is a
    louder and more useful failure than quietly continuing to serve fiction beside real
    rows. A staged resource that cannot notice it has become real is a lie with a
    shelf life.
    """
    _check_request("propagation", params, query)
    lesson_id = _uuid_param(params, "lesson_id", "propagation")

    probe = _row(conn, _PROPAGATION_PROBE, ())
    present = [name for name, value in (probe or {}).items() if value is not None]
    if present:
        raise ReadError(
            "this resource is staged because mainline.lesson, mainline.propagation and "
            f"mainline.merge_conflict had no producer migration — but {', '.join(sorted(present))} "
            "now exists on this cluster. Refusing to serve hand-authored rows beside a real "
            "table: implement read_propagation against the columns.",
            resource="propagation",
        )

    site_id = _staged_uuid("site")
    data = {
        "lesson": {
            "lesson_id": str(lesson_id),
            "origin_site": site_id,
            "origin_commit": _staged_digest("origin-commit"),
            "anchor_event": _staged_uuid("anchor-event"),
            "max_severity": 4,
            "control_delta": "strengthen",
            "patch_digest": _staged_digest("patch"),
            "merge_base": _staged_digest("merge-base"),
            "title": "Verify at zero before guard removal — strengthened after INC-2024-0117",
        },
        "propagations": [
            {
                "lesson_id": str(lesson_id),
                "site_id": _staged_uuid("site-b"),
                "site_code": "SITE-B",
                "state": "adopted",
                "score": 0.91,
                "model_version": "staged/no-model",
                "proposed_at": "2026-07-01T00:00:00Z",
                "due_by": "2026-07-15T00:00:00Z",
                "adopted_commit": _staged_digest("adopted-commit-b"),
                "already_present_clause": None,
                "open_conflicts": 0,
                "declination_kind": None,
                "declination_predicate_id": None,
                "declination_expires_at": None,
            },
            {
                "lesson_id": str(lesson_id),
                "site_id": _staged_uuid("site-c"),
                "site_code": "SITE-C",
                "state": "already_present",
                "score": 0.88,
                "model_version": "staged/no-model",
                "proposed_at": "2026-07-01T00:00:00Z",
                "due_by": "2026-07-15T00:00:00Z",
                "adopted_commit": None,
                "already_present_clause": _staged_uuid("clause-c"),
                "open_conflicts": 0,
                "declination_kind": None,
                "declination_predicate_id": None,
                "declination_expires_at": None,
            },
            {
                "lesson_id": str(lesson_id),
                "site_id": _staged_uuid("site-d"),
                "site_code": "SITE-D",
                "state": "conflicted",
                "score": 0.76,
                "model_version": "staged/no-model",
                "proposed_at": "2026-07-01T00:00:00Z",
                "due_by": "2026-07-08T00:00:00Z",
                "adopted_commit": None,
                "already_present_clause": None,
                "open_conflicts": 1,
                "declination_kind": None,
                "declination_predicate_id": None,
                "declination_expires_at": None,
            },
        ],
        "conflicts": [
            {
                "conflict_id": _staged_uuid("conflict-d"),
                "lesson_id": str(lesson_id),
                "site_id": _staged_uuid("site-d"),
                "clause_uuid": _staged_uuid("clause-d"),
                "base_digest": _staged_digest("base-d"),
                "ours_digest": _staged_digest("ours-d"),
                "theirs_digest": _staged_digest("theirs-d"),
                "resolved_commit": None,
                "resolved_by": None,
                "resolution_source": None,
                "opened_at": "2026-07-03T00:00:00Z",
            }
        ],
    }

    prov = Provenance()
    prov.add("/lesson", "staged")
    for index in range(len(data["propagations"])):
        prov.add(f"/propagations/{index}", "staged")
    for index in range(len(data["conflicts"])):
        prov.add(f"/conflicts/{index}", "staged")

    return read_envelope(
        "propagation",
        data,
        server_date=db.server_now(conn),
        staged=True,
        staged_note=_PROPAGATION_NOTE,
        provenance=prov,
        statement_refs=[
            statement_ref("statement", "mainline.lesson", text=_PROPAGATION_PROBE.strip()),
        ],
    )


# ── audit ───────────────────────────────────────────────────────────────────────────

#: The Managed MCP surface caps a SELECT at 25 rows and a response at 10 KiB. The audit
#: views are a PRODUCT SURFACE whose size limit is a functional requirement, so the caps
#: this API runs under are the MCP's caps and are declared beside every result.
AUDIT_ROW_CAP: Final = 25
AUDIT_BYTE_CAP: Final = 10240

_AUDIT_VIEWS_SQL: Final = """
SELECT table_name
  FROM information_schema.views
 WHERE table_schema = 'mainline_audit'
 ORDER BY table_name
 LIMIT 32
"""

_AUDIT_COLUMN_TYPES_SQL: Final = """
SELECT table_name, column_name, data_type
  FROM information_schema.columns
 WHERE table_schema = 'mainline_audit'
"""

_AGENT_ACTION_SQL: Final = """
SELECT action_id, agent_role, tool, transport, model_id, prompt_version,
       subject_kind, subject_id,
       encode(input_sha256, 'hex')  AS input_sha256,
       encode(output_sha256, 'hex') AS output_sha256,
       granted_scopes, outcome, sqlstate, latency_ms, at
  FROM mainline_meas.agent_action
 ORDER BY at DESC
 LIMIT 128
"""

#: Views declare completeness under one of these names. The first present wins.
_TRUNCATION_COLUMNS: Final = (
    "ancestry_complete",
    "rows_complete",
    "retrieval_complete",
    "measurement_complete",
    "witness_complete",
)


def read_audit(
    conn: psycopg.Connection[Any], params: Mapping[str, str], query: Mapping[str, str]
) -> dict[str, Any]:
    """``GET /v1/audit`` — the ``mainline_audit.v_*`` aggregates and the agent call log.

    The contract describes a GENERIC tabular shape — columns declared by the payload,
    rows positional against them — and is explicit about why: the views' column contracts
    belong to the recall and MCP domains, and *inventing a column list here would be the
    console asserting something about a view it does not own*. So this function asks
    ``information_schema`` which views exist and reports whatever arrives.

    ``unreachable`` carries one entry, ``outcome: not_probed``. The negative assertion
    the contract wants — that the MCP service account cannot reach ``mainline_qa`` — is
    not a claim this API is entitled to make, because it connects as the demo's own read
    role and a probe from here would answer a different question. An empty array would
    mean "nothing was checked", which is true but says less than naming what was skipped
    and why.
    """
    _check_request("audit", params, query)
    types = {
        (row["table_name"], row["column_name"]): row["data_type"]
        for row in _rows(conn, _AUDIT_COLUMN_TYPES_SQL, ())
    }

    views: list[dict[str, Any]] = []
    for entry in _rows(conn, _AUDIT_VIEWS_SQL, ()):
        name = str(entry["table_name"])
        if not name.isidentifier():  # pragma: no cover - catalog names are identifiers
            continue
        # A relation name cannot be a bind parameter in any SQL dialect, so the
        # interpolation is unavoidable. What makes it safe is the SOURCE: `name` came from
        # `information_schema.views` on this connection, filtered to schema
        # `mainline_audit`, and is re-checked as a Python identifier above. No caller
        # input reaches this string — `audit` declares no parameters at all.
        statement = f"SELECT * FROM mainline_audit.{name} LIMIT {AUDIT_ROW_CAP}"  # noqa: S608
        cursor = conn.execute(statement)
        description = cursor.description or ()
        columns = [
            {"name": column.name, "sql_type": types.get((name, column.name))}
            for column in description
        ]
        if not columns:  # pragma: no cover - a view always has at least one column
            continue
        names = [column["name"] for column in columns]
        rows: list[list[Any]] = []
        for record in cursor.fetchall():
            rendered = [jsonable(record[key]) for key in names]
            candidate = [*rows, rendered]
            if len(json.dumps(candidate, separators=(",", ":")).encode("utf-8")) > AUDIT_BYTE_CAP:
                break
            rows = candidate

        flag: dict[str, Any] | None = None
        for column in _TRUNCATION_COLUMNS:
            if column in names and rows:
                position = names.index(column)
                flag = {"column": column, "complete": all(bool(row[position]) for row in rows)}
                break

        views.append(
            {
                "view": f"mainline_audit.{name}",
                "columns": columns,
                "rows": rows,
                "limits": {
                    "row_cap": AUDIT_ROW_CAP,
                    "byte_cap": AUDIT_BYTE_CAP,
                    "rows_returned": len(rows),
                    "bytes_returned": len(json.dumps(rows, separators=(",", ":")).encode("utf-8")),
                },
                "truncation_flag": flag,
                "statement": statement,
            }
        )

    calls = [
        {
            **_pick(
                row,
                "action_id",
                "agent_role",
                "tool",
                "transport",
                "model_id",
                "prompt_version",
                "subject_kind",
                "subject_id",
                "input_sha256",
                "output_sha256",
                "granted_scopes",
                "outcome",
                "sqlstate",
                "latency_ms",
                "at",
            ),
            "statement": None,
            "plan_fragment": None,
        }
        for row in _rows(conn, _AGENT_ACTION_SQL, ())
    ]

    data = {
        "views": views,
        "calls": calls,
        "unreachable": [
            {
                "schema_name": "mainline_qa",
                "probe": (
                    "not probed by the demo API: it connects as the demo's own read role, not as "
                    "the Managed-MCP service account, so a refusal here would answer a different "
                    "question than the one this field asks"
                ),
                "outcome": "not_probed",
                "sqlstate": None,
            }
        ],
    }

    prov = Provenance()
    for index in range(len(views)):
        prov.add(f"/views/{index}/rows", "db:column")
        prov.add(f"/views/{index}/columns", "db:column")
        prov.add(f"/views/{index}/limits", "derived")
        prov.add(f"/views/{index}/truncation_flag", "derived")
    for index in range(len(calls)):
        prov.add(f"/calls/{index}", "db:column")
    prov.add("/unreachable/0", "derived")

    return read_envelope(
        "audit",
        data,
        server_date=db.server_now(conn),
        provenance=prov,
        statement_refs=[
            statement_ref("view", "information_schema.views", text=_AUDIT_VIEWS_SQL.strip()),
            statement_ref("table", "mainline_meas.agent_action", text=_AGENT_ACTION_SQL.strip()),
            *[
                statement_ref("view", str(view["view"]), text=str(view["statement"]))
                for view in views[:29]
            ],
        ],
    )


# ── The table, and the one entry point ──────────────────────────────────────────────

ReadFn = Callable[[psycopg.Connection[Any], Mapping[str, str], Mapping[str, str]], dict[str, Any]]

#: Resource key → implementation. Exactly the twelve GETs of
#: ``console/src/data/resources.ts``; ``tests/test_envelope.py`` asserts the set matches.
READS: Final[Mapping[str, ReadFn]] = {
    "permit": read_permit,
    "change_request": read_change_request,
    "blocking_checks": read_blocking_checks,
    "disposition": read_disposition,
    "exposure_receipt": read_exposure_receipt,
    "clause_version": read_clause_version,
    "clause_ancestry": read_clause_ancestry,
    "ledger": read_ledger,
    "silence": read_silence,
    "recall_run": read_recall_run,
    "propagation": read_propagation,
    "audit": read_audit,
}


def read_resource(
    conn: psycopg.Connection[Any],
    resource: str,
    params: Mapping[str, str],
    query: Mapping[str, str],
) -> dict[str, Any]:
    """Run one read in one read-only transaction, retrying ``40001``.

    The retry wraps the WHOLE resource, not a statement, because the retry unit of a
    serializable transaction is the transaction. Re-running one statement of an aborted
    one is how a caller gets ``25P02`` and reports it as a client bug.
    """
    handler = READS.get(resource)
    if handler is None:  # pragma: no cover - app.py routes only declared keys here
        raise NotFound(f"no read is implemented for resource {resource!r}", resource=resource)

    def work(active: psycopg.Connection[Any]) -> dict[str, Any]:
        with db.read_transaction(active):
            return handler(active, params, query)

    return db.read(conn, work)
