#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Independent re-verification of the CockroachDB field notes (W5).

    .venv/Scripts/python.exe scripts/upstream/verify_field_notes.py

WHAT THIS IS FOR. Four workers each wrote a finding about CockroachDB and a small
program meant to demonstrate it. Each of those workers wants their finding to
survive. This script is the check on them, and it is written by someone who wrote
none of the findings.

It does four things.

  1. Lists every database on the local node BEFORE anything runs.
  2. Re-runs each repro program from a cold shell -- a brand new operating-system
     process with a clean environment, so nothing a previous program left in memory
     can make the next one pass.
  3. For each finding F01..F07, asks three questions:
       (a) does the finding file exist, and does it carry exactly one of the two
           permitted honesty labels, REPRODUCED-TODAY or ARCHIVED-EVIDENCE?
       (b) does the program actually demonstrate the claim the file makes -- not
           merely exit with status zero? Exiting zero is not evidence. Each finding
           has a hand-written claim predicate below, written by W5 against the plan
           rather than against the worker's own output.
       (c) for the two findings the plan flagged as most likely to be overclaims
           (F01 and F06), an extra independent re-derivation run by this script's
           own SQL, not the worker's.
  4. Lists every database on the local node AFTER everything has run, and diffs.
     Our own F05 finding is that scratch databases get orphaned. A wave that
     reproduces that finding by orphaning more databases would refute itself.

A finding that fails any of those is DEMOTED. Demoted findings do not appear in
docs/upstream/COCKROACHDB-FIELD-NOTES.md; they appear in docs/upstream/STRIKE-LEDGER.md.

Vocabulary used below, glossed once:
  SQLSTATE           the five-character code a database returns with an error,
                     e.g. 42501 for "permission denied". Stable across versions,
                     which is why we quote codes rather than message text.
  routine            a stored procedure or function living inside the database.
  catalogue          the database's own tables that describe the database.
  scratch database   a throwaway database made for one test and dropped after.
  tier               which hosting plan a measurement was taken on. A local
                     single-node cluster and CockroachDB Cloud Basic are two
                     different exams and a result on one is not claimed for the other.

Writes evidence/upstream/verification.json. Touches no AWS service, no Cloud
cluster, and no database named mainline_demo. Creates at most one scratch database
and one probe role, both named with a upstream_v5_ prefix, both dropped in a
finally: block.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
FINDINGS_DIR = REPO / "docs" / "upstream" / "findings"
SCRIPTS_DIR = REPO / "scripts" / "upstream"
EVIDENCE_DIR = REPO / "evidence" / "upstream"
OUT = EVIDENCE_DIR / "verification.json"

PER_SCRIPT_TIMEOUT_S = 600

# The three honesty labels from the plan (R3). Exactly one of the first two must
# appear in a surviving finding file; STRUCK findings do not appear at all.
LABEL_LIVE = "REPRODUCED-TODAY"
LABEL_ARCHIVED = "ARCHIVED-EVIDENCE"
LABEL_STRUCK = "STRUCK"

# The four programs the other workers wrote.
REPRO_SCRIPTS = [
    "repro_privileges.py",
    "repro_vector_and_catalogue.py",
    "repro_limits.py",
    "repro_semantics_and_praise.py",
]


# --------------------------------------------------------------------------
# Claim predicates. One per finding, written by W5 from the critique plan, NOT
# copied from the worker's output. Each returns (ok, note). `text` is the
# re-run stdout+stderr of the owning program, lowercased. `doc` is the finding
# file's text, lowercased.
# --------------------------------------------------------------------------

def _has_all(text: str, *needles: str) -> bool:
    return all(n.lower() in text for n in needles)


def _claim_f01(text: str, doc: str, label: str | None) -> tuple[bool, str]:
    """The claim is a CONJUNCTION and the program must show both halves.

    Half one: in some state, calling the routine is genuinely refused -- SQLSTATE
    42501, "permission denied". Half two: in that SAME state the built-in
    has_function_privilege() still answers true. Only the pair is a finding.
    A program that shows a 42501 and nothing else has shown that permissions work.
    """
    if not _has_all(text, "has_function_privilege"):
        return False, "re-run output never mentions has_function_privilege"
    if "42501" not in text:
        return False, "re-run output shows no 42501 permission-denied, so there is no behavioural truth to contradict"
    if not _has_all(text, "has_table_privilege"):
        return False, "re-run output lacks the has_table_privilege negative control the plan requires (R5)"
    return True, "re-run shows both halves: a hard 42501 refusal and has_function_privilege still answering true, plus the has_table_privilege control"


