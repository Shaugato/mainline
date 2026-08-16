# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The other half of the same claim: you cannot quietly EDIT AWAY the clause under blame.

``POST /v1/demo/gate-run`` shows that a supervisor cannot ISSUE a permit that relies on a
clause a past incident's blame reaches. The obvious next question — *"fine, so couldn't
somebody just rewrite the rule?"* — is already answered by the seeded world and by nothing
in the demo's HTTP surface. ``POST /v1/demo/cr-gate-run`` is that answer, played against
the SECOND gated subject: ``mainline.change_request`` ``DEMO-MOC-0001``, which proposes to
``edit`` the very clause version the permit relies on, stands in ``checks_materialised``,
and carries one open obligation of severity 4 / ``blood_major`` / ``blame_ancestry``.

The two runs are mirror images and neither needed a new rule. The gate this one meets was
in the schema before this module existed: ``CONSTRAINT cr_gate_closed_when_merged`` on
``mainline.change_request`` (migration ``0051``) and the ``BEFORE UPDATE`` trigger
``cr_merge_gate`` (``0131``) over ``mainline.fn_cr_merge_gate`` (``0116``). What was
missing was an HTTP path on which a caller could ATTEMPT the edit and be refused.

THREE BEATS, AND TWO DECLARED ABSENCES
--------------------------------------
1. **The change request, with its open obligation.** Read-only. The projected counter and
   the count re-derived by the gate's own anti-join are reported side by side, because the
   difference between them is what beat 3 is about, and the four named CHECKs are read out
   of ``pg_catalog.pg_constraint`` rather than listed here.
2. **MERGE → REFUSED.** ``23514`` on ``cr_gate_closed_when_merged``, the constraint name
   REPORTED by the driver.
3. **THE PROJECTION-DRIFT ATTACK → REFUSED ANYWAY.**
   ``mainline.change_request.open_blocking`` is forced to zero out of band and the merge is
   attempted again. ``P0001`` naming ``mainline.fn_cr_merge_gate``, whose message carries
   the re-derived count against the forged zero.

There is no fourth beat, and the payload says so in words rather than by omission. Two
things this run cannot honestly play are declared, each with the grant rows that make it
so — see the two sections below. A beat marked ``skipped`` and dressed to look passing
would be a fabricated exhibit; silence would be worse, because a reader cannot audit an
absence nobody mentioned.

WHY THE MERGE IS A BARE ``UPDATE`` AND NOT THE KERNEL PROCEDURE
----------------------------------------------------------------
*(The procedure is ``mainline.merge_change_request``, invoked with ``CALL``. It is written
that way round throughout this file, keyword and name apart, and not out of taste:
``mainline_boundary.sqlrefs`` reads every string constant in this package — docstrings
included — and treats ``CALL <schema>.<routine>`` as an EXECUTE demand. Spelling the two
together here would make the privilege census believe this endpoint invokes a procedure it
deliberately does not, and a census that cannot be trusted is worse than none. This module
issues no ``CALL`` at all.)*

Because MEASURED, on 2026-08-16, against a database built from this repository's 271
migrations and seeded by ``scripts/deploy/seed_demo.py``, with ``mainline_api`` created and
granted by ``scripts/deploy/cloud_roles.py`` from ``db/GRANTS.yaml``:

======================================  ==========================================
as ``root``                             ``23503`` ``cr_legal_edge``
as ``mainline_api`` (the deployed role) ``42501`` *user mainline_api does not have
                                        INSERT privilege on relation cr_event*
======================================  ==========================================

The procedure's step 5 INSERTs into ``mainline.cr_event`` and ``mainline_api`` holds
**SELECT only** there (``db/GRANTS.yaml:761``). CockroachDB checks the privilege while
planning, so the privilege error arrives BEFORE the foreign key onto
``mainline.subject_transition`` can refuse the illegal edge — which means that on the
cluster this demo actually deploys to, a ``CALL`` beat would put ``42501`` on screen. **A
privilege error is not a gate refusal**: it says the writer never reached the gate
(``refusal.classify`` returns ``denied`` for it, deliberately), and presenting one as the
other is the exact fabrication this repository refuses. So the beat is not played, and the
measurement that removed it is in the payload as ``kernel_procedure_absent_sqlstate``
rather than in a comment nobody reads.

**Granting INSERT on ``mainline.cr_event`` is not the fix and is not this wave's to make.**
Widening the write surface of an endpoint on a Function URL carrying
``authorization_type = NONE`` is the founder's call. It is the same class as the standing
``transitions.materialise_checks`` / ``exposure_receipt`` finding, and it is left open in
the same way: recorded, not quietly closed.

**And the bare statement is the stronger exhibit anyway.** The gate is welded to the TABLE
— a ``CHECK`` on the column and two ``BEFORE UPDATE`` triggers, ``cr_merge_gate`` and
``z_cbm_gate_cr``, both carrying ``WHEN (NEW).state = 'merged'`` — not to the procedure. A
caller who skips the kernel's own procedure entirely, which is precisely what an attacker
does, meets the same named CHECK and the same named trigger function. The statement needs
only ``UPDATE`` on ``mainline.change_request`` (``GRANTS.yaml:755``) plus the SELECTs the
trigger cascade already holds (``cr_clause`` 758, ``clause_blame_current`` 664,
``blocking_check`` 630, ``disposition`` 633, ``cbm_account`` 681, ``identity_residue`` 764).

