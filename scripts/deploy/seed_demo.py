#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Seed the demo world into ``mainline_demo``, then prove the seeded permit is refusable.

Applies, in this order and idempotently:

* ``verticals/mainline/db/seeds/demo/demo_world.sql``  — the static corpus
* ``verticals/mainline/db/seeds/demo/demo_permit.sql`` — one permit, one open obligation

then VERIFIES the result by asking the database to merge that permit inside a transaction it
rolls back, and records the SQLSTATE and constraint name it saw.

WHY THE VERIFICATION IS A ROLLED-BACK MERGE AND NOT A ROW COUNT
---------------------------------------------------------------
Counting rows proves the seed ran. It does not prove the seed produced the *state the demo needs*,
and those are different claims: a permit with an open obligation and a missing boundary
certificate also has one blocking check, and refuses — with a different SQLSTATE, naming a
different exhibit, for a reason that has nothing to do with the product's central claim. The only
way to know which refusal this database will give a judge is to ask it, so this script asks.

It asks safely. ``docs/leads/deploy-plan.md`` §1.4 measured that CockroachDB honours
``ROLLBACK TO SAVEPOINT`` after a constraint refusal and that a full ``ROLLBACK`` leaves the
seeded row untouched, which is the property the whole demo rests on — every judge drives the real
gate against the real seeded history, concurrently, and the database is exactly as they found it.
This script exercises that property on every run and reads ``open_blocking`` back afterwards to
confirm nothing moved. If the rollback ever stops working, this is where it is found out.

EVERY TRANSACTION THIS SCRIPT OPENS AGAINST THE CLOUD, AND WHAT GUARDS IT
-------------------------------------------------------------------------
This is the script that writes to the DEPLOYED database, so each of its transactions is
stated here rather than left to be inferred. ``40001 RETRY_SERIALIZABLE`` is what a
multi-node cluster answers a loser, and it is not a Cloud-only phenomenon: it is
reproducible against a single node — six of six deliberate two-connection races —
``docs/diagnosis/retry-negative-control.md``.

* **The two seed FILES** — ``apply_seeds`` — go through ``cloud_chain.Applier``, which has
  retried ``40001`` since it was written and is proved to by ``--inject-40001``. Nothing
  changed there and nothing needed to; it is named here because it is the transaction a
  reader worries about first, and a half-applied seed in front of a judge is what it
  prevents.
* **The merge probe** — ``verify_refusable`` — is the one that was unguarded, and it is now
  ONE whole transaction under :func:`trappoint_testkit.txn.run_txn`, whose loop is
  ``trappoint_core.retry.run_gate``. It retries ``40001`` and only ``40001``; it attempts the
  ``23514`` this probe exists to obtain exactly ONCE, ever; and an exhausted budget is
  reported as ``UNDECIDED`` rather than as a refusal, because the database did not decide.
* **The two censuses** — ``census`` and ``observe`` — and the after-rollback read are NOT
  retried, and the reason is measurable rather than a judgement: they run on
  ``cloud_chain.Applier.conn``, which is opened ``autocommit=True``, so every statement is
  its own implicit transaction and CockroachDB restarts an implicit transaction server-side.
  Their ``conn.commit()`` calls are no-ops and are marked as such where they sit.

WHAT "IDEMPOTENT" MEANS HERE
----------------------------
Both seed files use fixed UUIDs, fixed timestamps, deterministic ``digest(...)`` values and
``ON CONFLICT DO NOTHING``. A second run inserts nothing, raises nothing, and produces an evidence
file whose row counts are identical to the first. ``--check`` runs the verification alone, without
applying anything, for use as a liveness probe against a database somebody else seeded.

Usage::

    .venv/Scripts/python.exe scripts/deploy/seed_demo.py                    # Cloud, from .env
    .venv/Scripts/python.exe scripts/deploy/seed_demo.py --check            # verify only
    .venv/Scripts/python.exe scripts/deploy/seed_demo.py \\
        --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable \\
        --database w_w2_cloud_database

Exit codes:

* ``0`` — the seed is present and the seeded permit's merge was REFUSED with the expected
  SQLSTATE and exhibit, and nothing persisted.
* ``1`` — the seed is present but the state is wrong: the merge was admitted, or refused for the
  wrong reason, or the rollback did not hold. **The evidence file is still written. Publish it.**
* ``2`` — no DSN, no seed files, or no database to talk to.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