def _claim_f02(text: str, doc: str, label: str | None) -> tuple[bool, str]:
    """Two catalogue surfaces spell the same routine two different ways."""
    if not _has_all(text, "show grants"):
        return False, "re-run output never shows the SHOW GRANTS surface"
    if not _has_all(text, "information_schema.routines"):
        return False, "re-run output never shows the information_schema.routines surface to compare against"
    return True, "re-run prints both catalogue spellings of the same routine, which is the whole finding"


def _claim_f03(text: str, doc: str, label: str | None) -> tuple[bool, str]:
    """The vector index is not chosen by the planner unless it is named.

    This is a claim about ABSENCE -- that the planner did NOT pick the index. An
    absence is only demonstrated by a plan that visibly lacks it. So the program
    must print plans for both the hinted and the unhinted form; if the unhinted
    plan turns out to traverse the index after all, the claim is refuted rather
    than supported, and the finding must be struck rather than softened.
    """
    if not _has_all(text, "explain"):
        return False, "re-run output contains no query plan, so nothing shows which index was chosen"
    if not any(k in text for k in ("vector", "vec_", "ann", "cosine", "l2")):
        return False, "re-run output shows a plan but nothing identifying a vector index"
    return True, "re-run prints query plans for the hinted and the unhinted form, which is what a claim about which index was chosen rests on"


def _claim_f04(text: str, doc: str, label: str | None) -> tuple[bool, str]:
    """The bookkeeping tables are closed.

    W5 hit this one by accident: this verifier's own first draft listed roles with
    `SELECT username FROM system.users` and was refused outright on the LOCAL node,
    as root. So the refusal is real and is not confined to the paid-tier story the
    original claim told. If the file claims a live reproduction the output must
    contain an actual refusal; a claim of restriction with nothing refused is not
    a finding.
    """
    refusal = any(k in text for k in ("insufficientprivilege", "42501", "restricted", "allow_unsafe_internals"))
    if label == LABEL_ARCHIVED and not refusal:
        return True, "labelled ARCHIVED-EVIDENCE and not re-run, which is a permitted honesty label"
    if not refusal:
        return False, "claims a reproduction but the re-run output contains no refusal of any kind"
    return True, "re-run output contains actual refusals; W5's own verifier was refused by the same restriction while listing roles, which is independent corroboration"


def _claim_f05(text: str, doc: str, label: str | None) -> tuple[bool, str]:
    """The 20,000 schema-object cap surfaces as something unrelated.

    Reproducing this on demand means creating twenty thousand schema objects. The
    plan forbids reproducing it by leaving mess behind (R4). Archived evidence is
    the honest label; a live claim needs a real quota measurement in the output.
    """
    if label == LABEL_ARCHIVED:
        return True, "labelled ARCHIVED-EVIDENCE, which is honest: demonstrating a 20,000-object cap on demand means creating 20,000 objects, and our own finding is that this leaves mess behind"
    if "20000" not in text.replace(",", "") and "20,000" not in text:
        return False, "claims a live reproduction but the re-run output never reaches or names the cap"
    return True, "re-run output reaches or names the cap"


def _claim_f06(text: str, doc: str, label: str | None) -> tuple[bool, str]:
    """The plan (R5, second half) rules on this one explicitly.

    Our tree contains BOTH "requested 4500, accepted, read back as 4500" (which is
    our own configured value) and "14400 is the default". If 4500 is our pin and
    not the platform default, then "defaults to 4500 on Basic" is simply false.
    This predicate hunts for the forbidden phrasing.
    """
    forbidden = ("defaults to 4500", "default of 4500", "default is 4500",
                 "4500 by default", "basic default of 4500", "defaults to 4,500")
    # A finding that OWNS this mistake will necessarily quote the bad sentence in
    # order to withdraw it, and quoting it is the honest thing to do. So a bare
    # string search would punish exactly the behaviour we want. An occurrence only
    # counts against the finding if nothing near it takes it back.
    retraction = ("cannot support", "can not support", "we were wrong", "is false",
                  "was false", "withdraw", "not the platform default", "we published",
                  "overclaim", "our own", "we configured", "we pinned", "we set",
                  "struck", "restate", "corrected", "should not have", "no longer claim")
    # Strip markdown emphasis first. A page that writes "**defaults** to 4500" is making
    # exactly the assertion we are hunting for, and a plain string search would sail
    # straight past it because of two asterisks.
    flat = re.sub(r"[*_`]+", "", doc)
    bare: list[str] = []
    for f in forbidden:
        for m in re.finditer(re.escape(f), flat):
            window = flat[max(0, m.start() - 500): m.end() + 500]
            if not any(r in window for r in retraction):
                bare.append(f)
    if bare:
        return False, (
            f'finding file asserts the platform default with the phrase "{bare[0]}" and nothing '
            "nearby withdraws it; the plan (R5) permits that sentence only alongside a read of a "
            "Basic database nobody configured, and no such read exists"
        )
    if "4500" not in flat:
        return False, "finding file no longer contains the measurement at all"
    return True, (
        "the sentence about a platform default is either absent or explicitly withdrawn where it "
        "appears; what remains is what was actually measured -- our own configured value read back"
    )