WHY THERE IS NO ADMISSION BEAT, AND WHY THAT IS SAID OUT LOUD
--------------------------------------------------------------
``gate_run``'s fourth beat exists because *a gate that always refuses is broken, not safe*.
That beat cannot be played here **honestly**, and the reason is two rows in the grant
matrix rather than an omission in this file:

* ``mainline.disposition`` cannot be signed without an exposure receipt that actually
  SHOWED the obligation — the composite foreign key on ``(check_id, receipt_id)`` says so.
* No such receipt exists for this obligation. ``mainline.exposure_receipt`` holds one row,
  ``subject_kind = 'permit'``, and its one ``exposure_line`` points at the permit's check.
* Minting one needs INSERT on ``mainline.exposure_receipt`` / ``exposure_line``, and
  ``mainline_api`` holds SELECT on both (``GRANTS.yaml:644``, ``:647``).

So the payload carries ``admission_beat: null``, the reason in words, those two grant rows,
and ``admission_proved_by: "POST /v1/demo/gate-run"`` — the endpoint where the admission IS
proved, against the subject that can carry it. The claim this run makes is narrower than
gate-run's and the payload says exactly how much narrower.

WHY IT PERSISTS NOTHING, AND HOW THAT IS PROVED RATHER THAN ASSERTED
---------------------------------------------------------------------
All three beats run inside ONE ``SERIALIZABLE`` transaction. Each write beat is fenced by
its own ``SAVEPOINT`` / ``ROLLBACK TO SAVEPOINT``, and the whole transaction is
``ROLLBACK``-ed. ``persisted: false`` is then a CONCLUSION from readings printed beside it:

1. **The ten unscoped whole-table counts, unchanged and unnarrowed.** They are IMPORTED
   from :mod:`mainline_demo_api.gate_run` rather than copied — ``_FINGERPRINT_SQL`` and
   ``_FINGERPRINT_TABLES`` are the same objects, so no table can leave one list and stay
   in the other. ``docs/leads/cloud-hardening-final.md`` R2 forbids narrowing them and
   this narrows nothing.
2. **A CR-scoped reading**, ADDED beside them: the ``change_request`` row's ``state``,
   ``head_seq``, ``gate_epoch``, ``open_blocking``, ``open_conflicts``, ``open_residue``
   and ``merged_commit``, plus ``cr_event`` and ``merge_record`` counts for this ``cr_id``.
   Neither of those two tables is among the ten, and adding them THERE would have narrowed
   nothing but would have changed a reading gate-run also depends on.
3. **A run-scoped witness.** ``gate_run``'s is the ``uuid4`` its admitted beat minted. This
   run admits nothing, so the witness is the subject row itself: beat 3 forces
   ``open_blocking`` to ``0`` — a write the database ADMITS, because both merge triggers
   carry ``WHEN (NEW).state = 'merged'`` and this statement sets no state — and after the
   rollback the column must read what it read before. That zero is a value THIS RUN wrote
   and no other caller did.

   Stated exactly, because the strength of the claim is the claim: the forced write is
   undone TWICE — by beat 3's own ``ROLLBACK TO SAVEPOINT``, and again by the transaction's
   ``ROLLBACK``. Both readings are in the payload (``counter_after_savepoint_rollback`` and
   the ``after`` fingerprint), so a reader can see which fence did what instead of taking a
   single boolean on trust. The same is true of ``gate_run``'s minted disposition and is
   why ``tests/test_transitions.py::test_a_run_that_really_persists_is_caught`` has to
   defeat both fences to make that check fire.

``self_persisted`` keys on the CR-scoped reading and the subject row; ``identical`` still
reports the ten counts and is still a statement about the DATABASE, which any other caller
can move. The verdict keys on the first, for the reason
``docs/diagnosis/gate-run-fingerprint.md`` records: a whole-table count cannot tell *"I
persisted something"* from *"somebody else did"*.

``cluster_logical_timestamp()`` is captured at the first beat and after the last. It is
constant within a CockroachDB transaction and moves between them, so equal endpoints are a
READ-ONLY witness that no beat quietly opened a transaction of its own.

WHAT THIS MODULE WILL NOT DO
----------------------------
It will not retry. ``40001`` aborts the run and is reported as ``outcome: "retry"`` with
the beats completed so far; ``transitions._demo_cr_gate_run`` re-runs the WHOLE function
under :func:`mainline_demo_api.retry.run_transaction`, which ``spec/errors.md`` §2.1
permits precisely because the re-run unit is the whole transaction from ``BEGIN``.

It will not compose a message. Every ``sqlstate``, ``constraint`` and ``message`` comes out
of the driver's error object through :func:`mainline_demo_api.refusal.diagnose`, and every
reason set out of ``trappoint.explain_refusal``.

It will not declare a beat successful because it did not raise, and it will not call an
``UPDATE`` that matched no row an admission — a compare-and-swap that missed did not get
past the gate, it never reached it, and that outcome is reported as ``error`` with the row
count that says so.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any, Final

import psycopg

