# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The demo history's identifiers — one definition, shared by the seed and the API.

The demo drives a REAL permit through a REAL gate. Both halves therefore have to agree on
which permit, and there are only two ways for two programs to agree on a UUID: copy it, or
derive it. Copying is what puts a stale identifier in one of them and a mystery 404 in the
demo the week of a deadline, so these are **derived**:

    namespace = uuid5(NAMESPACE_URL, "https://mainline.trappoint.org/demo/2026-08")
    permit_id = uuid5(namespace, "permit")

Anyone — the seeder, the API, a judge with a Python prompt — recomputes them from a string
that is in the repository. The literal values are written out beside the derivation as
:data:`EXPECTED`, and :func:`_selfcheck` runs at import: if the two ever disagree the
module refuses to load rather than serve a request against a permit nobody seeded.

Every identifier is also overridable from the environment, because the API and the seed
must be able to point at a *different* history without a code change — a second cluster, a
judge's private copy, or the local node a developer just migrated. The override is read at
call time, never cached at import, so a test can set one without reloading the module.

WHAT IS FIXED HERE AND WHAT IS READ FROM THE DATABASE
-----------------------------------------------------
Fixed: the identifiers the SEED chooses — the site, the permit, the clause, the precursor
event, the signer subjects. Read from the database at request time: the obligation, the
exposure receipt, the recall run, the counters, the state. That split is not arbitrary.
A derived identifier the API pinned would be the API asserting a fact about rows it did
not write; reading it back means the demo describes the database it actually found, and
says so when it finds nothing (:class:`ScenarioNotSeeded`).

AND ONE SUBJECT SITS ON THE OTHER SIDE OF THAT LINE ON PURPOSE
---------------------------------------------------------------
The CHANGE REQUEST — the second gated subject, the one
``POST /v1/demo/cr-gate-run`` drives — has no derivation at all.
``db/seeds/demo/demo_world.sql`` §10 fixes its ``cr_id`` as a literal in the
``dec0de00-…`` family and states, in the file, that the literal *"equals nothing in the
codebase; grep for any of them under apps/demo-api/src/ finds nothing"*. Restating it here
would make this module a second definition of a value the seed owns, which is the defect
``tests/conftest.py`` was rewritten to delete. So it is READ — :func:`resolve_cr_id` — and
``MAINLINE_DEMO_CR_ID`` overrides that read rather than seeding a fallback nothing seeds.
The demo Lambda sets no such variable, and needs none.

ROW SHAPE IS NOT A GLOBAL ANY MODULE MAY ASSUME
-----------------------------------------------
:func:`positional` lives in this module because it is the one :mod:`gate_run` and
:mod:`transitions` already import, and three copies of a two-line helper are three places
for it to drift.

It exists because :func:`mainline_demo_api.db.connection` opens every production connection
with ``psycopg.rows.dict_row`` — the convention :mod:`reads` and :mod:`health` are written
to — while the statements in these three modules are written to be read by POSITION. The
mismatch does not raise where it happens. Unpacking a ``dict`` yields its KEYS, so
``check_id`` became the literal string ``"check_id"`` and was bound as a query parameter one
statement later, which is the ``22P02`` recorded in ``evidence/deploy/rowfactory-defect.json``.

Flipping these modules to name-keyed access would not have been enough, and that is measured
rather than assumed: ``_FINGERPRINT_SQL`` returns ten columns CockroachDB all names
``count``, and both merge-record statements return two columns it names ``encode``, so a
``dict`` row COLLAPSES them — ten values arriving as one key, silently, with no error to
notice. Asking the cursor for tuples keeps every column and makes these modules independent
of the connection's factory in BOTH directions, which is what
``tests/test_row_factory_contract.py`` asserts.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import psycopg
from psycopg.rows import TupleRow, tuple_row