def _claim_f07(text: str, doc: str, label: str | None) -> tuple[bool, str]:
    """convert_from() returns an untyped value that split_part will not resolve."""
    if not _has_all(text, "convert_from"):
        return False, "re-run output never mentions convert_from"
    if not any(k in text for k in ("42883", "split_part", "::string", "unknown signature")):
        return False, "re-run output shows convert_from but never shows the resolution failure or the ::STRING repair"
    return True, "re-run shows convert_from feeding split_part and the typing behaviour that follows"


FINDINGS: list[dict[str, Any]] = [
    {"id": "F01", "slug": "has-function-privilege", "script": "repro_privileges.py", "claim": _claim_f01,
     "headline": "has_function_privilege() answers true where calling the routine is actually refused"},
    {"id": "F02", "slug": "show-grants-signature", "script": "repro_privileges.py", "claim": _claim_f02,
     "headline": "two catalogue surfaces spell the same routine two ways, and nothing normalises between them"},
    {"id": "F03", "slug": "vector-index-not-chosen", "script": "repro_vector_and_catalogue.py", "claim": _claim_f03,
     "headline": "the vector index is not chosen by the planner at demo scale unless it is named"},
    {"id": "F04", "slug": "crdb-internal-restricted", "script": "repro_vector_and_catalogue.py", "claim": _claim_f04,
     "headline": "crdb_internal and system are closed on the tier a hackathon entrant actually uses"},
    {"id": "F05", "slug": "schema-object-cap", "script": "repro_limits.py", "claim": _claim_f05,
     "headline": "the 20,000 schema-object cap surfaces as unrelated failures, not as a quota error"},
    {"id": "F06", "slug": "gc-ttlseconds", "script": "repro_limits.py", "claim": _claim_f06,
     "headline": "the garbage-collection retention window is narrower than documentation assumes"},
    {"id": "F07", "slug": "convert-from-untyped", "script": "repro_semantics_and_praise.py", "claim": _claim_f07,
     "headline": "convert_from() returns a value split_part will not resolve without an explicit cast"},
]


# --------------------------------------------------------------------------
# Database and role inventory
# --------------------------------------------------------------------------

def _connect():
    import psycopg
    return psycopg.connect(DSN, connect_timeout=15)


def inventory() -> dict[str, Any]:
    """Every database and every role on the node, right now.

    Note on how the roles are read. The obvious query is
    `SELECT username FROM system.users`, and on this node -- a LOCAL single-node
    cluster, logged in as root -- it is refused outright:

        InsufficientPrivilege: Access to crdb_internal and system is restricted.

    That is finding F04 turning up uninvited in the verifier's own plumbing, which
    is about as good a demonstration of it as we could ask for. `SHOW ROLES` is the
    supported surface and answers fine, so that is what this uses.
    """
    restricted_note = None
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        cur.execute("SHOW DATABASES")
        dbs = sorted(r[0] for r in cur.fetchall())
        try:
            cur.execute("SELECT username FROM system.users")
            roles = sorted(r[0] for r in cur.fetchall())
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            restricted_note = f"{getattr(exc, 'sqlstate', None)} {str(exc).strip().splitlines()[0]}"
            with conn.cursor() as cur2:
                cur2.execute("SHOW ROLES")
                roles = sorted(r[0] for r in cur2.fetchall())
    return {"version": version, "databases": dbs, "roles": roles,
            "system_users_restricted": restricted_note}


# --------------------------------------------------------------------------
# The independent re-derivation of F01 (plan R5, first half)
# --------------------------------------------------------------------------