# Run as a module (`python -m scripts.deploy.seed_demo`) or as a path
# (`python scripts/deploy/seed_demo.py`). The second form gives Python `scripts/deploy` as
# sys.path[0] and no package context at all, so the sibling import below would fail — which is
# exactly how an operator will invoke it, on a machine where `uv` is not installed and nothing
# has been `pip install -e`'d. Putting the repository root on the path here costs one branch and
# removes a class of "works on my machine".
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trappoint_testkit.txn import from_dsn, run_txn

from scripts.deploy.cloud_chain import _JITTER as JITTER
from scripts.deploy.cloud_chain import (
    DEFAULT_DATABASE,
    MAX_ATTEMPTS,
    RETRYABLE,
    Applier,
    cluster_label,
    database_report,
    load_dotenv,
    one_line,
    repo_root,
    rewrite_dsn,
    row_of,
    sqlstate_of,
)
from trappoint_core.errors import (
    AuthorisationDenied,
    GateRefused,
    RetryBudgetExhausted,
    UnmodelledRefusal,
)

EXIT_OK = 0
EXIT_WRONG_STATE = 1
EXIT_USAGE = 2

#: What the demo is about. `spec/conformance/manifest.toml` group 1, case CF-01: one open
#: obligation, no signed disposition, and the exhibit is a NAME rather than a message.
EXPECTED_SQLSTATE = "23514"
EXPECTED_CONSTRAINT = "gate_closed_when_issued"

#: The identifiers the seed files fix. Restated here so this script can be read on its own and so
#: that a drift between the SQL and the verifier is a test failure rather than a silent mismatch.
PERMIT_ID = "dec0de00-0006-4000-8000-000000000001"
CHECK_ID = "dec0de00-0007-4000-8000-000000000001"
SITE_ID = "dec0de00-0001-4000-8000-000000000001"
CLAUSE_UUID = "dec0de00-0004-4000-8000-000000000001"
EVENT_ID = "dec0de00-0005-4000-8000-000000000001"
RECEIPT_ID = "dec0de00-0008-4000-8000-000000000001"
RECALL_RUN_ID = "dec0de00-0009-4000-8000-000000000001"

#: Applied in this order. `demo_world.sql` first because everything in `demo_permit.sql` points
#: at it; `mainline_meas.recall_run.permit_id` is the one foreign key that runs the other way,
#: which is why the run lives in the second file rather than the first.
SEED_FILES: tuple[str, ...] = ("demo_world.sql", "demo_permit.sql")

#: Counted after every run. The demo's read surfaces are a function of these numbers, so a change
#: in any of them is a change in what a judge sees, and the evidence should make that diffable.
COUNTED: tuple[str, ...] = (
    "mainline.site",
    "mainline.person",
    "mainline.signing_credential",
    "mainline.commit_obj",
    "mainline.commit_edge",
    "mainline.doc",
    "mainline.clause",
    "mainline.clause_version",
    "mainline.event",
    "mainline.blame_edge",
    "mainline.clause_blame_closure",
    "mainline.cbm_account",
    "mainline.ledger_checkpoint",
    "mainline.cosignature",
    "mainline_meas.recall_policy",
    "mainline_meas.recall_run",
    "mainline_meas.silence_receipt",
    "mainline.permit",
    "mainline.permit_clause",
    "mainline.permit_event",
    "mainline.boundary_certificate",
    "mainline.blocking_check",
    "mainline.exposure_receipt",
    "mainline.exposure_line",
    "mainline.disposition",
    "mainline.merge_record",
    "mainline_ops.outbox",
)


def constraint_of(exc: psycopg.Error) -> tuple[str, str]:
    """Return ``(exhibit, how_it_was_obtained)``.

    ``spec/errors.md`` §3.1: ``diag.constraint_name`` is populated for a CHECK violation and is
    EMPTY for ``P0001``, where the raising body wrote the name into the message instead. The two
    are recorded differently — ``reported`` versus ``parsed`` — because a parsed exhibit is a
    weaker diagnosis and ``mainline.refusal_ledger``'s own CHECK insists the difference be stated.

    NO LONGER CALLED FROM THIS FILE, and that is recorded rather than left to be noticed.
    :func:`verify_refusable` now gets the same distinction from the specified taxonomy —
    ``trappoint_core.errors.diagnose`` sets ``GateRefused.weakened``, which is this
    function's ``"parsed"`` under another name — because the refusal has to travel out of a
    retry loop that classifies it, and two classifiers would be two things to keep correct.
    It survives as this file's spelling for a caller holding a raw ``psycopg.Error`` (the
    ``--check`` path may grow one), and it must not acquire a second, divergent opinion: if
    the two ever disagree, ``spec/errors.md`` §3.1 is the arbiter and this one loses.
    """
    diag = getattr(exc, "diag", None)
    reported = (diag.constraint_name if diag is not None else None) or ""
    if reported:
        return reported, "reported"
    message = str(exc)
    marker = "refused by "
    if marker in message:
        tail = message.split(marker, 1)[1]
        return tail.split()[0].rstrip(".,;"), "parsed"
    return "", "absent"