# THE TEN COUNTS ARE IMPORTED, NOT COPIED, AND THAT IS THE POINT.
#
# `docs/leads/cloud-hardening-final.md` R2 permits the persistence contract to move only by
# argument on the record and forbids narrowing this reading. A transcribed copy would
# satisfy that on the day it was written and drift the first time a table joined one list
# and not the other — the "second copy of a list is a second thing to drift" rule this
# repository states in `test_seed_covers_every_console_resource.py` and enforces in
# `test_privilege_census.py`. These are the SAME objects `gate_run` fingerprints with, so
# "no table left the list" is a property of the code rather than a claim in a comment.
# `tests/test_cr_gate_run.py::test_the_ten_unscoped_counts_are_gate_runs_own_list` asserts
# the identity, so an edit that re-typed them here would be red.
from .gate_run import _FINGERPRINT_SQL, _FINGERPRINT_TABLES
from .refusal import Diagnosis, classify, diagnose, refusal_payload, rfc3339
from .scenario import (
    ResolvedChangeRequest,
    Scenario,
    positional,
    resolve_change_request,
    resolve_cr_id,
)

__all__ = [
    "ADMISSION_ABSENT_GRANTS",
    "ADMISSION_PROVED_BY",
    "CR_CF01_EXHIBIT",
    "CR_CF01_SQLSTATE",
    "CR_CF03_EXHIBIT",
    "CR_CF03_SQLSTATE",
    "CR_GATE_RUN_SCHEMA_ID",
    "KERNEL_PROCEDURE_ABSENT_GRANTS",
    "KERNEL_PROCEDURE_ABSENT_SQLSTATE",
    "READ_SQLSTATE",
    "cr_gate_run",
]

#: The contract this module's payload satisfies. Governs `contracts/cr-gate-run.schema.json`.
CR_GATE_RUN_SCHEMA_ID: Final = (
    "https://console.mainline.trappoint.org/contracts/1.0/cr-gate-run.schema.json"
)

#: The two exhibits this run exists to produce, and the code a beat that did not raise
#: carries. Named after the conformance cases whose change-request arm they are: CF-01 is
#: the counter's own CHECK, CF-03 the re-derivation under a forged counter.
CR_CF01_SQLSTATE: Final = "23514"
CR_CF01_EXHIBIT: Final = "cr_gate_closed_when_merged"
CR_CF03_SQLSTATE: Final = "P0001"
CR_CF03_EXHIBIT: Final = "mainline.fn_cr_merge_gate"
READ_SQLSTATE: Final = "00000"

#: What ``mainline.merge_change_request(…)``, invoked with ``CALL``, answers **as the role
#: the deployed Function URL executes as**, measured rather than assumed — see the module
#: docstring, including why the keyword and the name are never written together here.
#: It is in the payload so that the absent beat is auditable from the response alone.
KERNEL_PROCEDURE_ABSENT_SQLSTATE: Final = "42501"
KERNEL_PROCEDURE_ABSENT_GRANTS: Final[tuple[str, ...]] = (
    "db/GRANTS.yaml:761 — mainline_api holds SELECT on mainline.cr_event, and no INSERT",
)

#: The two rows that make an admission beat impossible to play honestly on this subject.
ADMISSION_ABSENT_GRANTS: Final[tuple[str, ...]] = (
    "db/GRANTS.yaml:644 — mainline_api holds SELECT on mainline.exposure_receipt, no INSERT",
    "db/GRANTS.yaml:647 — mainline_api holds SELECT on mainline.exposure_line, no INSERT",
)

#: Where the admission this run cannot play IS proved, against the subject that carries the
#: receipt for it. Not an excuse — a pointer, so a reader can go and press it.
ADMISSION_PROVED_BY: Final = "POST /v1/demo/gate-run"

ADMISSION_ABSENT_REASON: Final = (
    "No admission beat is played on this subject, and none is faked. A disposition's "
    "composite foreign key lands on (check_id, receipt_id), so signing one requires an "
    "exposure receipt that actually SHOWED this obligation; mainline.exposure_receipt "
    "carries no row for this change request, and this endpoint's login may read "
    "exposure_receipt and exposure_line but may not write to either — the two grant rows "
    "beside this sentence are the authority for that — so it cannot mint one. A fourth "
    "beat marked 'skipped' and dressed to look passing would be a fabricated exhibit. The "
    f"admission is proved at {ADMISSION_PROVED_BY}, against the permit, which does carry "
    "the receipt — and a gate that always refuses is broken, not safe, so that beat is not "
    "optional and is not missing from the demo, only from THIS run."
)

KERNEL_PROCEDURE_ABSENT_REASON: Final = (
    "The kernel's own procedure — mainline.merge_change_request(...), invoked with CALL — "
    "is not played, and this endpoint issues no CALL statement at all. "
    "Measured on a database built from this repository's migrations and seed with "
    "mainline_api granted from db/GRANTS.yaml: as root it answers 23503 cr_legal_edge — "
    "the edge checks_materialised -> merged is not a row in mainline.subject_transition — "
    "but as mainline_api, the role this deployment's anonymous callers execute as, it "
    "answers 42501 'user mainline_api does not have INSERT privilege on relation "
    "cr_event', because the procedure's step 5 appends to mainline.cr_event and the "
    "privilege is checked while planning, before the foreign key can refuse. A privilege "
    "error says the writer never reached the gate; presenting one as a gate refusal would "
    "be a fabricated exhibit, so the beat was dropped rather than shown. Granting INSERT "
    "on mainline.cr_event to widen the write surface of an unauthenticated endpoint is not "
    "this endpoint's decision to make. The merge beat below reaches the same CHECK and the "
    "same trigger function by the bare statement instead — which is what an attacker who "
    "skips the procedure does, and is the stronger exhibit for it."
)

