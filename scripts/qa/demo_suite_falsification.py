#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this program makes no database claim of its own. It puts a DEFECT back and
#     asks the suite whether it notices.
# I: QA-FALSIFY-1 — a fix is DEMONSTRATED only when the defect it removed, put back by
#    hand, turns the named test red with a message that names the right file. A test that
#    passes with and without the bug has not been fixed; it has been bypassed. This program
#    is that experiment, as a command rather than as a memory.
# RATIONALE: three successive NO-GO verdicts on this repository came from fixes that were
#    believed rather than falsified, and the one shortcut that was ever caught — a seed
#    reshaped so that a value in `demo_world.sql` equalled an application constant — was
#    found by negative controls and not by a green board. A lead who only reads claims is
#    the failure mode. So the claims are re-run.
"""Re-plant every defect the demo-suite wave says it fixed, and record whether it bites.

USAGE

    $env:TRAPPOINT_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
    .venv/Scripts/python.exe scripts/qa/demo_suite_falsification.py            # all cases
    .venv/Scripts/python.exe scripts/qa/demo_suite_falsification.py --list
    .venv/Scripts/python.exe scripts/qa/demo_suite_falsification.py --dry-run
    .venv/Scripts/python.exe scripts/qa/demo_suite_falsification.py --case w3-counter-...

Exit code is 0 when every case reached its expected verdict, 1 otherwise. A non-zero exit
means *a claimed fix was not demonstrated*, which is not the same thing as a broken build
and must not be quieted with `continue-on-error` or `|| true`.

WHAT A CASE IS

Each :class:`Case` carries the worker whose claim it tests, the exact edit that puts the
defect back, the pytest node ids to drive, and the strings the red must contain. Three
kinds:

``plant``      edit the tree, run the nodes, require RED; the same nodes are run first
               WITHOUT the edit and required GREEN, because a test that was already
               failing proves nothing when it fails again.
``standing``   no edit: run the nodes and record that the defect is STILL THERE. This is
               what a worker who landed nothing looks like, and it is a result, not a gap.
``reproduction`` no edit: run the worker's OWN published reproduction, in the order it
               published, and require GREEN. A worker whose document describes a fix the
               tree does not carry fails here.
``absent``     the worker's deliverable files do not exist. Recorded, not run.

HOW THE TREE IS PROVEN CLEAN AFTERWARDS

Every byte of every file a case touches is read before the run and written back in a
``finally``; the SHA-256 of each is then compared with what it was. That comparison is the
binding proof, and it is stronger than the `git diff --exit-code` the brief asks for,
because THIS WORKING TREE IS NOT CLEAN TO BEGIN WITH: five concurrent waves have
uncommitted work in it, so a bare `git diff --exit-code` is non-zero before this program
starts and would stay non-zero however carefully it behaved. So both are done and both are
reported: the digest of `git diff` is captured before and after and must be IDENTICAL, and
`git diff --exit-code` is run and its result printed for the reader to interpret. A
falsification harness that leaves a defect behind is worse than none.

The planted W4 case deliberately makes the demo API write a row it should not, into the
scratch database named by ``MAINLINE_W4_DATABASE`` (defaulted here to a database this
program owns). Those rows carry ``external_ref LIKE 'FALSIFY-%'`` and are deleted after the
case, whatever the verdict.

ONE CASE WAS RETIRED, AND THE MEASUREMENT IT PRODUCED IS WORTH MORE THAN THE CASE

`w6-seed-loses-a-resource-row` cut the custody checkpoint out of `demo_world.sql` §8, to show
`test_seed_covers_every_console_resource.py` going red on a resource `conftest` does not
read. **The database refused the world instead** — `demo_permit.sql` did not apply, `P0001
MAINLINE: recall policy anchor is not inside a cosigned checkpoint` — so the plant never
reached the assertion. The case was removed rather than have its expectation rewritten to
match its result, which would have been the same act as reshaping a seed to match a
constant. What it teaches is kept here and in
`docs/diagnosis/demo-suite-falsification.md` §5.2: the demo world is welded so tightly that
almost no seeded subject can vanish silently, and `change_request` could go missing for
exactly one reason — nothing referenced it. It was declared by the console, routed by the
API, given a table and a nine-edge transition alphabet, and welded to nothing at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
TESTS: Final = "verticals/mainline/apps/demo-api/tests"
SRC: Final = "verticals/mainline/apps/demo-api/src/mainline_demo_api"
SEEDS: Final = "verticals/mainline/db/seeds/demo"
CONSOLE: Final = "verticals/mainline/apps/console/src/data"

#: This program's own scratch database, so a plant that writes cannot land in a database a
#: concurrent run is measuring. `tests/test_gate_run.py:143` reads this name from the
#: environment for exactly this reason.
SCRATCH_DB: Final = "w_w6_falsification_audit"

DEFAULT_DSN: Final = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"


_COVERS: Final = "test_seed_covers_every_console_resource.py"
_REFUSAL: Final = "test_refusal_row_factory.py"


def _node(module: str, case: str) -> str:
    """One pytest node id under the demo-api tests tree.

    A function rather than an implicit string concatenation inside a tuple: there, a
    missing comma glues two node ids into one that selects nothing, pytest exits 4, and a
    case reports "no tests ran" as though the plant had been evaluated.
    """
    return f"{TESTS}/{module}::{case}"


# ── The edit primitives ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Replace:
    """Replace *old* with *new*, exactly once. Anything else aborts the case.

    "Exactly once" is not fussiness. An anchor that matches twice means the file moved
    under this program, and a plant applied to the wrong half of a file is a case that
    reports a red for a reason nobody checked.
    """

    path: str
    old: str
    new: str

    def apply(self, text: str) -> str:
        count = text.count(self.old)
        if count != 1:
            raise SystemExit(
                f"{self.path}: the anchor for this plant occurs {count} times, not once. "
                f"The file has moved under this harness. Anchor: {self.old[:90]!r}"
            )
        return text.replace(self.old, self.new)


@dataclass(frozen=True)
class Cut:
    """Delete from the start of *after* up to (not including) the next *before*.

    Used for the seed plants, where the defect being restored is the ABSENCE of a block of
    INSERT statements and quoting a hundred and forty lines verbatim would be a copy of the
    seed inside a QA script — a second place for the seed to live, which is the class of
    mistake this whole wave is about.
    """

    path: str
    after: str
    before: str
    note: str = ""

    def apply(self, text: str) -> str:
        start = text.find(self.after)
        if start < 0:
            raise SystemExit(f"{self.path}: cut start anchor not found: {self.after[:90]!r}")
        end = text.find(self.before, start + len(self.after))
        if end < 0:
            raise SystemExit(f"{self.path}: cut end anchor not found: {self.before[:90]!r}")
        marker = f"-- PLANTED DEFECT (scripts/qa/demo_suite_falsification.py): {self.note}\n\n"
        return text[:start] + marker + text[end:]


Edit = Replace | Cut


@dataclass(frozen=True)
class Case:
    name: str
    worker: str
    #: What the worker says they fixed, in one sentence.
    claim: str
    #: What this case puts back, in one sentence.
    defect: str
    mode: str  # "plant" | "standing" | "reproduction" | "absent"
    plant_nodes: tuple[str, ...] = ()
    edits: tuple[Edit, ...] = ()
    #: Nodes run WITHOUT the plant, required green. Defaults to ``plant_nodes``.
    control_nodes: tuple[str, ...] = ()
    #: Substrings the red must contain. Missing one is "red for the wrong reason".
    expect: tuple[str, ...] = ()
    #: The file the red must name, so a green-by-accident elsewhere is not counted.
    names_file: str = ""
    #: For ``absent``: the deliverables that were expected to exist.
    deliverables: tuple[str, ...] = ()
    slow: str = ""
    #: Drop the fingerprinted fixture database before the planted run. Required for any
    #: plant that edits a SEED file — see :func:`_drop_fixture_database`.
    rebuild_fixture: bool = False
    touches: tuple[str, ...] = field(default_factory=tuple)

    def files(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys([edit.path for edit in self.edits] + list(self.touches)))


# ── The cases ───────────────────────────────────────────────────────────────────────

_W4_WRITE: Final = """    if _demo_subject_is_established(conn, scenario):
        return None

    return _error(
        423,
        "demo_subject_unidentified","""

_W4_PLANTED: Final = """    if _demo_subject_is_established(conn, scenario):
        return None

    # PLANTED DEFECT (scripts/qa/demo_suite_falsification.py, case w4-a-refusal-that-writes):
    # a refusal that writes. The row is committed BEFORE the 423 is returned, so the caller
    # is told no and the database is told yes — which is the behaviour W4's snapshot claims
    # to catch. `conn.rollback()` at the call site (transitions.py:1236) is what a plant
    # without the commit would lose to.
    conn.execute(
        "INSERT INTO mainline.permit "
        "(permit_id, site_id, site_role, external_ref, ref_name, opened_at, horizon_at) "
        "SELECT gen_random_uuid(), p.site_id, p.site_role, "
        "'FALSIFY-' || gen_random_uuid()::STRING, "
        "'refs/permits/falsify-' || gen_random_uuid()::STRING, now(), p.horizon_at "
        "FROM mainline.permit p LIMIT 1"
    )
    conn.commit()

    return _error(
        423,
        "demo_subject_unidentified","""

_TS_THIRTEENTH: Final = """  declare(
    'materialise_checks',"""

_TS_PLANTED: Final = """  declare(
    'recall_policy',
    'GET',
    '/v1/recall-policies/{policy_id}',
    `${C}recall-policy.schema.json`,
    'recall',
    'PLANTED by scripts/qa/demo_suite_falsification.py: a thirteenth GET resource, '
    + 'declared to a judge and seeded nowhere.',
  ),
  declare(
    'materialise_checks',"""

CASES: Final[tuple[Case, ...]] = (
    Case(
        name="w1-change-request-absent",
        worker="w1-change-request-seed",
        claim=(
            "demo_world.sql §10 seeds the second gated subject the console declares, and "
            "conftest._identifiers reads cr_id back out of the database with a query"
        ),
        defect=(
            "the change request, its cr_clause, its obligation and its genesis event are cut "
            "out of demo_world.sql — the state the seed was in at 073dfea"
        ),
        mode="plant",
        edits=(
            Cut(
                path=f"{SEEDS}/demo_world.sql",
                after="INSERT INTO mainline.change_request (",
                before="-- ══════",
                note="w1-change-request-absent — the second gated subject removed from the seed",
            ),
        ),
        plant_nodes=(
            _node(
                _COVERS,
                "test_the_demo_seed_carries_every_resource_the_console_declares[change_request]",
            ),
        ),
        # NOT `test_reads.py::test_every_read_satisfies_its_committed_contract[change_request]`,
        # which would be the obvious second node. It is ALREADY red at this HEAD: its
        # session-scoped `payloads` fixture errors on `KeyError: 'commit_v2'`, which is 63 of
        # the suite's 64 errors as measured on 2026-08-13. A node that is red WITHOUT the plant
        # can only produce an inconclusive case, so that defect is reported standing instead.
        expect=(
            "mainline.change_request",
            "holds 0 such rows",
            "demo_world.sql",
        ),
        names_file="conftest.py",
        rebuild_fixture=True,
        slow="changes _fingerprint(); the fixture database is rebuilt from 271 migrations",
    ),
    Case(
        name="w2-read-surface-standing",
        worker="w2-read-surface",
        claim=(
            "none landed: reads.py, health.py, app.py and test_reads.py are unchanged by this wave"
        ),
        defect=(
            "nothing is planted — the two defects W2 was given are driven as they stand, to "
            "record that they are still present rather than to falsify a fix that does not exist"
        ),
        mode="standing",
        plant_nodes=(
            _node(
                "test_reads.py", "test_an_undeclared_query_parameter_is_refused_rather_than_ignored"
            ),
            _node("test_reads.py", "test_health_is_200_with_a_real_schema_fingerprint"),
        ),
        expect=(),
    ),
    Case(
        name="w3-counter-that-decomposes",
        worker="w3-raising-branch",
        claim=(
            "_RAISES moved to identity_conserved_when_issued, whose counter open_residue was "
            "measured 0 on the seeded permit, so 0119a genuinely RAISES P0001"
        ),
        defect=(
            "_RAISES back to gate_closed_when_issued over open_blocking — the constraint whose "
            "counter is 1 on the deployed seed, so 0119a decomposes it and returns a diagnosis"
        ),
        mode="plant",
        edits=(
            Replace(
                path=f"{TESTS}/test_refusal_row_factory.py",
                old='_RAISES = "identity_conserved_when_issued"',
                new='_RAISES = "gate_closed_when_issued"',
            ),
            Replace(
                path=f"{TESTS}/test_refusal_row_factory.py",
                old='_RAISES_COUNTER = "open_residue"',
                new='_RAISES_COUNTER = "open_blocking"',
            ),
            Replace(
                path=f"{TESTS}/test_refusal_row_factory.py",
                old='_RAISES_COUNTER_SQL = "SELECT open_residue FROM mainline.permit '
                'WHERE permit_id = %s"',
                new='_RAISES_COUNTER_SQL = "SELECT open_blocking FROM mainline.permit '
                'WHERE permit_id = %s"',
            ),
        ),
        plant_nodes=(
            _node(_REFUSAL, "test_the_counter_behind_the_raising_constraint_is_zero"),
            _node(_REFUSAL, "test_the_declined_branch_declines_identically_under_both_factories"),
            _node(
                _REFUSAL, "test_the_savepoint_fence_survives_a_raise_inside_one_open_transaction"
            ),
        ),
        expect=(
            "mainline.permit.open_blocking is 1, not 0",
            "do NOT weaken the assertions below",
        ),
        names_file="test_refusal_row_factory.py",
    ),
    Case(
        name="w4-a-refusal-that-writes",
        worker="w4-refusal-that-writes",
        claim=(
            "the four POSTs write nothing, and the snapshot now carries the permit IDENTITIES "
            "rather than only a count, so a write is named rather than counted"
        ),
        defect=(
            "_demo_guard commits an INSERT into mainline.permit on the "
            "demo_subject_unidentified path and then returns the 423 — the screen says no and "
            "the database says yes"
        ),
        mode="plant",
        edits=(
            Replace(
                path=f"{SRC}/transitions.py",
                old=_W4_WRITE,
                new=_W4_PLANTED,
            ),
        ),
        plant_nodes=(
            _node(
                "test_demo_guard_anonymous.py",
                "test_the_four_posts_are_refused_with_the_permit_id_variable_unset",
            ),
        ),
        expect=(
            "permits_that_appeared",
            "FALSIFY-",
            "this is the API's own write",
        ),
        names_file="test_demo_guard_anonymous.py",
    ),
    Case(
        name="w5-order-independence-reproduction",
        worker="w5-order-independence",
        claim=(
            "docs/ci/demo-suite-order.md §1.5 — test_row_factory_contract.py splits the "
            "session-scoped BUILD from a function-scoped PUBLICATION of the four "
            "MAINLINE_DEMO_* names, so w1_database and w4_database stop fighting over one "
            "process environment"
        ),
        defect=(
            "no plant is needed here: W5 published its own three-node reproduction, and "
            "running it IN THAT ORDER is the experiment. Green means the leak is closed; red "
            "means the document describes a change the tree does not carry"
        ),
        mode="reproduction",
        plant_nodes=(
            _node("test_transitions.py", "test_the_shared_connection_is_the_one_db_py_opens"),
            _node(
                "test_row_factory_contract.py",
                "test_the_production_connection_really_is_dict_row",
            ),
            _node("test_transitions.py", "test_the_request_after_a_gate_run_is_not_a_503"),
        ),
    ),
    Case(
        name="w6-console-declares-a-thirteenth-resource",
        worker="w6-falsification-audit",
        claim=(
            "test_seed_covers_every_console_resource.py parses RESOURCE_KEYS out of the "
            "console, so a resource declared to a judge and seeded nowhere is red the day it "
            "is declared"
        ),
        defect=(
            "resources.ts declares a thirteenth GET resource, exactly as it declared "
            "change_request, with nothing in demo_world.sql behind it"
        ),
        mode="plant",
        edits=(
            Replace(path=f"{CONSOLE}/resources.ts", old=_TS_THIRTEENTH, new=_TS_PLANTED),
            Replace(
                path=f"{CONSOLE}/resources.ts",
                old="export const RESOURCE_KEYS = [\n  'audit',",
                new="export const RESOURCE_KEYS = [\n  'audit',\n  'recall_policy',",
            ),
        ),
        plant_nodes=(
            _node(
                _COVERS,
                "test_the_demo_seed_carries_every_resource_the_console_declares[recall_policy]",
            ),
            _node(_COVERS, "test_every_console_read_has_an_implementation_in_this_api"),
        ),
        control_nodes=(
            _node(
                _COVERS,
                "test_the_demo_seed_carries_every_resource_the_console_declares[change_request]",
            ),
            _node(_COVERS, "test_every_console_read_has_an_implementation_in_this_api"),
        ),
        expect=(
            "recall_policy",
            "the console declares resource",
        ),
        names_file="test_seed_covers_every_console_resource.py",
    ),
)


# ── Running one set of nodes ────────────────────────────────────────────────────────


def _interpreter() -> str:
    candidate = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if candidate.is_file():
        return str(candidate)
    candidate = REPO_ROOT / ".venv" / "bin" / "python"
    if candidate.is_file():
        return str(candidate)
    return sys.executable


@dataclass
class Run:
    exit_code: int
    tests: int
    failures: int
    errors: int
    skipped: int
    text: str
    seconds: float

    @property
    def red(self) -> bool:
        return self.failures + self.errors > 0

    @property
    def green(self) -> bool:
        return self.exit_code == 0 and self.tests > 0 and not self.red

    def summary(self) -> str:
        return (
            f"exit={self.exit_code} tests={self.tests} failures={self.failures} "
            f"errors={self.errors} skipped={self.skipped} in {self.seconds:.1f}s"
        )


def _run_nodes(nodes: tuple[str, ...], xml_path: Path, timeout: int) -> Run:
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    if xml_path.exists():
        xml_path.unlink()
    env = dict(os.environ)
    env.setdefault("TRAPPOINT_DSN", DEFAULT_DSN)
    env.setdefault("MAINLINE_W4_DATABASE", SCRATCH_DB)
    env["PYTHONIOENCODING"] = "utf-8"
    argv = [
        _interpreter(),
        "-u",
        "-m",
        "pytest",
        *nodes,
        "--crdb=reuse",
        "-q",
        "--tb=long",
        "-p",
        "no:cacheprovider",
        f"--junitxml={xml_path}",
    ]
    started = time.monotonic()
    proc = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    seconds = time.monotonic() - started
    text = proc.stdout + proc.stderr
    tests = failures = errors = skipped = 0
    if xml_path.is_file():
        suite = ET.parse(xml_path).getroot()[0]  # noqa: S314 - junit XML this file just wrote
        tests = int(suite.get("tests", 0))
        failures = int(suite.get("failures", 0))
        errors = int(suite.get("errors", 0))
        skipped = int(suite.get("skipped", 0))
        for case in suite:
            for kind in ("failure", "error"):
                for node in case.findall(kind):
                    text += f"\n[{kind}] {case.get('name')}: {node.get('message', '')}\n"
                    text += node.text or ""
    return Run(proc.returncode, tests, failures, errors, skipped, text, seconds)


# ── Applying and proving the revert ─────────────────────────────────────────────────


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


#: Symptoms of the fixture-database RACE rather than of the planted defect. `demo_database`
#: (tests/conftest.py) names its database after a fingerprint over the migrations AND the
#: seed, and has no interlock: two pytest sessions that compute the same fingerprint will
#: `DROP DATABASE IF EXISTS … CASCADE` and `CREATE DATABASE` on top of each other. A plant
#: that edits a seed file changes that fingerprint, so any OTHER session started while the
#: plant is in place lands on the same new name and can drop the database this run is
#: applying 271 migrations into. Measured 2026-08-13 with a concurrent
#: `scripts/qa/demo_suite_order.py shuffle` running five seeded suites.
_FIXTURE_RACE: Final = (
    "migrations did not apply into w3_demo_api_",
    "InvalidCatalogName",
    "does not exist",
)


def _git_diff_digest(paths: tuple[str, ...] = ()) -> str:
    """SHA-256 of `git diff`, optionally restricted to *paths*.

    Restricted is what this harness asserts on. An unrestricted digest is not a statement
    about THIS program in a tree five concurrent waves are writing to — measured: two
    neighbouring workers landed files into `verticals/mainline/apps/demo-api/tests/`
    during one 13-minute run, and an unrestricted comparison called that a dirty revert.
    """
    out = _git("diff", "--", *paths) if paths else _git("diff")
    return hashlib.sha256(out.stdout.encode("utf-8", "replace")).hexdigest()


def _fixture_fingerprint() -> str:
    """``conftest._fingerprint()``, called rather than re-implemented.

    The value names the fixture database, and it is a SHA-256 over the migration chain AND
    the seed files. Re-deriving it here would be a second copy of the thing this whole wave
    is about, so it is obtained by importing the module that owns it.
    """
    program = (
        f"import sys; sys.path.insert(0, r'{REPO_ROOT / TESTS}'); "
        "import conftest; print(conftest._fingerprint())"
    )
    proc = subprocess.run(
        [_interpreter(), "-c", program],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"could not read conftest._fingerprint(): {proc.stderr[-400:]}")
    return proc.stdout.strip()


def _drop_fixture_database(reason: str) -> str:
    """Drop ``w3_demo_api_<fingerprint>`` so a seed plant actually reaches the database.

    WITHOUT THIS THE SEED PLANTS ARE VACUOUS, and that is measured rather than feared. A
    plant that edits a seed changes the fingerprint, so `demo_database` looks for a new
    database name — and on 2026-08-13 it FOUND one, already built and already marked
    `w3_fixture.ready`, because a concurrent pytest session had created that exact name
    while the plant was in place and then seeded it from the file AFTER the plant was
    reverted. The planted run adopted a database whose CONTENT was the unplanted world
    under a name that says otherwise, and reported the case green in 25.7 s — the same
    25.4 s its control took, which is the tell. `w3_fixture.ready` certifies that a
    database was BUILT; it does not certify what it was built FROM.
    """
    try:
        import psycopg
    except ImportError:  # pragma: no cover - psycopg is a workspace dependency
        return "psycopg is not importable; nothing dropped"
    name = f"w3_demo_api_{_fixture_fingerprint()}"
    dsn = os.environ.get("TRAPPOINT_DSN", DEFAULT_DSN)
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" CASCADE')
    except Exception as exc:  # noqa: BLE001 - reported, not decided on
        return f"could not drop {name} ({reason}): {type(exc).__name__}: {exc}"
    return f"{name} dropped ({reason})"


def _cleanup_planted_rows() -> str:
    """Delete anything the W4 plant committed. Runs whatever the verdict was."""
    try:
        import psycopg
    except ImportError:  # pragma: no cover - psycopg is a workspace dependency
        return "psycopg is not importable; nothing cleaned"
    dsn = os.environ.get("TRAPPOINT_DSN", DEFAULT_DSN)
    database = os.environ.get("MAINLINE_W4_DATABASE", SCRATCH_DB)
    target = dsn.split("?", 1)
    base = target[0].rsplit("/", 1)[0]
    tail = f"?{target[1]}" if len(target) > 1 else ""
    try:
        with psycopg.connect(f"{base}/{database}{tail}", autocommit=True) as conn:
            cur = conn.execute("DELETE FROM mainline.permit WHERE external_ref LIKE 'FALSIFY-%'")
            return f"{cur.rowcount} planted permit row(s) deleted from {database}"
    except Exception as exc:  # noqa: BLE001 - cleanup reports, it does not decide
        return f"could not clean {database}: {type(exc).__name__}: {exc}"


def _verdict(  # noqa: PLR0911, PLR0912 - each return IS a distinct verdict, and collapsing
    # two of them would mean reporting 'inconclusive' and 'not demonstrated' as one result
    case: Case,
    control: Run | None,
    planted: Run | None,
) -> tuple[bool, str]:
    if case.mode == "absent":
        missing = [d for d in case.deliverables if not (REPO_ROOT / d).exists()]
        if missing:
            return False, (
                "NOT DEMONSTRATED — the worker's deliverables do not exist, so there is no "
                f"fix to put back: {', '.join(missing)}"
            )
        return True, "the deliverables exist; re-run with a plant once their defect is named"
    if case.mode == "reproduction":
        if planted is None:  # pragma: no cover - _execute always runs a reproduction case
            raise SystemExit(f"{case.name}: reproduction case reached the verdict with no run")
        if planted.red:
            return False, (
                "DEFECT STANDING — the worker's own published reproduction still fails in "
                "the order its document says is now green, so the tree does not carry the "
                f"change the document describes ({planted.summary()})"
            )
        return True, (
            "ORDER-DEPENDENCE CLOSED — the worker's own published reproduction passes in "
            f"the interleaved order that used to fail ({planted.summary()})"
        )
    if case.mode == "standing":
        if planted is None:  # pragma: no cover - _execute always runs a standing case
            raise SystemExit(f"{case.name}: standing case reached the verdict with no run")
        if planted.red:
            return True, (
                "DEFECT STANDING — no fix was claimed and the nodes are red as they were at "
                f"073dfea ({planted.summary()})"
            )
        return False, (
            "the nodes this worker was given are GREEN and no fix was landed, so either the "
            f"defect fixed itself or the baseline was wrong ({planted.summary()})"
        )

    if control is None or planted is None:  # pragma: no cover - _execute always runs both
        raise SystemExit(f"{case.name}: a plant case reached the verdict with no run")
    if not control.green:
        return False, (
            "INCONCLUSIVE — the control run (no plant) was not green, so a red under the "
            f"plant would prove nothing. control: {control.summary()}"
        )
    raced = [tell for tell in _FIXTURE_RACE if tell in planted.text]
    if raced:
        return False, (
            "INCONCLUSIVE — the planted run did not reach the assertion: the fixture "
            f"database was rebuilt and something raced it ({raced[0]!r}). This is the "
            "`demo_database` fingerprint race, not a verdict on the fix. Re-run this case "
            f"when no other pytest session is on the node. planted: {planted.summary()}"
        )
    if planted.skipped and not planted.red:
        return False, (
            "INCONCLUSIVE — the plant turned the test into a SKIP rather than a red, so the "
            "assertion was never evaluated. A skip is not a refusal and must never be read "
            f"as one. planted: {planted.summary()}"
        )
    if not planted.red:
        return False, (
            "NOT DEMONSTRATED — the defect was put back and the test STAYED GREEN. The fix "
            f"has not been shown to be load-bearing. planted: {planted.summary()}"
        )
    missing = [want for want in case.expect if want not in planted.text]
    if missing:
        return False, (
            "RED FOR THE WRONG REASON — the plant turned the test red but the message does "
            f"not contain {missing!r}. planted: {planted.summary()}"
        )
    if case.names_file and case.names_file not in planted.text:
        return False, (
            f"RED BUT UNATTRIBUTED — the message never names {case.names_file}. "
            f"planted: {planted.summary()}"
        )
    return True, (
        f"DEMONSTRATED — control green ({control.summary()}); planted red "
        f"({planted.summary()}) naming {case.names_file} and every expected string"
    )


def _execute(case: Case, out_dir: Path, timeout: int) -> dict[str, object]:
    print(f"\n=== {case.name}  [{case.worker}]  mode={case.mode}", flush=True)
    print(f"    claim : {case.claim}", flush=True)
    print(f"    plant : {case.defect}", flush=True)
    if case.slow:
        print(f"    note  : {case.slow}", flush=True)

    control: Run | None = None
    planted: Run | None = None
    before: dict[str, str] = {}
    originals: dict[Path, bytes] = {}

    if case.mode == "absent":
        ok, why = _verdict(case, None, None)
        print(f"    -> {why}", flush=True)
        return {
            "case": case.name,
            "worker": case.worker,
            "mode": case.mode,
            "demonstrated": ok,
            "verdict": why,
        }

    if case.mode in ("standing", "reproduction"):
        planted = _run_nodes(case.plant_nodes, out_dir / f"{case.name}.xml", timeout)
        print(f"    standing run: {planted.summary()}", flush=True)
        ok, why = _verdict(case, None, planted)
        print(f"    -> {why}", flush=True)
        return {
            "case": case.name,
            "worker": case.worker,
            "mode": case.mode,
            "demonstrated": ok,
            "verdict": why,
            "run": planted.summary(),
        }

    for rel in case.files():
        path = REPO_ROOT / rel
        originals[path] = path.read_bytes()
        before[rel] = _digest(path)

    try:
        control_nodes = case.control_nodes or case.plant_nodes
        control = _run_nodes(control_nodes, out_dir / f"{case.name}-control.xml", timeout)
        print(f"    control (no plant): {control.summary()}", flush=True)

        for edit in case.edits:
            path = REPO_ROOT / edit.path
            path.write_text(
                edit.apply(path.read_text(encoding="utf-8")), encoding="utf-8", newline=""
            )
        print(f"    planted into: {', '.join(case.files())}", flush=True)
        if case.rebuild_fixture:
            print(f"    {_drop_fixture_database('so the plant reaches the database')}", flush=True)

        planted = _run_nodes(case.plant_nodes, out_dir / f"{case.name}-planted.xml", timeout)
        print(f"    planted:            {planted.summary()}", flush=True)
    finally:
        if case.rebuild_fixture:
            print(f"    {_drop_fixture_database('leaving no planted database behind')}", flush=True)
        for path, blob in originals.items():
            path.write_bytes(blob)
        restored = {rel: _digest(REPO_ROOT / rel) for rel in case.files()}
        drift = [rel for rel in before if before[rel] != restored[rel]]
        if drift:
            raise SystemExit(
                f"REVERT FAILED for {case.name}: {drift} are not byte-identical to how this "
                "harness found them. Restore them by hand before doing anything else."
            )
        print(f"    reverted, byte-identical: {', '.join(case.files())}", flush=True)

    cleaned = _cleanup_planted_rows() if case.name.startswith("w4-") else "n/a"
    if cleaned != "n/a":
        print(f"    cleanup: {cleaned}", flush=True)

    ok, why = _verdict(case, control, planted)
    print(f"    -> {why}", flush=True)
    return {
        "case": case.name,
        "worker": case.worker,
        "mode": case.mode,
        "demonstrated": ok,
        "verdict": why,
        "control": control.summary() if control else None,
        "planted": planted.summary() if planted else None,
        "files": list(case.files()),
        "cleanup": cleaned,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--list", action="store_true", help="print the cases and exit")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="apply every plant IN MEMORY and report what it would change, then exit",
    )
    parser.add_argument("--case", action="append", default=[], help="run only these cases")
    parser.add_argument("--timeout", type=int, default=1800, help="per-run timeout in seconds")
    parser.add_argument(
        "--out", default="out/falsification", help="where the junit XMLs and the report go"
    )
    args = parser.parse_args(argv)

    if args.list:
        for case in CASES:
            print(f"{case.name:44s} {case.mode:9s} {case.worker}")
        return 0

    selected = [c for c in CASES if not args.case or c.name in args.case]
    unknown = set(args.case) - {c.name for c in CASES}
    if unknown:
        raise SystemExit(f"unknown case(s): {sorted(unknown)}")

    if args.dry_run:
        for case in selected:
            print(f"\n{case.name}  [{case.worker}]  mode={case.mode}")
            for edit in case.edits:
                path = REPO_ROOT / edit.path
                before_text = path.read_text(encoding="utf-8")
                after_text = edit.apply(before_text)
                kind = type(edit).__name__
                print(
                    f"  {kind:8s} {edit.path}: "
                    f"{len(before_text)} -> {len(after_text)} bytes "
                    f"(delta {len(after_text) - len(before_text):+d})"
                )
                if before_text == after_text:
                    raise SystemExit(f"{case.name}: {edit.path} would not change. Dead plant.")
            for node in case.plant_nodes:
                print(f"  node     {node}")
        return 0

    out_dir = REPO_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    touched = tuple(dict.fromkeys(path for case in selected for path in case.files()))
    diff_before = _git_diff_digest(touched)
    tree_before = _git_diff_digest()
    results = [_execute(case, out_dir, args.timeout) for case in selected]
    diff_after = _git_diff_digest(touched)
    tree_after = _git_diff_digest()

    exit_code_probe = _git("diff", "--exit-code")
    clean = diff_before == diff_after

    print("\n" + "=" * 88)
    print(f"{'case':44s} {'worker':26s} verdict")
    print("-" * 88)
    for row in results:
        mark = "OK  " if row["demonstrated"] else "FAIL"
        print(f"{mark} {row['case']:39s} {row['worker']:26s} {str(row['verdict'])[:40]}")
    print("=" * 88)
    print(
        f"the {len(touched)} file(s) this harness planted into are unchanged: {clean} "
        f"(scoped git diff digest {diff_before[:12]} -> {diff_after[:12]})"
    )
    print(
        f"whole-tree git diff digest {tree_before[:12]} -> {tree_after[:12]} "
        f"({
            'unchanged'
            if tree_before == tree_after
            else 'MOVED — a concurrent wave wrote '
            'to a file this harness never touched; the scoped digest above is the claim'
        })"
    )
    print(
        "`git diff --exit-code` returned "
        f"{exit_code_probe.returncode} — non-zero here means the tree carried uncommitted "
        "work BEFORE this harness ran, which is the normal state of this branch. The "
        "binding proof is the digest equality above and the per-file SHA-256 check in each "
        "case."
    )

    report = {
        "generated_by": "scripts/qa/demo_suite_falsification.py",
        "planted_paths": list(touched),
        "scoped_git_diff_digest_before": diff_before,
        "scoped_git_diff_digest_after": diff_after,
        "whole_tree_git_diff_digest_before": tree_before,
        "whole_tree_git_diff_digest_after": tree_after,
        "working_tree_unchanged": clean,
        "git_diff_exit_code": exit_code_probe.returncode,
        "cases": results,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report: {out_dir / 'report.json'}")

    if not clean:
        return 1
    return 0 if all(row["demonstrated"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
