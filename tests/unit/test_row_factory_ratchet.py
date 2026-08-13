# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — nothing here connects to a database. That is the point: this lane runs under
#     `--crdb=none`, so the row-shape rule is enforced on a laptop and in a CI job that
#     never waits for a cluster.
# I: QA-RATCHET-3 — every statement that READS a row declares the shape it reads it in.
"""The row-factory ratchet, proven RED before it is trusted GREEN.

`scripts/qa/row_factory_ratchet.py` exists because two production 500s in this repository
were the same defect wearing different clothes: a statement read a row in a shape nobody
had declared, and got whichever shape the connection's opener happened to choose.
`db.py:309` opens `row_factory=dict_row`; psycopg's default is `tuple_row`; every test that
opened its own connection therefore exercised the opposite of what the Lambda ran.

PL-2 applies to a scanner harder than to anything else it checks. A scanner reports
"0 findings" identically whether the tree is clean or its own matcher is broken, and this
one has already been measured broken twice in one sitting:

  * an `ast.walk` that stopped one level too late put every function's body into the module
    scope as well as its own, doubling every finding and letting module-level bindings
    claim local names;
  * a `setdefault` in the binding pass froze the first answer, so a row bound before its
    cursor had been resolved stayed `inherited` forever and a fully declared read was
    reported as undeclared.

Neither showed up as an error. Both showed up as a NUMBER that was wrong. So every rule
below is driven twice — once against a synthetic tree built to trip it, and once against a
synthetic tree built to look like it should trip it and not. The green half means nothing
without the red half; the red half means nothing without the near-miss beside it.

The three claims about THIS repository, at the bottom, are the ones with teeth:

  * `mainline_demo_api` — the package the demo serves from — is at ZERO, so the rule is a
    hard gate there rather than a debt ceiling.
  * the whole tree is at or below :data:`CEILING`, a number that may fall and may not rise.
  * the scan names a real disagreement OUTSIDE demo-api. A ratchet whose only findings are
    in the package its author owns is a ratchet that has not been pointed at anything.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "qa" / "row_factory_ratchet.py"
DEMO_API_SRC = REPO_ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "src"
PACKAGE = DEMO_API_SRC / "mainline_demo_api"

#: The repository's undeclared-row-read debt, measured on 2026-08-13 against `master` at
#: `2adad9e` with W1's `refusal.py` fix and W3's `testpaths` fix in the tree:
#:
#:     16 = inherited_positional_read 9 + both_shapes 1 + mixed_conventions 4
#:          + mutates_connection_row_factory 2
#:
#: A ceiling, not a target: `assert count <= CEILING`, so a worker who fixes one of the
#: nine legacy positional reads in `demo-api/tests` makes this test pass more comfortably
#: and is not obliged to touch this line. Raising it requires a diff someone approves.
#:
#: It lives here rather than in `qa/row-factory-ratchet.json` because `qa/` belongs to no
#: worker in this wave and a new file there would be an unowned edit. The scanner already
#: accepts `--baseline <path>` and emits the same `count` under `--json`, so moving the
#: number into `qa/` later changes where it is written down and not what it means.
CEILING = 16

#: The evidence the demo-correctness lead cited, kept as a coordinate rather than a count.
#: `mainline-custody-patrol` is owned by nobody in this wave, so this line is a stable
#: anchor: if the scanner ever stops naming it, the scanner broke, not the tree.
ANCHOR_FILE = (
    "verticals/mainline/packages/mainline-custody-patrol/src/mainline_custody_patrol/collect.py"
)
ANCHOR_LINE = 376


def _load() -> ModuleType:
    """Import the scanner by path; `scripts/` is deliberately not an importable package."""
    spec = importlib.util.spec_from_file_location("_row_factory_ratchet", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE execution: `dataclasses` resolves a class's own module out of
    # `sys.modules` while processing it, and a module that is not there yet fails with
    # `'NoneType' object has no attribute '__dict__'`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ratchet = _load()


# ── Synthetic trees ─────────────────────────────────────────────────────────────────

#: A file that makes its directory a HAZARD unit: something here opens mapping rows, so a
#: borrowed positional read inside the same unit genuinely cannot know what it will get.
#: Every "should fire" case below pairs its subject with this, because the gate is the
#: honest half of the rule — see the scanner's docstring for the 508-finding measurement
#: that made it necessary.
OPENER = """\
import psycopg
from psycopg.rows import dict_row


def connect(dsn):
    return psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