#: THE MERGE, AS A CALLER WHO SKIPS THE KERNEL'S PROCEDURE WOULD WRITE IT.
#:
#: ``head_seq = %s`` is a compare-and-swap and not decoration: without it a second caller
#: could move the head between this run's read and this statement and the run would report
#: a refusal about a row it had not read. A zero-row result is therefore a real outcome and
#: is reported as one — never as an admission, because an UPDATE that matched nothing did
#: not pass the gate, it never reached it.
_MERGE_SQL: Final = (
    "UPDATE mainline.change_request "
    "SET state = 'merged', head_seq = head_seq + 1, merged_commit = %s "
    "WHERE cr_id = %s AND head_seq = %s"
)

#: The attack. ADMITTED by the database — measured — because ``cr_merge_gate`` (0131) and
#: ``z_cbm_gate_cr`` (0145d) both carry ``WHEN (NEW).state = 'merged'`` and this statement
#: sets no state. That is exactly what a disarmed projector or a careless UPDATE leaves
#: behind, and it is why the gate re-derives instead of trusting the column.
_FORCE_SQL: Final = "UPDATE mainline.change_request SET open_blocking = 0 WHERE cr_id = %s"

_COUNTER_SQL: Final = "SELECT open_blocking FROM mainline.change_request WHERE cr_id = %s"

#: The named refusals, read out of the catalog rather than listed in Python — the exact
#: discipline ``reads._gate_constraints`` states and for the same reason: *which*
#: constraints are gate refusals is decided by the catalog's own text, so a fifth added by
#: a future migration appears here without an edit and a deleted one disappears. The
#: ``'merged'`` filter is applied in Python rather than as a ``LIKE`` for the same reason it
#: is there: the pattern would need a literal ``%`` in a statement this module also sends
#: with parameters elsewhere, and one careless edit later that is a ``22P02`` nobody
#: expected. Four rows on ``mainline.change_request`` today — measured, not asserted.
_NAMED_CHECKS_SQL: Final = """
SELECT con.conname, pg_get_constraintdef(con.oid)
  FROM pg_catalog.pg_constraint con
  JOIN pg_catalog.pg_class      rel ON rel.oid = con.conrelid
  JOIN pg_catalog.pg_namespace  nsp ON nsp.oid = rel.relnamespace
 WHERE nsp.nspname = 'mainline'
   AND rel.relname = 'change_request'
   AND con.contype = 'c'
 ORDER BY con.oid
"""

#: What makes a CHECK on a gated subject a GATE refusal: every one of them is shaped
#: ``state <> 'merged' OR <counter> = 0``, so the catalog's own predicate text decides.
_GATE_PREDICATE_MARK: Final = "'merged'"

#: The vocabulary this obligation offers. Read, never stated: the codes are about the
#: proposed EDIT — whether the control survives it, whether the anchor touched is the one
#: under blame, whether the precursor was answered elsewhere — and they are deliberately
#: NOT the permit's three, because ``PRIMARY KEY (check_id, defeater_code)`` makes a code
#: unique WITHIN a check and meaningless outside it. Nothing is signed here; this read
#: exists so the payload can show what a signer WOULD be asked, which is the whole reason
#: the obligation is a question rather than a checkbox.
_DEFEATERS_SQL: Final = (
    "SELECT o.defeater_code FROM mainline.defeater_option o "
    "WHERE o.check_id = %s ORDER BY o.defeater_code"
)

#: THE SAME QUESTION AS THE TEN COUNTS, ASKED OF THE SUBJECT THIS RUN DROVE.
#:
#: ``mainline.change_request`` and ``mainline.cr_event`` are NOT among the ten — see
#: ``gate_run._FINGERPRINT_TABLES`` — and they are added here rather than there for the
#: reason the plan gives: the ten prove something about the DATABASE and are deliberately
#: broad, and editing them would change a reading ``POST /v1/demo/gate-run`` also depends
#: on. ``merge_record`` IS among the ten and is counted again here, scoped, because a
#: whole-table count cannot say whose row moved.
_CR_COUNTS_SQL: Final = """
SELECT (SELECT count(*) FROM mainline.cr_event     WHERE cr_id = %s),
       (SELECT count(*) FROM mainline.merge_record WHERE cr_id = %s)
"""

_CR_COUNT_TABLES: Final[tuple[str, ...]] = ("mainline.cr_event", "mainline.merge_record")

#: The subject row itself, by VALUE. The attack beat mutates a column without changing any
#: count, so a check that counted rows and stopped there could not see the one write this
#: run actually makes.
_CR_ROW_SQL: Final = """
SELECT state::STRING, head_seq, gate_epoch, open_blocking, open_conflicts, open_residue,
       encode(merged_commit, 'hex')
  FROM mainline.change_request WHERE cr_id = %s
"""

_BEAT_2_SAVEPOINT: Final = "cr_gate_run_beat_2"
_BEAT_3_SAVEPOINT: Final = "cr_gate_run_beat_3"


class _Undecided(Exception):
    """``40001`` — the transaction is undecided and the run cannot continue."""

    def __init__(self, diagnosis: Diagnosis) -> None:
        super().__init__(diagnosis.message)
        self.diagnosis = diagnosis