__all__ = [
    "DEMO_NAMESPACE",
    "DEMO_NAMESPACE_URL",
    "ENV_PREFIX",
    "EXPECTED",
    "ResolvedChangeRequest",
    "ResolvedScenario",
    "Scenario",
    "ScenarioNotSeeded",
    "demo_uuid",
    "from_env",
    "positional",
    "resolve",
    "resolve_change_request",
    "resolve_cr_id",
]


def positional(
    conn: psycopg.Connection[Any],
    sql: str,
    params: Sequence[Any] | None = None,
) -> psycopg.Cursor[TupleRow]:
    """Run *sql* and return a cursor whose rows are TUPLES, whatever factory *conn* has.

    The row factory is set on the CURSOR, which is psycopg's own mechanism for exactly
    this: the statement declares the shape it is written against instead of inheriting one
    from whoever opened the connection. Nothing about *conn* is mutated, so a caller that
    opened it with ``dict_row`` for :mod:`reads` still has ``dict_row`` afterwards.

    See the module docstring for why position rather than name is the right convention for
    these statements — several of them return columns CockroachDB gives duplicate names,
    which a ``dict`` row silently collapses.
    """
    return conn.cursor(row_factory=tuple_row).execute(sql, params)


#: The string every demo identifier is derived from. Changing it re-mints the whole
#: history and is therefore a deliberate act with a diff, which is the point.
DEMO_NAMESPACE_URL: Final = "https://mainline.trappoint.org/demo/2026-08"

#: uuid5(NAMESPACE_URL, DEMO_NAMESPACE_URL) — c82d4e5f-961f-590a-95bb-7ea3db2858db.
DEMO_NAMESPACE: Final = uuid.uuid5(uuid.NAMESPACE_URL, DEMO_NAMESPACE_URL)

#: Environment variables are `MAINLINE_DEMO_<NAME>`, upper-cased.
ENV_PREFIX: Final = "MAINLINE_DEMO_"


def demo_uuid(name: str) -> uuid.UUID:
    """Return the demo identifier for *name*, derived rather than remembered."""
    return uuid.uuid5(DEMO_NAMESPACE, name)


#: The derivation's answers, written out so that a reader does not have to run Python to
#: know what the seed is expected to contain, and so that :func:`_selfcheck` can prove the
#: two forms agree. These are the values `w2-cloud-database` seeds.
EXPECTED: Final[Mapping[str, str]] = {
    "site": "c333eb17-a6c8-5729-8e73-8d49a7ab3971",
    "permit": "077a6fdd-2167-559c-b2ff-8e3c8352504d",
    "clause": "512b662e-1208-51a4-be59-ecb4f3ca085f",
    "event": "bf94c82a-1aac-5cb0-87c9-b371d958f158",
    "blocking-check": "ccfb9428-d644-5836-a4ae-1ff89bcc7aa5",
    "exposure-receipt": "01db9651-393f-5089-9aef-f38d2808f4c7",
    "recall-run": "24b9c644-dfb3-53dd-9bec-7176437b947c",
    "commit": "4fbbd371-06cf-5e02-b03a-49ce2ba5c4aa",
    # The commit the CHANGE REQUEST's merge attempt names. Derived like every other name
    # here, and deliberately NOT the permit's: two subjects proposing the same commit id
    # would be a coincidence a reader could not check, and `mainline.cr_commit_sized`
    # wants 32 bytes either way. It is never written — the merge it belongs to is refused
    # and the whole transaction is rolled back — but a value that is never written is
    # exactly the kind that drifts unnoticed, so it is derived and self-checked with the
    # rest rather than typed once into `POST /v1/demo/cr-gate-run`.
    "cr-commit": "2901ead3-5fec-575c-9869-46849f9202c2",
}


def _selfcheck() -> None:
    wrong = {n: (v, str(demo_uuid(n))) for n, v in EXPECTED.items() if str(demo_uuid(n)) != v}
    if wrong:
        raise RuntimeError(
            "mainline_demo_api.scenario is inconsistent with itself: the uuid5 derivation "
            f"no longer produces the committed identifiers {wrong!r}. Either "
            "DEMO_NAMESPACE_URL changed without EXPECTED being regenerated, or EXPECTED "
            "was edited by hand. Both would silently point the demo at a permit nobody "
            "seeded."
        )


