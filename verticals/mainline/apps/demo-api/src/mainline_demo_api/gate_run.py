# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The demo, in one transaction that is rolled back: refuse, refuse under attack, admit.

``POST /v1/demo/gate-run`` plays four beats against the seeded permit and returns what the
DATABASE said at each one. It is the product's central claim reduced to a single HTTP call
a judge can make from a browser:

1. **The permit, with its open obligation.** Read-only. The projected counter and the
   re-derived count are both reported, side by side, because the difference between them
   is what beats 2 and 3 are about.
2. **MERGE → REFUSED.** ``23514`` on ``gate_closed_when_issued``, the constraint name
   REPORTED by the driver. A plain CHECK, doing what a CHECK does.
3. **THE PROJECTION-DRIFT ATTACK → REFUSED ANYWAY.** ``mainline.permit.open_blocking`` is
   forced to zero out of band — exactly what a disarmed projector or a careless ``UPDATE``
   leaves behind — and the merge is attempted again. It refuses with ``P0001`` naming
   ``mainline.fn_permit_merge_gate``, because the gate **re-derives** the count from
   ``blocking_check`` LEFT JOIN ``disposition`` instead of trusting the column. This is
   the beat that distinguishes the product from a CHECK constraint, and it is the reason
   rule P-2 says a projection is *enforced, never trusted*.
4. **SIGN ONE DISPOSITION → ADMITTED.** ``00000``, a ``merge_record`` row, and a
   ``clearance_digest`` the SERVER computed over the (check, disposition) set. *A gate that
   always refuses is broken, not safe*, and this beat is the only thing that proves ours is
   not.

WHERE BEAT 4's CREDENTIAL IDS COME FROM
---------------------------------------
``signer_credential_id`` and ``countersigner_credential_id`` are FOREIGN KEYS onto
``mainline.signing_credential``. This module used to DERIVE them —
``sha256(b"cred" + b"signer")`` — while ``db/seeds/demo/demo_world.sql`` enrolled
``digest('mainline-demo/credential/demo.signer','sha256')``, so beat 4 failed
``23503 disposition_signer_credential_id_fkey`` against the database that is actually
deployed and the run answered ``200`` carrying its own verdict as ``NOT PROVEN``. They are
now READ from the table that owns them, by ``signer_sub``, through
:func:`mainline_demo_api.credentials.resolve_credential_id` — and read BEFORE the beats'
transaction is opened, so a subject with no enrolled credential is a typed refusal that
names the subject and the table (``422 demo_history_not_seeded``) rather than a foreign-key
violation caught inside beat 4's savepoint and reported as though the GATE had spoken. It
had not; nothing about the product is demonstrated by a missing row. See
``credentials.py``'s module docstring for why resolving beats deriving in every seed this
demo can meet.

WHERE BEAT 4's DEFEATER VOCABULARY COMES FROM
----------------------------------------------
``defeater_vocab_sha256`` is the digest of the option set the signer was SHOWN.
``db/migrations/0064_defeater_option.sql``: it *"digests the whole option set, not the row,
so a signature that pins it pins the ALTERNATIVES the signer declined as well as the one
they chose"*. Until 2026-08-14 this beat bound ``_sha("defeater-vocab")`` —
``sha256(b"defeater-vocab")``, the SHA-256 of an ASCII string — and the deployed
CockroachDB Cloud recorded that constant on its one signed disposition
(``console/fixtures/bundles/demo-cloud/frames/GET-f116fc2724f1b968.json``,
``signed.defeater_vocab_sha256``). So the demo's signature pinned nothing, and would have
gone on pinning nothing after the vocabulary rows landed: seeding the options without
closing this moves the visible half of the defect and leaves the invisible half.

The digest is now RESOLVED from ``mainline.defeater_option`` through
:func:`mainline_demo_api.defeaters.resolve_defeater_vocabulary`, in the same read-only
transaction as the credentials and for the same reason, and the code this beat signs with
is checked for MEMBERSHIP of the set that was offered. There is no foreign key from
``mainline.disposition`` onto ``mainline.defeater_option`` — ``0066_disposition.sql``
carries only ``CONSTRAINT disposition_defeater_code_stated CHECK (defeater_code <> '')`` —
so nothing in the database would notice a signature naming a code no screen ever showed.
That check is made here or it is not made at all.

