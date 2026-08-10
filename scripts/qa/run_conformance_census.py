# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Execute the TRAPPOINT conformance suite to completion and publish a per-case census.

```bash
python scripts/qa/run_conformance_census.py --build
python scripts/qa/run_conformance_census.py --dsn "$LOCAL_DSN" --run-id 20260810T000000Z
```

**What this script is for.** ``docs/HONESTY.md`` has said, in those words, that *this
census demonstrates no conformance case*: the suite existed, imported, and had never been
executed end to end against a migrated MAINLINE schema. This script executes it and
accounts for every case the manifest declares by name — pass, fail and cannot-run — with a
reason a stranger can check attached to every non-pass.

**It does not tune the run.** It never passes ``--requires`` (which would declare a token
satisfied on a human's say-so), never edits a case, never edits the manifest, and never
narrows the selection. It passes ``--autodetect-requires`` so that an unmet capability is
*measured* against ``pg_class`` / ``pg_roles`` / ``pg_policies`` and reported as a
cannot-run naming the object, rather than shrugged off as a skip. The pass count is an
observation, not a target.

**The exit code is about completeness, not greenness**, and that is deliberate — a red
census that accounts for all 71 cases is the deliverable; a green one that accounted for
30 would be worthless:

``0``
    the census is complete — every declared case carries a status, no case is ``PENDING``,
    no case ``ERROR``ed, and every non-``PASSED`` case carries a reason naming an object.
``1``
    the census was written but is not complete: a ``PENDING`` (no implementation), an
    ``ERROR`` (the runner itself broke), or a non-pass whose reason names nothing an
    engineer could go and look at.
``2``
    the census could not be produced at all — no database, no manifest, no corpus.

**Reproducibility.** ``--run-id`` pins the tenancy scope, and every case's ``site_id`` is
``uuid5(namespace, f"{run_id}:{case_id}")`` (see ``trappoint_conformance.site``). The
census publishes the ``site_id`` it derived for each case and a ``census_digest`` over the
``(id, status)`` rows, and when it overwrites an earlier census that carried the same
``run_id`` it *compares* the two and publishes the comparison. A second run with the same
``--run-id`` therefore proves its own reproducibility, in the artefact, without a human
diffing anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFORMANCE_SRC = REPO_ROOT / "packages" / "trappoint-conformance" / "src"
CONFORMANCE_CASES = REPO_ROOT / "packages" / "trappoint-conformance"

for _path in (CONFORMANCE_SRC, CONFORMANCE_CASES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from trappoint_conformance.manifest import (  # noqa: E402  — after the sys.path graft
    Case,
    Manifest,
    ManifestError,
    load_manifest,
)
from trappoint_conformance.site import scope_for  # noqa: E402

EXIT_COMPLETE = 0
EXIT_INCOMPLETE = 1
EXIT_CANNOT_PRODUCE = 2

DEFAULT_DATABASE = "prod_w9"

#: The local node, addressed by **literal IPv4 address and never by name**. MEASURED on
#: this machine, 2026-08-10, with the node up and answering:
#:
#: ==================  ====================
#: host                connect + ``SELECT 1``
#: ==================  ====================
#: ``localhost``       130.05 s
#: ``127.0.0.1``        0.00 s
#: ==================  ====================
#:
#: Windows resolves ``localhost`` to ``::1`` first; the container publishes on IPv4 only,
#: so every connection pays a full IPv6 connect timeout before falling back. One
#: connection is a nuisance; a chain driver that opens one per phase, and a conformance
#: run that opens one per probe, turn a ten-minute build into an apparent hang — which is
#: exactly how this was found, after two builds were killed for looking stuck when they
#: were merely resolving. ``justfile``'s ``LOCAL_DSN`` has always used ``127.0.0.1``; this
#: constant now agrees with it, and the ``--dsn`` handed to the chain driver overrides its
#: own ``localhost`` default for the same reason.
LOCAL_NODE = "postgresql://root@127.0.0.1:26257/{database}?sslmode=disable"

DEFAULT_JSON = Path("qa/conformance-census.json")
DEFAULT_MD = Path("docs/release/conformance-census.md")

#: The sentence §9 of the specification permits, quoted verbatim in the rendered document
#: because a census that stated its own entitlement in its own words would be a second
#: source of truth about what conformance means.
SPEC_README = Path("spec/conformance/README.md")

STATUS_ORDER = ("passed", "failed", "cannot_run", "skipped", "pending", "error")

STATUS_MARK = {
    "passed": "PASS",
    "failed": "FAIL",
    "cannot_run": "CANNOT RUN",
    "skipped": "SKIPPED",
    "pending": "PENDING",
    "error": "ERROR",
}

STATUS_MEANS = {
    "passed": "the database refused exactly as the manifest says it must",
    "failed": "it did not — including a relation reported absent, named here",
    "cannot_run": "nothing was asked of the gate: the legal world would not build, or a "
    "declared capability was measured absent",
    "skipped": "a capability token was unmet and nobody looked (should not occur under "
    "--autodetect-requires)",
    "pending": "the manifest declares the case and no implementation exists",
    "error": "the runner itself broke — always fatal",
}


class CensusError(Exception):
    """The census could not be produced. Exit 2, never a partial artefact."""


#: ``CREATE DATABASE`` and ``DROP DATABASE`` cannot run inside the migration runner's own
#: connection (they are cluster-level DDL against a database that may not exist yet), so
#: they go through a one-shot child. Held as constants rather than inline argv strings so
#: the SQL is readable in one place and the argv lists stay short.
_RESET_DATABASE = (
    "import sys, psycopg\n"
    "conn = psycopg.connect(sys.argv[1], autocommit=True)\n"
    "conn.execute('DROP DATABASE IF EXISTS ' + sys.argv[2] + ' CASCADE')\n"
    "conn.execute('CREATE DATABASE ' + sys.argv[2])\n"
    "conn.close()\n"
)

_DROP_DATABASE = (
    "import sys, psycopg\n"
    "conn = psycopg.connect(sys.argv[1], autocommit=True)\n"
    "conn.execute('DROP DATABASE IF EXISTS ' + sys.argv[2] + ' CASCADE')\n"
    "conn.close()\n"
)


# ─────────────────────────────────────────────────────────────────────────────
# The database
# ─────────────────────────────────────────────────────────────────────────────


def _venv_bin(name: str) -> Path | None:
    """Return the repository venv's console script for *name*, if it is installed.

    Windows and POSIX layouts differ (``Scripts`` vs ``bin``, ``.exe`` vs bare) and this
    script is run on both, so the lookup is by existence rather than by platform test.
    """
    for directory, suffix in ((".venv/Scripts", ".exe"), (".venv/bin", "")):
        candidate = REPO_ROOT / directory / f"{name}{suffix}"
        if candidate.is_file():
            return candidate
    found = shutil.which(name)
    return Path(found) if found else None


def _python() -> str:
    """The interpreter that runs child processes: this one, always.

    ``sys.executable`` and not ``python``: the census is run from the repository venv and
    a child that resolved ``python`` off PATH could import a different ``psycopg``.
    """
    return sys.executable


def _run(cmd: Sequence[str | Path], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a child process, capturing both streams as text."""
    return subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


_DSN_IN_TEXT = re.compile(r"postgres(?:ql)?://\S+")


def _dsn_from_output(text: str) -> str | None:
    """Return the last DSN a child process printed, or None.

    The *last* one on purpose: a chain driver that echoes its inputs before it echoes the
    database it built would otherwise hand back the DSN it was given.
    """
    found = _DSN_IN_TEXT.findall(text)
    return found[-1].rstrip("'\",;") if found else None


def _build_via_chain_script(database: str, keep: bool) -> tuple[str, dict[str, Any]] | None:
    """Drive ``scripts/chain/apply_chain.py --keep`` and reuse the DSN it prints.

    Returns ``None`` when that script is not in the tree, so the caller can fall through
    to the deployment runner. It is **not** re-implemented here: this wave's chain driver
    is owned by another worker and this function only calls it and reads its output.
    """
    script = REPO_ROOT / "scripts" / "chain" / "apply_chain.py"
    if not script.is_file():
        return None

    # `apply_chain` issues a bare `CREATE DATABASE` — it documents the database as
    # "CREATEd, never reused" — so a census database left over from a previous run makes
    # it refuse before it starts. The census owns this database, so the census clears it.
    reset = _run(
        [_python(), "-c", _DROP_DATABASE, LOCAL_NODE.format(database="defaultdb"), database]
    )
    if reset.returncode != 0:
        raise CensusError(f"could not clear database {database}: {reset.stderr.strip()}")

    cmd = [
        _python(),
        str(script),
        "--keep",
        "--database",
        database,
        # Its own default is `postgresql://root@localhost:…`, and on this host `localhost`
        # costs 130 s per connect against 0.00 s for `127.0.0.1` (see LOCAL_NODE). The
        # census passes the address so the build is not spent in the resolver.
        "--dsn",
        LOCAL_NODE.format(database="defaultdb"),
        # `each` is the RECORD mode and belongs to the chain artefact, which is where a
        # per-file attestation claim is made. The conformance suite reads none of that —
        # it needs a migrated schema and nothing else — and `each` recomputes a schema
        # fingerprint after every one of 271 statements, turning a ten-minute census into
        # a thirty-minute one. `just conform-census` has to be a command somebody runs.
        "--attest",
        "final",
        # The chain worker owns `evidence/`. A census that scattered files into another
        # worker's tree would be writing outside its declared paths, so it does not.
        "--no-evidence",
    ]
    proc = _run(cmd)
    combined = f"{proc.stdout}\n{proc.stderr}"
    dsn = _dsn_from_output(combined)
    if proc.returncode != 0 or dsn is None:
        raise CensusError(
            f"scripts/chain/apply_chain.py exited {proc.returncode} and the census could "
            f"not read a DSN from its output. Last 2000 characters:\n{combined[-2000:]}"
        )

    # The chain driver REDACTS the DSN before printing it. That is right of it — the
    # evidence file records argv verbatim and "verbatim" must never mean "including a
    # credential" — but a redacted password is not a password, so connecting with it would
    # fail with an authentication error the reader would then go and debug as a schema
    # problem. On the local passwordless node redaction is a no-op and this never fires;
    # against a cluster that has one, the census rebuilds the DSN rather than pretending.
    redacted = ":***@" in dsn
    if redacted:
        dsn = LOCAL_NODE.format(database=database)

    return dsn, {
        "method": "scripts/chain/apply_chain.py",
        "command": " ".join(str(c) for c in cmd),
        "returncode": proc.returncode,
        "keep": keep,
        "dsn_was_redacted_in_output": redacted,
        "tail": combined.strip().splitlines()[-12:],
    }


def _build_via_deployment_runner(database: str) -> tuple[str, dict[str, Any]]:
    """Bootstrap and apply the tree through ``trappoint migrate`` — the deployment runner.

    The fallback when ``scripts/chain/apply_chain.py`` is not in the tree. This is not a
    re-implementation of the chain drive; it is the *same* CLI a deployment uses, invoked
    with the same two subcommands, and the census records which of the two paths built the
    database so a reader is never left guessing what "--build" meant on the day it ran.
    """
    trappoint = _venv_bin("trappoint")
    if trappoint is None:
        raise CensusError(
            "neither scripts/chain/apply_chain.py nor the `trappoint` console script is "
            "available, so --build cannot construct a migrated database. Install the "
            "workspace (`uv sync --all-packages`, or `pip install -e "
            "packages/trappoint-migrate`) or pass --dsn for a database you built yourself."
        )
    dsn = LOCAL_NODE.format(database=database)
    steps: list[dict[str, Any]] = []

    # DROP then CREATE, always. A migration tree is forward-only, so `up` against a
    # database that already carries the tree is a no-op and the "fresh build" would be
    # last week's schema wearing today's timestamp. It is also the recovery the producers
    # plan §1.6 prescribes after a halt: a fresh database per attempt, never
    # `trappoint migrate force`. This database belongs to the census; nothing else may.
    create = _run(
        [
            _python(),
            "-c",
            _RESET_DATABASE,
            LOCAL_NODE.format(database="defaultdb"),
            database,
        ]
    )
    steps.append({"step": "drop + create database", "returncode": create.returncode})
    if create.returncode != 0:
        raise CensusError(f"could not create database {database}: {create.stderr.strip()}")

    runs: tuple[tuple[str, list[str | Path]], ...] = (
        ("bootstrap", [trappoint, "migrate", "bootstrap", "--dsn", dsn]),
        (
            "up",
            [
                trappoint,
                "migrate",
                "up",
                "--dsn",
                dsn,
                "--tree",
                "mainline",
                "--migrations",
                "verticals/mainline/db/migrations",
                "--attest",
                "final",
            ],
        ),
    )
    for label, argv in runs:
        proc = _run(argv)
        combined = f"{proc.stdout}\n{proc.stderr}".strip()
        steps.append(
            {
                "step": label,
                "command": " ".join(str(c) for c in argv),
                "returncode": proc.returncode,
                "tail": combined.splitlines()[-8:],
            }
        )
        if proc.returncode != 0 and label == "bootstrap":
            raise CensusError(f"trappoint migrate bootstrap failed: {combined[-2000:]}")

    return dsn, {
        "method": "trappoint migrate bootstrap + up (deployment runner)",
        "note": (
            "scripts/chain/apply_chain.py was not in the tree at census time; the census "
            "drove the deployment runner directly. A non-zero `up` return code is "
            "RECORDED, not hidden: the suite is then run against whatever the tree did "
            "apply, and every case that needs an unapplied object reports it by name."
        ),
        "steps": steps,
    }


def _cluster_version(dsn: str) -> str:
    """``SELECT version()`` — a claim of conformance cites the version it was made at."""
    import psycopg

    with psycopg.connect(dsn, autocommit=True, application_name="conformance-census") as conn:
        row = conn.execute("SELECT version()").fetchone()
    return str(row[0]) if row else "<unknown>"


def _applied_migrations(dsn: str) -> dict[str, Any]:
    """How much of the tree is actually in this database, straight from the ledger.

    Every ``CANNOT RUN: relation … does not exist`` below is only worth reading next to
    this: a census taken against a half-applied tree and one taken against a complete tree
    say the same words about very different situations. The ledger's own
    ``schema_migration.state`` is reported as a distribution rather than reduced to a
    boolean, because *which* non-applied state a row is in (``dirty``, ``failed``) is the
    difference between a halt and a refusal.
    """
    import psycopg

    out: dict[str, Any] = {"tree_files_on_disk": None, "applied": None, "by_state": None}
    tree = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"
    if tree.is_dir():
        out["tree_files_on_disk"] = len(sorted(tree.glob("*.sql")))
    try:
        with psycopg.connect(dsn, autocommit=True, application_name="conformance-census") as conn:
            row = conn.execute("SELECT count(*) FROM trappoint.schema_migration").fetchone()
            out["applied"] = int(row[0]) if row else None
            rows = conn.execute(
                "SELECT state::STRING, count(*) FROM trappoint.schema_migration GROUP BY 1"
            ).fetchall()
            out["by_state"] = {str(r[0]): int(r[1]) for r in rows}
    except psycopg.Error as exc:
        out["error"] = f"could not read trappoint.schema_migration: {exc}".strip()
    return out


def _drop_database(database: str) -> str:
    """Drop the census database. Reported, never silent."""
    proc = _run(
        [
            _python(),
            "-c",
            _DROP_DATABASE,
            LOCAL_NODE.format(database="defaultdb"),
            database,
        ]
    )
    if proc.returncode != 0:
        return f"DROP DATABASE {database} FAILED: {proc.stderr.strip()}"
    return f"DROP DATABASE {database} CASCADE"


# ─────────────────────────────────────────────────────────────────────────────
# The suite
# ─────────────────────────────────────────────────────────────────────────────


def _conform_argv(dsn: str, profile: str, run_id: str | None, manifest: Path | None) -> list[str]:
    """The exact command line the census runs, published verbatim in both artefacts.

    The installed ``trappoint-conform`` console script when there is one — that is the
    command a judge types, and publishing a different one would make the header a
    paraphrase. ``python -m trappoint_conformance.cli`` is the fallback for a checkout
    where the distribution is on ``PYTHONPATH`` but no script shim was written.

    ``--autodetect-requires`` is here and ``--requires`` is deliberately not: the first is
    a measurement against the live catalogues, the second is a human's assertion, and a
    census that accepted the second would be a census that could be made greener by typing.
    """
    console = _venv_bin("trappoint-conform")
    head: list[str] = (
        [str(console)] if console is not None else [_python(), "-m", "trappoint_conformance.cli"]
    )
    argv = [
        *head,
        "--dsn",
        dsn,
        "--profile",
        profile,
        "--autodetect-requires",
        "--json",
    ]
    if run_id:
        argv += ["--run-id", run_id]
    if manifest:
        argv += ["--manifest", str(manifest)]
    return argv


def _run_suite(argv: Sequence[str]) -> tuple[dict[str, Any], str]:
    """Run ``trappoint-conform`` and parse its JSON. Returns ``(report, stderr)``."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    graft = os.pathsep.join(str(p) for p in (CONFORMANCE_SRC, CONFORMANCE_CASES))
    env["PYTHONPATH"] = f"{graft}{os.pathsep}{existing}" if existing else graft

    proc = subprocess.run(
        list(argv),
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    stdout = proc.stdout.strip()
    if not stdout:
        raise CensusError(
            f"trappoint-conform printed nothing on stdout (exit {proc.returncode}). "
            f"stderr:\n{proc.stderr.strip()[-2000:]}"
        )
    brace = stdout.find("{")
    if brace < 0:
        raise CensusError(f"trappoint-conform printed no JSON object:\n{stdout[-2000:]}")
    try:
        report = json.loads(stdout[brace:])
    except json.JSONDecodeError as exc:
        raise CensusError(
            f"trappoint-conform's --json output did not parse: {exc}\n{stdout[-2000:]}"
        ) from exc
    return report, proc.stderr.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Reasons
# ─────────────────────────────────────────────────────────────────────────────

#: A reason "names an object" when it contains something an engineer can go and look at:
#: a schema-qualified relation, a quoted identifier, a capability token, a constraint or
#: function name, or a SQLSTATE. Checked rather than assumed, because *every non-pass
#: carries a reason a stranger can check* is the contract this whole artefact is for, and
#: a contract nobody verifies is a wish.
_OBJECTISH = (
    re.compile(r"\b[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\b"),  # schema.relation, fn calls
    re.compile(r'"[^"]+"'),  # quoted identifier
    re.compile(r"\b(?:role|policy):\S+"),  # capability token
    # A SQLSTATE, and the digit lookahead is not pedantry: a bare `[0-9A-Z]{5}` matches
    # the literal word ERROR, so a reason that said nothing but "ERROR" would have been
    # scored as naming an object and the completeness gate would have passed a vacuous
    # sentence. The gate is only worth having if it cannot be satisfied by its own labels.
    re.compile(r"\b(?=[0-9A-Z]{5}\b)(?=[0-9A-Z]*[0-9])[0-9A-Z]{5}\b"),
    re.compile(r"\b(?:gate|trg|fn|chk|ck)_[a-z0-9_]+\b"),  # exhibit names
)


def _names_an_object(reason: str) -> bool:
    """Whether *reason* names something a reader could go and inspect."""
    return any(pattern.search(reason) for pattern in _OBJECTISH)


#: ``building the LEGAL world failed at 'clause_version'`` -> ``'clause_version'``.
_WORLD_STEP = re.compile(r"failed at ('[^']+'|\"[^\"]+\")")

#: Everything after the runner's ``Cause:`` marker — the driver's own sentence, which is
#: the part that names the column, relation or constraint the setup tripped over.
_WORLD_CAUSE = re.compile(r"Cause:\s*(.+)\Z", re.S)


def _reason_failed(case: Case, result: Mapping[str, Any], detail: str) -> str:
    """``FAIL: expected <state> <exhibit>, observed <state> <exhibit>``, then the detail.

    The manifest's expectation goes beside the observation so the sentence is readable
    without the manifest open, which is the whole test of whether a stranger can check it.
    """
    state = result.get("observed_sqlstate")
    constraint = result.get("observed_constraint")
    observed = (
        f"{state or '<none>'} {constraint or '<no exhibit>'}"
        if (state or constraint)
        else "no refusal at all (the history completed)"
    )
    head = f"FAIL: expected {case.expect_sqlstate} {case.expect_constraint}, observed {observed}"
    if result.get("exhibit_weakened"):
        head += " (exhibit INFERRED from the message, not reported by the driver)"
    return f"{head}. {detail}" if detail else head


def _reason_cannot_run(case: Case, detail: str) -> str:
    """Either *the world would not build* or *a required object was measured absent*.

    Both are cannot-runs and both must name their object, but they are different sentences
    about different things and the report never merges them.
    """
    body = detail
    for prefix in ("CANNOT RUN — ", "CANNOT RUN - ", "CANNOT RUN: "):
        if body.startswith(prefix):
            body = body[len(prefix) :]
            break
    if body.startswith("WORLD NOT BUILT"):
        step = _WORLD_STEP.search(body)
        cause = _WORLD_CAUSE.search(body)
        where = f" at {step.group(1)}" if step else ""
        why = " ".join(cause.group(1).split()) if cause else " ".join(body.split())
        return (
            f"CANNOT RUN: legal world could not be built{where} — {why}. "
            f"Nothing was asked of the gate, so this is not a red gate: it is a setup "
            f"statement the database refused."
        )
    required = ", ".join(case.requires) or "<no capability token>"
    return f"CANNOT RUN: {body or f'requires {required}'}"


def _reason_for(case: Case, result: Mapping[str, Any]) -> str:
    """Build the published reason for one non-``PASSED`` case."""
    status = str(result.get("status", ""))
    detail = str(result.get("detail", "")).strip()
    required = ", ".join(case.requires) or "<no capability token>"

    if status == "failed":
        return _reason_failed(case, result, detail)
    if status == "cannot_run":
        return _reason_cannot_run(case, detail)
    if status == "skipped":
        return (
            f"SKIPPED: requires {required}, and no probe result was available for it. "
            f"{detail}".strip()
        )
    if status == "pending":
        return (
            f"PENDING: the manifest declares {case.id} and no implementation is registered "
            f"for it in the conformance corpus (packages/trappoint-conformance/cases). "
            f"{detail}".strip()
        )
    return f"ERROR: the runner itself broke on {case.id} — {detail or '<no detail>'}"


def _pass_note(case: Case, result: Mapping[str, Any]) -> str:
    """One line for a green case, so a reader sees what it actually observed."""
    detail = str(result.get("detail", "")).strip()
    if case.cls == "admit":
        return detail or f"{case.id}: the legal history was admitted (00000)"
    observed = (
        f"{result.get('observed_sqlstate') or case.expect_sqlstate} on "
        f"{result.get('observed_constraint') or case.expect_constraint}"
    )
    return f"refused {observed}. {detail}".strip()


# ─────────────────────────────────────────────────────────────────────────────
# The census
# ─────────────────────────────────────────────────────────────────────────────


#: Values that vary run to run and must not split one cause into forty. Scope uuids and
#: per-case external refs are the only two: everything else in a driver message is signal.
_VOLATILE = (
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "<site_id>"),
    (re.compile(r"\bconf-cf\d+[a-z0-9-]*", re.I), "<external_ref>"),
    (re.compile(r"\bCF-\d+\b"), "<case>"),
)


def _cause_signature(row: Mapping[str, Any]) -> str:
    """Normalise one non-pass reason to the defect it is an instance of.

    Forty-six cases blocked by one wrong column name is **one** finding reported forty-six
    times, and a report that does not say so invites a reader to believe there are
    forty-six things wrong. The grouping is derived, never hand-maintained: it is the
    reason string with the per-case scope id, external ref and case id masked out.
    """
    text = str(row.get("reason", ""))
    for pattern, replacement in _VOLATILE:
        text = pattern.sub(replacement, text)
    return " ".join(text.split())


def _systemic_causes(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group every non-``PASSED`` case by its normalised cause, largest group first."""
    groups: dict[str, list[str]] = {}
    for row in rows:
        if row["status"] == "passed":
            continue
        groups.setdefault(_cause_signature(row), []).append(str(row["id"]))
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[1][0]))
    return [
        {"cases": ids, "n": len(ids), "status": _status_of(rows, ids[0]), "cause": cause}
        for cause, ids in ordered
    ]


def _status_of(rows: Sequence[Mapping[str, Any]], case_id: str) -> str:
    """The status of one case id, for labelling a cause group."""
    return next((str(r["status"]) for r in rows if r["id"] == case_id), "unknown")


def _digest(rows: Iterable[Mapping[str, Any]]) -> str:
    """A stable digest over the ``(id, status)`` pairs — the thing a re-run must match."""
    payload = "\n".join(f"{r['id']}={r['status']}" for r in sorted(rows, key=lambda r: r["id"]))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _previous(path: Path) -> dict[str, Any] | None:
    """Read the census this run is about to overwrite, if there is one."""
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _reproducibility(
    previous: dict[str, Any] | None,
    run_id: str,
    rows: list[dict[str, Any]],
    build_method: str,
) -> dict[str, Any]:
    """Compare this census with the one it replaces, when the ``run_id`` is the same.

    This is what makes ``--run-id`` a *demonstration* rather than a flag: run the census
    twice with the same id and the second artefact carries the verdict on the first.

    **What "reproducible" means here, precisely, because the corpus makes it subtle.**
    A pinned ``run_id`` fixes each case's ``site_id`` to
    ``uuid5(namespace, f"{run_id}:{case_id}")``, so a re-run lands in the same tenancy —
    that is the point. But the corpus **never tears down**: several tables under test are
    append-only, so a builder that cleaned up would exercise a delete path the product
    refuses to have (``trappoint_conformance.site``). Consequently a second run with the
    same ``run_id`` against a **retained** database re-inserts rows the first run already
    wrote and its worlds collide on ``pk_permit`` — MEASURED, 2026-08-10, eight cases went
    ``PASSED`` -> ``CANNOT_RUN`` that way. That is not flakiness and it is not a defect in
    the gate; it is append-only doing its job.

    So the reproducibility claim this census makes is the one that is actually true:
    **two runs at the same ``run_id``, each against a freshly built schema, land on the
    same rows.** The build method of both runs is recorded here so the claim can never be
    read as the stronger one it is not.
    """
    if previous is None:
        return {
            "compared": False,
            "why": "no earlier census at this path to compare against",
        }
    prior_run = str(previous.get("run", {}).get("run_id", ""))
    if prior_run != run_id:
        return {
            "compared": False,
            "why": (
                f"the earlier census carried run_id {prior_run!r}, this one {run_id!r}; "
                "a comparison across run ids would compare different tenancies"
            ),
            "previous_run_id": prior_run,
        }
    prior_rows = {str(c.get("id")): c for c in previous.get("cases", [])}
    differing = []
    for row in rows:
        before = prior_rows.get(row["id"])
        if before is None:
            differing.append({"id": row["id"], "before": "<absent>", "after": row["status"]})
        elif str(before.get("status")) != row["status"]:
            differing.append(
                {"id": row["id"], "before": before.get("status"), "after": row["status"]}
            )
    reported = {r["id"] for r in rows}
    for case_id, before_row in prior_rows.items():
        if case_id not in reported:
            differing.append(
                {"id": case_id, "before": before_row.get("status"), "after": "<absent>"}
            )
    previous_digest = str(previous.get("census_digest", ""))
    previous_build = str(previous.get("build", {}).get("method", "<unrecorded>"))
    both_fresh = "apply_chain" in previous_build or "migrate" in previous_build
    both_fresh = both_fresh and ("apply_chain" in build_method or "migrate" in build_method)
    return {
        "compared": True,
        "run_id": run_id,
        "previous_digest": previous_digest,
        "digest": _digest(rows),
        "identical": not differing and previous_digest == _digest(rows),
        "differing_cases": differing,
        "previous_generated_at": previous.get("run", {}).get("generated_at"),
        "previous_build_method": previous_build,
        "build_method": build_method,
        "both_runs_built_a_fresh_schema": both_fresh,
        "caveat": (
            ""
            if both_fresh
            else (
                "at least one of the two runs attached to a retained database rather than "
                "building a fresh one. The corpus never tears down (append-only tables), so "
                "a second run at the same run_id re-inserts rows the first already wrote and "
                "its worlds collide on the primary key. Compare fresh builds, or expect "
                "CANNOT RUN where the first run passed."
            )
        ),
        "site_ids_identical": all(
            str(prior_rows.get(r["id"], {}).get("site_id", "")) == r["site_id"]
            for r in rows
            if r["id"] in prior_rows
        ),
    }


def build_census(
    *,
    manifest: Manifest,
    profile: str,
    report: Mapping[str, Any],
    argv: Sequence[str],
    dsn: str,
    cluster_version: str,
    build_record: Mapping[str, Any] | None,
    schema_state: Mapping[str, Any],
    stderr: str,
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fold the manifest and the runner's report into the published census."""
    selected = manifest.for_profile(profile)
    by_id = {str(r.get("id")): r for r in report.get("results", [])}
    run_id = str(report.get("run_id") or "")

    rows: list[dict[str, Any]] = []
    for case in selected:
        result = by_id.get(case.id)
        if result is None:
            # A declared case the runner never reported on. It is not a pass, it is not a
            # skip, and it must not vanish: the whole contract is that every declared case
            # is accounted for by name.
            rows.append(
                {
                    "id": case.id,
                    "title": case.title,
                    "class": case.cls,
                    "expect_sqlstate": case.expect_sqlstate,
                    "expect_constraint": case.expect_constraint,
                    "requires": list(case.requires),
                    "refusal_depth_min": case.refusal_depth_min,
                    "milestone": case.milestone,
                    "status": "error",
                    "reason": (
                        f"ERROR: the manifest declares {case.id} for profile {profile} and "
                        f"trappoint-conform reported no result for it. The runner's "
                        f"selection and the manifest's selection disagree."
                    ),
                    "reason_names_object": True,
                    "observed_sqlstate": None,
                    "observed_constraint": None,
                    "exhibit_weakened": False,
                    "site_id": str(scope_for(run_id, case.id).site_id) if run_id else None,
                    "runner_detail": "",
                }
            )
            continue

        status = str(result.get("status", "error"))
        reason = "" if status == "passed" else _reason_for(case, result)
        rows.append(
            {
                "id": case.id,
                "title": case.title,
                "class": case.cls,
                "expect_sqlstate": case.expect_sqlstate,
                "expect_constraint": case.expect_constraint,
                "requires": list(case.requires),
                "refusal_depth_min": case.refusal_depth_min,
                "milestone": case.milestone,
                "status": status,
                "reason": reason,
                "reason_names_object": True if status == "passed" else _names_an_object(reason),
                "observed_sqlstate": result.get("observed_sqlstate"),
                "observed_constraint": result.get("observed_constraint"),
                "exhibit_weakened": bool(result.get("exhibit_weakened")),
                "site_id": str(scope_for(run_id, case.id).site_id) if run_id else None,
                "note": _pass_note(case, result) if status == "passed" else "",
                "runner_detail": str(result.get("detail", "")),
            }
        )

    totals = {status: sum(1 for r in rows if r["status"] == status) for status in STATUS_ORDER}
    unreasoned = [r["id"] for r in rows if r["status"] != "passed" and not r["reason_names_object"]]
    complete = (
        totals["pending"] == 0
        and totals["error"] == 0
        and not unreasoned
        and len(rows) == len(selected)
    )

    capabilities = report.get("capabilities") or {}
    census: dict[str, Any] = {
        "artefact": "conformance-census",
        "run": {
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "command": " ".join(str(a) for a in argv),
            "census_command": " ".join([Path(sys.argv[0]).as_posix(), *sys.argv[1:]]),
            "run_id": run_id,
            "profile": profile,
            "schema": report.get("schema"),
            "spec_version": report.get("spec_version") or manifest.spec_version,
            "manifest": manifest.path.relative_to(REPO_ROOT).as_posix()
            if manifest.path.is_relative_to(REPO_ROOT)
            else str(manifest.path),
            "manifest_declared_case_count": manifest.declared_case_count,
            "dsn": _redact(dsn),
            "cluster_version": cluster_version,
            "runner_green": bool(report.get("green")),
            "runner_stderr": stderr.splitlines()[-12:] if stderr else [],
        },
        "schema_state": dict(schema_state),
        "build": dict(build_record)
        if build_record
        else {"method": "pre-existing database (--dsn)"},
        "totals": totals,
        "selected": len(rows),
        "completeness": {
            "complete": complete,
            "why": _completeness_sentence(totals, unreasoned, len(rows), len(selected)),
            "cases_without_a_reason_naming_an_object": unreasoned,
        },
        "capabilities": capabilities,
        "systemic_causes": _systemic_causes(rows),
        "cases": rows,
    }
    census["census_digest"] = _digest(rows)
    census["reproducibility"] = _reproducibility(
        previous, run_id, rows, str(census["build"].get("method", "<unrecorded>"))
    )
    return census


def _completeness_sentence(
    totals: Mapping[str, int], unreasoned: Sequence[str], reported: int, selected: int
) -> str:
    """Say, in one line, why the census is or is not complete."""
    problems = []
    if reported != selected:
        problems.append(f"{selected - reported} declared case(s) produced no row")
    if totals["pending"]:
        problems.append(f"{totals['pending']} PENDING (no implementation)")
    if totals["error"]:
        problems.append(f"{totals['error']} ERROR (the runner broke)")
    if unreasoned:
        problems.append(
            f"{len(unreasoned)} non-pass reason(s) name no object: {', '.join(unreasoned)}"
        )
    if not problems:
        return (
            "every declared case carries a status, nothing is PENDING, nothing ERRORed, "
            "and every non-PASSED case carries a reason naming an object"
        )
    return "; ".join(problems)


def _redact(dsn: str) -> str:
    """Strip any password from a DSN before it is published."""
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", dsn)


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────


def _spec_entitlement() -> tuple[str, str]:
    """Return the §9 sentences, read out of the specification rather than restated.

    Falls back to a short quotation of the CLI's own epilogue if the file moves, and says
    which it used, because a document that silently paraphrased its normative source would
    be exactly the kind of second claim this repository refuses to make.
    """
    path = REPO_ROOT / SPEC_README
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        does = re.search(r"\*\*It does entitle you to say:\*\*(.+?)\n\n", text, re.S)
        not_does = re.search(r"\*\*It does not entitle you to say:\*\*(.+?)\n\n", text, re.S)
        if does and not_does:
            clean = lambda m: " ".join(m.group(1).split())  # noqa: E731
            return clean(does), clean(not_does)
    return (
        (
            "the database refused every history this specification says it must refuse, by "
            "the exact mechanism it names, at the named profile and version."
        ),
        (
            "that the vertical's obligations are the right obligations, or that the system "
            "is secure against a privileged operator."
        ),
    )


def _md_escape(text: str) -> str:
    """Make a string safe inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _md_header(census: Mapping[str, Any]) -> list[str]:
    """Front matter: version, profile, cluster, and the exact command that produced this."""
    run = census["run"]
    out: list[str] = []
    out.append("<!--")
    out.append("SPDX-FileCopyrightText: 2026 MAINLINE contributors")
    out.append("SPDX-License-Identifier: CC-BY-4.0")
    out.append("-->")
    out.append("")
    out.append("# The conformance census — every case, by name")
    out.append("")
    out.append(
        f"**Generated** {run['generated_at']} · **spec** `{run['spec_version']}` · "
        f"**profile** `{run['profile']}` · **schema** `{run['schema']}` · "
        f"**run-id** `{run['run_id']}`"
    )
    out.append("")
    out.append(f"**Cluster** `{run['cluster_version']}`  ")
    out.append(f"**Database** `{run['dsn']}`  ")
    out.append(
        f"**Manifest** `{run['manifest']}` — {run['manifest_declared_case_count']} cases declared"
    )
    out.append("")
    out.append("```")
    out.append(run["command"])
    out.append("```")
    out.append("")
    return out


def _md_entitlement(census: Mapping[str, Any]) -> list[str]:
    """§9, quoted rather than paraphrased, and what this particular run does not claim."""
    totals = census["totals"]
    does, does_not = _spec_entitlement()
    out: list[str] = []
    out.append("---")
    out.append("")
    out.append("## What a green case entitles the reader to say")
    out.append("")
    out.append(
        f"`spec/conformance/README.md` §9 is the authority and it is quoted rather than "
        f"paraphrased. **It does entitle you to say:** {does} **It does not entitle you to "
        f"say:** {does_not}"
    )
    out.append("")
    out.append(
        "So a PASS below means one thing and one thing only: for that history, the "
        "database issued the exact SQLSTATE and the exact exhibit the manifest names. It "
        "is not a statement that the obligation modelled is the right obligation, that a "
        "severity was scored well, or that anything outside the named refusal works. A "
        "claim of conformance MUST cite version and profile, which is why both are in the "
        "header above and in every machine-readable row of "
        "[`qa/conformance-census.json`](../../qa/conformance-census.json)."
    )
    out.append("")
    out.append(
        f"**This run is not green, and publishing it is the point.** "
        f"{totals['passed']} of {census['selected']} cases passed. The census exists to "
        f"account for the other {census['selected'] - totals['passed']} by name, each with "
        f"a reason naming an object a reader can go and look at. `docs/HONESTY.md` said "
        f"this suite demonstrated no conformance case; this document is the first time it "
        f"has been executed end to end against a migrated MAINLINE schema."
    )
    out.append("")
    return out


def _md_totals(census: Mapping[str, Any]) -> list[str]:
    """The counts, the completeness verdict, and the schema state they were taken on."""
    run = census["run"]
    totals = census["totals"]
    out: list[str] = []
    out.append("---")
    out.append("")
    out.append("## Totals")
    out.append("")
    out.append("| status | n | what it means |")
    out.append("|---|---:|---|")
    for status in STATUS_ORDER:
        out.append(f"| **{STATUS_MARK[status]}** | {totals[status]} | {STATUS_MEANS[status]} |")
    out.append(f"| — | **{census['selected']}** | cases selected for profile `{run['profile']}` |")
    out.append("")
    completeness = census["completeness"]
    verdict = "COMPLETE" if completeness["complete"] else "INCOMPLETE"
    out.append(f"**Census verdict: {verdict}** — {completeness['why']}.")
    out.append("")
    out.append(
        "The census's own gate is *completeness*, not greenness: zero `PENDING`, zero "
        "`ERROR`, and a reason naming an object on every non-pass. A red census that "
        "accounts for all 71 cases is the deliverable; a green one that accounted for 30 "
        "would be worth nothing."
    )
    out.append("")

    schema_state = census.get("schema_state", {})
    if schema_state:
        out.append("### The schema the suite ran against")
        out.append("")
        applied = schema_state.get("applied")
        on_disk = schema_state.get("tree_files_on_disk")
        by_state = schema_state.get("by_state") or {}
        states = ", ".join(f"`{k}` {v}" for k, v in sorted(by_state.items())) or "not readable"
        out.append(
            f"`trappoint.schema_migration` carries **{applied}** row(s) ({states}); the tree "
            f"holds **{on_disk}** `.sql` file(s). Every case below that names a missing "
            f"relation is measured against exactly this state, not against an aspiration."
        )
        if schema_state.get("error"):
            out.append("")
            out.append(f"> {schema_state['error']}")
        out.append("")
    return out


def _md_reproducibility(census: Mapping[str, Any]) -> list[str]:
    """The digest, and the verdict on the previous census at the same ``run_id``."""
    run = census["run"]
    repro = census.get("reproducibility", {})
    out: list[str] = []
    out.append("## Reproducibility")
    out.append("")
    out.append(
        f"`census_digest` = `{census['census_digest']}` — sha256 over the sorted `id=status` rows."
    )
    out.append("")
    if repro.get("compared"):
        if repro.get("identical"):
            out.append(
                f"**Re-run confirmed.** An earlier census at this path carried the same "
                f"`run_id` (`{repro['run_id']}`, generated {repro.get('previous_generated_at')}) "
                f"and the same digest `{repro['previous_digest']}`. All "
                f"{census['selected']} cases landed on the same status and the same "
                f"`site_id`, which is what `--run-id` is for: "
                f'`site_id = uuid5(namespace, "<run_id>:<case_id>")`, so a re-run lands on '
                f"exactly the tenancy the first run used."
            )
        else:
            out.append(
                f"**Re-run DIFFERED.** Same `run_id` (`{repro['run_id']}`), different "
                f"outcome. Previous digest `{repro.get('previous_digest')}`; cases that "
                f"moved: "
                + ", ".join(
                    f"`{d['id']}` {d['before']} → {d['after']}"
                    for d in repro.get("differing_cases", [])
                )
                + "."
            )
        out.append("")
        out.append(
            f"- previous run built by `{repro.get('previous_build_method')}`; this run by "
            f"`{repro.get('build_method')}`"
        )
        if repro.get("caveat"):
            out.append("")
            out.append(f"> **Caveat.** {repro['caveat']}")
        else:
            out.append("")
            out.append(
                "> **What this claims, exactly.** Two runs at the same `run_id`, each "
                "against a freshly built schema, land on the same rows. It does *not* claim "
                "that a re-run against a **retained** database is idempotent, and it is not: "
                "the corpus never tears down, because several tables under test are "
                "append-only and a builder that cleaned up would exercise a delete path the "
                "product refuses to have. MEASURED, 2026-08-10: a second run at the same "
                "`run_id` against the retained database moved eight cases from `PASS` to "
                '`CANNOT RUN` on `duplicate key value violates unique constraint "pk_permit"`. '
                "That is append-only working, not the suite flaking."
            )
    else:
        out.append(
            f"Not compared this run — {repro.get('why', 'no prior census')}. Re-run with "
            f"`--run-id {run['run_id']}` and this section becomes the comparison."
        )
    out.append("")
    return out


def _md_capabilities(census: Mapping[str, Any]) -> list[str]:
    """Every ``requires`` token, resolved against the live catalogues, satisfied or not."""
    caps = census.get("capabilities") or {}
    probed = caps.get("probed") or []
    out: list[str] = []
    if probed:
        out.append("## Capability probe")
        out.append("")
        satisfied = [c for c in probed if c.get("satisfied")]
        out.append(
            f"{len(satisfied)} of {len(probed)} `requires` tokens are satisfied on database "
            f"`{caps.get('database')}` (schema `{caps.get('schema')}`), measured against "
            f"`pg_class`, `pg_namespace`, `pg_roles` and `pg_policies`. **No token was "
            f"declared satisfied by hand** — the census never passes `--requires`."
        )
        out.append("")
        out.append("| token | kind | object | satisfied | detail / reason |")
        out.append("|---|---|---|:--:|---|")
        for cap in sorted(probed, key=lambda c: (not c.get("satisfied"), str(c.get("token")))):
            mark = "yes" if cap.get("satisfied") else "**no**"
            body = cap.get("detail") if cap.get("satisfied") else cap.get("reason")
            out.append(
                f"| `{_md_escape(str(cap.get('token')))}` | {cap.get('kind')} | "
                f"`{_md_escape(str(cap.get('object')))}` | {mark} | "
                f"{_md_escape(str(body or ''))} |"
            )
        out.append("")
    return out


def _md_causes(census: Mapping[str, Any]) -> list[str]:
    """The non-passes collapsed to the distinct defects they are instances of."""
    totals = census["totals"]
    causes = census.get("systemic_causes") or []
    out: list[str] = []
    if causes:
        out.append("---")
        out.append("")
        out.append("## The non-passes, grouped by cause")
        out.append("")
        out.append(
            f"{census['selected'] - totals['passed']} non-passing cases resolve to "
            f"**{len(causes)} distinct cause(s)**. The grouping is derived from the reason "
            f"strings with the per-case scope id and external ref masked out — it is not a "
            f"hand-maintained list — and it is here because *one* wrong column name blocking "
            f"forty-six cases is one finding reported forty-six times, and a report that did "
            f"not say so would invite a reader to believe there were forty-six things wrong."
        )
        out.append("")
        for index, group in enumerate(causes, start=1):
            out.append(
                f"**{index}. {STATUS_MARK[group['status']]}, {group['n']} case(s)** — "
                f"{_md_escape(group['cause'])}"
            )
            out.append("")
            out.append(f"> {', '.join(f'`{c}`' for c in group['cases'])}")
            out.append("")
    return out


def _md_case_table(census: Mapping[str, Any]) -> list[str]:
    """One row per declared case, in manifest order. Nothing is omitted."""
    rows: list[dict[str, Any]] = list(census["cases"])
    out: list[str] = []
    out.append("---")
    out.append("")
    out.append("## Every case")
    out.append("")
    out.append("| case | status | class | expects | requires | title |")
    out.append("|---|---|---|---|---|---|")
    for row in rows:
        requires = ", ".join(f"`{r}`" for r in row["requires"]) or "—"
        out.append(
            f"| `{row['id']}` | **{STATUS_MARK[row['status']]}** | {row['class']} | "
            f"`{row['expect_sqlstate']}` `{_md_escape(row['expect_constraint'])}` | "
            f"{requires} | {_md_escape(row['title'])} |"
        )
    out.append("")
    out.append("---")
    out.append("")
    return out


def _md_case_detail(census: Mapping[str, Any]) -> list[str]:
    """Each case again, grouped by status, with its reason and its tenancy."""
    rows: list[dict[str, Any]] = list(census["cases"])
    out: list[str] = []
    for status in STATUS_ORDER:
        group = [r for r in rows if r["status"] == status]
        if not group:
            continue
        out.append(f"## {STATUS_MARK[status]} — {len(group)} case(s)")
        out.append("")
        out.append(f"*{STATUS_MEANS[status]}.*")
        out.append("")
        for row in group:
            out.append(f"### `{row['id']}` — {row['title']}")
            out.append("")
            out.append(
                f"- **class** `{row['class']}` · **expects** `{row['expect_sqlstate']}` on "
                f"`{row['expect_constraint']}` · **refusal depth ≥** {row['refusal_depth_min']} "
                f"· **milestone** `{row['milestone']}`"
            )
            if row["requires"]:
                out.append(f"- **requires** {', '.join(f'`{r}`' for r in row['requires'])}")
            if row["site_id"]:
                out.append(f"- **site_id** `{row['site_id']}`")
            if status == "passed":
                if row.get("note"):
                    out.append(f"- **observed** {_md_escape(row['note'])}")
            else:
                out.append("")
                out.append(f"> {_md_escape(row['reason'])}")
            out.append("")
        out.append("---")
        out.append("")
    return out


def _md_provenance(census: Mapping[str, Any]) -> list[str]:
    """How the database was built, and what was deliberately not touched to produce this."""
    run = census["run"]
    out: list[str] = []
    out.append("## How this was produced")
    out.append("")
    build = census.get("build", {})
    out.append(f"- **database built by** {build.get('method')}")
    if build.get("note"):
        out.append(f"- {build['note']}")
    out.append(
        f"- **census script** `scripts/qa/run_conformance_census.py` (`{run['census_command']}`)"
    )
    out.append(
        "- **no case implementation, no manifest entry and no `--requires` declaration was "
        "touched to produce this document.** The suite was run with `--autodetect-requires` "
        "so that an unmet capability is measured and named rather than asserted."
    )
    out.append(
        "- **machine-readable twin** "
        "[`qa/conformance-census.json`](../../qa/conformance-census.json)"
    )
    out.append("")
    out.append(f"Re-run: `just conform-census`, or `{run['census_command']}`.")
    out.append("")
    return out


#: The document, in order. A list rather than a two-hundred-line function so a section can
#: be read, reordered or tested on its own.
_SECTIONS = (
    _md_header,
    _md_entitlement,
    _md_totals,
    _md_reproducibility,
    _md_capabilities,
    _md_causes,
    _md_case_table,
    _md_case_detail,
    _md_provenance,
)


def render_markdown(census: Mapping[str, Any]) -> str:
    """Render ``docs/release/conformance-census.md`` from the census."""
    lines: list[str] = []
    for section in _SECTIONS:
        lines.extend(section(census))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_conformance_census.py",
        description=(
            "Execute the TRAPPOINT conformance suite against a migrated MAINLINE schema "
            "and publish a per-case census: pass, fail and cannot-run, with a reason "
            "naming an object on every non-pass."
        ),
    )
    parser.add_argument("--dsn", default=None, help="run against this database (or $TRAPPOINT_DSN)")
    parser.add_argument(
        "--build",
        action="store_true",
        help=(
            "build the database first: `python scripts/chain/apply_chain.py --keep` when "
            "that script is in the tree, otherwise `trappoint migrate bootstrap` + `up` — "
            "the deployment runner. Which one ran is recorded in the census."
        ),
    )
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        help=f"database name for --build (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument("--profile", default="mainline", help="binding profile (default: mainline)")
    parser.add_argument(
        "--run-id", default=None, help="pin the tenancy scope; a re-run lands on the same rows"
    )
    parser.add_argument("--manifest", type=Path, default=None, help="path to manifest.toml")
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="do not drop the --build database afterwards (it is dropped by default)",
    )
    return parser


def _require_dsn(dsn: str | None) -> str:
    """Return *dsn*, or refuse. A census without a database is not a census."""
    if dsn:
        return dsn
    raise CensusError(
        "no DSN. Pass --dsn, set TRAPPOINT_DSN, or pass --build to construct a migrated "
        "database on the local node."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    args = _parser().parse_args(list(argv) if argv is not None else sys.argv[1:])

    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"census: {exc}", file=sys.stderr)
        return EXIT_CANNOT_PRODUCE

    build_record: dict[str, Any] | None = None
    dsn = args.dsn or os.environ.get("TRAPPOINT_DSN") or os.environ.get("LOCAL_DSN")
    built_database: str | None = None

    try:
        if args.build:
            via_script = _build_via_chain_script(args.database, keep=True)
            if via_script is not None:
                dsn, build_record = via_script[0], dict(via_script[1])
            else:
                dsn, record = _build_via_deployment_runner(args.database)
                build_record = dict(record)
            built_database = args.database
            print(f"census: built {dsn} via {build_record['method']}", file=sys.stderr)
        dsn = _require_dsn(dsn)

        cluster_version = _cluster_version(dsn)
        schema_state = _applied_migrations(dsn)
        conform_argv = _conform_argv(dsn, args.profile, args.run_id, args.manifest)
        report, stderr = _run_suite(conform_argv)
        previous = _previous(
            REPO_ROOT / args.json_out if not args.json_out.is_absolute() else args.json_out
        )
        census = build_census(
            manifest=manifest,
            profile=args.profile,
            report=report,
            argv=conform_argv,
            dsn=dsn,
            cluster_version=cluster_version,
            build_record=build_record,
            schema_state=schema_state,
            stderr=stderr,
            previous=previous,
        )
    except CensusError as exc:
        print(f"census: CANNOT PRODUCE — {exc}", file=sys.stderr)
        return EXIT_CANNOT_PRODUCE
    finally:
        if built_database and not args.keep:
            print(f"census: {_drop_database(built_database)}", file=sys.stderr)

    json_out = args.json_out if args.json_out.is_absolute() else REPO_ROOT / args.json_out
    md_out = args.md_out if args.md_out.is_absolute() else REPO_ROOT / args.md_out
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(census, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_out.write_text(render_markdown(census), encoding="utf-8")

    totals = census["totals"]
    print(
        f"census · {totals['passed']}/{census['selected']} passed · "
        + " · ".join(
            f"{STATUS_MARK[s].lower()} {totals[s]}"
            for s in STATUS_ORDER
            if s != "passed" and totals[s]
        )
    )
    print(f"census · spec {census['run']['spec_version']} · profile {census['run']['profile']}")
    print(f"census · {census['census_digest']}")
    print(f"census · wrote {json_out.relative_to(REPO_ROOT)} and {md_out.relative_to(REPO_ROOT)}")
    repro = census.get("reproducibility", {})
    if repro.get("compared"):
        print(
            "census · re-run "
            + (
                "IDENTICAL to the previous census at the same run-id"
                if repro.get("identical")
                else f"DIFFERED: {repro.get('differing_cases')}"
            )
        )
    if census["completeness"]["complete"]:
        print("census · COMPLETE — " + census["completeness"]["why"])
        return EXIT_COMPLETE
    print("census · INCOMPLETE — " + census["completeness"]["why"], file=sys.stderr)
    return EXIT_INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