_selfcheck()


#: 32 bytes, because ``CONSTRAINT cr_commit_sized`` on ``mainline.change_request`` says 32.
#: One uuid5 twice, exactly as the permit's :attr:`Scenario.merged_commit` is built.
_CR_MERGED_COMMIT: Final = demo_uuid("cr-commit").bytes + demo_uuid("cr-commit").bytes


class ScenarioNotSeeded(RuntimeError):
    """The demo history is not in this database.

    Deliberately distinct from a refusal and from a transport failure. "The gate did not
    refuse" and "there was nothing to ask" are different findings and only one of them is
    about the product — the same distinction ``scripts/proof/gate_refusal.py`` draws with
    its exit codes.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Scenario:
    """The identifiers the seed chooses. Nothing here is read from a database."""

    permit_id: uuid.UUID
    site_id: uuid.UUID
    clause_uuid: uuid.UUID
    event_id: uuid.UUID
    signer_sub: str
    countersigner_sub: str
    #: The commit the merge attempt records. 32 bytes; the demo derives it from the
    #: namespace so a replayed run and a live run name the same commit.
    merged_commit: bytes
    #: THE SECOND GATED SUBJECT, AND THE ONE IDENTIFIER HERE THAT IS NOT DERIVED AND NOT
    #: STATED. ``None`` means *ask the database*, and that is the default on purpose.
    #:
    #: Every other identifier above is ``uuid5`` of a string in this repository, so the
    #: seeder and the API can agree without copying. The change request cannot join that
    #: scheme: ``db/seeds/demo/demo_world.sql`` §10 fixes its ``cr_id`` as a literal in the
    #: ``dec0de00-…`` family and says in the file why — *"chosen to equal nothing in the
    #: codebase; grep for any of them under apps/demo-api/src/ finds nothing"*. Writing
    #: that literal here would make this module the second definition of a value the seed
    #: owns, which is the exact defect ``tests/conftest.py`` was rewritten to delete and
    #: the one that put a ``23503`` in front of a judge.
    #:
    #: So it is READ, by :func:`resolve_cr_id`, the way :mod:`mainline_demo_api.subjects`
    #: reads every identifier it publishes. ``MAINLINE_DEMO_CR_ID`` overrides that for a
    #: deployment carrying more than one change request; the demo Lambda sets no such
    #: variable and needs none, which is the other half of the reason the default is a
    #: read and not a constant.
    cr_id: uuid.UUID | None = None
    #: The commit the CHANGE REQUEST's merge attempt names. 32 bytes, derived — see
    #: ``EXPECTED['cr-commit']``. Never written: the merge it belongs to is refused.
    cr_merged_commit: bytes = _CR_MERGED_COMMIT

    def as_json(self) -> dict[str, Any]:
        return {
            "permit_id": str(self.permit_id),
            "site_id": str(self.site_id),
            "clause_uuid": str(self.clause_uuid),
            "event_id": str(self.event_id),
            "signer_sub": self.signer_sub,
            "countersigner_sub": self.countersigner_sub,
            "merged_commit": self.merged_commit.hex(),
            # `null` is a fact and not an omission: it says this deployment did not name a
            # change request and the run will ask the database which one it holds.
            "cr_id": None if self.cr_id is None else str(self.cr_id),
            "cr_merged_commit": self.cr_merged_commit.hex(),
        }


def _env_uuid(env: Mapping[str, str], name: str, fallback: uuid.UUID) -> uuid.UUID:
    raw = env.get(ENV_PREFIX + name.replace("-", "_").upper(), "").strip()
    if not raw:
        return fallback
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ScenarioNotSeeded(
            f"{ENV_PREFIX}{name.replace('-', '_').upper()}={raw!r} is not a UUID"
        ) from exc


def _env_uuid_or_none(env: Mapping[str, str], name: str) -> uuid.UUID | None:
    """Read an overridable identifier that has NO derivation to fall back to.

    Distinct from :func:`_env_uuid`, and the difference is the whole point: an absent
    ``MAINLINE_DEMO_PERMIT_ID`` falls back to a ``uuid5`` both halves of the demo can
    recompute, while an absent ``MAINLINE_DEMO_CR_ID`` has nothing to fall back TO — the
    seed fixes that identifier as a literal. ``None`` is therefore the honest answer and
    it means "ask the database", not "use the default".
    """
    raw = env.get(ENV_PREFIX + name.replace("-", "_").upper(), "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ScenarioNotSeeded(
            f"{ENV_PREFIX}{name.replace('-', '_').upper()}={raw!r} is not a UUID"
        ) from exc


def from_env(env: Mapping[str, str] | None = None) -> Scenario:
    """Build the scenario, letting the environment override any identifier.

    Read at call time rather than at import so that a test — or a Lambda whose
    configuration changed between invocations — sees the current value.
    """
    src = os.environ if env is None else env
    return Scenario(
        permit_id=_env_uuid(src, "permit_id", demo_uuid("permit")),
        site_id=_env_uuid(src, "site_id", demo_uuid("site")),
        clause_uuid=_env_uuid(src, "clause_uuid", demo_uuid("clause")),
        event_id=_env_uuid(src, "event_id", demo_uuid("event")),
        signer_sub=src.get(ENV_PREFIX + "SIGNER_SUB", "").strip() or "demo.signer",
        countersigner_sub=(
            src.get(ENV_PREFIX + "COUNTERSIGNER_SUB", "").strip() or "demo.countersigner"
        ),
        merged_commit=demo_uuid("commit").bytes + demo_uuid("commit").bytes,
        cr_id=_env_uuid_or_none(src, "cr_id"),
        cr_merged_commit=_CR_MERGED_COMMIT,
    )


@dataclass(frozen=True, slots=True)
class ResolvedScenario:
    """The scenario plus what the database says about it, read in one round trip.

    ``open_blocking`` is the PROJECTED counter — the column a trigger wrote — and
    ``open_derived`` is the same quantity re-derived from ``blocking_check`` LEFT JOIN
    ``disposition`` by the anti-join the gate itself uses. They are carried separately and
    never reconciled here, because the whole product is the observation that a gate which
    trusts the first is a gate one UPDATE disarms.
    """

    scenario: Scenario
    external_ref: str
    state: str
    head_seq: int
    gate_epoch: int
    open_blocking: int
    open_derived: int
    #: The single open obligation the demo turns on, or ``None`` when none is open.
    check_id: uuid.UUID | None
    #: The live exposure receipt covering that obligation, or ``None``. A disposition
    #: cannot be signed without one — the composite foreign key says so.
    receipt_id: uuid.UUID | None
    site_code: str

    @property
    def permit_id(self) -> uuid.UUID:
        return self.scenario.permit_id

    def as_json(self) -> dict[str, Any]:
        return {
            "subject_kind": "permit",
            "subject_id": str(self.scenario.permit_id),
            "external_ref": self.external_ref,
            "state": self.state,
            "head_seq": self.head_seq,
            "gate_epoch": self.gate_epoch,
            "open_blocking": self.open_blocking,
            "open_blocking_derived": self.open_derived,
            "blocking_check_id": str(self.check_id) if self.check_id else None,
            "exposure_receipt_id": str(self.receipt_id) if self.receipt_id else None,
            "site_code": self.site_code,
        }


#: One statement, so the counters, the state and the obligation are read at ONE moment.
#: Two statements would let a concurrent materialisation land between them and produce a
#: description of a permit that never existed.
_RESOLVE_SQL: Final = """
SELECT p.external_ref,
       p.state::STRING,
       p.head_seq,
       p.gate_epoch,
       p.open_blocking,
       (SELECT count(*)
          FROM mainline.blocking_check bc
         WHERE bc.permit_id = p.permit_id
           AND NOT EXISTS (SELECT 1 FROM mainline.disposition d
                            WHERE d.check_id = bc.check_id
                              AND d.retracted_by IS NULL
                              AND (d.expires_at IS NULL OR d.expires_at > now()))) AS open_derived,
       (SELECT bc.check_id
          FROM mainline.blocking_check bc
         WHERE bc.permit_id = p.permit_id
           AND NOT EXISTS (SELECT 1 FROM mainline.disposition d
                            WHERE d.check_id = bc.check_id
                              AND d.retracted_by IS NULL
                              AND (d.expires_at IS NULL OR d.expires_at > now()))
         ORDER BY bc.check_id
         LIMIT 1) AS check_id,
       st.site_code
  FROM mainline.permit p
  JOIN mainline.site st ON st.site_id = p.site_id
 WHERE p.permit_id = %s