def _logical_timestamp(conn: psycopg.Connection[Any]) -> str:
    """Read CockroachDB's transaction-scoped logical clock.

    Constant within a transaction and monotonic between them, which is what makes it a
    read-only witness that the beats shared one transaction rather than a claim this module
    makes about itself.
    """
    row = positional(conn, "SELECT cluster_logical_timestamp()::STRING").fetchone()
    if row is None:  # pragma: no cover - a scalar SELECT always returns a row
        raise RuntimeError("cluster_logical_timestamp() returned no row")
    return str(row[0])


def _fingerprint(conn: psycopg.Connection[Any], cr_id: uuid.UUID) -> dict[str, Any]:
    """Three readings, taken together: the ten, the CR's own counts, and the CR's row."""
    counts = positional(conn, _FINGERPRINT_SQL).fetchone()
    if counts is None:  # pragma: no cover - ten scalar subqueries always return one row
        raise RuntimeError("the fingerprint statement returned no row")
    scoped = positional(conn, _CR_COUNTS_SQL, (cr_id, cr_id)).fetchone()
    if scoped is None:  # pragma: no cover - two scalar subqueries always return one row
        raise RuntimeError("the change-request-scoped statement returned no row")
    row = positional(conn, _CR_ROW_SQL, (cr_id,)).fetchone()
    return {
        # strict=True: the imported table list and the statement's ten subqueries are one
        # list written twice, and a zip that truncated silently would report a persistence
        # check over FEWER tables than the payload claims. CockroachDB names all ten of
        # those columns `count`, so a dict row collapses them to one — which is why every
        # statement here goes through `positional`.
        "row_counts": {name: int(n) for name, n in zip(_FINGERPRINT_TABLES, counts, strict=True)},
        "subject_row_counts": {
            name: int(n) for name, n in zip(_CR_COUNT_TABLES, scoped, strict=True)
        },
        "change_request_row": (
            None
            if row is None
            else {
                "state": row[0],
                "head_seq": int(row[1]),
                "gate_epoch": int(row[2]),
                "open_blocking": int(row[3]),
                "open_conflicts": int(row[4]),
                "open_residue": int(row[5]),
                "merged_commit": row[6],
            }
        ),
    }


def _beat(ordinal: int, name: str, label: str, **expected: Any) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "name": name,
        "label": label,
        "expected": expected,
        "outcome": "skipped",
        "sqlstate": None,
        "constraint": None,
        "constraint_source": None,
        "message": None,
        "matched_expectation": False,
        "elapsed_ms": 0.0,
        "statement": None,
        "refusal": None,
        "observed": {},
        "note": None,
    }


def _record_refusal(
    conn: psycopg.Connection[Any],
    beat: dict[str, Any],
    exc: psycopg.Error,
    resolved: ResolvedChangeRequest,
    attempt: dict[str, Any],
) -> None:
    """Fill *beat* from the driver's error object. Raises :class:`_Undecided` on 40001.

    ``denied`` — ``42501`` — lands in the ``error`` branch beside every other unmodelled
    code, and its note says which one it was. That is not a technicality on this endpoint:
    the beat this module DROPPED was dropped because it produced exactly that code as the
    deployed role, so a ``42501`` arriving on a beat that IS played must be reported as the
    privilege failure it is and never as a refusal the gate made.
    """
    found = diagnose(exc)
    kind = classify(found)
    if kind == "retry":
        raise _Undecided(found)

    beat["sqlstate"] = found.sqlstate or None
    beat["constraint"] = found.constraint or None
    beat["constraint_source"] = found.constraint_source
    beat["message"] = found.message

    if kind != "refused":
        denied = (
            " 42501 is a PRIVILEGE failure: the writer never reached the gate, so this is "
            "not a refusal and is not reported as one — it is the same code that removed "
            "the kernel-procedure beat from this run."
            if kind == "denied"
            else ""
        )
        beat["outcome"] = "error"
        beat["note"] = (
            f"{found.sqlstate or '(no sqlstate)'} is outside the refusal taxonomy "
            f"(23514, 23503, 23505, P0001) or carried no exhibit.{denied} spec/errors.md "
            "§1.1 makes that a defect to be reported, not an edge case to be smoothed over."
        )
        return

    beat["outcome"] = "refused"
    beat["refusal"] = refusal_payload(
        conn,
        found,
        subject_kind="change_request",
        subject_id=str(resolved.cr_id),
        gate_epoch=resolved.gate_epoch,
        attempt=attempt,
    )


def _match(beat: dict[str, Any]) -> None:
    expected = beat["expected"]
    beat["matched_expectation"] = all(
        (
            beat["outcome"] == expected.get("outcome"),
            expected.get("sqlstate") in (None, beat["sqlstate"]),
            expected.get("constraint") in (None, beat["constraint"]),
            expected.get("constraint_source") in (None, beat["constraint_source"]),
        )
    )


def _attempt_merge(conn: psycopg.Connection[Any], resolved: ResolvedChangeRequest) -> int:
    """Issue the bare merge statement and return how many rows it matched."""
    cursor = positional(
        conn,
        _MERGE_SQL,
        (resolved.scenario.cr_merged_commit, resolved.cr_id, resolved.head_seq),
    )
    return int(cursor.rowcount)


