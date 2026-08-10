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

from scripts.deploy.cloud_chain import (
    DEFAULT_DATABASE,
    Applier,
    cluster_label,
    load_dotenv,
    one_line,
    repo_root,
    rewrite_dsn,
    sqlstate_of,
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
    """
    rows: list[dict[str, Any]] = []
    for name in SEED_FILES:
        path = seeds / name
        if not path.is_file():
            raise SystemExit(f"seed_demo: no seed file at {path}")
        outcome = applier.run(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "file": name,
                "seconds": outcome.seconds,
                "attempts": outcome.attempts,
                "sqlstate": outcome.sqlstate,
                "error": outcome.error,
            }
        )
        status = "OK" if outcome.ok else f"FAILED {outcome.sqlstate}"
        print(
            f"  seed         {name:<20} {status:<16} {outcome.seconds:>6.2f}s "
            f"attempts={outcome.attempts}",
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
    conn.commit()
    return out


def verify_refusable(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    """Ask the database to merge the seeded permit, then roll the whole thing back.

    Nothing here is allowed to persist. The transaction is opened explicitly, the procedure is
    called, the outcome — refusal or admission — is captured, and the transaction is rolled back
    on BOTH paths. An admission that committed would leave the demo in a merged state and the
    next judge would see a different database from the last one.
    """
    payload = {"permit": PERMIT_ID, "merged_by": "demo.signer", "probe": "seed_demo.verify"}
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    leaf = hashlib.sha256(b"\x00" + canon).digest()
    merged_commit = hashlib.sha256(b"mainline-demo/commit/verify-merge").digest()

    conn.execute("BEGIN")
    conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    started = time.time()
    try:
        conn.execute(
            "CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)",
            (PERMIT_ID, merged_commit, "demo.signer", "human", Jsonb(payload), canon, 1, leaf),
        )
    except psycopg.Error as exc:
        seconds = round(time.time() - started, 3)
        exhibit, source = constraint_of(exc)
        state = sqlstate_of(exc)
        message = one_line(exc)
        conn.rollback()
        result = {
            "outcome": "REFUSED",
            "sqlstate": state,
            "constraint": exhibit,
            "constraint_source": source,
            "message": message,
            "seconds": seconds,
            "expected_sqlstate": EXPECTED_SQLSTATE,
            "expected_constraint": EXPECTED_CONSTRAINT,
            "as_expected": state == EXPECTED_SQLSTATE and exhibit == EXPECTED_CONSTRAINT,
        }
    else:
        seconds = round(time.time() - started, 3)
        conn.rollback()
        result = {
            "outcome": "ADMITTED",
            "sqlstate": "00000",
            "constraint": "",
            "constraint_source": "absent",
            "message": (
                "the seeded permit MERGED. The demo's central claim is not demonstrable against "
                "this database: an open obligation did not stop an issue."
            ),
            "seconds": seconds,
            "expected_sqlstate": EXPECTED_SQLSTATE,
            "expected_constraint": EXPECTED_CONSTRAINT,
            "as_expected": False,
        }

    # THE OTHER HALF OF THE CLAIM: nothing persisted. Read after the rollback, in a fresh
    # transaction, from the base tables.
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
def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:  # noqa: PLR0912
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

    applier = Applier(dsn)
    version = applier.conn.execute("SELECT version()").fetchone()
    user = applier.conn.execute("SELECT current_user").fetchone()
    evidence["target"]["version"] = str(version[0]) if version else "unknown"
    evidence["target"]["connected_as"] = str(user[0]) if user else "unknown"

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

    observed = evidence["observed"]
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

    evidence["verification"] = verify_refusable(applier.conn)
    applier.close()

    verification = evidence["verification"]
    if verification["outcome"] != "REFUSED":
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
    print()
    print(f"cluster       {target['cluster']}")
    print(f"database      {target['database']}  (as {target.get('connected_as')})")
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