"""


def scan(tmp_path: Path, files: dict[str, str]) -> Any:
    """Write *files* under *tmp_path* and scan them as if that were the repository root."""
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body), encoding="utf-8")
    return ratchet.scan([tmp_path], repo_root=tmp_path)


def kinds(report: Any) -> list[str]:
    return [finding.kind for finding in report.ordered()]


def at(report: Any, kind: str) -> list[int]:
    return sorted(f.line for f in report.findings if f.kind == kind)


# ── RED: each rule, tripped on purpose ──────────────────────────────────────────────


def test_the_refusal_defect_of_2026_08_12_is_named_with_its_line(tmp_path: Path) -> None:
    """The exact shape that took `/v1/gate/run` to a 500 on beats 2 and 3 of every run.

    Four statements through `positional()` and one bare fetch whose row is indexed at [0].
    Under `dict_row` that index is `KeyError: 0`, and CockroachDB names the single
    unaliased column `explain_refusal`, so there is no ordinal 0 to find.
    """
    report = scan(
        tmp_path,
        {
            "pkg/db.py": OPENER,
            "pkg/refusal.py": """\
                from .scenario import positional


                def explain(conn, subject):
                    positional(conn, "SAVEPOINT trappoint_explain")
                    row = conn.execute(
                        "SELECT trappoint.explain_refusal(%s)", (subject,)
                    ).fetchone()
                    positional(conn, "RELEASE SAVEPOINT trappoint_explain")
                    return row[0] if row else None
                """,
        },
    )
    # Two findings, two DIFFERENT lines, and the pair is the point: the positional read is
    # reported where the row is indexed (line 10) and the undeclared statement where it is
    # issued (line 6). A scanner that reported both at one line would be naming the
    # symptom's location, which is the mistake `22P02` made in the first place.
    assert at(report, "inherited_positional_read") == [10], report.ordered()
    assert at(report, "mixed_conventions") == [6], report.ordered()
    named = report.ordered()[0]
    assert named.path.endswith("refusal.py")
    assert "scenario.positional(conn, sql, params)" in named.fix
    assert "KeyError" in named.detail


def test_unpacking_a_borrowed_row_into_names_is_named(tmp_path: Path) -> None:
    """`scenario.resolve`'s original defect: unpacking a dict yields its KEYS.

    It does not raise. It binds the seven-letter string `check_id` as `$2` of the next
    statement and comes back as `22P02: could not parse "check_id" as type uuid`, one
    statement away from where the mistake was made. Nothing but a structural rule finds
    this, because the symptom names the wrong line.
    """
    report = scan(
        tmp_path,
        {
            "pkg/db.py": OPENER,
            "pkg/scenario.py": """\
                def resolve(conn):
                    permit_id, check_id, receipt_id = conn.execute(
                        "SELECT permit_id, check_id, receipt_id FROM demo"
                    ).fetchone()
                    return conn.execute("SELECT 1 FROM t WHERE id = %s", (check_id,))
                """,
        },
    )
    assert kinds(report) == ["inherited_positional_read"], report.ordered()
    assert "column NAMES" in report.findings[0].detail


def test_a_row_read_both_ways_is_named_with_no_hazard_at_all(tmp_path: Path) -> None:
    """`collect.py:376`'s shape, in a unit that opens nothing.

    Ungated on purpose. Every other finding needs evidence that mapping rows really arrive
    in that unit; this one does not, because the code is already saying it does not know
    which shape it will get. That is the state the declared conventions exist to replace.
    """
    report = scan(
        tmp_path,
        {
            "solo/collect.py": """\
                def seq_for_leaf_hash(self, site_code, leaf_hash):
                    with self.connection.cursor() as cur:
                        cur.execute("SELECT seq FROM t WHERE h = %s", (leaf_hash,))
                        row = cur.fetchone()
                    if row is None:
                        return None
                    return int(row[0] if isinstance(row, (list, tuple)) else row["seq"])
                """,
        },
    )
    assert kinds(report) == ["both_shapes"], report.ordered()
    assert report.findings[0].line == 7
    assert "delete the isinstance()" in report.findings[0].fix


def test_mutating_a_live_connection_s_factory_is_named_even_when_restored(
    tmp_path: Path,
) -> None:
    """Save-and-restore narrows the window; it does not close it.

    Anything the body calls runs inside the changed window, on the same warm container,
    and `reads.py` is exactly what that body calls.
    """
    report = scan(
        tmp_path,
        {
            "pkg/capture.py": """\
                from psycopg.rows import dict_row


                def read(conn, handler):
                    previous = conn.row_factory
                    conn.row_factory = dict_row
                    try:
                        return handler(conn)
                    finally:
                        conn.row_factory = previous
                """,
        },
    )
    assert kinds(report) == ["mutates_connection_row_factory"] * 2
    assert at(report, "mutates_connection_row_factory") == [6, 10]


def test_contradicting_a_declaration_is_named(tmp_path: Path) -> None:
    """A cursor told to make tuples, read by name. The intent is on the page."""
    report = scan(
        tmp_path,
        {
            "pkg/gate.py": """\
                from psycopg.rows import tuple_row


                def head(conn):
                    row = conn.cursor(row_factory=tuple_row).execute(
                        "SELECT head_seq FROM permit"
                    ).fetchone()
                    return row["head_seq"]
                """,
        },
    )
    assert kinds(report) == ["declared_shape_contradicted"], report.ordered()
    assert "duplicate names" in report.findings[0].fix


# ── GREEN: the near-misses, which are what make the reds mean something ──────────────


def test_reading_a_borrowed_connection_by_name_only_is_not_a_finding(tmp_path: Path) -> None:
    """`reads.py`'s convention, and the reason the rule is not "never inherit".

    Twelve GET resources make 43 name-keyed accesses off the connection `db.connection()`
    opened. Banning `conn.execute(...).fetchone()` outright would have demanded all twelve
    be rewritten to buy nothing, which is why the rule asks for a DECLARATION instead. This
    is the case that would have caught that mistake.
    """
    report = scan(
        tmp_path,
        {
            "pkg/db.py": OPENER,
            "pkg/reads.py": """\
                def row(conn, sql, args):
                    result = conn.execute(sql, args).fetchone()
                    return dict(result) if result is not None else None


                def rows(conn, sql, args):
                    return [dict(item) for item in conn.execute(sql, args).fetchall()]


                def permit(conn, permit_id):
                    sql = "SELECT * FROM permit WHERE id = %s"
                    found = conn.execute(sql, (permit_id,)).fetchone()
                    return {"state": found["state"], "seq": found["head_seq"]}
                """,
        },
    )
    assert report.findings == [], report.ordered()
    assert report.conventions["pkg/reads.py"].verdict == "name"


def test_an_explicit_dict_row_cursor_is_a_declaration(tmp_path: Path) -> None:
    """`health.py`'s convention: the statement says what it wants, and gets it."""
    report = scan(
        tmp_path,
        {
            "pkg/db.py": OPENER,
            "pkg/health.py": """\
                from psycopg.rows import dict_row


                def read(conn, statement):
                    with conn.cursor(row_factory=dict_row) as cur:
                        cur.execute(statement)
                        row = cur.fetchone()
                    return row["migrations_applied"]
                """,
        },
    )
    assert report.findings == [], report.ordered()
    assert report.conventions["pkg/health.py"].verdict == "name"