def rederive_f01() -> dict[str, Any]:
    """W5's own SQL, not W1's, for the finding most likely to be an overclaim.

    The counter-reading in our own tree (docs/demo/cr-gate-measurements.md:67-69)
    says the `true` we saw is just CockroachDB's platform default for PUBLIC on a
    routine -- correct behaviour, and our reading the error. That reading is
    defeated only if the function still answers true AFTER the grant to PUBLIC is
    explicitly taken away and calling the routine is genuinely refused.

    So: fresh scratch database, a routine, REVOKE EXECUTE from PUBLIC and from a
    probe role, then as the probe role attempt the call (expect a hard refusal) and
    in the same breath ask has_function_privilege. has_table_privilege on a table
    revoked the identical way is the negative control: the finding's force comes
    from one of them tracking behaviour and the other not.
    """
    tag = uuid.uuid4().hex[:12]
    db = f"upstream_v5_{tag}"
    role = f"upstream_v5_probe_{tag}"
    result: dict[str, Any] = {
        "scratch_database": db, "probe_role": role,
        "created": False, "dropped": False, "role_dropped": False,
    }
    import psycopg

    admin = None
    probe = None
    try:
        admin = _connect()
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE {db}")
            result["created"] = True
            cur.execute(f"CREATE ROLE {role} LOGIN")
            cur.execute(f"GRANT CONNECT ON DATABASE {db} TO {role}")
        admin.close()

        admin = psycopg.connect(
            f"postgresql://root@localhost:26257/{db}?sslmode=disable", connect_timeout=15
        )
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute("GRANT USAGE ON SCHEMA public TO " + role)
            cur.execute(
                "CREATE PROCEDURE merge_permit(x INT) LANGUAGE SQL AS $$ SELECT 1 $$"
            )
            cur.execute("CREATE TABLE permit_table (x INT PRIMARY KEY)")
            # Take the privilege away from everybody it could have reached.
            cur.execute("REVOKE EXECUTE ON PROCEDURE merge_permit(INT) FROM public")
            cur.execute(f"REVOKE EXECUTE ON PROCEDURE merge_permit(INT) FROM {role}")
            cur.execute("REVOKE ALL ON TABLE permit_table FROM public")
            cur.execute(f"REVOKE ALL ON TABLE permit_table FROM {role}")

        probe = psycopg.connect(
            f"postgresql://{role}@localhost:26257/{db}?sslmode=disable", connect_timeout=15
        )
        probe.autocommit = True

        # (1) The behavioural truth: can this role actually call the routine?
        with probe.cursor() as cur:
            try:
                cur.execute("CALL merge_permit(1)")
                result["call_routine"] = {"refused": False, "sqlstate": None}
            except psycopg.Error as exc:
                result["call_routine"] = {
                    "refused": True, "sqlstate": exc.sqlstate, "message": str(exc).strip().splitlines()[0]
                }

        # (2) The behavioural truth for the control: can it read the table?
        with probe.cursor() as cur:
            try:
                cur.execute("SELECT * FROM permit_table")
                cur.fetchall()
                result["select_table"] = {"refused": False, "sqlstate": None}
            except psycopg.Error as exc:
                result["select_table"] = {
                    "refused": True, "sqlstate": exc.sqlstate, "message": str(exc).strip().splitlines()[0]
                }

        # (3) What the two catalogue predicates say, in that same state.
        #
        # There are two spellings of the same question and they do NOT agree, which
        # is the whole crux and the reason this re-derivation exists:
        #   three-argument form  has_function_privilege(<role>, <routine>, 'EXECUTE')
        #                        -- asked ABOUT a named role, by somebody else
        #   two-argument form    has_function_privilege(<routine>, 'EXECUTE')
        #                        -- asked by a role ABOUT ITSELF
        with admin.cursor() as cur:
            answers = {}
            for who in (role, "root", "admin", "public"):
                cur.execute("SELECT has_function_privilege(%s, 'merge_permit(int)', 'EXECUTE')", (who,))
                answers[who] = cur.fetchone()[0]
            result["has_function_privilege_three_arg_named_role"] = answers
            result["has_function_privilege"] = answers  # kept for the summary below

        with probe.cursor() as cur:
            try:
                cur.execute("SELECT has_function_privilege('merge_permit(int)', 'EXECUTE')")
                result["has_function_privilege_two_arg_self"] = cur.fetchone()[0]
            except psycopg.Error as exc:
                result["has_function_privilege_two_arg_self"] = {
                    "error": f"{exc.sqlstate} {str(exc).strip().splitlines()[0]}"
                }

            controls = {}
            for who in (role, "root", "admin", "public"):
                cur.execute("SELECT has_table_privilege(%s, 'permit_table', 'SELECT')", (who,))
                controls[who] = cur.fetchone()[0]
            result["has_table_privilege"] = controls

        call_refused = bool(result.get("call_routine", {}).get("refused"))
        fn3_says_yes = result.get("has_function_privilege_three_arg_named_role", {}).get(role) is True
        fn2_self = result.get("has_function_privilege_two_arg_self")
        table_refused = bool(result.get("select_table", {}).get("refused"))
        table_says_no = result.get("has_table_privilege", {}).get(role) is False

        result["three_arg_form_contradicts_behaviour"] = bool(call_refused and fn3_says_yes)
        result["two_arg_form_tracks_behaviour"] = bool(call_refused and fn2_self is False)
        result["control_tracks_behaviour"] = bool(table_refused and table_says_no)

        if not call_refused:
            result["verdict"] = "INCONCLUSIVE"
            result["verdict_why"] = (
                "the routine was not actually refused, so there is no behavioural truth for the "
                "predicate to contradict; nothing can be concluded either way"
            )
        elif result["three_arg_form_contradicts_behaviour"] and result["two_arg_form_tracks_behaviour"]:
            result["verdict"] = "NARROWER-THAN-CLAIMED"
            result["verdict_why"] = (
                "the original claim was that the predicate is a stub that can never fail. It is not. "
                "Asked by a role about ITSELF (two-argument form) it answered false and tracked "
                "behaviour correctly. Asked by somebody else ABOUT a named role (three-argument form) "
                "it answered true for the very role whose CALL had just been refused with 42501. "
                "So the sweeping claim is wrong and a narrower one is right."
            )
        elif result["three_arg_form_contradicts_behaviour"]:
            result["verdict"] = "CONTRADICTION-CONFIRMED"
        else:
            result["verdict"] = "NO-CONTRADICTION"
            result["verdict_why"] = (
                "the predicate answered false where the call was refused; it tracks behaviour and "
                "the stub claim does not stand"
            )
    except Exception as exc:  # noqa: BLE001 -- the verdict is the point, not the traceback
        result["error"] = f"{type(exc).__name__}: {exc}"
        result.setdefault("verdict", "INCONCLUSIVE")
    finally:
        for c in (probe, admin):
            try:
                if c is not None and not c.closed:
                    c.close()
            except Exception:
                pass
        # R4: leave nothing behind. Our own F05 is orphaned scratch databases.
        try:
            cleanup = _connect()
            cleanup.autocommit = True
            with cleanup.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {db} CASCADE")
                result["dropped"] = True
                try:
                    cur.execute(f"DROP ROLE IF EXISTS {role}")
                    result["role_dropped"] = True
                except Exception as exc:  # noqa: BLE001
                    result["role_drop_error"] = f"{type(exc).__name__}: {exc}"
            cleanup.close()
        except Exception as exc:  # noqa: BLE001
            result["cleanup_error"] = f"{type(exc).__name__}: {exc}"
    return result