"""

#: The live exposure receipt that actually SHOWED the obligation. Chosen by the exposure
#: line, not by recency alone: a disposition's composite foreign key lands on
#: (check_id, receipt_id), so a receipt that never displayed this check is not a receipt
#: this signature may cite.
_RECEIPT_SQL: Final = """
SELECT r.receipt_id
  FROM mainline.exposure_receipt r
  JOIN mainline.exposure_line l ON l.receipt_id = r.receipt_id
 WHERE r.permit_id = %s AND l.check_id = %s AND r.expires_at > now()
 ORDER BY r.issued_at DESC
 LIMIT 1
"""


def resolve(conn: psycopg.Connection[Any], scenario: Scenario | None = None) -> ResolvedScenario:
    """Read the seeded history back out of *conn*.

    Raises:
        ScenarioNotSeeded: no permit with that identifier. The message names the
            identifier and the environment variable that overrides it, because the
            failure a stranger hits here is always "I pointed it at the wrong database"
            and a message that does not say which permit was wanted cannot tell them so.
    """
    sc = scenario or from_env()
    row = positional(conn, _RESOLVE_SQL, (sc.permit_id,)).fetchone()
    if row is None:
        raise ScenarioNotSeeded(
            f"no mainline.permit with permit_id {sc.permit_id} in this database. The demo "
            f"history is seeded by w2-cloud-database; override the identifier with "
            f"{ENV_PREFIX}PERMIT_ID if this deployment seeded a different one."
        )
    (
        external_ref,
        state,
        head_seq,
        gate_epoch,
        open_blocking,
        open_derived,
        check_id,
        site_code,
    ) = row

    receipt_id: uuid.UUID | None = None
    if check_id is not None:
        got = positional(conn, _RECEIPT_SQL, (sc.permit_id, check_id)).fetchone()
        receipt_id = got[0] if got else None

    return ResolvedScenario(
        scenario=sc,
        external_ref=external_ref,
        state=state,
        head_seq=int(head_seq),
        gate_epoch=int(gate_epoch),
        open_blocking=int(open_blocking),
        open_derived=int(open_derived),
        check_id=check_id,
        receipt_id=receipt_id,
        site_code=site_code,
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# the second gated subject
#
# THE SAME TWO QUESTIONS, ASKED OF A SUBJECT WHOSE IDENTIFIER CANNOT BE DERIVED.
#
# `resolve` above answers "what does the database say about the permit this deployment
# names". The permit is NAMED by a uuid5 both the seed and the API recompute. The change
# request is not: `demo_world.sql` §10 fixes `cr_id` as a literal and states, in the file,
# that the literal appears nowhere under `apps/demo-api/src/`. So the question splits in
# two and both halves are asked of the database:
#
#   `resolve_cr_id`          — WHICH change request. A read, refusing rather than
#                              choosing when the answer is not exactly one row.
#   `resolve_change_request` — WHAT the database says about it, in ONE statement, for the
#                              same reason `_RESOLVE_SQL` is one statement: two would let
#                              a concurrent write land between them and produce a
#                              description of a subject that never existed.
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ResolvedChangeRequest:
    """The change request as the database has it, plus the obligation the gate turns on.

    ``open_blocking`` is the PROJECTED counter — the column ``fn_check_materialised``
    wrote — and ``open_derived`` is the same quantity re-derived by the anti-join
    ``mainline.fn_cr_merge_gate`` itself performs over ``blocking_check`` LEFT JOIN
    ``disposition``. They are carried separately and never reconciled here, for the reason
    :class:`ResolvedScenario` gives: a gate that trusts the first is a gate one ``UPDATE``
    disarms, and demonstrating that is the entire point of the run these feed.
    """

    scenario: Scenario
    cr_id: uuid.UUID
    external_ref: str
    ref_name: str
    target_ref: str
    state: str
    head_seq: int
    gate_epoch: int
    open_blocking: int
    open_conflicts: int
    open_residue: int
    merged_commit: str | None
    open_derived: int
    #: The single open obligation the CR gate turns on, or ``None`` when none is open.
    check_id: uuid.UUID | None
    #: ``mainline.blocking_check.severity`` (0-5), ``virulence`` and ``origin`` for that
    #: obligation, all three PROJECTED by ``fn_check_project`` from the blame closure and
    #: none of them supplied by the seed. ``None`` when there is no open obligation.
    severity: int | None
    virulence: str | None
    origin: str | None
    site_code: str

    def as_json(self) -> dict[str, Any]:
        return {
            "subject_kind": "change_request",
            "subject_id": str(self.cr_id),
            "external_ref": self.external_ref,
            "ref_name": self.ref_name,
            "target_ref": self.target_ref,
            "state": self.state,
            "head_seq": self.head_seq,
            "gate_epoch": self.gate_epoch,
            "open_blocking": self.open_blocking,
            "open_blocking_derived": self.open_derived,
            "open_conflicts": self.open_conflicts,
            "open_residue": self.open_residue,
            "merged_commit": self.merged_commit,
            "blocking_check_id": str(self.check_id) if self.check_id else None,
            "severity": self.severity,
            "virulence": self.virulence,
            "origin": self.origin,
            "site_code": self.site_code,
        }


#: EVERY change request in the database, ordered by its primary key. No predicate and no
#: ``LIMIT``: "exactly one row" is then an assertion about the whole database rather than
#: about whichever row a scan reached first, which is the discipline
#: :mod:`mainline_demo_api.subjects` states and ``tests/conftest.py::_sole`` enforces for
#: the permit. An unordered ``LIMIT 1`` over a table that grew a second row would be a coin
#: toss made silently, on the day somebody seeded a second change request.
_CR_SOLE_SQL: Final = "SELECT cr.cr_id FROM mainline.change_request cr ORDER BY cr.cr_id"

#: One statement. The subject row, the re-derived count, and the chosen obligation's three
#: PROJECTED columns, all read at ONE moment — see the section header above.
_CR_RESOLVE_SQL: Final = """
WITH open_obligation AS (
  SELECT bc.check_id, bc.severity, bc.virulence::STRING AS virulence, bc.origin
    FROM mainline.blocking_check bc
   WHERE bc.cr_id = %s
     AND NOT EXISTS (SELECT 1 FROM mainline.disposition d
                      WHERE d.check_id = bc.check_id
                        AND d.retracted_by IS NULL
                        AND (d.expires_at IS NULL OR d.expires_at > now()))
),
chosen AS (SELECT * FROM open_obligation ORDER BY check_id LIMIT 1)
SELECT cr.external_ref,
       cr.ref_name,
       cr.target_ref,
       cr.state::STRING,
       cr.head_seq,
       cr.gate_epoch,
       cr.open_blocking,
       cr.open_conflicts,
       cr.open_residue,
       encode(cr.merged_commit, 'hex'),
       (SELECT count(*) FROM open_obligation),
       (SELECT check_id FROM chosen),
       (SELECT severity FROM chosen),
       (SELECT virulence FROM chosen),
       (SELECT origin FROM chosen),
       st.site_code
  FROM mainline.change_request cr
  JOIN mainline.site st ON st.site_id = cr.site_id
 WHERE cr.cr_id = %s