def test_a_module_that_opened_its_own_connection_may_read_it_positionally(
    tmp_path: Path,
) -> None:
    """psycopg's default IS `tuple_row`, and 207 sites in this tree rely on that.

    An opener has already answered the question for its own reads. Calling this a defect
    is what turned a 16-finding report into a 508-finding one in which the four real
    defects could not be seen.
    """
    report = scan(
        tmp_path,
        {
            "pkg/probe.py": """\
                import psycopg


                def count(dsn):
                    with psycopg.connect(dsn, autocommit=True) as conn:
                        row = conn.execute("SELECT count(*) FROM permit").fetchone()
                        return int(row[0])
                """,
        },
    )
    assert report.findings == [], report.ordered()
    assert report.default_openers == 1


def test_positional_declares_the_shape_and_clears_the_module(tmp_path: Path) -> None:
    """`scenario.positional()` at every site: the demo-api package's own convention."""
    report = scan(
        tmp_path,
        {
            "pkg/db.py": OPENER,
            "pkg/gate_run.py": """\
                from .scenario import positional


                def fingerprint(conn):
                    counts = positional(conn, "SELECT count(*) FROM a").fetchone()
                    head = positional(conn, "SELECT head_seq FROM p WHERE id = %s", (1,)).fetchone()
                    return [int(n) for n in counts], head[0]
                """,
        },
    )
    assert report.findings == [], report.ordered()
    assert report.conventions["pkg/gate_run.py"].verdict == "position"


# ── The pragma is a declaration, not a mute button ───────────────────────────────────