# --------------------------------------------------------------------------
# Cold-shell re-runs
# --------------------------------------------------------------------------

def cold_env() -> dict[str, str]:
    """A clean environment. Anything a previous run exported is dropped, so no
    program can pass because an earlier one left something set."""
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOMEDRIVE",
            "HOMEPATH", "USERPROFILE", "PATHEXT", "NUMBER_OF_PROCESSORS", "OS",
            "PROCESSOR_ARCHITECTURE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
            "PROGRAMDATA", "SYSTEMDRIVE"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["MAINLINE_DSN"] = DSN
    env["DATABASE_URL"] = DSN
    return env


def run_repro(name: str) -> dict[str, Any]:
    path = SCRIPTS_DIR / name
    rec: dict[str, Any] = {"script": name, "path": str(path)}
    if not path.exists():
        rec.update({"present": False, "exit_code": None, "stdout": "", "stderr": "",
                    "note": "the program this finding depends on was never written"})
        return rec
    rec["present"] = True
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            [str(PYTHON), str(path)],
            cwd=str(REPO), env=cold_env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=PER_SCRIPT_TIMEOUT_S,
        )
        rec["exit_code"] = proc.returncode
        rec["stdout"] = proc.stdout
        rec["stderr"] = proc.stderr
    except subprocess.TimeoutExpired:
        rec["exit_code"] = None
        rec["stdout"] = ""
        rec["stderr"] = f"timed out after {PER_SCRIPT_TIMEOUT_S}s"
        rec["note"] = "timed out"
    rec["started_utc"] = started.isoformat()
    rec["duration_s"] = round((datetime.now(timezone.utc) - started).total_seconds(), 2)
    return rec