"""


def resolve_cr_id(conn: psycopg.Connection[Any], scenario: Scenario | None = None) -> uuid.UUID:
    """Name the change request this deployment's demo drives, without inventing one.

    ``MAINLINE_DEMO_CR_ID`` wins when it is set. Otherwise the database is asked, and the
    answer is accepted only when it is EXACTLY ONE row — not "the first one".

    Raises:
        ScenarioNotSeeded: the database holds no change request, or more than one and no
            override says which. Both messages name the count and the variable, because
            the two failures a stranger actually hits here are "I pointed it at the wrong
            database" and "this cluster carries a second subject", and a message that
            reports neither cannot tell them apart.
    """
    sc = scenario or from_env()
    if sc.cr_id is not None:
        return sc.cr_id
    rows = positional(conn, _CR_SOLE_SQL).fetchall()
    if len(rows) != 1:
        raise ScenarioNotSeeded(
            f"this database holds {len(rows)} mainline.change_request row(s) and exactly "
            f"one is required to drive the change-request gate without choosing between "
            f"them. The demo history is seeded by db/seeds/demo/demo_world.sql §10, which "
            f"writes exactly one; set {ENV_PREFIX}CR_ID to name the subject if this "
            "deployment carries more."
        )
    return uuid.UUID(str(rows[0][0]))


def resolve_change_request(
    conn: psycopg.Connection[Any],
    scenario: Scenario | None = None,
    *,
    cr_id: uuid.UUID | None = None,
) -> ResolvedChangeRequest:
    """Read the seeded change request back out of *conn*.

    Args:
        conn: a live connection. The read joins whatever transaction is open, so a caller
            playing beats inside one sees the same snapshot its beats will write against.
        scenario: the identifiers to drive. Defaults to :func:`from_env`.
        cr_id: the subject, when the caller has already named it. Supplied by
            :mod:`mainline_demo_api.cr_gate_run` so that the reading taken BEFORE its
            transaction and the reading taken INSIDE it are about the same row even on a
            cluster whose change-request table grew a row between them — resolving the
            identifier twice would let those two readings describe two subjects.

    Raises:
        ScenarioNotSeeded: no change request with that identifier, or none to choose.
    """
    sc = scenario or from_env()
    subject = cr_id if cr_id is not None else resolve_cr_id(conn, sc)
    row = positional(conn, _CR_RESOLVE_SQL, (subject, subject)).fetchone()
    if row is None:
        raise ScenarioNotSeeded(
            f"no mainline.change_request with cr_id {subject} in this database. The demo "
            f"history is seeded by db/seeds/demo/demo_world.sql §10; override the "
            f"identifier with {ENV_PREFIX}CR_ID if this deployment seeded a different one."
        )
    (
        external_ref,
        ref_name,
        target_ref,
        state,
        head_seq,
        gate_epoch,
        open_blocking,
        open_conflicts,
        open_residue,
        merged_commit,
        open_derived,
        check_id,
        severity,
        virulence,
        origin,
        site_code,
    ) = row
    return ResolvedChangeRequest(
        scenario=sc,
        cr_id=subject,
        external_ref=external_ref,
        ref_name=ref_name,
        target_ref=target_ref,
        state=state,
        head_seq=int(head_seq),
        gate_epoch=int(gate_epoch),
        open_blocking=int(open_blocking),
        open_conflicts=int(open_conflicts),
        open_residue=int(open_residue),
        merged_commit=merged_commit,
        open_derived=int(open_derived),
        check_id=check_id,
        severity=None if severity is None else int(severity),
        virulence=virulence,
        origin=origin,
        site_code=site_code,
    )
