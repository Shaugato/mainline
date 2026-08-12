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

The claim that the four beats really did share one transaction is also proved rather than
asserted. ``cluster_logical_timestamp()`` is constant within a CockroachDB transaction and
moves between them, so it is captured at the first beat and after the last; equal values
are a read-only witness that no beat quietly opened a transaction of its own.

WHAT THIS MODULE WILL NOT DO
----------------------------
It will not retry. ``40001`` aborts the run, is reported as ``outcome: "retry"`` with the
beats completed so far, and the caller decides. A driver that re-sent the merge because a
socket closed is a driver that can issue a permit twice.

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

from .refusal import Diagnosis, classify, diagnose, refusal_payload, rfc3339
from .scenario import ResolvedScenario, Scenario, positional, resolve

__all__ = [
    "ADMISSION_SQLSTATE",
    "CF01_EXHIBIT",
    "CF01_SQLSTATE",
    "CF03_EXHIBIT",
    "CF03_SQLSTATE",
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
        'MECHANISM_PRESENT_AND_VERIFIED', %s, %s, %s, %s, 1, 'x', %s, %s, %s, 'ES256',
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
    row = positional(conn, _PERMIT_ROW_SQL, (permit_id,)).fetchone()
    return {
        # strict=True: `_FINGERPRINT_TABLES` and the statement's ten subqueries are one
        # list written twice, and a zip that truncated silently would report a persistence
        # check over FEWER tables than the payload claims. CockroachDB names all ten of
        # those columns `count`, so a dict row collapses them to one — measured, and the
        # reason this pair is now guarded rather than merely converted.
        "row_counts": {name: int(n) for name, n in zip(_FINGERPRINT_TABLES, counts, strict=True)},
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
    before = _fingerprint(conn, resolve(conn, scenario).permit_id)
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
        else:
            conn.execute("SAVEPOINT gate_run_beat_4")
            disposition_id = uuid.uuid4()
            try:
                conn.execute(
                    _DISPOSITION_SQL,
                    (
                        disposition_id,
                        resolved.check_id,
                        resolved.receipt_id,
                        resolved.permit_id,
                        resolved.scenario.site_id,
                        _sha("defeater-vocab"),
                        _RATIONALE,
                        _sha("evidence", str(disposition_id)),
                        resolved.scenario.signer_sub,
                        _sha("cred", "signer"),
                        resolved.scenario.countersigner_sub,
                        _sha("cred", "cosigner"),
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
    conn.rollback()

    identical = before == after
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
    if not identical:
        failures.append(
            "the affected tables are NOT byte-identical before and after the run; the "
            "transaction was supposed to persist nothing"
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
            "tables": list(_FINGERPRINT_TABLES),
            "note": (
                "Row counts over every table the four beats can write, taken before the "
                "transaction opened and after it was rolled back, plus mainline.permit's "
                "own columns — because the attack beat mutates a column without changing "
                "a count."
            ),
        },
    }