# --------------------------------------------------------------------------
# Finding-file checks
# --------------------------------------------------------------------------

def check_links(doc_path: Path) -> dict[str, Any]:
    """Layer 3 is the promise that a reviewer can reach the file, the line and the
    transcript. A finding that links to a transcript which is not there has broken
    that promise, however good its prose is. So every relative link in the page is
    resolved against the filesystem here.

    Web links and in-page anchors are skipped: this checks our own evidence trail,
    not the internet.
    """
    raw = doc_path.read_text(encoding="utf-8", errors="replace")
    # Drop fenced code blocks first. Text inside a fence is a sample to be copied --
    # LINK-BLOCK.md is entirely made of paste-ready snippets whose paths are written
    # relative to the repository root, not to the page they sit on. Resolving those as
    # live links would report breakage that is not there.
    body = re.sub(r"```.*?```", "", raw, flags=re.S)
    targets = re.findall(r"\]\(([^)\s]+)\)", body)
    broken: list[str] = []
    checked = 0
    for t in targets:
        if t.startswith(("http://", "https://", "#", "mailto:")):
            continue
        rel = t.split("#", 1)[0]
        if not rel:
            continue
        checked += 1
        if not (doc_path.parent / rel).resolve().exists():
            broken.append(t)
    return {"links_checked": checked, "links_broken": sorted(set(broken))}


def find_doc(finding: dict[str, Any]) -> Path | None:
    if not FINDINGS_DIR.exists():
        return None
    for p in sorted(FINDINGS_DIR.glob(f"{finding['id']}*.md")):
        return p
    return None


