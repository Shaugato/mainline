# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``GET /v1/demo/subjects`` — the kernel naming its own subjects, out of its own tables.

WHY THIS ROUTE EXISTS
---------------------
Every screen in the console opens on ONE subject and every read route needs that subject's
identifier in its path: ``/v1/permits/{permit_id}``, ``/v1/checks/{check_id}/disposition``,
``/v1/clauses/{clause_uuid}/versions/{commit_id}``. The console had no way to **ask** which
identifiers exist. ``GET /v1/audit`` is aggregate-first — it carries ``site_id`` and a commit
prefix and, across all fourteen views, never a ``permit_id``, a ``check_id`` or a
``clause_uuid``. So a screen could either be handed an identifier by a human, or carry one
in its own source.

It carried one in its own source, and that is the defect this route closes.
``CustodyScreen.tsx`` shipped ``DEFAULT_SITE_CODE = 'BLK-07'`` — a fixture string that leaked
out of ``tests/vectors/checkpoint.json`` and that no seed in this repository has ever
written; ``ClauseDiffScreen.tsx`` shipped a clause UUID and a commit id that the deployed
kernel answers ``404`` for. Measured against the live Function URL on 2026-08-15, both of
those screens are ``HTTP 404`` on arrival and the headline Gate screen renders *"NO SUBJECT
ADDRESSED"*.

**The obvious repair is the same bug with a luckier constant.** Pasting
``dec0de00-0006-…`` into a ``.tsx`` file produces a console that works today, fails the
moment the seed changes, and cannot say which of the two it is doing. The only component
that can name a subject without inventing one is the component that holds the rows.

THE RULE THIS MODULE IS WRITTEN UNDER
-------------------------------------
**Every identifier, label and count in the payload is SELECTed.** Not one is a Python
constant, an f-string, or a default argument. There is no fallback identifier in this file
and there is nothing to fall back to: when a subject is not in the database it is *absent
from the payload* and named in :data:`~subjects` ``absent`` with the reason, and when the
database carries no demo world at all the route answers ``404``.

Three kinds of string in the body are NOT column values, and each is named here rather than
discovered later:

* the JSON **keys** — structure, not data;
* ``absent[].relation`` — the relation name, obtained from the database's own
  ``to_regclass``, so a subject reported absent has been confirmed to have a table to be
  absent from. ``to_regclass`` returning ``NULL`` is a different sentence ("no such table
  on this cluster") and the payload says that one instead;
* ``absent[].reason`` — prose. A row that does not exist cannot describe its own absence.
  This is the one place in the payload where the words are ours, and it is exactly the
  place where there is no row to speak.

HOW A SUBJECT IS CHOSEN WHEN THE SEED CARRIES MORE THAN ONE
-----------------------------------------------------------
Never "the first one the database happened to return". Every statement below carries an
explicit ``ORDER BY`` ending in the primary key, so the choice is a function of the data and
not of the plan, and every statement reports ``count`` — the number of rows that satisfied
the same predicate — beside the row it chose. **This is measured, not hypothetical:** the
seeded ``mainline_demo`` carries TWO ``mainline.blocking_check`` rows, one whose subject is
the permit and one whose subject is the change request, and the live URL answers 200 for
both. An unordered ``LIMIT 1`` over that table is a coin toss between two obligations that
belong to two different screens, and it would have looked correct on whichever day it was
first run.

Subjects hang off one another exactly as the schema does. The site is the root; the permit is
chosen within the site; the open blocking check, the recall run and the exposure receipt are
chosen within the permit; the clause, the event and the change request within the site. A
subject whose anchor is absent is reported absent *for that reason*, named, rather than
searched for globally — a permit-scoped receipt found under some other permit would be a row
this demo does not mean.

WHAT THE PAYLOAD IS SHAPED LIKE, AND WHY IT IS SHAPED TWICE
------------------------------------------------------------
``data`` carries the same facts in two arrangements, and each has a reader:

**The addressing vector** — ``permit_id``, ``cr_id``, ``check_id``, ``receipt_id``,
``clause_uuid``, ``commit_id``, ``run_id``, ``lesson_id``, ``site_code``, ``site_id``.
Every member is named after a path or query parameter ``console/src/data/resources.ts``
already declares, so the index answers exactly one question per member: *what value goes in
that declared slot*. A member is ``null`` when the row is not there. ``null`` is not a
placeholder — it is the absence itself, and the reason for it is one lookup away in
``absent``.

**``subjects``** — one object per subject that EXISTS, carrying ``count`` (how many rows
satisfied the same predicate the chosen row was chosen from) and the columns the addressing
vector has no slot for: the permit's ``state`` and ``gate_epoch``, the clause's ``head_gen``,
the event's ``kind``. A subject that does not exist has **no key here at all**. That is the
strict form of the rule: nothing in ``subjects`` is ever a value standing in for a row.

**``absent``** — one entry per subject that was looked for and not found, naming the relation
(as the database's own ``to_regclass`` resolved it) and the reason.

THE ENVELOPE
------------
Built by :func:`envelope.read_envelope`, exactly like the console's twelve reads, because
``resources.ts`` declares ``demo_subjects`` and :data:`envelope.SCHEMA_IDS` therefore names
its contract. It is dispatched through :data:`reads.READS` for the same reason — one
transaction, one snapshot, one ``40001`` retry, chosen by the same code that chooses them
for every other read rather than by a second copy of that decision living here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import psycopg

from . import db, reads
from .envelope import SCHEMA_IDS, Provenance, jsonable, read_envelope, statement_ref

__all__ = [
    "ADDRESSED_SLOTS",
    "SUBJECTS_RESOURCE",
    "SUBJECTS_SCHEMA_ID",
    "read_subjects",
]

#: The resource key. Routed by ``app._routes()``, declared by ``console/src/data/
#: resources.ts``, parameter-checked through ``reads._DECLARED_PARAMS`` and dispatched
#: through ``reads.READS``.
SUBJECTS_RESOURCE: Final = "demo_subjects"

#: The ``$id`` of the contract governing ``data``. Read off :data:`envelope.SCHEMA_IDS`
#: rather than rebuilt here: that table is the transcription of the console's own
#: ``declare()`` calls and ``tests/test_envelope.py`` compares the two key for key, so a
#: second construction of this string would be a second place for it to be wrong.
SUBJECTS_SCHEMA_ID: Final = SCHEMA_IDS[SUBJECTS_RESOURCE]

#: The addressing vector, in the order the payload carries it. Every name is a path or
#: query parameter ``resources.ts`` declares, and this tuple is the list of questions this
#: resource answers. It is NOT a list of values — every one of them is filled from a column
#: or left ``null``.
ADDRESSED_SLOTS: Final[tuple[str, ...]] = (
    "site_id",
    "site_code",
    "permit_id",
    "cr_id",
    "check_id",
    "receipt_id",
    "clause_uuid",
    "commit_id",
    "run_id",
    "lesson_id",
)


# ── The statements ──────────────────────────────────────────────────────────────────
#
# `count(*) OVER ()` is evaluated after WHERE and before ORDER BY/LIMIT, so each statement
# returns the CHOSEN row and the size of the set it was chosen from, in one pass and one
# snapshot. Computing the count separately would be two questions asked at two moments.

_SITE_SQL: Final = """
SELECT count(*) OVER ()  AS count,
       s.site_id,
       s.site_code
  FROM mainline.site AS s
 ORDER BY s.site_code, s.site_id
 LIMIT 1
"""

_PERMIT_SQL: Final = """
SELECT count(*) OVER ()  AS count,
       p.permit_id,
       p.ref_name,
       p.external_ref,
       p.state::text     AS state,
       p.gate_epoch,
       p.open_blocking
  FROM mainline.permit AS p
 WHERE p.site_id = %s
 ORDER BY p.opened_at, p.permit_id
 LIMIT 1
"""

#: The OPEN obligation, and ``open`` is not a column. It is the absence of a live row in
#: ``mainline.disposition``, computed by the LATERAL exactly as ``reads.read_blocking_checks``
#: computes it — one derivation, written twice, would be one derivation that can disagree
#: with itself, so this is the same shape deliberately and the tests compare the two answers.
_CHECK_SQL: Final = """
SELECT count(*) OVER ()        AS count,
       bc.check_id,
       bc.subject_kind::text   AS subject_kind,
       bc.permit_id,
       bc.cr_id,
       bc.clause_uuid,
       encode(bc.commit_id, 'hex') AS commit_id,
       bc.precursor_event_id
  FROM mainline.blocking_check AS bc
  LEFT JOIN LATERAL (
         SELECT d.disposition_id
           FROM mainline.disposition AS d
          WHERE d.check_id = bc.check_id AND d.retracted_by IS NULL
          ORDER BY d.signed_at DESC
          LIMIT 1
       ) AS live ON true
 WHERE bc.permit_id = %s
   AND live.disposition_id IS NULL
 ORDER BY bc.materialised_at, bc.check_id
 LIMIT 1
"""

#: ``head_gen`` and ``head_label`` come from the LEFT JOIN and are NULL when no
#: ``mainline.clause_version`` row exists at the clause's own ``head_commit``. That is the
#: exact condition under which ``GET /v1/clauses/{uuid}/versions/{commit}`` answers 404, so
#: the index reports it as a value the console can read rather than leaving a caller to
#: discover it by being refused.
_CLAUSE_SQL: Final = """
SELECT count(*) OVER ()               AS count,
       c.clause_uuid,
       c.activity_root,
       encode(c.head_commit, 'hex')   AS head_commit,
       cv.gen                         AS head_gen,
       cv.printed_label               AS head_label
  FROM mainline.clause AS c
  LEFT JOIN mainline.clause_version AS cv
         ON cv.clause_uuid = c.clause_uuid AND cv.commit_id = c.head_commit
 WHERE c.site_id = %s
 ORDER BY c.activity_root, c.clause_uuid
 LIMIT 1
"""

_EVENT_SQL: Final = """
SELECT count(*) OVER ()  AS count,
       e.event_id,
       e.external_ref,
       e.kind::text      AS kind,
       e.severity_gate
  FROM mainline.event AS e
 WHERE e.site_id = %s
 ORDER BY e.occurred_at, e.event_id
 LIMIT 1
"""

_CHANGE_REQUEST_SQL: Final = """
SELECT count(*) OVER ()  AS count,
       cr.cr_id,
       cr.ref_name,
       cr.external_ref,
       cr.state::text    AS state
  FROM mainline.change_request AS cr
 WHERE cr.site_id = %s
 ORDER BY cr.opened_at, cr.cr_id
 LIMIT 1
"""

_RECALL_RUN_SQL: Final = """
SELECT count(*) OVER ()  AS count,
       r.run_id,
       r.policy_version,
       r.index_generation
  FROM mainline_meas.recall_run AS r
 WHERE r.permit_id = %s
 ORDER BY r.started_at, r.run_id
 LIMIT 1
"""

_RECEIPT_SQL: Final = """
SELECT count(*) OVER ()      AS count,
       x.receipt_id,
       x.subject_kind::text  AS subject_kind,
       x.expires_at
  FROM mainline.exposure_receipt AS x
 WHERE x.permit_id = %s
 ORDER BY x.issued_at, x.receipt_id
 LIMIT 1
"""

#: Asked once, for every relation this route indexes, so that "absent" can distinguish
#: *the table is there and holds no such row* from *this cluster has no such table*.
_RELATIONS_SQL: Final = """
SELECT to_regclass('mainline.site')             AS site,
       to_regclass('mainline.permit')           AS permit,
       to_regclass('mainline.blocking_check')   AS blocking_check,
       to_regclass('mainline.clause')           AS clause,
       to_regclass('mainline.event')            AS event,
       to_regclass('mainline.change_request')   AS change_request,
       to_regclass('mainline_meas.recall_run')  AS recall_run,
       to_regclass('mainline.exposure_receipt') AS exposure_receipt
"""


# ── Absence, which is a claim and therefore has to be argued ────────────────────────


def _relation_phrase(relation: Any, fallback: str) -> str:
    """Name the relation a subject is absent from, using the database's own answer.

    ``to_regclass`` returns the resolved relation OID rendered as its qualified name, or
    ``NULL`` when nothing of that name exists. Both are true sentences and they are
    different ones, so the caller gets whichever the cluster gave. *fallback* is the name
    that was LOOKED FOR — it is not a claim that anything exists.
    """
    return str(relation) if relation is not None else f"{fallback} (no such relation)"


def _absent(subject: str, relation: Any, looked_for: str, reason: str) -> dict[str, Any]:
    return {
        "subject": subject,
        "relation": _relation_phrase(relation, looked_for),
        "reason": reason,
    }


# ── The read ────────────────────────────────────────────────────────────────────────


def _row(conn: psycopg.Connection[Any], sql: str, args: Sequence[Any]) -> dict[str, Any] | None:
    result = conn.execute(sql, args).fetchone()
    return dict(result) if result is not None else None


def _subject(row: Mapping[str, Any], *names: str) -> dict[str, Any]:
    """Render a chosen row as a payload object: ``count`` first, then the named columns."""
    out: dict[str, Any] = {"count": int(row["count"])}
    out.update({name: jsonable(row[name]) for name in names})
    return out


def _statement_refs() -> list[dict[str, Any]]:
    return [
        statement_ref("table", "mainline.site", text=_SITE_SQL.strip()),
        statement_ref("table", "mainline.permit", text=_PERMIT_SQL.strip()),
        statement_ref("table", "mainline.blocking_check", text=_CHECK_SQL.strip()),
        statement_ref("table", "mainline.clause", text=_CLAUSE_SQL.strip()),
        statement_ref("table", "mainline.event", text=_EVENT_SQL.strip()),
        statement_ref("table", "mainline.change_request", text=_CHANGE_REQUEST_SQL.strip()),
        statement_ref("table", "mainline_meas.recall_run", text=_RECALL_RUN_SQL.strip()),
        statement_ref("table", "mainline.exposure_receipt", text=_RECEIPT_SQL.strip()),
        statement_ref("statement", "pg_catalog.to_regclass", text=_RELATIONS_SQL.strip()),
    ]


def _read(conn: psycopg.Connection[Any]) -> dict[str, Any]:  # noqa: PLR0912 - eight subjects,
    # each with its own predicate, its own order and its own named absence. Splitting them
    # into helpers would put the SQL, the choice and the reason for absence in three places
    # per subject, and the whole value of this module is that those three are read together.
    """Build the payload from one snapshot, or raise :class:`reads.NotFound`."""
    relations = _row(conn, _RELATIONS_SQL, ()) or {}

    subjects: dict[str, Any] = {}
    absent: list[dict[str, Any]] = []

    site = _row(conn, _SITE_SQL, ())
    if site is None:
        raise reads.NotFound(
            "no mainline.site row: this database carries no demo world, so there is no "
            "subject to index. GET /v1/demo/subjects names the rows the demo seed created "
            "(mainline.site, mainline.permit, mainline.blocking_check, mainline.clause, "
            "mainline.event, mainline.change_request, mainline_meas.recall_run, "
            "mainline.exposure_receipt) and it looked for a site first because every other "
            "subject is chosen within one. Apply verticals/mainline/db/seeds/demo/"
            "{demo_world,demo_permit}.sql; nothing here will invent a subject to answer 200.",
            resource=SUBJECTS_RESOURCE,
        )
    subjects["site"] = _subject(site, "site_id", "site_code")
    site_id = site["site_id"]

    permit = _row(conn, _PERMIT_SQL, (site_id,))
    if permit is None:
        absent.append(
            _absent(
                "permit",
                relations.get("permit"),
                "mainline.permit",
                f"no row with site_id {site['site_id']} — the site this index chose carries "
                "no permit, so there is no gated subject for the Gate or Silence screens to "
                "open on.",
            )
        )
    else:
        subjects["permit"] = _subject(
            permit, "permit_id", "ref_name", "external_ref", "state", "gate_epoch", "open_blocking"
        )

    permit_id = permit["permit_id"] if permit is not None else None
    anchor = (
        f"no row with permit_id {permit['permit_id']}"
        if permit is not None
        else "not looked for: its anchor mainline.permit carries no row for the chosen site"
    )

    check = _row(conn, _CHECK_SQL, (permit_id,)) if permit_id is not None else None
    if check is None:
        absent.append(
            _absent(
                "blocking_check",
                relations.get("blocking_check"),
                "mainline.blocking_check",
                f"{anchor} that has no live mainline.disposition. An obligation that has "
                "been signed is not an OPEN obligation, and this index names the open one "
                "because that is the one the gate refuses on.",
            )
        )
    else:
        subjects["blocking_check"] = _subject(
            check,
            "check_id",
            "subject_kind",
            "permit_id",
            "cr_id",
            "clause_uuid",
            "commit_id",
            "precursor_event_id",
        )

    clause = _row(conn, _CLAUSE_SQL, (site_id,))
    if clause is None:
        absent.append(
            _absent(
                "clause",
                relations.get("clause"),
                "mainline.clause",
                f"no row with site_id {site['site_id']} — the Diff screen addresses a clause "
                "at a commit and this site carries no clause.",
            )
        )
    else:
        subjects["clause"] = _subject(
            clause, "clause_uuid", "activity_root", "head_commit", "head_gen", "head_label"
        )

    event = _row(conn, _EVENT_SQL, (site_id,))
    if event is None:
        absent.append(
            _absent(
                "event",
                relations.get("event"),
                "mainline.event",
                f"no row with site_id {site['site_id']} — GET /v1/lessons/{{lesson_id}}/"
                "propagation takes an event identifier and this site has recorded no event.",
            )
        )
    else:
        subjects["event"] = _subject(event, "event_id", "external_ref", "kind", "severity_gate")

    change_request = _row(conn, _CHANGE_REQUEST_SQL, (site_id,))
    if change_request is None:
        absent.append(
            _absent(
                "change_request",
                relations.get("change_request"),
                "mainline.change_request",
                f"no row with site_id {site['site_id']} — the second gated subject kind is "
                "not present in this database.",
            )
        )
    else:
        subjects["change_request"] = _subject(
            change_request, "cr_id", "ref_name", "external_ref", "state"
        )

    recall_run = _row(conn, _RECALL_RUN_SQL, (permit_id,)) if permit_id is not None else None
    if recall_run is None:
        absent.append(
            _absent(
                "recall_run",
                relations.get("recall_run"),
                "mainline_meas.recall_run",
                f"{anchor}. mainline_meas.recall_run.permit_id is NOT NULL, so a recall run "
                "cannot exist before the permit it was run for.",
            )
        )
    else:
        subjects["recall_run"] = _subject(
            recall_run, "run_id", "policy_version", "index_generation"
        )

    receipt = _row(conn, _RECEIPT_SQL, (permit_id,)) if permit_id is not None else None
    if receipt is None:
        absent.append(
            _absent(
                "exposure_receipt",
                relations.get("exposure_receipt"),
                "mainline.exposure_receipt",
                f"{anchor}. A receipt whose subject is a change request has a NULL permit_id "
                "and is deliberately not offered here: exposure.schema.json requires "
                "permit_id, and reads.read_exposure_receipt answers 409 for such a row.",
            )
        )
    else:
        subjects["exposure_receipt"] = _subject(receipt, "receipt_id", "subject_kind", "expires_at")

    # THE ADDRESSING VECTOR. Every value below is lifted out of a row this function already
    # chose — there is no second query and no second choice, so the vector and `subjects`
    # cannot disagree about which permit the demo means. `.get(...)` against a subject that
    # is absent yields None, and the reason for that None is in `absent`, by name.
    def slot(subject: str, member: str) -> Any:
        chosen = subjects.get(subject)
        return chosen.get(member) if chosen is not None else None

    addressed: dict[str, Any] = {
        "site_id": slot("site", "site_id"),
        "site_code": slot("site", "site_code"),
        "permit_id": slot("permit", "permit_id"),
        "cr_id": slot("change_request", "cr_id"),
        "check_id": slot("blocking_check", "check_id"),
        "receipt_id": slot("exposure_receipt", "receipt_id"),
        "clause_uuid": slot("clause", "clause_uuid"),
        "commit_id": slot("clause", "head_commit"),
        "run_id": slot("recall_run", "run_id"),
        "lesson_id": slot("event", "event_id"),
    }
    return {**addressed, "subjects": subjects, "absent": absent}


def _provenance(data: Mapping[str, Any]) -> Provenance:
    """Chip every pointer in the payload.

    The addressing vector is chipped ``db:column`` where it carries a value and left
    unchipped where it is ``null`` — the contract permits an unclaimed field and forbids a
    claim about a field that is not there, and ``db:column`` beside a ``null`` would be the
    claim that a column held nothing when in fact no row was found.

    ``count`` is ``derived``: it is ``count(*) OVER ()``, an aggregate this statement asked
    for, not a column anybody wrote. Every other member of a subject IS a column and says
    so. The ``absent`` entries are ``derived`` too — an absence is a conclusion drawn from
    a query that returned nothing, and there is no column that holds it.
    """
    prov = Provenance()
    for name in ADDRESSED_SLOTS:
        if data.get(name) is not None:
            prov.add(f"/{name}", "db:column")
    for name, subject in data["subjects"].items():
        prov.add(f"/subjects/{name}/count", "derived")
        prov.columns(f"/subjects/{name}", (key for key in subject if key != "count"))
    for index in range(len(data["absent"])):
        prov.add(f"/absent/{index}", "derived")
    return prov


def read_subjects(
    conn: psycopg.Connection[Any],
    params: Mapping[str, str],
    query: Mapping[str, str],
) -> dict[str, Any]:
    """``GET /v1/demo/subjects`` — one envelope naming every subject this database carries.

    A ``reads.ReadFn`` like the other twelve, and dispatched by :func:`reads.read_resource`,
    so the transaction, the snapshot and the ``40001`` retry are the ones every read gets
    rather than a second copy of that decision living here. It matters more here than
    elsewhere: nine statements run at nine moments could report a ``count`` that disagreed
    with the row beside it, which is an index that watched the world change while
    describing it.

    ``staged`` is false. Every value came out of a column, and the one resource this index
    points at that IS staged — ``propagation`` — says so in its own envelope, where the
    claim belongs.

    Raises :class:`reads.NotFound` when ``mainline.site`` is empty. That is the whole 404
    condition and it is the only one: a database with a site and nothing else answers 200
    with seven named absences, because "the demo world exists and is incomplete" is a
    different and more useful sentence than "not found".
    """
    reads.check_request(SUBJECTS_RESOURCE, params, query)
    data = _read(conn)
    return read_envelope(
        SUBJECTS_RESOURCE,
        data,
        server_date=db.server_now(conn),
        provenance=_provenance(data),
        statement_refs=_statement_refs(),
    )