def apply_seeds(applier: Applier, seeds: Path) -> list[dict[str, Any]]:
    """Apply each seed file as ONE statement batch, retrying ``40001``.

    One batch per file, not one per statement. The seed files are written so that the whole file
    is a single implicit transaction — the second ``permit_event`` reads the first's generated
    ``chain_digest``, and the projection triggers take ``FOR UPDATE`` on the permit — so splitting
    them would change what is being seeded, not merely how.

    THIS IS THE SECOND APPLIER, AND IT SHARES THE FIRST ONE'S RETRY LOOP. ``cloud_chain.Applier``
    is imported rather than reimplemented, so a fix to the ``40001`` handling cannot be applied to
    the migration chain and forgotten here. ``--inject-40001`` therefore proves this path too, and
    it proves it on a *real* seed file: the injection is raised before the statement is sent, so
    the retry re-runs a file that has not partially applied, which is the only way an injected
    recovery is evidence about the real one.
    """
    rows: list[dict[str, Any]] = []
    for name in SEED_FILES:
        path = seeds / name
        if not path.is_file():
            raise SystemExit(f"seed_demo: no seed file at {path}")
        outcome = applier.run(path.read_text(encoding="utf-8"), label=name)
        rows.append(row_of(name, outcome))
        status = "OK" if outcome.ok else f"FAILED {outcome.sqlstate}"
        injected = f" injected={outcome.injected_40001}" if outcome.injected_40001 else ""
        print(
            f"  seed         {name:<20} {status:<16} {outcome.seconds:>6.2f}s "
            f"attempts={outcome.attempts}{injected}",
            flush=True,
        )
        if not outcome.ok:
            print(f"               {outcome.error}", flush=True)
    return rows


def census(conn: psycopg.Connection[Any]) -> dict[str, int | str]:
    counts: dict[str, int | str] = {}
    for table in COUNTED:
        try:
            row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
            counts[table] = int(row[0]) if row else 0
        except psycopg.Error as exc:
            conn.rollback()
            counts[table] = f"ERROR {sqlstate_of(exc)}"
    return counts