WHY IT PERSISTS NOTHING, AND WHY THAT IS NOT A COMPROMISE
---------------------------------------------------------
All four beats run inside ONE ``SERIALIZABLE`` transaction. Each write beat is fenced by
``SAVEPOINT`` / ``ROLLBACK TO SAVEPOINT``, so a constraint refusal undoes its own beat
without killing the transaction, and the whole transaction is ``ROLLBACK``-ed at the end —
including the beat that SUCCEEDED. Measured on CockroachDB v26.2.5 before a line of this
file was written (``evidence/deploy/lead/savepoint-probe-20260810.txt``, and again by this
worker's tests).

That single decision removes the entire class of problems a public demo usually has.
There is no per-visitor state, no reset button, no session table, no cleanup sweeper and
no lock. Fifty judges can press the button at the same time and each sees the same four
beats against the same seeded history, because none of them changed it. The payload says
``persisted: false`` and then **proves it**: a fingerprint of the affected tables is taken
before the transaction opens and again after it closes, and both are in the response.

That fingerprint is TEN UNSCOPED WHOLE-TABLE COUNTS, on purpose, and it stays that way —
``contracts/gate-run.schema.json`` asks for the broad check and gives the reason. What it
cannot do on its own is tell *"I persisted something"* from *"somebody else did"*, and
until 2026-08-14 the difference was reported as this endpoint's own failure: one row
committed by any other caller into any of those ten tables, between the two readings, made
the run answer ``NOT PROVEN`` carrying the sentence *"the transaction was supposed to
persist nothing"* — about a transaction that had persisted nothing. So the run now also
asks a question only IT can answer: the ``uuid4`` beat 4 minted for its disposition is a
value no other writer holds, and after the rollback it is gone, and this subject's own row
counts and permit row are unchanged. ``identical`` still reports the ten counts; the
VERDICT keys on the run-scoped evidence. Neither reading was narrowed and no table left
the list — see ``docs/diagnosis/gate-run-fingerprint.md`` for the reproduction that
identified the writer, and ``docs/deploy/gate-run-contract.md`` §3 for the argument, made
under ``docs/leads/cloud-hardening-final.md`` ruling **R2**, which is what permits the
contract to move at all.

The claim that the four beats really did share one transaction is also proved rather than
asserted. ``cluster_logical_timestamp()`` is constant within a CockroachDB transaction and
moves between them, so it is captured at the first beat and after the last; equal values
are a read-only witness that no beat quietly opened a transaction of its own.

WHAT THIS MODULE WILL NOT DO
----------------------------
It will not retry. ``40001`` aborts the run, is reported as ``outcome: "retry"`` with the
beats completed so far, and the caller decides. A driver that re-sent the merge because a
socket closed is a driver that can issue a permit twice.

One call to this function is therefore exactly one attempt, and that is what makes it a
legitimate retryable unit ONE LEVEL UP: ``transitions._demo_gate_run`` re-runs the whole
function under :func:`mainline_demo_api.retry.run_transaction` when it comes back
undecided, which ``spec/errors.md`` §2.1 permits precisely because the unit re-run is the
whole transaction from ``BEGIN`` and not a statement replayed into a poisoned one. Nothing
here re-sends a statement, and nothing here decides on the caller's behalf; the sentence
above is unchanged, and the paragraph it sits in is why re-running is safe at all — this
run persists nothing, so a second attempt asks the same question of the same rows.

It will not compose a message. Every ``sqlstate``, ``constraint`` and ``message`` in the
response comes out of the driver's error object through
:func:`mainline_demo_api.refusal.diagnose`; every reason set comes out of
``trappoint.explain_refusal``.

It will not declare a beat successful because it did not raise. Each beat carries the
expectation it was written against and a ``matched_expectation`` boolean, and the run's
``verdict`` is ``PROVEN`` only when every beat matched. A demo that reported ``ADMITTED``
where it expected ``REFUSED`` would still return 200; it would say ``NOT PROVEN``, and
saying so is the whole discipline.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Final

import psycopg
from psycopg.types.json import Jsonb

from .credentials import resolve_credential_id
from .defeaters import resolve_defeater_vocabulary
from .refusal import Diagnosis, classify, diagnose, refusal_payload, rfc3339
from .scenario import ResolvedScenario, Scenario, positional, resolve

__all__ = [
    "ADMISSION_SQLSTATE",
    "CF01_EXHIBIT",
    "CF01_SQLSTATE",
    "CF03_EXHIBIT",
    "CF03_SQLSTATE",
    "DEMO_DEFEATER_CODE",
    "GATE_RUN_SCHEMA_ID",
    "canonical_json",
    "gate_run",
]

#: The contract this module's payload satisfies. Governs `contracts/gate-run.schema.json`.
GATE_RUN_SCHEMA_ID: Final = (
    "https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json"
)

#: `spec/conformance/manifest.toml` group 1, and the two rows this demo exists to show.
CF01_SQLSTATE: Final = "23514"
CF01_EXHIBIT: Final = "gate_closed_when_issued"
CF03_SQLSTATE: Final = "P0001"
CF03_EXHIBIT: Final = "mainline.fn_permit_merge_gate"
ADMISSION_SQLSTATE: Final = "00000"

_MERGE_SQL: Final = "CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)"

_FORCE_SQL: Final = "UPDATE mainline.permit SET open_blocking = 0 WHERE permit_id = %s"

#: The defeater the demo's one signature names, and the only thing about the vocabulary
#: this module states rather than reads.
#:
#: It is the demo's authored answer to the obligation — the recalled precursor
#: ``DEMO-INC-0001`` is answered by a verified zero-energy isolation procedure, which is
#: what :data:`_RATIONALE` says in prose — and it is the code the deployed Cloud recorded
#: on its ADMITTED merge (``demo-cloud/sql/beat-4-merge-admitted-00000.txt``, and
#: ``GET-f116fc2724f1b968.json``'s ``signed.defeater_code``). It is a CHOICE, not a digest,
#: which is why it may be stated here at all: what a signer picks is theirs, and 0064 puts
#: exactly four things in the signer's gift — the kind, the defeater code, the rationale
#: and the signature.
#:
#: Stating it does not make it legal. It is checked for membership of the vocabulary the
#: database actually offers, before the beats' transaction opens, and the run refuses if
#: this check never offered it. A hard-coded code that nothing verified is precisely the
#: *"click-through with a signature on it"* 0064's rationale exists to forbid, and it was
#: hard-coded into the statement below — unverifiable, because a literal inside a
#: statement cannot be compared with anything — until 2026-08-14.
DEMO_DEFEATER_CODE: Final = "MECHANISM_PRESENT_AND_VERIFIED"

#: Every column on this row except the four a signer actually chooses is PROJECTED by
#: `fn_disposition_project` from authoritative rows and the values supplied here are
#: overwritten (invariant I02). The subject, the site, the virulence, the clearance
#: requirements, the signer's rank and organisation, the competency snapshot and the
#: reading-floor verdict are all read from elsewhere. What the signer chooses is the KIND,
#: the defeater code, the rationale and the signature.
_DISPOSITION_SQL: Final = """
INSERT INTO mainline.disposition (
  disposition_id, check_id, receipt_id, subject_kind, permit_id, site_id, kind, virulence,
  closure_gen, defeater_code, defeater_vocab_sha256, rationale, evidence_sha256, signer_sub,
  signer_rank, signer_org, signer_credential_id, countersigner_sub,
  countersigner_credential_id, signature_alg, authenticator_data, client_data_json,
  user_verified, competency_snapshot, competency_source_id, competency_sha256,
  req_compensating, req_second_signer, req_foreign_org, req_predicate, req_reassert,
  min_signer_rank, severity_snapshot, deliberation_seconds, evidence_opened,
  prior_override_count)
VALUES (%s, %s, %s, 'permit', %s, %s, 'applied', 'routine', 0,
        %s, %s, %s, %s, %s, 1, 'x', %s, %s, %s, 'ES256',
        %s, %s, true, %s, %s, %s, false, false, false, false, false, 1, 0, 0, true, 0)
"""

#: Read by POSITION, through :func:`scenario.positional`, and it has to be: CockroachDB
#: names both ``encode(...)`` columns ``encode``, so a dict row keeps six of these seven
#: values and drops one without saying which.
_MERGE_RECORD_SQL: Final = """
SELECT encode(m.clearance_digest, 'hex'),
       encode(m.merged_commit, 'hex'),
       m.gate_epoch,
       m.merged_at,
       p.state::STRING,
       p.open_blocking,
       p.head_seq
  FROM mainline.merge_record m
  JOIN mainline.permit p ON p.permit_id = m.permit_id
 WHERE m.subject_id = %s
"""

#: The tables the four beats can write, counted before the transaction opens and after it
#: closes. Scoped rather than exhaustive on purpose: counting all 89 tables would cost 89
#: round trips to prove something about ten of them, and the ten are the ten a merge, a
#: disposition and a forced counter can touch. `mainline.permit` is compared by VALUE as
#: well as by count, because the attack beat mutates a column without changing a count.
_FINGERPRINT_SQL: Final = """
SELECT (SELECT count(*) FROM mainline.permit),
       (SELECT count(*) FROM mainline.permit_event),
       (SELECT count(*) FROM mainline.merge_record),
       (SELECT count(*) FROM mainline.disposition),
       (SELECT count(*) FROM mainline.ledger_intake),
       (SELECT count(*) FROM mainline.refusal_ledger),
       (SELECT count(*) FROM mainline.blocking_check),
       (SELECT count(*) FROM mainline.exposure_receipt),
       (SELECT count(*) FROM mainline.exposure_line),
       (SELECT count(*) FROM mainline_ops.outbox)
"""

_FINGERPRINT_TABLES: Final[tuple[str, ...]] = (
    "mainline.permit",
    "mainline.permit_event",
    "mainline.merge_record",
    "mainline.disposition",
    "mainline.ledger_intake",
    "mainline.refusal_ledger",
    "mainline.blocking_check",
    "mainline.exposure_receipt",
    "mainline.exposure_line",
    "mainline_ops.outbox",
)

#: THE SAME QUESTION, ASKED OF THE SUBJECT THIS RUN DROVE — added BESIDE the ten unscoped
#: counts above and never in place of them.
#:
#: The ten counts prove something about the DATABASE. This statement proves something about
#: the RUN, and the two are different claims that were being read as one. A whole-table
#: count cannot distinguish *"I persisted something"* from *"somebody else did"*, so any
#: caller committing a row into any of those ten tables between the two readings made this
#: endpoint answer ``NOT PROVEN`` and accuse itself, in the payload, of a write it had not
#: made. Measured, and reproduced deliberately, in ``docs/diagnosis/gate-run-fingerprint.md``.
#:
#: These three tables are the only ones the four beats can write a row into *and have it
#: survive*: beat 4 inserts one ``mainline.disposition`` and then calls
#: ``mainline.merge_permit``, which writes ``merge_record`` and ``permit_event`` for this
#: permit. Beats 2 and 3 were REFUSED — the database wrote nothing to refuse — and beat 3's
#: out-of-band ``UPDATE`` shows up in ``_PERMIT_ROW_SQL``'s column values below, which is
#: the reading the schema keeps for exactly that reason.
_SUBJECT_COUNTS_SQL: Final = """
SELECT (SELECT count(*) FROM mainline.merge_record WHERE permit_id = %s),
       (SELECT count(*) FROM mainline.permit_event WHERE permit_id = %s),
       (SELECT count(*) FROM mainline.disposition  WHERE permit_id = %s)
"""

_SUBJECT_COUNT_TABLES: Final[tuple[str, ...]] = (
    "mainline.merge_record",
    "mainline.permit_event",
    "mainline.disposition",
)

#: The sharpest evidence this run can offer, because it is the only identifier in the whole
#: transaction that NOBODY ELSE COULD HAVE PRODUCED: the ``uuid4`` beat 4 minted for its
#: disposition. Beat 4 is the one beat the database ACCEPTED, and every other row it causes
#: is written by ``mainline.merge_permit`` in the same transaction as that disposition — so
#: if this row is gone, that transaction did not commit and none of its other rows are here
#: either. One statement, and it settles the whole claim.
_MINTED_DISPOSITION_SQL: Final = (
    "SELECT count(*) FROM mainline.disposition WHERE disposition_id = %s"
)

_PERMIT_ROW_SQL: Final = """
SELECT state::STRING, head_seq, gate_epoch, open_blocking, unmet_floor_count,
       countersigned_count, encode(merged_commit, 'hex')
  FROM mainline.permit WHERE permit_id = %s
"""

_RATIONALE: Final = (
    "The recalled precursor is answered by a verified zero-energy isolation procedure "
    "re-issued after the incident, and this permit's scope is covered by that procedure "
    "in full. Verification at zero is witnessed and recorded before any intrusive work "
    "begins, so the mechanism the incident found missing is present and exercised here."
)


# ═══════════════════════════════════════════════════════════════════════════════════════
# canonicalisation
# ═══════════════════════════════════════════════════════════════════════════════════════


def canonical_json(payload: dict[str, Any]) -> tuple[bytes, str]:
    """Return ``(canonical_bytes, implementation)`` for the merge payload.

    ``mainline.merge_permit`` takes ``a_canon_bytes`` and ``a_leaf_hash`` from the CLIENT,
    and 0117's header says why: SQL cannot canonicalise to RFC 8785, CockroachDB's own
    JSONB key ordering is not reproducible by a third party, and a server-computed leaf
    would be a hash nobody outside the cluster could recheck — the opposite of what a
    custody ledger is for.

    ``trappoint_jcs`` is the repository's authority and is used when it imports. The
    fallback is ``json.dumps(sort_keys=True, separators=(",", ":"))``, which coincides
    with RFC 8785 for the ASCII strings and small integers this payload actually contains
    and is NOT a general JCS implementation. Which one ran is returned, and travels in the
    response — a digest whose derivation is unstated is a digest nobody can recompute.
    """
    try:
        from trappoint_jcs import canonicalise
    except ImportError:
        return (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            ),
            "mainline_demo_api.gate_run.canonical_json (sorted-key JSON; ASCII payloads only)",
        )
    canon = canonicalise(payload)
    canon_bytes = canon if isinstance(canon, bytes) else str(canon).encode("utf-8")
    return canon_bytes, "trappoint_jcs.canonicalise"