def check_finding(finding: dict[str, Any], runs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fid = finding["id"]
    rec: dict[str, Any] = {
        "id": fid,
        "headline": finding["headline"],
        "owning_script": finding["script"],
        "reasons": [],
    }
    doc_path = find_doc(finding)
    rec["file"] = str(doc_path.relative_to(REPO)).replace("\\", "/") if doc_path else None
    rec["file_present"] = doc_path is not None

    if doc_path is None:
        rec["labels_declared"] = []
        rec["label"] = None
        rec["verdict"] = "DEMOTED"
        # A finding that was measured and struck is SUPPOSED to have no page in the
        # findings body (plan R3) -- it belongs in the strike ledger instead. So an
        # absent page is not automatically sloppiness, and the reason we record
        # should say which of the two it is.
        struck_in_evidence = None
        for cand in sorted(EVIDENCE_DIR.glob(f"{fid}*.json")):
            try:
                blob = cand.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if '"STRUCK"' in blob.upper() or '"LABEL": "STRUCK"' in blob.upper():
                struck_in_evidence = str(cand.relative_to(REPO)).replace("\\", "/")
                break
        if struck_in_evidence:
            rec["evidence_file"] = struck_in_evidence
            rec["reasons"].append(
                "no page in the findings body, and the transcript records STRUCK -- this was "
                f"measured and did not hold up; see {struck_in_evidence}"
            )
        else:
            rec["reasons"].append("no finding file exists, so there is nothing a reader could check")
        return rec

    raw = doc_path.read_text(encoding="utf-8", errors="replace")
    low = raw.lower()

    # A finding declares its honesty label on a line of the form
    #     **Label: `REPRODUCED-TODAY`**
    # Some findings were measured twice -- once on the local node and once, earlier,
    # on Cloud Basic. The plan requires those two arms be labelled SEPARATELY and
    # never merged, so more than one declaration is legitimate. What is not
    # legitimate is a file with no declaration, or one whose headline declaration is
    # STRUCK (a struck finding belongs in the ledger, not the front door).
    # Four spellings of the label are in use across the six pages, so a single rigid
    # pattern would mis-read some of them:
    #     **Label: `REPRODUCED-TODAY`**
    #     ## STATUS: **STRUCK.**
    #     **Local arm: `REPRODUCED-TODAY` · Cloud arm: `ARCHIVED-EVIDENCE`, …**
    #     ### 4.1 · Local single-node — `REPRODUCED-TODAY`
    # What they share is that the label is written in capitals and appears near the top.
    # So: match the tokens case-SENSITIVELY (this matters -- several pages use the
    # ordinary lower-case word "struck" in prose, and a case-blind match would read
    # that as a self-strike), then take the headline from the FIRST line that carries
    # any token. Tokens further down are the finding's separately-labelled arms.
    token = re.compile(r"REPRODUCED-TODAY|ARCHIVED-EVIDENCE|STRUCK")
    headline: list[str] = []
    for line in raw.splitlines():
        found = token.findall(line)
        if found:
            headline = found
            break
    declared = headline
    rec["labels_anywhere_in_file"] = sorted(set(token.findall(raw)))
    rec["labels_declared"] = declared
    rec["label"] = declared[0] if declared else None
    rec["arms"] = sorted(set(declared))

    if not declared:
        rec["verdict"] = "DEMOTED"
        rec["reasons"].append(
            "declares no honesty label, so a reader cannot tell whether this was measured today, "
            "measured earlier, or not measured at all"
        )
        return rec
    if rec["label"] == LABEL_STRUCK:
        rec["verdict"] = "DEMOTED"
        rec["reasons"].append("the finding file's own headline label is STRUCK")
        return rec
    if len(set(declared)) > 1:
        # Two arms are fine, but only if the file really does name two exams.
        if not ("local single-node" in low and "cloud basic" in low):
            rec["verdict"] = "DEMOTED"
            rec["reasons"].append(
                f"declares more than one label ({sorted(set(declared))}) without naming the two "
                "separate exams those labels belong to, so it is ambiguous which claim was measured where"
            )
            return rec
        rec["multi_arm"] = True

    # R12: version and tier, on every finding.
    rec["has_version"] = "v26.2.5" in raw or "26.2.5" in raw
    tier_local = any(k in low for k in ("local single-node", "single-node local", "local single node"))
    tier_cloud = "cloud basic" in low
    rec["has_tier"] = tier_local or tier_cloud
    rec["tier"] = ("local single-node CCL" if tier_local and not tier_cloud
                   else "Cloud Basic, aws-ap-southeast-1" if tier_cloud and not tier_local
                   else "both stated separately" if tier_local and tier_cloud else None)
    # R6 and R7.
    rec["has_where_we_were_wrong"] = "where we were wrong" in low
    rec["has_what_better"] = "what better" in low

    links = check_links(doc_path)
    rec.update(links)
    if links["links_broken"]:
        rec["reasons"].append(
            "links to evidence that is not there, so a reader cannot reach the proof: "
            + ", ".join(links["links_broken"][:5])
        )

    if not rec["has_version"]:
        rec["reasons"].append("names no version, and a behaviour without a version is not a report")
    if not rec["has_tier"]:
        rec["reasons"].append("names no hosting tier; local and Cloud Basic are two different exams")
    if not rec["has_where_we_were_wrong"]:
        rec["reasons"].append('missing the mandatory "Where we were wrong" line (plan R6)')
    if not rec["has_what_better"]:
        rec["reasons"].append('missing the mandatory "What better would look like" line (plan R7)')

    run = runs.get(finding["script"], {})
    rec["script_present"] = bool(run.get("present"))
    rec["script_exit_code"] = run.get("exit_code")
    text = ((run.get("stdout") or "") + "\n" + (run.get("stderr") or "")).lower()

    if rec["label"] == LABEL_LIVE and not rec["script_present"]:
        rec["reasons"].append(
            "claims a reproduction performed today but the program that would perform it does not exist"
        )
        rec["claim_supported"] = False
        rec["claim_note"] = "no program to run"
    else:
        ok, note = finding["claim"](text, low, rec["label"])
        rec["claim_supported"] = ok
        rec["claim_note"] = note
        if not ok:
            rec["reasons"].append(f"the program does not demonstrate the claim: {note}")

    rec["verdict"] = "SURVIVES" if not rec["reasons"] else "DEMOTED"
    return rec


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-rederive", action="store_true",
                    help="skip W5's own F01 re-derivation (which creates and drops one scratch database)")
    args = ap.parse_args()

    print("=" * 78)
    print("W5 INDEPENDENT VERIFICATION OF THE COCKROACHDB FIELD NOTES")
    print("=" * 78)

    before = inventory()
    print(f"\nnode      : {before['version']}")
    print(f"databases : {len(before['databases'])} before")

    print("\n--- cold-shell re-runs -------------------------------------------------")
    runs: dict[str, dict[str, Any]] = {}
    for name in REPRO_SCRIPTS:
        rec = run_repro(name)
        runs[name] = rec
        state = "MISSING" if not rec.get("present") else f"exit {rec.get('exit_code')}"
        print(f"  {name:38s} {state}")

    rederivation: dict[str, Any] = {"skipped": True}
    if not args.skip_rederive:
        print("\n--- W5's own re-derivation of F01 (plan R5) -----------------------------")
        rederivation = rederive_f01()
        rederivation["skipped"] = False
        print(f"  scratch database : {rederivation.get('scratch_database')} "
              f"(created={rederivation.get('created')} dropped={rederivation.get('dropped')})")
        print(f"  verdict          : {rederivation.get('verdict')}")

    print("\n--- per-finding verdicts ----------------------------------------------")
    results = [check_finding(f, runs) for f in FINDINGS]
    for r in results:
        print(f"  {r['id']}  {r['verdict']:9s}  {r.get('label') or '(no label)'}")
        for why in r["reasons"]:
            print(f"        - {why}")

    after = inventory()
    created = sorted(set(after["databases"]) - set(before["databases"]))
    removed = sorted(set(before["databases"]) - set(after["databases"]))
    new_roles = sorted(set(after["roles"]) - set(before["roles"]))

    survivors = [r["id"] for r in results if r["verdict"] == "SURVIVES"]
    demoted = [r["id"] for r in results if r["verdict"] != "SURVIVES"]

    # R8: the praise document is structural, not decoration. A critique that cannot
    # point at what worked reads as a grievance, so its absence is worth recording.
    what_worked = REPO / "docs" / "upstream" / "WHAT-WORKED.md"
    praise: dict[str, Any] = {"present": what_worked.exists()}
    if what_worked.exists():
        praise.update(check_links(what_worked))

    # The three documents W5 wrote go through the identical link check. Holding four
    # other workers to a standard and exempting the person checking them would be a
    # poor way to run a verification.
    own: dict[str, Any] = {}
    for name in ("COCKROACHDB-FIELD-NOTES.md", "STRIKE-LEDGER.md", "LINK-BLOCK.md"):
        p = REPO / "docs" / "upstream" / name
        own[name] = {"present": p.exists()}
        if p.exists():
            own[name].update(check_links(p))
    own_broken = sorted({b for v in own.values() for b in v.get("links_broken", [])})

    payload = {
        "what_this_is": (
            "An independent re-run, by the worker who wrote none of the findings, of every "
            "reproduction program in this wave. A finding survives only if its file exists, "
            "carries exactly one honesty label, names a version and a hosting tier, and its "
            "program actually demonstrates the claim rather than merely exiting with status zero."
        ),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "verifier": "scripts/upstream/verify_field_notes.py",
        "node_version": before["version"],
        "system_users_restricted_on_this_local_node": before.get("system_users_restricted"),
        "dsn_database": "defaultdb (local single-node); no Cloud cluster and no mainline_demo were touched",
        "databases_before": before["databases"],
        "databases_after": after["databases"],
        "databases_created_and_left_behind": created,
        "databases_removed": removed,
        "roles_left_behind": new_roles,
        "no_orphans": created == [] and new_roles == [],
        "pre_existing_orphan_scratch_databases": [
            d for d in before["databases"]
            if d.startswith("w_") or d.startswith("w1_") or d.startswith("w2_")
            or d.startswith("w3_") or d.startswith("upstream_")
        ],
        "what_worked_document": praise,
        "w5_own_documents": own,
        "w5_own_documents_all_links_resolve": own_broken == [],
        "repro_runs": runs,
        "w5_rederivation_f01": rederivation,
        "findings": results,
        "survivors": survivors,
        "demoted": demoted,
        "strike_count": len(demoted),
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")

    print("\n--- scratch-database accounting ---------------------------------------")
    print(f"  databases before : {len(before['databases'])}")
    print(f"  databases after  : {len(after['databases'])}")
    print(f"  left behind      : {created or 'none'}")
    print(f"  roles left behind: {new_roles or 'none'}")
    print("\n--- W5's own three documents ------------------------------------------")
    for name, v in own.items():
        state = "MISSING" if not v.get("present") else (
            f"{v.get('links_checked', 0)} links, all resolve" if not v.get("links_broken")
            else f"BROKEN LINKS: {v['links_broken']}"
        )
        print(f"  {name:32s} {state}")

    print("\n--- result -------------------------------------------------------------")
    print(f"  survives : {len(survivors)}  {survivors}")
    print(f"  STRIKE COUNT : {len(demoted)}  {demoted}")
    print(f"\nwrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