def observe(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    """Read the state the demo depends on, from the database rather than from the seed file."""
    out: dict[str, Any] = {}
    permit = conn.execute(
        "SELECT state::STRING, open_blocking, gate_epoch, head_seq, site_role::STRING, "
        "external_ref, under_hold FROM mainline.permit WHERE permit_id = %s",
        (PERMIT_ID,),
    ).fetchone()
    out["permit"] = (
        None
        if permit is None
        else {
            "permit_id": PERMIT_ID,
            "state": permit[0],
            "open_blocking": int(permit[1]),
            "gate_epoch": int(permit[2]),
            "head_seq": int(permit[3]),
            "site_role": permit[4],
            "external_ref": permit[5],
            "under_hold": bool(permit[6]),
        }
    )
    check = conn.execute(
        "SELECT severity, virulence::STRING, closure_gen, origin, precursor_event_id, "
        "recall_run_id FROM mainline.blocking_check WHERE check_id = %s",
        (CHECK_ID,),
    ).fetchone()
    out["blocking_check"] = (
        None
        if check is None
        else {
            "check_id": CHECK_ID,
            "severity": int(check[0]),
            "virulence": check[1],
            "closure_gen": int(check[2]),
            "origin": check[3],
            "precursor_event_id": str(check[4]),
            "recall_run_id": str(check[5]),
            "projected_by": (
                "mainline.fn_check_project from mainline.clause_blame_current (MI25) — "
                "the seed supplied severity 0 / virulence 'routine' and both were overwritten"
            ),
        }
    )
    # EXACTLY ONE PERMIT, and the count is taken three ways on purpose. "the seed is present"
    # and "the seed is the only thing present" are different claims, and only the second one
    # tells a judge that the database they are about to drive has not accumulated leftovers
    # from an earlier run, a test, or somebody's manual poke at the gate.
    totals = conn.execute(
        "SELECT count(*), count(*) FILTER (WHERE permit_id = %s), "
        "count(*) FILTER (WHERE external_ref LIKE 'DEMO-%%') FROM mainline.permit",
        (PERMIT_ID,),
    ).fetchone()
    out["permits_in_database"] = int(totals[0]) if totals else 0
    out["the_demo_permit"] = int(totals[1]) if totals else 0
    out["permits_flagged_demo"] = int(totals[2]) if totals else 0
    dispositions = conn.execute(
        "SELECT count(*) FROM mainline.disposition WHERE check_id = %s", (CHECK_ID,)
    ).fetchone()
    out["dispositions_against_the_check"] = int(dispositions[0]) if dispositions else 0
    trigger = conn.execute(
        "SELECT count(*) FROM information_schema.triggers "
        "WHERE event_object_schema = 'mainline' AND event_object_table = 'blocking_check' "
        "AND trigger_name = 'check_materialised'"
    ).fetchone()
    out["projection_trigger_check_materialised_present"] = bool(trigger and trigger[0])
    # The gate re-derives this number instead of trusting the column (P-2). Reading it here with
    # the gate's own query is how the evidence shows the projection and the derivation AGREE
    # before anybody starts forcing counters out of band.
    derived = conn.execute(
        "SELECT count(*) FROM mainline.blocking_check bc WHERE bc.permit_id = %s "
        "AND NOT EXISTS (SELECT 1 FROM mainline.disposition d WHERE d.check_id = bc.check_id "
        "AND d.retracted_by IS NULL AND (d.expires_at IS NULL OR d.expires_at > now()))",
        (PERMIT_ID,),
    ).fetchone()
    out["re_derived_open_obligations"] = int(derived[0]) if derived else 0
    # NOT A TRANSACTION, AND THEREFORE NOT A RETRY SITE — stated rather than left to a
    # reader to work out. `conn` is `cloud_chain.Applier.conn`, opened `autocommit=True`
    # (cloud_chain.py:371), so each SELECT above is its own IMPLICIT transaction and
    # CockroachDB restarts an implicit transaction SERVER-side; there is no multi-statement
    # unit here for a client retry to be OF. This `commit()` is consequently a no-op — kept
    # because removing it would read as a claim that something changed. What this DOES cost
    # is a consistent snapshot: the eight reads above are eight instants, not one. That is a
    # separate (and unchanged) property of this census and is not what a retry would fix.
    conn.commit()
    return out


class _Admitted(Exception):
    """The seeded permit MERGED. Raised so the adapter DISCARDS the transaction.

    Not an error condition in the transport sense — it is the outcome this probe is looking
    for the absence of. It is an exception because :func:`trappoint_testkit.txn.run_txn`
    COMMITS whatever its callable returns, and committing here would merge the demo permit
    on the deployed cluster and leave the next judge a different database from the last one.
    ``run_txn``'s ``finally`` rolls back and closes on any exception, and ``run_gate`` passes
    a non-``psycopg`` exception straight through without classifying it — so raising is the
    supported way to say "do not commit this" and get the rollback the docstring promises.
    """


def _attempt_seeded_merge(conn: psycopg.Connection[Any]) -> None:
    """Call ``mainline.merge_permit`` on the seeded permit. Never returns normally.

    The WORK half of one whole transaction. It does not commit, does not roll back and does
    not catch: ``run_txn`` owns the first two and ``run_gate`` owns the third, which is what
    makes a ``40001`` here a RETRY of the whole call and a ``23514`` here a REFUSAL attempted
    exactly once, ever.
    """
    payload = {"permit": PERMIT_ID, "merged_by": "demo.signer", "probe": "seed_demo.verify"}
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    leaf = hashlib.sha256(b"\x00" + canon).digest()
    merged_commit = hashlib.sha256(b"mainline-demo/commit/verify-merge").digest()
    conn.execute(
        "CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)",
        (PERMIT_ID, merged_commit, "demo.signer", "human", Jsonb(payload), canon, 1, leaf),
    )
    raise _Admitted


def verify_refusable(dsn: str, conn: psycopg.Connection[Any]) -> dict[str, Any]:
    """Ask the database to merge the seeded permit, then roll the whole thing back.

    Nothing here is allowed to persist. The procedure is called inside a transaction of its
    own, the outcome — refusal, admission or undecided — is captured, and the transaction is
    rolled back on EVERY path. An admission that committed would leave the demo in a merged
    state and the next judge would see a different database from the last one.

    CONTENDED, AND THIS IS THE ONE IN THIS FILE THAT IS. This runs against the DEPLOYED
    CockroachDB Cloud database — multi-node, ``SERIALIZABLE`` — and ``CALL
    mainline.merge_permit`` is a read-modify-write over the permit, its obligations and its
    event chain. Two judges driving ``POST /v1/demo/gate-run`` while ``deploy.sh`` re-runs
    this probe is the demo's actual concurrency, and a Cloud cluster also restarts
    transactions for clock uncertainty with no second writer at all.

    **WHAT THAT USED TO COST, and it is not a hypothetical shape.** The old body caught
    ``psycopg.Error`` and classified whatever it caught as ``REFUSED``. A ``40001`` therefore
    came out as ``{"outcome": "REFUSED", "sqlstate": "40001"}``, ``as_expected`` went false,
    and ``deploy.sh`` reported ``VERDICT WRONG STATE`` — a transient conflict published as a
    broken demo, on the deployment path, minutes before a judge arrives. **An undecided
    transaction is not a refusal** (``spec/errors.md`` §5): the database did not decide, so
    the honest answers are "ask again" (which the loop now does, up to the policy's budget)
    and then ``UNDECIDED``, which is reported as its own outcome and never as a verdict about
    the gate.

    **AND WHAT IS DELIBERATELY NOT RETRIED.** ``23514 gate_closed_when_issued`` is the
    answer this probe exists to obtain. ``run_gate`` raises it as
    :class:`~trappoint_core.errors.GateRefused` on the FIRST attempt and never asks again —
    ``spec/errors.md`` §4, because a client that retried a refusal would write five identical
    rows for one attempted history and the refusal ledger's count would stop being a count of
    anything. That property is not re-implemented here; it is the reason the loop is imported.

    Args:
        dsn: the database this run seeded. ``run_txn`` opens its OWN connection from this —
            a fresh one per attempt — because a retry that reused a poisoned connection
            would replay statements into a transaction CockroachDB has already aborted.
        conn: the applier's autocommit connection, used only for the after-rollback read.
    """
    started = time.time()
    try:
        run_txn(
            from_dsn(dsn),
            _attempt_seeded_merge,
            subject_kind="permit",
            subject_id=PERMIT_ID,
        )
    except _Admitted:
        result = {
            "outcome": "ADMITTED",
            "sqlstate": "00000",
            "constraint": "",
            "constraint_source": "absent",
            "message": (
                "the seeded permit MERGED. The demo's central claim is not demonstrable against "
                "this database: an open obligation did not stop an issue."
            ),
            "seconds": round(time.time() - started, 3),
            "expected_sqlstate": EXPECTED_SQLSTATE,
            "expected_constraint": EXPECTED_CONSTRAINT,
            "as_expected": False,
        }
    except GateRefused as refused:
        # `weakened` is the same distinction `constraint_of` draws: the database REPORTED
        # `diag.constraint_name`, or the exhibit was recovered from the message. The
        # refusal ledger's own CHECK insists the difference be stated, so it is carried
        # here rather than flattened.
        result = {
            "outcome": "REFUSED",
            "sqlstate": refused.sqlstate,
            "constraint": refused.constraint,
            "constraint_source": "parsed" if refused.weakened else "reported",
            "message": " ".join(refused.message.split()),
            "seconds": round(time.time() - started, 3),
            "expected_sqlstate": EXPECTED_SQLSTATE,
            "expected_constraint": EXPECTED_CONSTRAINT,
            "as_expected": (
                refused.sqlstate == EXPECTED_SQLSTATE and refused.constraint == EXPECTED_CONSTRAINT
            ),
        }
    except RetryBudgetExhausted as exhausted:
        result = {
            "outcome": "UNDECIDED",
            "sqlstate": RETRYABLE,
            "constraint": "",
            "constraint_source": "absent",
            "message": (
                f"{exhausted}. The cluster returned 40001 on every attempt, so this merge was "
                "never decided. That is NOT a refusal and NOT an admission: nothing here is "
                "evidence about the gate, and re-running the probe is the remedy."
            ),
            "seconds": round(time.time() - started, 3),
            "expected_sqlstate": EXPECTED_SQLSTATE,
            "expected_constraint": EXPECTED_CONSTRAINT,
            "as_expected": False,
        }
    except (AuthorisationDenied, UnmodelledRefusal) as exc:
        # 42501, or a SQLSTATE outside the five the specification models. Reported as
        # itself rather than dressed as a gate refusal — a permission error and a refusal
        # have different remedies and only one of them is about the product.
        result = {
            "outcome": "REFUSED",
            "sqlstate": getattr(exc, "sqlstate", "") or "",
            "constraint": "",
            "constraint_source": "absent",
            "message": f"{type(exc).__name__}: {' '.join(str(exc).split())}",
            "seconds": round(time.time() - started, 3),
            "expected_sqlstate": EXPECTED_SQLSTATE,
            "expected_constraint": EXPECTED_CONSTRAINT,
            "as_expected": False,
        }

    # THE OTHER HALF OF THE CLAIM: nothing persisted. Read after the rollback, on the
    # applier's AUTOCOMMIT connection, so each statement is its own implicit transaction —
    # the same stated reason as `observe()`, and the reason the `commit()` below is a no-op.
    after = conn.execute(
        "SELECT state::STRING, open_blocking, gate_epoch FROM mainline.permit WHERE permit_id = %s",
        (PERMIT_ID,),
    ).fetchone()
    merge_records = conn.execute(
        "SELECT count(*) FROM mainline.merge_record WHERE subject_id = %s", (PERMIT_ID,)
    ).fetchone()
    conn.commit()
    result["after_rollback"] = {
        "permit_state": after[0] if after else None,
        "open_blocking": int(after[1]) if after else None,
        "gate_epoch": int(after[2]) if after else None,
        "merge_record_rows": int(merge_records[0]) if merge_records else None,
        "nothing_persisted": bool(
            after is not None
            and after[0] == "dispositioned"
            and int(after[1]) == 1
            and merge_records is not None
            and int(merge_records[0]) == 0
        ),
    }
    return result


# One branch per FAILURE MODE, and the branch is the point. "the permit is missing",
# "the permit is in the wrong state", "the counter did not move", "the projection did not
# run", "a disposition already exists", "the merge was admitted", "it refused for the wrong
# reason" and "the rollback did not hold" are eight different diagnoses with eight different
# fixes. A generic assertion helper would report all eight as one line of the form
# `expected X got Y`, which is exactly the report nobody can act on at 2 a.m.
def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:  # noqa: PLR0912, PLR0915
    root = repo_root()
    seeds = args.seeds or (root / "verticals" / "mainline" / "db" / "seeds" / "demo")
    dsn = rewrite_dsn(
        args.dsn,
        database=args.database,
        connect_timeout=args.connect_timeout,
        application_name="mainline-deploy-seed",
    )
    started = time.time()

    evidence: dict[str, Any] = {
        "artefact": "MAINLINE demo seed",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/deploy/seed_demo.py",
        "honesty": (
            "No real incident, no real site, no real fatality. Every row named below is "
            "synthetic and corresponds to nobody. See verticals/mainline/demo/DEMO-HONESTY.md."
        ),
        "target": {"cluster": cluster_label(args.dsn), "database": args.database},
        "subject": {
            "permit_id": PERMIT_ID,
            "check_id": CHECK_ID,
            "site_id": SITE_ID,
            "clause_uuid": CLAUSE_UUID,
            "precursor_event_id": EVENT_ID,
            "exposure_receipt_id": RECEIPT_ID,
            "recall_run_id": RECALL_RUN_ID,
        },
    }

    applier = Applier(dsn, inject_40001=args.inject_40001, inject_into=args.inject_into)
    version = applier.conn.execute("SELECT version()").fetchone()
    user = applier.conn.execute("SELECT current_user").fetchone()
    observed = applier.database
    evidence["target"]["version"] = str(version[0]) if version else "unknown"
    evidence["target"]["connected_as"] = str(user[0]) if user else "unknown"
    evidence["target"]["database_selection"] = database_report(args.dsn, args.database, observed)
    print(
        f"  connected    {observed} as {evidence['target']['connected_as']} "
        f"(SELECT current_database(); the DSN's path segment said "
        f"'{evidence['target']['database_selection']['dsn_path_segment']}' and was overridden)",
        flush=True,
    )
    # REFUSING BEATS READING THE WRONG DATABASE. On the committed DSN this script would connect
    # to `defaultdb`, find no `mainline` schema and report `UndefinedTable` — a scary message
    # about a database that is perfectly healthy, and the single most time-wasting failure this
    # deployment has produced. The database is named explicitly and then confirmed by the server.
    if observed != args.database:
        applier.close()
        evidence["failures"] = [
            (
                f"asked for database {args.database!r} and the server answered "
                f"current_database() = {observed!r}. Nothing was seeded and nothing was read."
            )
        ]
        evidence["verdict"] = "WRONG DATABASE"
        return EXIT_WRONG_STATE, evidence

    if args.check:
        evidence["seed_files"] = "not applied (--check)"
    else:
        evidence["seed_files"] = apply_seeds(applier, seeds)

    failures: list[str] = []
    if isinstance(evidence["seed_files"], list):
        for row in evidence["seed_files"]:
            if row["error"]:
                failures.append(f"{row['file']} did not apply [{row['sqlstate']}]: {row['error']}")

    evidence["row_counts"] = census(applier.conn)
    evidence["observed"] = observe(applier.conn)

    seed_rows = evidence["seed_files"] if isinstance(evidence["seed_files"], list) else []
    evidence["retry"] = {
        "executor": "scripts/deploy/cloud_chain.Applier — the same one the migration chain uses",
        "retryable_sqlstate": RETRYABLE,
        "max_attempts": MAX_ATTEMPTS,
        "files_that_needed_a_retry": sum(
            1 for r in seed_rows if r["attempts"] > r["injected_40001"] + 1
        ),
        "files_with_injected_retries": sum(1 for r in seed_rows if r["injected_40001"]),
        "injected_by_this_run": args.inject_40001,
        "note": (
            "files_that_needed_a_retry counts SPONTANEOUS retries only — a 40001 the cluster "
            "produced. Retries this program injected with --inject-40001 are counted separately "
            "and are never allowed to inflate the first number."
        ),
        "merge_probe_executor": (
            "trappoint_testkit.txn.run_txn over trappoint_core.retry.run_gate — the WHOLE "
            "transaction, retried from BEGIN on a fresh connection. It is a DIFFERENT loop "
            "from the Applier's above, and deliberately so: the Applier retries one "
            "statement batch it re-sends in full, while the probe's unit is a transaction "
            "whose refusal must be attempted exactly once. Both retry 40001 and only 40001."
        ),
        "merge_probe_refusal_is_never_retried": (
            "spec/errors.md §4. run_gate raises GateRefused on the first 23514/23503/23505/"
            "P0001 and never asks again: a retried refusal writes N identical rows into "
            "mainline.refusal_ledger for one attempted history."
        ),
    }

    observed = evidence["observed"]
    if observed.get("permits_in_database") != 1:
        failures.append(
            f"{observed.get('permits_in_database')} permits stand in mainline.permit, expected "
            "exactly 1 — the demo database has accumulated state that is not the seed"
        )
    if observed["permit"] is None:
        failures.append("the seeded permit does not exist")
    elif observed["permit"]["state"] != "dispositioned":
        failures.append(
            f"the seeded permit is in state {observed['permit']['state']!r}, not 'dispositioned'"
        )
    elif observed["permit"]["open_blocking"] != 1:
        failures.append(
            f"open_blocking reads {observed['permit']['open_blocking']}, not 1 — the projection "
            "trigger did not run, or a disposition already exists"
        )
    if observed["blocking_check"] is None:
        failures.append("the seeded blocking check does not exist")
    else:
        if observed["blocking_check"]["severity"] != 4:
            failures.append(
                f"the check projected severity {observed['blocking_check']['severity']}, not 4"
            )
        if observed["blocking_check"]["virulence"] != "blood_major":
            failures.append(
                f"the check projected virulence {observed['blocking_check']['virulence']!r}, "
                "not 'blood_major'"
            )
    if observed["dispositions_against_the_check"] != 0:
        failures.append(
            f"{observed['dispositions_against_the_check']} disposition(s) already stand against "
            "the seeded obligation — the demo's first beat would not refuse"
        )

    evidence["verification"] = verify_refusable(dsn, applier.conn)
    applier.close()

    verification = evidence["verification"]
    if verification["outcome"] == "UNDECIDED":
        # A distinct branch, because it has a distinct remedy. "the gate admitted" is a
        # statement about the product; "the cluster never decided" is a statement about
        # contention, and reporting the second as the first is how a transient 40001
        # becomes a WRONG STATE verdict on the deployment path.
        failures.append(
            "the merge probe was never decided: 40001 on every attempt of the retry budget. "
            "Nothing here is evidence about the gate — re-run seed_demo.py --check."
        )
    elif verification["outcome"] != "REFUSED":
        failures.append("the seeded permit MERGED — the gate admitted an open obligation")
    elif not verification["as_expected"]:
        failures.append(
            f"the merge was refused with [{verification['sqlstate']}] "
            f"{verification['constraint']!r}, expected [{EXPECTED_SQLSTATE}] "
            f"{EXPECTED_CONSTRAINT!r}"
        )
    if not verification["after_rollback"]["nothing_persisted"]:
        failures.append(
            "the rollback did not hold: the permit or the merge_record table changed after a "
            "transaction that was rolled back"
        )

    evidence["total_seconds"] = round(time.time() - started, 1)
    evidence["failures"] = failures
    evidence["verdict"] = "SEEDED AND REFUSABLE" if not failures else "WRONG STATE"
    return (EXIT_OK if not failures else EXIT_WRONG_STATE), evidence


def summarise(evidence: dict[str, Any]) -> None:
    target = evidence["target"]
    verification = evidence.get("verification", {})
    observed = evidence.get("observed", {})
    selection = target.get("database_selection", {})
    print()
    print(f"cluster       {target['cluster']}")
    print(
        f"database      {selection.get('confirmed_by_server', target['database'])}  "
        f"(as {target.get('connected_as')}; confirmed by SELECT current_database(), "
        f"DSN path segment '{selection.get('dsn_path_segment', '?')}')"
    )
    print(
        f"permits       {observed.get('permits_in_database')} in mainline.permit, "
        f"{observed.get('the_demo_permit')} is the demo permit"
    )
    print(f"permit        {evidence['subject']['permit_id']}")
    print(f"check         {evidence['subject']['check_id']}")
    if observed.get("permit"):
        permit = observed["permit"]
        print(
            f"state         {permit['state']}  open_blocking={permit['open_blocking']}  "
            f"gate_epoch={permit['gate_epoch']}  head_seq={permit['head_seq']}"
        )
    if observed.get("blocking_check"):
        check = observed["blocking_check"]
        print(
            f"obligation    severity={check['severity']} virulence={check['virulence']} (projected)"
        )
    print(f"dispositions  {observed.get('dispositions_against_the_check')}")
    print(
        f"MERGE         {verification.get('outcome')} [{verification.get('sqlstate')}] "
        f"{verification.get('constraint')} ({verification.get('constraint_source')})"
    )
    print(
        f"rollback      nothing_persisted="
        f"{verification.get('after_rollback', {}).get('nothing_persisted')}"
    )
    for failure in evidence.get("failures", []):
        print(f"  ! {failure}")
    print(f"VERDICT       {evidence['verdict']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_demo",
        description=(
            "Seed the MAINLINE demo world and prove the seeded permit's merge is refused by "
            "the database, with nothing persisted."
        ),
    )
    parser.add_argument("--dsn", default=None, help="DSN (default: COCKROACH_DSN from .env)")
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--seeds", type=Path, default=None, help="directory holding the seed SQL")
    parser.add_argument("--out", type=Path, default=None, help="evidence path")
    parser.add_argument("--check", action="store_true", help="verify only; apply neither seed file")
    parser.add_argument("--connect-timeout", type=int, default=20)
    parser.add_argument(
        "--inject-40001",
        type=int,
        default=0,
        metavar="N",
        help=(
            "raise a simulated 40001 on the first N attempts of one seed file, before it "
            "reaches the server, to prove the shared retry loop recovers"
        ),
    )
    parser.add_argument(
        "--inject-into",
        default=None,
        metavar="SUBSTRING",
        help="only inject into the seed file whose name or text contains SUBSTRING",
    )
    parser.add_argument(
        "--jitter-seed",
        type=int,
        default=None,
        help="seed the backoff jitter so a published transcript is reproducible",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    root = repo_root()
    load_dotenv(root)
    args = build_parser().parse_args(argv)
    args.dsn = args.dsn or os.environ.get("COCKROACH_DSN")
    if not args.dsn:
        print(
            "seed_demo: no DSN. Pass --dsn, or put COCKROACH_DSN in the repo-root .env.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    out = args.out or (root / "evidence" / "deploy" / "cloud-seed.json")
    if args.jitter_seed is not None:
        JITTER.seed(args.jitter_seed)

    try:
        code, evidence = run(args)
    except psycopg.OperationalError as exc:
        print(f"seed_demo: could not reach the cluster: {one_line(exc)}", file=sys.stderr)
        return EXIT_USAGE

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    out.with_suffix(out.suffix + ".license").write_text(
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: CC-BY-4.0\n",
        encoding="utf-8",
    )
    summarise(evidence)
    print(f"evidence      {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