def _not_a_refusal(beat: dict[str, Any], matched: int) -> None:
    """Record an UPDATE that raised nothing, telling ADMITTED from MATCHED NOTHING."""
    if matched == 0:
        beat["outcome"] = "error"
        beat["sqlstate"] = READ_SQLSTATE
        beat["note"] = (
            "the merge statement matched NO row, so the gate was never asked: the "
            "compare-and-swap on head_seq missed, which means another writer moved this "
            "change request's head between the read and this statement. That is not an "
            "admission and it is not a refusal — nothing was decided — and re-running the "
            "endpoint asks the question again against the head that is there now."
        )
        return
    beat["outcome"] = "admitted"
    beat["sqlstate"] = READ_SQLSTATE
    beat["note"] = (
        "the merge was ADMITTED with an open obligation — the gate did not hold. "
        "cr_gate_closed_when_merged and mainline.fn_cr_merge_gate were both expected to "
        "refuse this statement and neither did."
    )


def cr_gate_run(  # noqa: PLR0912, PLR0915 — one straight line of three beats; splitting it
    # into per-beat helpers would hide the ORDER, and the order is the argument.
    conn: psycopg.Connection[Any],
    scenario: Scenario | None = None,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Play the three beats against the seeded change request and roll everything back.

    Args:
        conn: a psycopg connection. Must not be in autocommit — the whole point is one
              transaction — and is left with no transaction in progress on return.
        scenario: the identifiers to drive. Defaults to :func:`scenario.from_env`.
        run_id: identifier for this run. Minted when absent.

    Returns:
        The payload governed by ``contracts/cr-gate-run.schema.json``.

    Raises:
        ScenarioNotSeeded: this database holds no change request, or holds more than one
            and nothing says which. Distinct from every outcome above: "there was nothing
            to ask" is not "the gate did not refuse", and only one of them is about the
            product.
    """
    if conn.autocommit:
        raise ValueError(
            "cr_gate_run needs a connection that is NOT in autocommit: the three beats "
            "share one transaction, and that is the property the demo is showing."
        )

    started = time.perf_counter()
    generated_at = rfc3339(datetime.now(UTC))
    conn.rollback()  # a clean slate, whatever the caller left behind

    # ── BEFORE. Read in a transaction of its own, which is then rolled back, so that the
    #    fingerprint is the COMMITTED state rather than anything the beats can see.
    #
    #    THE IDENTIFIER IS RESOLVED ONCE AND THEN CARRIED. `resolve_cr_id` may have to ASK
    #    the database which change request this is (there is no derivation for it — see
    #    `scenario.py`), and asking twice would let the two fingerprints describe two
    #    different subjects on a cluster whose change-request table grew a row in between.
    #    The ROW is read twice, deliberately: once here against the committed state and
    #    once inside the beats' transaction, which is what makes `counters_agree` a
    #    statement about the snapshot the beats actually wrote against.
    cr_id = resolve_cr_id(conn, scenario)
    before = _fingerprint(conn, cr_id)
    conn.rollback()

    conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    opened_ts = _logical_timestamp(conn)
    resolved = resolve_change_request(conn, scenario, cr_id=cr_id)

    beats: list[dict[str, Any]] = [
        _beat(
            1,
            "read",
            "The change request, and the obligation that is still open on it.",
            outcome="read",
        ),
        _beat(
            2,
            "merge",
            "MERGE the change request — the edit lands on the protected branch. One open "
            "obligation, no signed disposition.",
            outcome="refused",
            sqlstate=CR_CF01_SQLSTATE,
            constraint=CR_CF01_EXHIBIT,
            constraint_source="reported",
        ),
        _beat(
            3,
            "projection_drift_attack",
            "THE ATTACK: force the projected counter to zero out of band, then merge again.",
            outcome="refused",
            sqlstate=CR_CF03_SQLSTATE,
            constraint=CR_CF03_EXHIBIT,
            constraint_source="parsed",
        ),
    ]
    undecided: Diagnosis | None = None
    #: What beat 3 forced the counter to, hoisted so the persistence check can report the
    #: witness it wrote. Stays ``None`` when the beat never got that far.
    forced_counter: int | None = None
    #: The counter read back INSIDE the transaction after beat 3's savepoint rollback. The
    #: first of the two fences, reported so the second one is not asked to carry the whole
    #: claim on its own.
    counter_after_savepoint: int | None = None

    try:
        # ── BEAT 1 · THE CHANGE REQUEST ─────────────────────────────────────────────
        mark = time.perf_counter()
        named_checks = [
            {"constraint": str(row[0]), "predicate": str(row[1])}
            for row in positional(conn, _NAMED_CHECKS_SQL).fetchall()
            if _GATE_PREDICATE_MARK in str(row[1])
        ]
        defeaters: list[str] = []
        if resolved.check_id is not None:
            offered = positional(conn, _DEFEATERS_SQL, (resolved.check_id,)).fetchall()
            defeaters = [str(row[0]) for row in offered]
        beats[0]["outcome"] = "read"
        beats[0]["sqlstate"] = READ_SQLSTATE
        beats[0]["statement"] = (
            "SELECT … FROM mainline.change_request JOIN mainline.site …; "
            "SELECT … FROM pg_catalog.pg_constraint …; "
            "SELECT defeater_code FROM mainline.defeater_option …"
        )
        beats[0]["observed"] = {
            "state": resolved.state,
            "gate_epoch": resolved.gate_epoch,
            "head_seq": resolved.head_seq,
            "open_blocking_projected": resolved.open_blocking,
            "open_blocking_derived": resolved.open_derived,
            "counters_agree": resolved.open_blocking == resolved.open_derived,
            "blocking_check_id": str(resolved.check_id) if resolved.check_id else None,
            "severity": resolved.severity,
            "virulence": resolved.virulence,
            "origin": resolved.origin,
            "defeater_options": defeaters,
            "named_checks": named_checks,
        }
        beats[0]["elapsed_ms"] = round((time.perf_counter() - mark) * 1000, 3)
        _match(beats[0])

        # ── BEAT 2 · THE REFUSAL ────────────────────────────────────────────────────
        mark = time.perf_counter()
        beats[1]["statement"] = _MERGE_SQL
        conn.execute(f"SAVEPOINT {_BEAT_2_SAVEPOINT}")
        try:
            matched = _attempt_merge(conn, resolved)
        except psycopg.Error as exc:
            conn.execute(f"ROLLBACK TO SAVEPOINT {_BEAT_2_SAVEPOINT}")
            _record_refusal(
                conn,
                beats[1],
                exc,
                resolved,
                {"kind": "merge", "gate_epoch": resolved.gate_epoch},
            )
        else:
            conn.execute(f"ROLLBACK TO SAVEPOINT {_BEAT_2_SAVEPOINT}")
            _not_a_refusal(beats[1], matched)
            beats[1]["observed"] = {"rows_matched": matched}
        conn.execute(f"RELEASE SAVEPOINT {_BEAT_2_SAVEPOINT}")
        beats[1]["elapsed_ms"] = round((time.perf_counter() - mark) * 1000, 3)
        _match(beats[1])

        # ── BEAT 3 · THE PROJECTION-DRIFT ATTACK ────────────────────────────────────
        mark = time.perf_counter()
        beats[2]["statement"] = f"{_FORCE_SQL}; {_MERGE_SQL}"
        conn.execute(f"SAVEPOINT {_BEAT_3_SAVEPOINT}")
        try:
            conn.execute(_FORCE_SQL, (resolved.cr_id,))
            got = positional(conn, _COUNTER_SQL, (resolved.cr_id,)).fetchone()
            forced_counter = int(got[0]) if got else None
            beats[2]["observed"] = {
                "counter_forced_to": forced_counter,
                "open_blocking_derived": resolved.open_derived,
                "attack": (
                    "mainline.change_request.open_blocking set out of band — what a "
                    "disarmed projector or a careless UPDATE leaves behind. The database "
                    "ADMITS this write: cr_merge_gate and z_cbm_gate_cr both carry WHEN "
                    "(NEW).state = 'merged', and this statement sets no state."
                ),
            }
            matched = _attempt_merge(conn, resolved)
        except psycopg.Error as exc:
            conn.execute(f"ROLLBACK TO SAVEPOINT {_BEAT_3_SAVEPOINT}")
            _record_refusal(
                conn,
                beats[2],
                exc,
                resolved,
                {"kind": "merge", "gate_epoch": resolved.gate_epoch},
            )
        else:
            conn.execute(f"ROLLBACK TO SAVEPOINT {_BEAT_3_SAVEPOINT}")
            _not_a_refusal(beats[2], matched)
            beats[2]["observed"]["rows_matched"] = matched
        conn.execute(f"RELEASE SAVEPOINT {_BEAT_3_SAVEPOINT}")
        # THE FIRST FENCE, READ BACK. Beat 3's savepoint has undone the forced write; this
        # is that undo, observed rather than assumed, and it is reported beside the `after`
        # fingerprint so a reader can see which of the two rollbacks restored the counter
        # instead of being handed one boolean covering both.
        restored = positional(conn, _COUNTER_SQL, (resolved.cr_id,)).fetchone()
        counter_after_savepoint = int(restored[0]) if restored else None
        beats[2]["observed"]["counter_after_savepoint_rollback"] = counter_after_savepoint
        beats[2]["elapsed_ms"] = round((time.perf_counter() - mark) * 1000, 3)
        _match(beats[2])

        closed_ts = _logical_timestamp(conn)
    except _Undecided as stop:
        undecided = stop.diagnosis
        closed_ts = None
    finally:
        # THE WHOLE TRANSACTION GOES BACK. This line is the demo's contract with every
        # judge who presses the button after this one.
        conn.rollback()

    after = _fingerprint(conn, cr_id)
    conn.rollback()

    # ── WHAT THE TWO READINGS EACH PROVE ───────────────────────────────────────────────
    #
    # `identical` compares the WHOLE fingerprint — the ten unscoped counts, this subject's
    # own two counts and its row — and it answers "did anything move". Any other caller
    # committing one row into any of those ten tables makes it false, about a transaction
    # that persisted nothing, which is why it is not what the verdict keys on.
    #
    # `self_persisted` answers the question the payload makes a claim about: did anything
    # THIS RUN wrote survive. Two readings, and each is something only this run could have
    # caused — the subject's own row (where beat 3's out-of-band UPDATE would show) and the
    # subject's own cr_event / merge_record counts (where an admitted merge would).
    identical = before == after
    counter_before = (before["change_request_row"] or {}).get("open_blocking")
    counter_after = (after["change_request_row"] or {}).get("open_blocking")
    self_evidence: dict[str, Any] = {
        "counter_forced_to": forced_counter,
        "counter_after_savepoint_rollback": counter_after_savepoint,
        "counter_before": counter_before,
        "counter_after_rollback": counter_after,
        "witness_written": forced_counter is not None,
        "subject_row_counts_before": before["subject_row_counts"],
        "subject_row_counts_after": after["subject_row_counts"],
        "change_request_row_identical": (
            before["change_request_row"] == after["change_request_row"]
        ),
    }
    self_persisted = (
        before["change_request_row"] != after["change_request_row"]
        or before["subject_row_counts"] != after["subject_row_counts"]
    )
    concurrent_writes = (
        None
        if identical
        else {
            table: [before["row_counts"][table], after["row_counts"][table]]
            for table in _FINGERPRINT_TABLES
            if before["row_counts"][table] != after["row_counts"][table]
        }
    )

    failures: list[str] = []
    if undecided is not None:
        failures.append(
            f"the transaction was UNDECIDED ({undecided.sqlstate}): {undecided.message}. "
            "That is not a refusal — the gate never got to say anything — and this driver "
            "does not re-send a merge on the caller's behalf."
        )
    for beat in beats:
        if undecided is not None and beat["outcome"] == "skipped":
            continue
        if not beat["matched_expectation"]:
            failures.append(
                f"beat {beat['ordinal']} ({beat['name']}): expected "
                f"{beat['expected']}, observed outcome={beat['outcome']!r} "
                f"sqlstate={beat['sqlstate']!r} constraint={beat['constraint']!r} "
                f"constraint_source={beat['constraint_source']!r}"
            )
    if self_persisted:
        failures.append(
            "this run PERSISTED something and the transaction was supposed to persist "
            f"nothing: the counter this run forced to {forced_counter} reads "
            f"{counter_after} after the rollback where it read {counter_before} before, "
            f"the subject's own row counts went {before['subject_row_counts']} → "
            f"{after['subject_row_counts']}, and its change_request row "
            f"{'is unchanged' if self_evidence['change_request_row_identical'] else 'MOVED'}"
        )

    return {
        "schema_id": CR_GATE_RUN_SCHEMA_ID,
        "run_id": run_id or str(uuid.uuid4()),
        "generated_at": generated_at,
        "outcome": "retry" if undecided is not None else "completed",
        "verdict": "PROVEN" if not failures else "NOT PROVEN",
        "failures": failures,
        "persisted": False,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "transaction": {
            "isolation": "SERIALIZABLE",
            "disposition": "rolled_back",
            "opened_logical_timestamp": opened_ts,
            "closed_logical_timestamp": closed_ts,
            # Constant within a CockroachDB transaction and moving between them. Equal
            # endpoints are a READ-ONLY witness that all three beats shared one
            # transaction — not an assertion this file makes about itself.
            "single_transaction": closed_ts is not None and closed_ts == opened_ts,
            "savepoints": [_BEAT_2_SAVEPOINT, _BEAT_3_SAVEPOINT],
            "retry_sqlstate": undecided.sqlstate if undecided is not None else None,
        },
        "subject": resolved.as_json(),
        "beats": beats,
        # ── THE TWO BEATS THIS RUN DOES NOT PLAY, DECLARED RATHER THAN OMITTED ────────
        # Both are null with a reason and the grant rows behind it. A reader can check
        # every sentence here against db/GRANTS.yaml without leaving the payload, which is
        # the difference between a stated absence and a silent one.
        "admission_beat": None,
        "admission_absent_reason": ADMISSION_ABSENT_REASON,
        "admission_absent_grants": list(ADMISSION_ABSENT_GRANTS),
        "admission_proved_by": ADMISSION_PROVED_BY,
        "kernel_procedure_beat": None,
        "kernel_procedure_absent_reason": KERNEL_PROCEDURE_ABSENT_REASON,
        "kernel_procedure_absent_sqlstate": KERNEL_PROCEDURE_ABSENT_SQLSTATE,
        "kernel_procedure_absent_grants": list(KERNEL_PROCEDURE_ABSENT_GRANTS),
        "persistence_check": {
            "before": before,
            "after": after,
            "identical": identical,
            "self_persisted": self_persisted,
            "self_evidence": self_evidence,
            "concurrent_writes": concurrent_writes,
            "tables": list(_FINGERPRINT_TABLES),
            "subject_tables": list(_CR_COUNT_TABLES),
            "note": (
                "The ten unscoped whole-table counts are gate_run's own list, imported "
                "rather than copied so no table can leave one and stay in the other. "
                "`identical` compares the WHOLE reading — those ten included — so it is "
                "false whenever any part of it moved, which any other caller writing into "
                "any of the ten can cause. Beside them, and never in place of them, two "
                "readings scoped to THIS change request — its cr_event and merge_record "
                "counts, and its own row by value, because the attack beat mutates a "
                "column without changing a count. `self_persisted` is those two, and it is "
                "what the verdict keys on. The run-scoped witness is the counter beat 3 "
                "forced to zero: a value this run wrote and no other caller did. It is "
                "undone twice — by beat 3's own ROLLBACK TO SAVEPOINT, read back as "
                "`counter_after_savepoint_rollback`, and again by the transaction's "
                "ROLLBACK, read back in `after` — and both readings are here so the "
                "strength of the claim is visible rather than asserted."
            ),
        },
    }