def _leaf(canon: bytes) -> bytes:
    import hashlib

    return hashlib.sha256(b"\x00" + canon).digest()


def _sha(*parts: bytes | str) -> bytes:
    import hashlib

    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8") if isinstance(part, str) else part)
    return digest.digest()


# ═══════════════════════════════════════════════════════════════════════════════════════
# the run
# ═══════════════════════════════════════════════════════════════════════════════════════


def _logical_timestamp(conn: psycopg.Connection[Any]) -> str:
    """Read CockroachDB's transaction-scoped logical clock.

    Constant within a transaction and monotonic between them, which is what makes it a
    read-only witness that the four beats shared one transaction rather than a claim this
    module makes about itself.
    """
    row = positional(conn, "SELECT cluster_logical_timestamp()::STRING").fetchone()
    if row is None:  # pragma: no cover - a scalar SELECT always returns a row
        raise RuntimeError("cluster_logical_timestamp() returned no row")
    return str(row[0])


class _Undecided(Exception):
    """``40001`` — the transaction is undecided and the run cannot continue."""

    def __init__(self, diagnosis: Diagnosis) -> None:
        super().__init__(diagnosis.message)
        self.diagnosis = diagnosis


def _fingerprint(conn: psycopg.Connection[Any], permit_id: uuid.UUID) -> dict[str, Any]:
    counts = positional(conn, _FINGERPRINT_SQL).fetchone()
    if counts is None:  # pragma: no cover - ten scalar subqueries always return one row
        raise RuntimeError("the fingerprint statement returned no row")
    subject = positional(conn, _SUBJECT_COUNTS_SQL, (permit_id, permit_id, permit_id)).fetchone()
    if subject is None:  # pragma: no cover - three scalar subqueries always return one row
        raise RuntimeError("the subject-scoped statement returned no row")
    row = positional(conn, _PERMIT_ROW_SQL, (permit_id,)).fetchone()
    return {
        # strict=True: `_FINGERPRINT_TABLES` and the statement's ten subqueries are one
        # list written twice, and a zip that truncated silently would report a persistence
        # check over FEWER tables than the payload claims. CockroachDB names all ten of
        # those columns `count`, so a dict row collapses them to one — measured, and the
        # reason this pair is now guarded rather than merely converted.
        "row_counts": {name: int(n) for name, n in zip(_FINGERPRINT_TABLES, counts, strict=True)},
        # strict=True for the same reason as above, and this reading is what makes the one
        # above answerable: it counts the SAME tables for THIS permit only, so a delta here
        # is this run's and a delta only up there is somebody else's.
        "subject_row_counts": {
            name: int(n) for name, n in zip(_SUBJECT_COUNT_TABLES, subject, strict=True)
        },
        "permit_row": (
            None
            if row is None
            else {
                "state": row[0],
                "head_seq": int(row[1]),
                "gate_epoch": int(row[2]),
                "open_blocking": int(row[3]),
                "unmet_floor_count": int(row[4]),
                "countersigned_count": int(row[5]),
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


def _call_merge(conn: psycopg.Connection[Any], resolved: ResolvedScenario) -> str:
    sc = resolved.scenario
    payload = {
        "permit": str(sc.permit_id),
        "merged_by": sc.signer_sub,
        "source": "POST /v1/demo/gate-run",
    }
    canon, impl = canonical_json(payload)
    conn.execute(
        _MERGE_SQL,
        (
            sc.permit_id,
            sc.merged_commit,
            sc.signer_sub,
            "human",
            Jsonb(payload),
            canon,
            1,
            _leaf(canon),
        ),
    )
    return impl


def _record_refusal(
    conn: psycopg.Connection[Any],
    beat: dict[str, Any],
    exc: psycopg.Error,
    resolved: ResolvedScenario,
    attempt: dict[str, Any],
) -> None:
    """Fill *beat* from the driver's error object. Raises :class:`_Undecided` on 40001."""
    found = diagnose(exc)
    kind = classify(found)
    if kind == "retry":
        raise _Undecided(found)

    beat["sqlstate"] = found.sqlstate or None
    beat["constraint"] = found.constraint or None
    beat["constraint_source"] = found.constraint_source
    beat["message"] = found.message

    if kind != "refused":
        beat["outcome"] = "error"
        beat["note"] = (
            f"{found.sqlstate or '(no sqlstate)'} is outside the refusal taxonomy "
            "(23514, 23503, 23505, P0001) or carried no exhibit. spec/errors.md §1.1 "
            "makes that a defect to be reported, not an edge case to be smoothed over."
        )
        return

    beat["outcome"] = "refused"
    beat["refusal"] = refusal_payload(
        conn,
        found,
        subject_kind="permit",
        subject_id=str(resolved.permit_id),
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


def gate_run(  # noqa: PLR0912, PLR0915 — one straight line of four beats; splitting it
    # into per-beat helpers would hide the ORDER, and the order is the argument.
    conn: psycopg.Connection[Any],
    scenario: Scenario | None = None,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Play the four beats against *conn* and roll everything back.

    Args:
        conn: a psycopg connection. Must not be in autocommit — the whole point is one
              transaction — and is left with no transaction in progress on return.
        scenario: the identifiers to drive. Defaults to :func:`scenario.from_env`.
        run_id: identifier for this run. Minted when absent.

    Returns:
        The payload governed by ``contracts/gate-run.schema.json``.

    Raises:
        ScenarioNotSeeded: the demo history is not in this database. Distinct from every
            outcome above: "there was nothing to ask" is not "the gate did not refuse".
        CredentialNotEnrolled: no unrevoked credential is enrolled for the signer or the
            countersigner. A ``ScenarioNotSeeded``, and raised before the beats' transaction
            opens, so an unenrolled subject costs a 422 that names it rather than a 23503
            inside beat 4 dressed up as a refusal the gate never made.
        CredentialAmbiguous: a subject holds several live credentials and a disposition
            names one.
        DefeaterVocabularyAbsent: the open obligation offers no defeater options, so beat
            4's signature could not pin the vocabulary it was chosen from. Also a
            ``ScenarioNotSeeded``, also raised before the beats' transaction opens.
        DefeaterVocabularyAmbiguous: the obligation's options carry more than one distinct
            digest, which 0064 says cannot be true of one generation.
        DefeaterNotOffered: the obligation offers a vocabulary and
            :data:`DEMO_DEFEATER_CODE` is not in it. A ``ValueError``, which
            ``handle_transition`` answers with ``422 unprocessable_request``.
    """
    if conn.autocommit:
        raise ValueError(
            "gate_run needs a connection that is NOT in autocommit: the four beats share "
            "one transaction, and that is the property the demo is showing."
        )

    started = time.perf_counter()
    generated_at = rfc3339(datetime.now(UTC))
    conn.rollback()  # a clean slate, whatever the caller left behind

    # ── BEFORE. Read in a transaction of its own, which is then rolled back, so that the
    #    fingerprint is the COMMITTED state rather than anything the beats can see.
    #    `resolve` raises ScenarioNotSeeded here, before a transaction has been opened for
    #    the beats — so a wrong database costs a 422, not a dangling transaction.
    opening = resolve(conn, scenario)
    before = _fingerprint(conn, opening.permit_id)

    #    THE TWO CREDENTIAL IDS BEAT 4 SIGNS WITH ARE RESOLVED HERE, IN THIS SAME READ-ONLY
    #    TRANSACTION, FOR THE SAME REASON. They are foreign keys onto
    #    `mainline.signing_credential` and this module does not derive them; a subject with
    #    no enrolled credential is a PRECONDITION that fails, and it fails while there is
    #    still nothing to roll back. Resolving them inside beat 4 instead would turn a
    #    missing row into `23503 disposition_signer_credential_id_fkey`, caught by the
    #    savepoint, diagnosed by `refusal.diagnose` and reported as a refusal — an exhibit
    #    the gate never produced, on a run that would still answer 200.
    signer_credential_id = resolve_credential_id(conn, opening.scenario.signer_sub)
    countersigner_credential_id = resolve_credential_id(conn, opening.scenario.countersigner_sub)

    #    AND SO IS THE DEFEATER VOCABULARY BEAT 4 PINS, for a reason that is the mirror
    #    image rather than a copy. A missing credential at least FAILS — `23503`, in the
    #    wrong place and dressed as a refusal, but visibly. A missing vocabulary fails
    #    nowhere: `mainline.disposition` has no foreign key onto `mainline.defeater_option`,
    #    so a signature over an option set that does not exist commits, admits, and reports
    #    `PROVEN`. That is why this read is a PRECONDITION and not an expectation: the only
    #    place the condition can be caught is before anything is signed.
    #
    #    Read for `opening.check_id` — the obligation as the committed state has it — and
    #    carried into beat 4, which re-reads the permit inside its own transaction and is
    #    checked below for having found the same obligation.
    vocabulary = (
        resolve_defeater_vocabulary(conn, opening.check_id)
        if opening.check_id is not None
        else None
    )
    if vocabulary is not None:
        vocabulary.require(DEMO_DEFEATER_CODE)
    conn.rollback()

    conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    opened_ts = _logical_timestamp(conn)
    resolved = resolve(conn, scenario)

    beats: list[dict[str, Any]] = [
        _beat(
            1,
            "read",
            "The permit, and the obligation that is still open on it.",
            outcome="read",
        ),
        _beat(
            2,
            "merge",
            "MERGE the permit. One open obligation, no signed disposition.",
            outcome="refused",
            sqlstate=CF01_SQLSTATE,
            constraint=CF01_EXHIBIT,
            constraint_source="reported",
        ),
        _beat(
            3,
            "projection_drift_attack",
            "THE ATTACK: force the projected counter to zero out of band, then merge again.",
            outcome="refused",
            sqlstate=CF03_SQLSTATE,
            constraint=CF03_EXHIBIT,
            constraint_source="parsed",
        ),
        _beat(
            4,
            "admit",
            "Sign one disposition against the obligation, then merge again.",
            outcome="admitted",
            sqlstate=ADMISSION_SQLSTATE,
        ),
    ]
    undecided: Diagnosis | None = None
    canon_impl = "not reached"
    #: The identifier beat 4 mints, hoisted so the persistence check below can ask the
    #: database for it after the rollback. Stays ``None`` when beat 4 never ran.
    minted_disposition_id: uuid.UUID | None = None

    try:
        # ── BEAT 1 · THE PERMIT ─────────────────────────────────────────────────────
        mark = time.perf_counter()
        beats[0]["outcome"] = "read"
        beats[0]["sqlstate"] = ADMISSION_SQLSTATE
        beats[0]["statement"] = "SELECT … FROM mainline.permit JOIN mainline.site …"
        beats[0]["observed"] = {
            "state": resolved.state,
            "gate_epoch": resolved.gate_epoch,
            "head_seq": resolved.head_seq,
            "open_blocking_projected": resolved.open_blocking,
            "open_blocking_derived": resolved.open_derived,
            "blocking_check_id": str(resolved.check_id) if resolved.check_id else None,
            "counters_agree": resolved.open_blocking == resolved.open_derived,
        }
        beats[0]["elapsed_ms"] = round((time.perf_counter() - mark) * 1000, 3)
        _match(beats[0])

        # ── BEAT 2 · THE REFUSAL ────────────────────────────────────────────────────
        mark = time.perf_counter()
        beats[1]["statement"] = _MERGE_SQL
        conn.execute("SAVEPOINT gate_run_beat_2")
        try:
            canon_impl = _call_merge(conn, resolved)
        except psycopg.Error as exc:
            conn.execute("ROLLBACK TO SAVEPOINT gate_run_beat_2")
            _record_refusal(
                conn,
                beats[1],
                exc,
                resolved,
                {"kind": "merge", "gate_epoch": resolved.gate_epoch},
            )
        else:
            conn.execute("ROLLBACK TO SAVEPOINT gate_run_beat_2")
            beats[1]["outcome"] = "admitted"
            beats[1]["sqlstate"] = ADMISSION_SQLSTATE
            beats[1]["note"] = (
                "the merge was ADMITTED with an open obligation — the gate did not hold"
            )
        conn.execute("RELEASE SAVEPOINT gate_run_beat_2")
        beats[1]["elapsed_ms"] = round((time.perf_counter() - mark) * 1000, 3)
        _match(beats[1])

        # ── BEAT 3 · THE PROJECTION-DRIFT ATTACK ────────────────────────────────────
        mark = time.perf_counter()
        beats[2]["statement"] = f"{_FORCE_SQL}; {_MERGE_SQL}"
        conn.execute("SAVEPOINT gate_run_beat_3")
        try:
            conn.execute(_FORCE_SQL, (resolved.permit_id,))
            forced = positional(
                conn,
                "SELECT open_blocking FROM mainline.permit WHERE permit_id = %s",
                (resolved.permit_id,),
            ).fetchone()
            beats[2]["observed"] = {
                "counter_forced_to": int(forced[0]) if forced else None,
                "open_blocking_derived": resolved.open_derived,
                "attack": (
                    "mainline.permit.open_blocking set out of band — what a disarmed "
                    "projector or a careless UPDATE leaves behind"
                ),
            }
            _call_merge(conn, resolved)
        except psycopg.Error as exc:
            conn.execute("ROLLBACK TO SAVEPOINT gate_run_beat_3")
            _record_refusal(
                conn,
                beats[2],
                exc,
                resolved,
                {"kind": "merge", "gate_epoch": resolved.gate_epoch},
            )
        else:
            conn.execute("ROLLBACK TO SAVEPOINT gate_run_beat_3")
            beats[2]["outcome"] = "admitted"
            beats[2]["sqlstate"] = ADMISSION_SQLSTATE
            beats[2]["note"] = (
                "the merge was ADMITTED against a forged counter — the gate trusted its "
                "own projection, which is the one thing it must never do"
            )
        conn.execute("RELEASE SAVEPOINT gate_run_beat_3")
        beats[2]["elapsed_ms"] = round((time.perf_counter() - mark) * 1000, 3)
        _match(beats[2])

        # ── BEAT 4 · THE ADMISSION ──────────────────────────────────────────────────
        mark = time.perf_counter()
        beats[3]["statement"] = f"{' '.join(_DISPOSITION_SQL.split())}; {_MERGE_SQL}"
        if resolved.check_id is None or resolved.receipt_id is None:
            beats[3]["outcome"] = "skipped"
            beats[3]["note"] = (
                "no open obligation with a live exposure receipt on this permit, so there "
                "is nothing to sign a disposition against. A disposition's composite "
                "foreign key lands on (check_id, receipt_id); the API does not fabricate "
                "either."
            )
        elif vocabulary is None or vocabulary.check_id != resolved.check_id:
            # The obligation moved between the read-only opening and this transaction, so
            # the vocabulary resolved above belongs to a different check. Signing anyway
            # would record the digest of one obligation's option set against another's —
            # the exact silent reinterpretation `disposition.schema.json` says the digest
            # exists to prevent — and nothing in the database would refuse it. Beat 4 is
            # skipped and says so; a run that cannot pin what it signed proves nothing,
            # and reporting it as ADMITTED would be the fabricated exhibit.
            beats[3]["outcome"] = "skipped"
            beats[3]["note"] = (
                "the open obligation changed between the opening read and the beats' "
                f"transaction: the defeater vocabulary was resolved for "
                f"{vocabulary.check_id if vocabulary else None} and this transaction found "
                f"{resolved.check_id}. A disposition pins the digest of the option set its "
                "own check offered, so this run will not sign one it cannot pin. Re-run; "
                "this demo persists nothing, so nothing is left half-done."
            )
        else:
            conn.execute("SAVEPOINT gate_run_beat_4")
            disposition_id = uuid.uuid4()
            minted_disposition_id = disposition_id
            try:
                conn.execute(
                    _DISPOSITION_SQL,
                    (
                        disposition_id,
                        resolved.check_id,
                        resolved.receipt_id,
                        resolved.permit_id,
                        resolved.scenario.site_id,
                        # The code, and then the digest of the set it was chosen FROM. Both
                        # come from `mainline.defeater_option`: the digest is read off the
                        # rows and the code was checked for membership of them before this
                        # transaction opened. Neither is computed here, and there is no
                        # constant to fall back to — see the module docstring for the one
                        # that used to be here and what it pinned.
                        DEMO_DEFEATER_CODE,
                        vocabulary.vocab_sha256,
                        _RATIONALE,
                        _sha("evidence", str(disposition_id)),
                        resolved.scenario.signer_sub,
                        # Read from `mainline.signing_credential` before this transaction
                        # opened; see the module docstring. Never derived here — the table
                        # owns the value and the foreign key says so.
                        signer_credential_id,
                        resolved.scenario.countersigner_sub,
                        countersigner_credential_id,
                        _sha("authenticator", str(disposition_id)),
                        canonical_json({"challenge": disposition_id.hex, "type": "webauthn.get"})[
                            0
                        ],
                        Jsonb({"authorisations": ["ISOLATION_AUTHORITY"]}),
                        uuid.uuid4(),
                        _sha("competency", resolved.scenario.signer_sub),
                    ),
                )
                closed = positional(
                    conn,
                    "SELECT open_blocking FROM mainline.permit WHERE permit_id = %s",
                    (resolved.permit_id,),
                ).fetchone()
                canon_impl = _call_merge(conn, resolved)
            except psycopg.Error as exc:
                conn.execute("ROLLBACK TO SAVEPOINT gate_run_beat_4")
                _record_refusal(
                    conn,
                    beats[3],
                    exc,
                    resolved,
                    {
                        "kind": "applied",
                        "check_id": str(resolved.check_id),
                        "gate_epoch": resolved.gate_epoch,
                    },
                )
            else:
                record = positional(conn, _MERGE_RECORD_SQL, (resolved.permit_id,)).fetchone()
                beats[3]["outcome"] = "admitted"
                beats[3]["sqlstate"] = ADMISSION_SQLSTATE
                beats[3]["observed"] = {
                    "disposition_id": str(disposition_id),
                    "disposition_kind": "applied",
                    "open_blocking_after_signature": int(closed[0]) if closed else None,
                    "merge_record": (
                        None
                        if record is None
                        else {
                            "clearance_digest": record[0],
                            "merged_commit": record[1],
                            "gate_epoch": int(record[2]),
                            "merged_at": record[3].astimezone(UTC).isoformat(),
                            "permit_state": record[4],
                            "permit_open_blocking": int(record[5]),
                            "permit_head_seq": int(record[6]),
                        }
                    ),
                }
                conn.execute("ROLLBACK TO SAVEPOINT gate_run_beat_4")
            conn.execute("RELEASE SAVEPOINT gate_run_beat_4")
        beats[3]["elapsed_ms"] = round((time.perf_counter() - mark) * 1000, 3)
        _match(beats[3])

        closed_ts = _logical_timestamp(conn)
    except _Undecided as stop:
        undecided = stop.diagnosis
        closed_ts = None
    finally:
        # THE WHOLE TRANSACTION GOES BACK, including the beat that succeeded. This line is
        # the demo's contract with every judge who presses the button after this one.
        conn.rollback()

    after = _fingerprint(conn, resolved.permit_id)
    minted_survived = 0
    if minted_disposition_id is not None:
        found = positional(conn, _MINTED_DISPOSITION_SQL, (minted_disposition_id,)).fetchone()
        minted_survived = int(found[0]) if found else 0
    conn.rollback()

    # ── WHAT THE TWO READINGS EACH PROVE, AND WHY THEY ARE NO LONGER ONE SENTENCE ──────
    #
    # `identical` is the ten unscoped counts and the permit row, unchanged and still taken
    # over every table the four beats can write. It answers "did the database move".
    #
    # `self_persisted` answers the question the payload actually makes a claim about: "did
    # anything THIS RUN wrote survive". The two were the same sentence until 2026-08-14,
    # and the difference between them is a defect a judge could meet: any other caller
    # committing one row into any of those ten tables between the two readings made this
    # endpoint answer NOT PROVEN and print "the transaction was supposed to persist
    # nothing" — about a transaction that had persisted nothing. Measured, reproduced and
    # ruled on in `docs/diagnosis/gate-run-fingerprint.md`; the contract change is argued
    # in `docs/deploy/gate-run-contract.md` §3 under `docs/leads/cloud-hardening-final.md`
    # ruling R2, which forbids narrowing the ten counts and this does not narrow them.
    #
    # Three things are asked, and each is something only this run could have caused:
    #   * the disposition beat 4 MINTED is present — a uuid4 no other writer holds;
    #   * this permit's own merge_record / permit_event / disposition counts moved;
    #   * this permit's row itself moved — where beat 3's out-of-band UPDATE would show.
    identical = before == after
    self_evidence = {
        "minted_disposition_id": (
            None if minted_disposition_id is None else str(minted_disposition_id)
        ),
        "minted_disposition_rows_after_rollback": minted_survived,
        "subject_row_counts_before": before["subject_row_counts"],
        "subject_row_counts_after": after["subject_row_counts"],
        "permit_row_identical": before["permit_row"] == after["permit_row"],
    }
    self_persisted = (
        minted_survived > 0
        or before["subject_row_counts"] != after["subject_row_counts"]
        or before["permit_row"] != after["permit_row"]
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
            f"nothing: the disposition it minted ({minted_disposition_id}) is present in "
            f"{minted_survived} row(s) after the rollback, the subject's own row counts "
            f"went {before['subject_row_counts']} → {after['subject_row_counts']}, and its "
            f"permit row "
            f"{'is unchanged' if before['permit_row'] == after['permit_row'] else 'MOVED'}"
        )

    return {
        "schema_id": GATE_RUN_SCHEMA_ID,
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
            # cluster_logical_timestamp() is constant within a CockroachDB transaction and
            # moves between them. Equal endpoints are a READ-ONLY witness that all four
            # beats shared one transaction — not an assertion this file makes about itself.
            "single_transaction": closed_ts is not None and closed_ts == opened_ts,
            "savepoints": ["gate_run_beat_2", "gate_run_beat_3", "gate_run_beat_4"],
            "retry_sqlstate": undecided.sqlstate if undecided is not None else None,
            "canonicalisation": canon_impl,
        },
        "subject": resolved.as_json(),
        "beats": beats,
        "persistence_check": {
            "before": before,
            "after": after,
            "identical": identical,
            "self_persisted": self_persisted,
            "self_evidence": self_evidence,
            "concurrent_writes": concurrent_writes,
            "tables": list(_FINGERPRINT_TABLES),
            "note": (
                "Row counts over every table the four beats can write, taken before the "
                "transaction opened and after it was rolled back, plus mainline.permit's "
                "own columns — because the attack beat mutates a column without changing "
                "a count. `identical` is that reading and it is about the DATABASE. "
                "`self_persisted` is about THIS RUN: the disposition beat 4 minted is a "
                "uuid4 no other writer holds, and it is gone, and this subject's own row "
                "counts and permit row are unchanged. The verdict keys on the second, "
                "because a whole-table count cannot tell 'I persisted something' from "
                "'somebody else did' and this endpoint used to report the difference as "
                "its own failure."
            ),
        },
    }