def test_a_rowshape_pragma_declares_a_borrowed_read(tmp_path: Path) -> None:
    """`# rowshape: name` on a statement that then reads by name: no finding.

    This is the escape hatch, and it has to exist: `test_the_production_connection_really_
    is_dict_row` reads the connection's OWN shape on purpose, which is structurally
    indistinguishable from having forgotten to declare one.
    """
    report = scan(
        tmp_path,
        {
            "pkg/db.py": OPENER,
            "pkg/premise.py": """\
                def one(conn):
                    row = conn.execute("SELECT 1 AS one").fetchone()  # rowshape: name
                    return row["one"]
                """,
        },
    )
    assert report.findings == [], report.ordered()


def test_a_rowshape_pragma_that_lies_fails_louder_than_no_pragma(tmp_path: Path) -> None:
    """The same statement, the same pragma, an index instead of a key.

    If the pragma suppressed rather than declared, this would be silent — and a
    suppression comment is how every ratchet in this repository would eventually be
    disarmed one line at a time. Instead the declaration becomes the thing the code is
    measured against, and the finding is SHARPER than the undeclared version: it can say
    which of the two is wrong.
    """
    report = scan(
        tmp_path,
        {
            "pkg/db.py": OPENER,
            "pkg/premise.py": """\
                def one(conn):
                    row = conn.execute("SELECT 1 AS one").fetchone()  # rowshape: name
                    return row[0]
                """,
        },
    )
    assert kinds(report) == ["declared_shape_contradicted"], report.ordered()
    assert "declares the name convention" in report.findings[0].detail


# ── Non-vacuity: the scanner can be shown to have looked ─────────────────────────────


def test_an_empty_tree_reports_zero_and_says_so(tmp_path: Path) -> None:
    """The control for every green above: 0 findings over 0 files is not a clean tree."""
    report = scan(tmp_path, {"pkg/nothing.py": "VALUE = 1\n"})
    assert report.findings == []
    assert report.files_scanned == 1
    assert report.files_parsed == 0, "a file with no psycopg token is not parsed"
    assert report.conventions["pkg/nothing.py"].verdict == "silent"


def test_a_name_bound_twice_in_one_scope_is_dropped_rather_than_guessed(
    tmp_path: Path,
) -> None:
    """The false-positive class that cost this scanner its first three `both_shapes`.

    `row` fetched near the top of a function and reused as a comprehension target near the
    bottom is one name and two things. Python's scoping cannot tell them apart without
    running the code, and neither can this. Reporting the second as a positional read of
    the first is a manufactured finding, and a manufactured finding is how a ratchet stops
    being believed.
    """
    report = scan(
        tmp_path,
        {
            "pkg/db.py": OPENER,
            "pkg/report.py": """\
                def summarise(conn, doc):
                    row = conn.execute("SELECT version()").fetchone()
                    version = row["version"]
                    total = sum(1 for row in doc["packages"].values() if row[0])
                    return version, total
                """,
        },
    )
    assert report.findings == [], report.ordered()


# ── This repository ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def repo_report() -> Any:
    """One scan of the whole tree, shared. It takes about ten seconds; do it once."""
    return ratchet.scan([REPO_ROOT])


def test_the_repository_scan_is_not_vacuous(repo_report: Any) -> None:
    """A ratchet over a glob that matched nothing prints the same sentence as a clean one."""
    assert repo_report.files_scanned > 900, repo_report.files_scanned
    assert repo_report.files_parsed > 150, repo_report.files_parsed
    assert repo_report.unparseable == [], repo_report.unparseable
    assert len(repo_report.non_default_openers) >= 10
    assert repo_report.default_openers >= 100


def test_the_demo_api_package_declares_every_row_it_reads() -> None:
    """The hard gate: `mainline_demo_api` is at ZERO, not at a ceiling.

    This is the same claim `verticals/.../tests/test_row_factory_contract.py` makes, made
    here as well because that module is marked `requires_cluster` and therefore SKIPS on a
    checkout with no CockroachDB. A structural rule that only runs when a database happens
    to be up is a rule that does not run on the machine where it is most needed.
    """
    report = ratchet.scan([PACKAGE])
    assert report.files_parsed >= 7, report.files_parsed
    assert report.findings == [], "\n".join(
        [
            "mainline_demo_api reads a row in a shape nobody declared:",
            *(finding.render() for finding in report.ordered()),
        ]
    )
    verdicts = {Path(p).name: c.verdict for p, c in report.conventions.items()}
    assert "mixed" not in verdicts.values(), verdicts


def test_the_scanner_names_a_real_disagreement_outside_the_demo_api(repo_report: Any) -> None:
    """Pointed at the whole tree, not at its author's own package.

    `collect.py` handles BOTH row shapes defensively:

        int(row[0] if isinstance(row, (list, tuple)) else row["seq"])

    Nothing is broken there today. What is wrong is that the author could not know which
    shape would arrive, so the code answers both — which is precisely the condition the
    declared conventions remove, and precisely what `refusal.py` and `scenario.resolve`
    looked like before they became 500s.
    """
    mine = "verticals/mainline/apps/demo-api"
    outside = [f for f in repo_report.ordered() if not f.path.startswith(mine)]
    assert outside, "every finding is inside this worker's own package; the scan is inbred"
    anchor = [f for f in outside if f.path == ANCHOR_FILE and f.line == ANCHOR_LINE]
    assert anchor, (
        f"{ANCHOR_FILE}:{ANCHOR_LINE} is the measured defensive both-shapes read this "
        "ratchet was built around and it is no longer reported. Either it was fixed — in "
        "which case delete this test and say so — or the scanner stopped seeing it, which "
        f"is the failure this file exists to catch. Outside demo-api: "
        f"{[(f.path, f.line, f.kind) for f in outside]}"
    )
    assert anchor[0].kind == "both_shapes"


def test_the_repo_wide_count_may_fall_and_may_not_rise(repo_report: Any) -> None:
    """The ratchet itself.

    A ceiling rather than an equality, so a worker who declares one of the nine legacy
    positional reads in `demo-api/tests` does not have to come back here to edit a number.
    An increase is a hard stop and names every finding, because a row-shape declaration
    that was removed is a 500 that has not happened yet.
    """
    assert repo_report.count <= CEILING, "\n".join(
        [
            f"row-factory debt rose from {CEILING} to {repo_report.count}.",
            *(finding.render() for finding in repo_report.ordered()),
            "",
            (
                "Declare the shape at the statement, or - if the increase is genuinely "
                f"correct - raise CEILING in {Path(__file__).name} in a diff someone "
                "approves. Raising it is allowed. Raising it silently is not."
            ),
        ]
    )
    if repo_report.count < CEILING:
        pytest.skip(
            f"row-factory debt is down to {repo_report.count} from {CEILING}; "
            "tighten CEILING to lock the improvement in."
        )


# ── The command line, which is what CI would run ────────────────────────────────────


def test_the_script_refuses_above_a_ceiling_and_accepts_at_one(tmp_path: Path) -> None:
    """`--max` is the CI contract, so it is exercised as a process, not as an import."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "db.py").write_text(OPENER, encoding="utf-8")
    (tmp_path / "pkg" / "bad.py").write_text(
        'def go(conn):\n    return conn.execute("SELECT 1").fetchone()[0]\n', encoding="utf-8"
    )
    argv = [sys.executable, str(SCRIPT), str(tmp_path), "--quiet"]

    refused = subprocess.run([*argv, "--max", "0"], capture_output=True, text=True, check=False)
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert "REFUSED" in refused.stdout

    accepted = subprocess.run([*argv, "--max", "1"], capture_output=True, text=True, check=False)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert "at the ceiling (1)" in accepted.stdout


def test_the_script_emits_a_machine_readable_count(tmp_path: Path) -> None:
    """The number a ratchet compares has to be readable without parsing prose."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "db.py").write_text(OPENER, encoding="utf-8")
    (tmp_path / "pkg" / "bad.py").write_text(
        'def go(conn):\n    return conn.execute("SELECT 1").fetchone()[0]\n', encoding="utf-8"
    )
    out = tmp_path / "census.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path), "--json", "--write", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    doc = json.loads(proc.stdout)
    assert doc == json.loads(out.read_text(encoding="utf-8")) or doc["count"] == 1
    assert doc["schema"] == ratchet.SCHEMA
    assert doc["count"] == 1
    assert doc["by_kind"]["inherited_positional_read"] == 1
    assert doc["openers"]["non_default_count"] == 1
    assert doc["findings"][0]["file"].endswith("bad.py")
    assert doc["findings"][0]["line"] == 2
    assert doc["findings"][0]["fix"]


def test_the_script_never_writes_to_a_source_file(tmp_path: Path) -> None:
    """The one property that makes it safe to run anywhere, asserted rather than promised."""
    (tmp_path / "pkg").mkdir()
    source = tmp_path / "pkg" / "bad.py"
    body = 'def go(conn):\n    return conn.execute("SELECT 1").fetchone()[0]\n'
    source.write_text(body, encoding="utf-8")
    (tmp_path / "pkg" / "db.py").write_text(OPENER, encoding="utf-8")
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.py"))}

    subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path), "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*.py"))}
    assert after == before
