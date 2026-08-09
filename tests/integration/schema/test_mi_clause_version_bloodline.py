# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""MI15 / I05 — the BLOODLINE monotone guard on ``mainline.clause_version``.

What this suite proves
----------------------
``mainline.clause_version`` has carried ``sev_max``, ``blood_size`` and ``blood_root`` since
migration 0029 with nothing defending their direction. Migrations 0141 and 0146 add the guard
``spec/invariants/I05-ancestry-monotone.md`` names — ``mainline.fn_clause_version_guard`` — and
``spec/conformance/manifest.toml`` case ``CF-56`` pins its SQLSTATE at ``P0001`` and its exhibit at
that exact function name. This file executes the refusals, executes the admissions, and — the part
that makes the rest mean anything — executes the same matrix against the SAME schema with the
guard absent, in the same run, so the red baseline is a measurement rather than a memory.

PL-2, made mechanical
---------------------
A suite that has never been red asserts nothing. ``test_red_anchor_*`` applies migrations
0001-0049a into a second database WITHOUT 0141/0146 and asserts that every history this file
refuses is **accepted** there. If somebody deletes the guard, those tests keep passing and the
green ones fail; if somebody weakens the guard into a no-op, the green ones fail. There is no
edit that makes both halves pass except a guard that actually refuses.

What is deliberately not asserted
---------------------------------
* Nothing about the FIRING ORDER of two row-level triggers on one table. CockroachDB v26.2 does
  not document it. ``test_the_two_guards_coexist`` asserts both triggers are attached and that
  each one's own refusal still fires; it says nothing about which runs first.
* Nothing about the birth dodge. ``parent_version IS NULL`` starts a fresh lineage at zero and is
  admitted here on purpose — 0029 makes it a visible claim, and Conservation of Blame Mass (0049)
  is what interrogates it. ``test_a_birth_version_is_admitted`` records that this is a choice.

Running it
----------
The source tier needs no cluster. The cluster tier (``@pytest.mark.requires_cluster``) finds a
CockroachDB v26.2 in this order and **skips with a reason** rather than faking anything:

1. a session ``dsn`` fixture, if ``tests/integration/schema/conftest.py`` (owned by ``dm-runner``)
   is present, so every schema suite shares one cluster;
2. ``$MAINLINE_TEST_DSN`` / ``$COCKROACH_URL`` / ``$CRDB_URL`` / ``$TRAPPOINT_DSN``;
3. a ``cockroach`` binary on ``PATH`` (in-memory single node, session-scoped);
4. a running Docker daemon (``cockroachdb/cockroach:latest-v26.2``).

MI15 is NOT verified by a skipped run, and the skip message says which of the four is missing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Paths, names and the six pinned messages
# ══════════════════════════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "verticals" / "mainline" / "db"
MIGRATIONS_DIR = DB_DIR / "migrations"
MANIFEST = REPO_ROOT / "spec" / "conformance" / "manifest.toml"

FN_FILE = "0141_fn_clause_version_guard.sql"
TRG_FILE = "0146_trg_clause_version_guard.sql"

#: Not a preference. ``spec/conformance/manifest.toml`` CF-56 carries this string as
#: ``expect_constraint`` and I05's OBSERVABLE table names it as the exhibit. A conformance case
#: whose exhibit does not exist is a case that cannot pass.
FUNCTION_NAME = "mainline.fn_clause_version_guard"

#: The name 0140's header reserved for this guard on this table.
TRIGGER_NAME = "clause_version_guard"

#: Everything below `0050` plus the two vertical-guard pairs. One statement per file (the tree is
#: linted for exactly that), so the applier never splits — which matters, because 0140 and 0141
#: carry ``$$``-quoted bodies full of semicolons.
EXTRA_FILES: tuple[str, ...] = (
    "0140_fn_delta_witness_guard.sql",
    FN_FILE,
    "0145_trg_delta_witness_guard.sql",
    TRG_FILE,
)
FOUNDATION_LAST = 49

MSG_INSERT_SEV = (
    "MAINLINE: blame ancestry never shrinks — this version lowers sev_max below its parent"
)
MSG_INSERT_SIZE = (
    "MAINLINE: blame ancestry never shrinks — this version lowers blood_size below its parent"
)
MSG_REROOT = (
    "MAINLINE: blood_root changed while blood_size did not — an MMR over an unchanged "
    "multiset has an unchanged root"
)
MSG_SELF_PARENT = "MAINLINE: a clause version may not declare itself its own parent"
MSG_NO_PARENT = (
    "MAINLINE: the parent clause version is not readable — MI15 cannot be decided, so the "
    "write is refused"
)
MSG_UPDATE_SEV = (
    "MAINLINE: blame ancestry never shrinks — this update lowers clause_version.sev_max"
)
MSG_UPDATE_SIZE = (
    "MAINLINE: blame ancestry never shrinks — this update lowers clause_version.blood_size"
)

ALL_MESSAGES: tuple[str, ...] = (
    MSG_INSERT_SEV,
    MSG_INSERT_SIZE,
    MSG_REROOT,
    MSG_SELF_PARENT,
    MSG_NO_PARENT,
    MSG_UPDATE_SEV,
    MSG_UPDATE_SIZE,
)

MR5_FILENAME = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")
CRDB_IMAGE = "cockroachdb/cockroach:latest-v26.2"
CONTAINER_NAME = "mainline-mi15-test"
READY_TIMEOUT_S = 90.0
DOCKER_PROBE_TIMEOUT_S = 20.0
DOCKER_RUN_TIMEOUT_S = 120.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# SOURCE TIER — no cluster, runs anywhere
# ══════════════════════════════════════════════════════════════════════════════════════════════


def strip_sql_comments(text: str) -> str:
    """Remove ``--`` and ``/* */`` comments, preserving string literals and quoted identifiers."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        out.append("''")
                        i += 2
                        continue
                    out.append("'")
                    i += 1
                    break
                out.append(text[i])
                i += 1
            continue
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n and text[i] != '"':
                out.append(text[i])
                i += 1
            if i < n:
                out.append('"')
                i += 1
            continue
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def top_level_statement_count(text: str) -> int:
    """Count ``;`` outside comments, string literals and ``$$``-quoted routine bodies."""
    body = strip_sql_comments(text)
    count, i, n, in_dollar = 0, 0, len(body), False
    while i < n:
        if body.startswith("$$", i):
            in_dollar = not in_dollar
            i += 2
            continue
        ch = body[i]
        if not in_dollar and ch == "'":
            i += 1
            while i < n and body[i] != "'":
                i += 1
            i += 1
            continue
        if not in_dollar and ch == ";":
            count += 1
        i += 1
    return count


def test_both_files_exist_and_obey_the_one_filename_convention() -> None:
    """MR-5: ``NNNN[a-z]_lower_snake_slug.sql``. No ``.up.sql``, no second dot."""
    for name in (FN_FILE, TRG_FILE):
        path = MIGRATIONS_DIR / name
        assert path.is_file(), f"{name} is missing; MI15 has no guard without it"
        assert MR5_FILENAME.match(name), f"{name} violates MR-5's filename convention"


def test_the_files_sit_in_their_allocated_bands_in_the_right_order() -> None:
    """The function is in the vertical FUNCTION band, the trigger in the vertical TRIGGER band.

    ``migrations.allocation.toml`` grants ``0140-0144z`` to vertical PL/pgSQL functions and
    ``0145-0149z`` to vertical triggers, both to ``datamodel/dm-functions-triggers + algorithms``.
    Ordering is lexicographic on the whole stem, so 0029 < 0141 < 0146 puts the table before the
    function before the trigger — every dependency pointing backwards.
    """
    assert int(FN_FILE[:4]) in range(140, 145), "the function is outside the vertical function band"
    assert int(TRG_FILE[:4]) in range(145, 150), "the trigger is outside the vertical trigger band"
    assert FN_FILE < TRG_FILE, "the trigger must sort after the function it attaches"
    assert FN_FILE > "0029_clause_version.sql", "the guard must sort after the table it guards"


@pytest.mark.parametrize("name", [FN_FILE, TRG_FILE])
def test_each_file_carries_the_four_linted_header_keys_and_one_statement(name: str) -> None:
    """``MI:``, ``I:``, ``COUNSEL-GATED:``, ``RATIONALE:``, and exactly one top-level statement."""
    text = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
    for key in ("MI: MI15", "I: I05", "COUNSEL-GATED: no", "RATIONALE:"):
        assert key in text, f"{name} omits the linted header key {key!r}"
    assert "SPDX-License-Identifier: FSL-1.1-ALv2" in text, f"{name} carries no REUSE licence tag"
    count = top_level_statement_count(text)
    assert count == 1, (
        f"{name} declares {count} top-level statements. CockroachDB DDL is not transactional "
        "across statements, so a half-applied file leaves an undiagnosable dirty marker."
    )


def test_the_function_name_is_the_exhibit_cf56_already_names() -> None:
    """CF-56's ``expect_constraint`` is a contract, not documentation.

    The conformance manifest was written before this guard existed and it names
    ``mainline.fn_clause_version_guard`` as the exhibit for *a clause version whose sev_max is
    lower than its parent's*. A guard under any other name leaves CF-56 unpassable.
    """
    manifest = MANIFEST.read_text(encoding="utf-8")
    block = manifest.split('id = "CF-56"', 1)
    assert len(block) == 2, "CF-56 is absent from spec/conformance/manifest.toml"
    case = block[1].split("[[case]]", 1)[0]
    assert f'expect_constraint = "{FUNCTION_NAME}"' in case, (
        f"CF-56 names a different exhibit than {FUNCTION_NAME}"
    )
    assert 'expect_sqlstate = "P0001"' in case, "CF-56 no longer expects P0001"
    body = (MIGRATIONS_DIR / FN_FILE).read_text(encoding="utf-8")
    assert f"CREATE FUNCTION {FUNCTION_NAME}()" in body, (
        f"0141 does not define {FUNCTION_NAME}; CF-56 would have no exhibit"
    )


def test_every_refusal_message_this_suite_pins_is_present_in_the_function_body() -> None:
    """The strings the cluster tier asserts on are the strings the function actually raises."""
    body = strip_sql_comments((MIGRATIONS_DIR / FN_FILE).read_text(encoding="utf-8"))
    raised = set(re.findall(r"MESSAGE\s*=\s*'([^']*)'", body))
    assert raised == set(ALL_MESSAGES), (
        "the messages 0141 raises and the messages this suite pins have diverged.\n"
        f"  raised but unpinned: {sorted(raised - set(ALL_MESSAGES))}\n"
        f"  pinned but unraised: {sorted(set(ALL_MESSAGES) - raised)}\n"
        "A refusal nobody pinned is a refusal nobody can rely on."
    )
    # Eight RAISE statements, seven distinct messages: the re-rooting refusal is worded identically
    # in the INSERT arm and the UPDATE arm because it is the same defect against a different
    # baseline, and a writer who hits it should not have to work out which arm caught them.
    raises = body.upper().count("RAISE EXCEPTION")
    assert raises == 8, f"0141 has {raises} RAISE statements; the six documented refusals need 8"
    errcodes = set(re.findall(r"ERRCODE\s*=\s*'([^']*)'", body))
    assert errcodes == {"P0001"}, (
        f"the refusals must all be P0001 — CF-56 and I05 both pin it; found {sorted(errcodes)}"
    )


def test_the_trigger_is_after_insert_or_update_for_each_row() -> None:
    """The timing is the decision in 0146; if somebody flips it back, this says why not.

    ``BEFORE`` was built and measured: it cannot see a parent written by its own statement (a
    one-statement bypass of MI15) and it runs ahead of referential integrity, which would replace
    ``fk_parent_version``'s 23503 with a trigger message and turn a green ``test_mi_spine`` test
    red. The evidence table is in 0141's header.
    """
    statement = strip_sql_comments((MIGRATIONS_DIR / TRG_FILE).read_text(encoding="utf-8"))
    collapsed = " ".join(statement.split()).upper()
    assert f"CREATE TRIGGER {TRIGGER_NAME.upper()} AFTER INSERT OR UPDATE" in collapsed, (
        "0146 must attach AFTER INSERT OR UPDATE; see its header for the measurement"
    )
    assert "ON MAINLINE.CLAUSE_VERSION" in collapsed
    assert "FOR EACH ROW" in collapsed
    assert f"EXECUTE FUNCTION {FUNCTION_NAME.upper()}()" in collapsed


def test_the_dm_spine_red_scan_now_finds_a_guard() -> None:
    """The green counterpart of ``test_pl2_red_mi15_bloodline_guard_does_not_exist_yet``.

    That test scans every migration for a ``CREATE FUNCTION`` whose body reads ``sev_max`` or
    ``blood_size`` and RAISEs, and asserts the list is non-empty. It was RED by design for the
    whole of the spine band. This runs the identical scan so the promotion is visible from the
    file that caused it, rather than only from ``dm-spine``'s suite.
    """
    guards: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        body = strip_sql_comments(path.read_text(encoding="utf-8")).lower()
        if not re.search(r"\bcreate\s+(or\s+replace\s+)?function\b", body):
            continue
        if "sev_max" not in body and "blood_size" not in body:
            continue
        if "raise" in body:
            guards.append(path.name)
    assert FN_FILE in guards, (
        f"{FN_FILE} is not recognised as a BLOODLINE guard by dm-spine's own scan. "
        "MI15 stays `pending` until it is."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLUSTER TIER
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Cluster:
    """A reachable CockroachDB, and where it came from."""

    dsn: str
    provenance: str
    proc: subprocess.Popen[bytes] | None = None
    owns_docker: bool = False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_until_ready(dsn: str, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
        except psycopg.Error:
            time.sleep(1.0)
        else:
            return True
    return False


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """A dead Docker daemon does not refuse ``docker info``; it BLOCKS, so this bounds it."""
    try:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _from_env() -> Cluster | None:
    for name in ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN"):
        value = os.environ.get(name)
        if value:
            return Cluster(dsn=value, provenance=f"${name}")
    return None


def _from_local_binary(tmp: Path) -> Cluster | None:
    binary = shutil.which("cockroach")
    if binary is None:
        return None
    port, http_port = _free_port(), _free_port()
    proc = subprocess.Popen(
        [
            binary,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
            f"--listen-addr=127.0.0.1:{port}",
            f"--http-addr=127.0.0.1:{http_port}",
        ],
        cwd=str(tmp),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"local `cockroach` binary on {port}", proc=proc)
    proc.terminate()
    return None


def _from_docker() -> Cluster | None:
    if shutil.which("docker") is None:
        return None
    probe = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=DOCKER_PROBE_TIMEOUT_S)
    if probe is None or probe.returncode != 0:
        return None
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    port = _free_port()
    started = _docker(
        [
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "-p",
            f"{port}:26257",
            CRDB_IMAGE,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
        ],
        timeout=DOCKER_RUN_TIMEOUT_S,
    )
    if started is None or started.returncode != 0:
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on {port}", owns_docker=True)
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    return None


@pytest.fixture(scope="session")
def mi15_cluster(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Cluster]:
    """One cluster for the whole file, shared with dm-runner's ``dsn`` fixture when present."""
    # A blanket `except` and not `except FixtureLookupError`: pytest does not export that class
    # publicly. A `Skipped` from their fixture derives from BaseException and propagates untouched,
    # which is what we want — their skip reason is better than ours.
    try:
        shared = request.getfixturevalue("dsn")
    except Exception:  # noqa: BLE001
        shared = None
    if isinstance(shared, str) and shared:
        yield Cluster(dsn=shared, provenance="the `dsn` fixture from tests/integration/schema")
        return

    found = _from_env() or _from_local_binary(tmp_path_factory.mktemp("crdb")) or _from_docker()
    if found is None:
        pytest.skip(
            "no CockroachDB v26.2 reachable. Provide one of: tests/integration/schema/conftest.py "
            "with a session `dsn` fixture (dm-runner), $MAINLINE_TEST_DSN, a `cockroach` binary on "
            f"PATH, or a running Docker daemon for `docker run {CRDB_IMAGE}`. MI15 is NOT verified "
            "by a skipped run."
        )
    try:
        yield found
    finally:
        if found.proc is not None:
            found.proc.terminate()
        if found.owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


def foundation_paths() -> list[Path]:
    """Every migration up to and including 0049a, in the runner's lexicographic order."""
    return sorted(
        p
        for p in MIGRATIONS_DIR.glob("*.sql")
        if MR5_FILENAME.match(p.name) and int(p.name[:4]) <= FOUNDATION_LAST
    )


def _apply(conn: Any, path: Path) -> None:
    """Apply one file as ONE statement.

    Never split: the tree is linted for exactly one top-level statement per file, and 0140/0141
    carry ``$$``-quoted bodies whose semicolons a splitter would cut through.
    """
    try:
        conn.execute(path.read_text(encoding="utf-8"))
    except psycopg.Error as exc:
        raise AssertionError(f"{path.name} failed to apply: [{exc.sqlstate}] {exc}") from exc


@dataclass
class Schema:
    """A database with a known set of migrations applied."""

    dsn: str
    guarded: bool

    def connect(self) -> Any:
        return psycopg.connect(self.dsn, autocommit=True)


@pytest.fixture(scope="session")
def schemas(mi15_cluster: Cluster) -> Iterator[tuple[Schema, Schema]]:
    """Two databases from the same migrations: one with the guard, one without.

    The unguarded one is the red anchor. Building it here, in the same session, from the same
    files, is what makes ``red before green`` a property of every run rather than a claim about a
    run somebody did once.
    """
    from psycopg.conninfo import make_conninfo

    suffix = uuid.uuid4().hex[:10]
    guarded_db, unguarded_db = f"mi15_guarded_{suffix}", f"mi15_unguarded_{suffix}"
    with psycopg.connect(mi15_cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {guarded_db}")
        admin.execute(f"CREATE DATABASE {unguarded_db}")

    # make_conninfo rather than string surgery: an env-supplied DSN may carry
    # `options=--cluster=…` (CockroachDB Cloud), an sslrootcert path, or no path component at all.
    guarded_dsn = make_conninfo(mi15_cluster.dsn, dbname=guarded_db)
    unguarded_dsn = make_conninfo(mi15_cluster.dsn, dbname=unguarded_db)

    foundation = foundation_paths()
    for dsn, guarded in ((guarded_dsn, True), (unguarded_dsn, False)):
        with psycopg.connect(dsn, autocommit=True) as conn:
            for path in foundation:
                _apply(conn, path)
            if guarded:
                for name in EXTRA_FILES:
                    _apply(conn, MIGRATIONS_DIR / name)

    print(
        f"\n[mi15] cluster: {mi15_cluster.provenance}"
        f"\n[mi15] guarded={guarded_db} unguarded={unguarded_db}"
        f"\n[mi15] applied {len(foundation)} foundation migrations (+{len(EXTRA_FILES)} guarded)"
    )
    try:
        yield Schema(dsn=guarded_dsn, guarded=True), Schema(dsn=unguarded_dsn, guarded=False)
    finally:
        with psycopg.connect(mi15_cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {guarded_db} CASCADE")
            admin.execute(f"DROP DATABASE IF EXISTS {unguarded_db} CASCADE")


@pytest.fixture
def conn(schemas: tuple[Schema, Schema]) -> Iterator[Any]:
    """One autocommit connection against the GUARDED database, per test.

    Autocommit rather than a rolled-back transaction: a refused statement must not be able to hide
    behind a rollback that also erases the rows the test wrote before it.
    """
    connection = schemas[0].connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def red_conn(schemas: tuple[Schema, Schema]) -> Iterator[Any]:
    """One autocommit connection against the UNGUARDED database — the red anchor."""
    connection = schemas[1].connect()
    try:
        yield connection
    finally:
        connection.close()


# ── fixture helpers ───────────────────────────────────────────────────────────────────────────


def _digest(seed: str) -> bytes:
    """A 32-byte id. Real commit ids are sha256 over JCS bytes; this is the same shape."""
    return hashlib.sha256(seed.encode("utf-8")).digest()


@dataclass
class Lineage:
    """The four rows every scenario needs before it can write a version."""

    site_id: str
    doc_id: str
    clause_uuid: str
    tag: str

    def commit(self, label: str) -> bytes:
        return _digest(f"{self.tag}:{label}")


def _lineage(conn: Any, *, commits: int = 6) -> Lineage:
    site_id, doc_id, clause_uuid = (str(uuid.uuid4()) for _ in range(3))
    tag = uuid.uuid4().hex
    lineage = Lineage(site_id=site_id, doc_id=doc_id, clause_uuid=clause_uuid, tag=tag)
    for gen in range(commits):
        envelope = json.dumps({"gen": gen, "parents": [], "site": site_id}, sort_keys=True)
        conn.execute(
            """
            INSERT INTO mainline.commit_obj
              (commit_id, site_id, gen, ref_name, author_sub, message, envelope, envelope_bytes)
            VALUES (%s, %s::UUID, %s, %s, %s, %s, %s::JSONB, %s)
            """,
            (
                lineage.commit(f"c{gen}"),
                site_id,
                gen,
                "site/test/main",
                "sub-test",
                "test commit",
                envelope,
                envelope.encode("utf-8"),
            ),
        )
    conn.execute(
        """
        INSERT INTO mainline.doc (doc_id, site_id, doc_code, title, state, open_token_count)
        VALUES (%s::UUID, %s::UUID, %s, %s, 'live', 0)
        """,
        (doc_id, site_id, f"PRO-{tag[:6]}", "Test procedure"),
    )
    conn.execute(
        """
        INSERT INTO mainline.clause (clause_uuid, site_id, birth_commit, activity_root)
        VALUES (%s::UUID, %s::UUID, %s, 'isolation')
        """,
        (clause_uuid, site_id, lineage.commit("c0")),
    )
    return lineage


_VERSION_SQL = """
INSERT INTO mainline.clause_version
  (clause_uuid, gen, commit_id, site_id, doc_id, activity_root, parent_version,
   ordinal, raw_text, canon_text, canon_version, canon_sha256, anchor_set,
   cat_confidence, control_delta, delta_basis, blood_root, blood_peaks, blood_size, sev_max)
VALUES
  (%s::UUID, %s, %s, %s::UUID, %s::UUID, 'isolation', %s,
   %s, %s, %s, 1, %s, ARRAY[]::STRING[],
   'ok', %s::mainline.control_delta, 'lattice', %s, ARRAY[]::BYTES[], %s, %s)
"""


def _version_params(
    lin: Lineage,
    *,
    gen: int,
    commit_label: str,
    parent: bytes | None,
    sev_max: int,
    blood_size: int,
    root_label: str,
    control_delta: str = "restate",
    text: str = "Isolate stored energy before intrusive work.",
) -> tuple[Any, ...]:
    return (
        lin.clause_uuid,
        gen,
        lin.commit(commit_label),
        lin.site_id,
        lin.doc_id,
        parent,
        gen,
        text,
        text,
        hashlib.sha256(text.encode("utf-8")).digest(),
        control_delta,
        _digest(f"{lin.tag}:root:{root_label}"),
        blood_size,
        sev_max,
    )


def _write_version(conn: Any, lin: Lineage, **kwargs: Any) -> None:
    conn.execute(_VERSION_SQL, _version_params(lin, **kwargs))


def _refusal(conn: Any, lin: Lineage, **kwargs: Any) -> Any:
    with pytest.raises(psycopg.Error) as caught:
        _write_version(conn, lin, **kwargs)
    return caught.value


def _seed_parent(conn: Any, lin: Lineage, *, sev_max: int = 5, blood_size: int = 7) -> None:
    _write_version(
        conn,
        lin,
        gen=0,
        commit_label="c0",
        parent=None,
        sev_max=sev_max,
        blood_size=blood_size,
        root_label="a",
    )


def assert_refused(exc: Any, expected_message: str) -> None:
    assert exc.sqlstate == "P0001", (
        f"expected P0001 (CF-56 and I05 both pin it); got {exc.sqlstate}: {exc}"
    )
    assert expected_message in str(exc), (
        f"the refusal fired but with the wrong exhibit.\n  expected: {expected_message}\n"
        f"  actual:   {exc}"
    )


# ── the guard is attached ─────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_the_guard_is_attached_after_insert_and_after_update(conn: Any) -> None:
    """``information_schema.triggers`` is the exhibit that the DDL landed as written."""
    rows = conn.execute(
        """
        SELECT action_timing, event_manipulation, action_orientation
          FROM information_schema.triggers
         WHERE event_object_schema = 'mainline'
           AND event_object_table = 'clause_version'
           AND trigger_name = %s
         ORDER BY event_manipulation
        """,
        (TRIGGER_NAME,),
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [("AFTER", "INSERT"), ("AFTER", "UPDATE")], (
        f"{TRIGGER_NAME} is not attached AFTER INSERT and AFTER UPDATE; got {rows}"
    )
    assert all(r[2] == "ROW" for r in rows), "the guard must be FOR EACH ROW; NEW/OLD is the input"


@pytest.mark.requires_cluster
def test_the_two_guards_coexist_on_one_table(conn: Any) -> None:
    """MI15's guard and MI22's ``z_delta_witness_required`` share ``clause_version``.

    Both are asserted present and each is shown to still refuse its own history. Nothing here
    asserts which fires FIRST: CockroachDB v26.2 does not document the firing order of two
    row-level triggers, and neither guard's answer depends on it.
    """
    names = {
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT trigger_name FROM information_schema.triggers
             WHERE event_object_schema = 'mainline' AND event_object_table = 'clause_version'
            """
        ).fetchall()
    }
    assert {TRIGGER_NAME, "z_delta_witness_required"} <= names, (
        f"expected both vertical guards on clause_version; found {sorted(names)}"
    )

    lineage = _lineage(conn)
    witness_refusal = _refusal(
        conn,
        lineage,
        gen=0,
        commit_label="c0",
        parent=None,
        sev_max=0,
        blood_size=0,
        root_label="a",
        control_delta="weaken",
    )
    assert witness_refusal.sqlstate == "P0001"
    assert "minimal witness set" in str(witness_refusal), (
        "MI22's guard stopped refusing once MI15's was attached; the two interfere"
    )

    other = _lineage(conn)
    _seed_parent(conn, other)
    assert_refused(
        _refusal(
            conn,
            other,
            gen=1,
            commit_label="c1",
            parent=other.commit("c0"),
            sev_max=0,
            blood_size=0,
            root_label="b",
        ),
        MSG_INSERT_SEV,
    )


# ── R1-R3: the INSERT arm ─────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_mi15_a_child_may_not_lower_sev_max_below_its_parent(conn: Any) -> None:
    """CF-56, executed. The O-Ring Ratchet: a rewrite may reword; it may not un-write the death.

    Every column in the refused insert is individually legal — 0 is inside ``sev_range``, the
    parent pointer resolves, every foreign key holds. What is illegal is the DIRECTION, and a
    direction is a fact about two rows, which is why this is a trigger and not a CHECK.
    """
    lineage = _lineage(conn)
    _seed_parent(conn, lineage, sev_max=5, blood_size=7)
    assert_refused(
        _refusal(
            conn,
            lineage,
            gen=1,
            commit_label="c1",
            parent=lineage.commit("c0"),
            sev_max=0,
            blood_size=0,
            root_label="b",
            text="Isolate energy where practicable.",
        ),
        MSG_INSERT_SEV,
    )


@pytest.mark.requires_cluster
def test_mi15_a_child_may_not_lower_blood_size_below_its_parent(conn: Any) -> None:
    """The mass half. ``sev_max`` is a maximum, so it survives deleting all but the worst ancestor.

    Guarding the maximum alone would let nine years of accumulated obligation be discarded while
    the headline number stayed at 5 — and the count is what Conservation of Blame Mass balances.
    """
    lineage = _lineage(conn)
    _seed_parent(conn, lineage, sev_max=5, blood_size=7)
    assert_refused(
        _refusal(
            conn,
            lineage,
            gen=1,
            commit_label="c1",
            parent=lineage.commit("c0"),
            sev_max=5,
            blood_size=3,
            root_label="b",
        ),
        MSG_INSERT_SIZE,
    )


@pytest.mark.requires_cluster
def test_mi15_a_child_may_not_swap_blood_root_at_an_unchanged_size(conn: Any) -> None:
    """No silent re-rooting.

    ``blood_root`` is an MMR root over the ancestry's ``{H(event_id || severity)}`` and
    ``blood_size`` counts what is in it. An unchanged count means an unchanged multiset, and an
    MMR over an unchanged multiset has an unchanged root. A new root at the same size is a swapped
    commitment — which is how a bounded disclosure proof comes to point at a different history.
    """
    lineage = _lineage(conn)
    _seed_parent(conn, lineage, sev_max=5, blood_size=7)
    assert_refused(
        _refusal(
            conn,
            lineage,
            gen=1,
            commit_label="c1",
            parent=lineage.commit("c0"),
            sev_max=5,
            blood_size=7,
            root_label="different",
        ),
        MSG_REROOT,
    )


@pytest.mark.requires_cluster
def test_a_faithful_restatement_and_a_growing_ancestry_are_both_admitted(conn: Any) -> None:
    """The guard must be discriminating, not universal. Two controls.

    A restatement carries the parent's ancestry forward unchanged — same severity, same size, same
    root. A version that learns of new blame grows: a higher severity, a larger size, a new root.
    A guard that refused either would be a guard somebody disables.
    """
    lineage = _lineage(conn)
    _seed_parent(conn, lineage, sev_max=3, blood_size=7)
    _write_version(
        conn,
        lineage,
        gen=1,
        commit_label="c1",
        parent=lineage.commit("c0"),
        sev_max=3,
        blood_size=7,
        root_label="a",
    )
    _write_version(
        conn,
        lineage,
        gen=2,
        commit_label="c2",
        parent=lineage.commit("c1"),
        sev_max=5,
        blood_size=11,
        root_label="grown",
    )
    rows = conn.execute(
        "SELECT gen, sev_max, blood_size FROM mainline.clause_version "
        "WHERE clause_uuid = %s::UUID ORDER BY gen",
        (lineage.clause_uuid,),
    ).fetchall()
    assert [tuple(r) for r in rows] == [(0, 3, 7), (1, 3, 7), (2, 5, 11)]


@pytest.mark.requires_cluster
def test_a_birth_version_is_admitted_and_the_dodge_is_named(conn: Any) -> None:
    """``parent_version IS NULL`` has no ancestry to shrink, and is admitted deliberately.

    This is the birth dodge, stated rather than hidden: a writer can start a fresh lineage at zero.
    0029's MATCH SIMPLE composite FK makes that a VISIBLE claim, and the residue machinery in 0049
    is what interrogates it — an evaded weakening surfaces there as an orphaned obligation, which
    is a louder gate than the one it was hiding from. This guard closes one hole and names this.
    """
    lineage = _lineage(conn)
    _write_version(
        conn,
        lineage,
        gen=0,
        commit_label="c0",
        parent=None,
        sev_max=0,
        blood_size=0,
        root_label="a",
    )
    count = conn.execute(
        "SELECT count(*) FROM mainline.clause_version WHERE clause_uuid = %s::UUID",
        (lineage.clause_uuid,),
    ).fetchone()[0]
    assert count == 1


# ── R4/R5: the pointer itself ─────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_a_version_may_not_declare_itself_its_own_parent(conn: Any) -> None:
    """A self-parented row satisfies ``fk_parent_version`` and would compare against itself.

    The composite FK is evaluated once the statement's rows exist, so a row pointing at its own
    ``commit_id`` resolves — to itself. Its ancestry then trivially equals its parent's and every
    monotonicity test passes. Without this branch the guard has a one-column bypass, and the red
    anchor below shows the row is accepted outright when the guard is absent.
    """
    lineage = _lineage(conn)
    assert_refused(
        _refusal(
            conn,
            lineage,
            gen=0,
            commit_label="c0",
            parent=lineage.commit("c0"),
            sev_max=0,
            blood_size=0,
            root_label="a",
        ),
        MSG_SELF_PARENT,
    )


@pytest.mark.requires_cluster
def test_a_dangling_parent_is_still_23503_and_not_a_trigger_message(conn: Any) -> None:
    """The reason this guard is AFTER and not BEFORE, asserted rather than argued.

    A BEFORE trigger runs ahead of referential integrity, so it would reach the guard's
    fail-closed branch and raise P0001 — replacing ``fk_parent_version``'s 23503, by name, with a
    trigger message, and turning ``test_mi_spine``'s green cross-clause test red. AFTER leaves the
    referential-integrity exhibit intact, which is the better exhibit for this fact.
    """
    lineage = _lineage(conn)
    _seed_parent(conn, lineage)
    exc = _refusal(
        conn,
        lineage,
        gen=1,
        commit_label="c1",
        parent=_digest("a commit that produced no version row"),
        sev_max=5,
        blood_size=7,
        root_label="a",
    )
    assert exc.sqlstate == "23503", (
        f"expected 23503 from fk_parent_version; got {exc.sqlstate}: {exc}. If this is P0001 the "
        "guard has been moved to BEFORE and has taken the FK's refusal away from it."
    )
    assert "fk_parent_version" in str(exc), "the constraint name is the courtroom exhibit"


@pytest.mark.requires_cluster
def test_a_parent_from_another_clause_is_still_23503(conn: Any) -> None:
    """Lineage cannot cross obligations, and the FK is still what says so."""
    first, second = _lineage(conn), _lineage(conn)
    _seed_parent(conn, first)
    exc = _refusal(
        conn,
        second,
        gen=0,
        commit_label="c0",
        parent=first.commit("c0"),
        sev_max=5,
        blood_size=7,
        root_label="a",
    )
    assert exc.sqlstate == "23503", f"expected 23503; got {exc.sqlstate}: {exc}"
    assert "fk_parent_version" in str(exc)


# ── R6: the UPDATE arm ────────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_an_update_may_not_lower_sev_max(conn: Any) -> None:
    """The shortest path to a laundered ancestry, and it is shorter than writing a child.

    ``clause_version`` is append-only by intent and nothing on the tree enforces that yet, so a
    guard that covered INSERT alone would be guarding the front door of an open building.
    """
    lineage = _lineage(conn)
    _seed_parent(conn, lineage, sev_max=5, blood_size=7)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "UPDATE mainline.clause_version SET sev_max = 0 WHERE clause_uuid = %s::UUID",
            (lineage.clause_uuid,),
        )
    assert_refused(caught.value, MSG_UPDATE_SEV)


@pytest.mark.requires_cluster
def test_an_update_may_not_lower_blood_size(conn: Any) -> None:
    """Same invariant, the mass half, against the row's own former self."""
    lineage = _lineage(conn)
    _seed_parent(conn, lineage, sev_max=5, blood_size=7)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "UPDATE mainline.clause_version SET blood_size = 1 WHERE clause_uuid = %s::UUID",
            (lineage.clause_uuid,),
        )
    assert_refused(caught.value, MSG_UPDATE_SIZE)


@pytest.mark.requires_cluster
def test_an_update_may_not_swap_blood_root_at_an_unchanged_size(conn: Any) -> None:
    """Re-rooting in place is the same defect as re-rooting across a version boundary."""
    lineage = _lineage(conn)
    _seed_parent(conn, lineage, sev_max=5, blood_size=7)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "UPDATE mainline.clause_version SET blood_root = %s WHERE clause_uuid = %s::UUID",
            (_digest("a root nobody can account for"), lineage.clause_uuid),
        )
    assert_refused(caught.value, MSG_REROOT)


@pytest.mark.requires_cluster
def test_an_update_that_grows_the_ancestry_is_admitted(conn: Any) -> None:
    """MI15 is monotone, not immutable.

    A projector that learns of a new blame edge must be able to raise ``sev_max``, grow
    ``blood_size`` and write the new root. Refusing that would make the guard the reason the
    ancestry is wrong.
    """
    lineage = _lineage(conn)
    _seed_parent(conn, lineage, sev_max=2, blood_size=3)
    conn.execute(
        "UPDATE mainline.clause_version SET sev_max = 5, blood_size = 9, blood_root = %s "
        "WHERE clause_uuid = %s::UUID",
        (_digest("a root that commits to nine facts"), lineage.clause_uuid),
    )
    row = conn.execute(
        "SELECT sev_max, blood_size FROM mainline.clause_version WHERE clause_uuid = %s::UUID",
        (lineage.clause_uuid,),
    ).fetchone()
    assert tuple(row) == (5, 9)


# ── the multi-row statement: why AFTER, measured ──────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_one_statement_may_not_write_a_parent_and_a_shrinking_child(conn: Any) -> None:
    """The bypass a BEFORE trigger cannot close.

    A row-level BEFORE trigger reads the statement's snapshot and therefore cannot see a row its
    own statement wrote, so for ``INSERT … VALUES (parent), (shrinking child)`` it either waves
    the shrink through — the FK being satisfied at end of statement by the parent the same
    statement just wrote — or refuses every multi-row load of a version chain, including the
    legitimate ones a corpus loader performs. AFTER sees the parent and refuses exactly the
    shrinking child. The control immediately below is the other half of that claim.
    """
    lineage = _lineage(conn)
    both = _VERSION_SQL.strip() + ", " + _VERSION_SQL.split("VALUES", 1)[1].strip()
    params = _version_params(
        lineage,
        gen=0,
        commit_label="c0",
        parent=None,
        sev_max=5,
        blood_size=7,
        root_label="a",
    ) + _version_params(
        lineage,
        gen=1,
        commit_label="c1",
        parent=lineage.commit("c0"),
        sev_max=0,
        blood_size=0,
        root_label="b",
    )
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(both, params)
    assert_refused(caught.value, MSG_INSERT_SEV)
    count = conn.execute(
        "SELECT count(*) FROM mainline.clause_version WHERE clause_uuid = %s::UUID",
        (lineage.clause_uuid,),
    ).fetchone()[0]
    assert count == 0, "the statement was refused but its rows survived"


@pytest.mark.requires_cluster
def test_one_statement_may_write_a_parent_and_a_growing_child(conn: Any) -> None:
    """The control: a bulk load of a legitimate version chain still lands.

    This is what a fail-closed BEFORE trigger gets wrong — it refuses this too, which makes it a
    ban on multi-row inserts rather than an enforcement of MI15.
    """
    lineage = _lineage(conn)
    both = _VERSION_SQL.strip() + ", " + _VERSION_SQL.split("VALUES", 1)[1].strip()
    params = _version_params(
        lineage,
        gen=0,
        commit_label="c0",
        parent=None,
        sev_max=5,
        blood_size=7,
        root_label="a",
    ) + _version_params(
        lineage,
        gen=1,
        commit_label="c1",
        parent=lineage.commit("c0"),
        sev_max=5,
        blood_size=8,
        root_label="b",
    )
    conn.execute(both, params)
    count = conn.execute(
        "SELECT count(*) FROM mainline.clause_version WHERE clause_uuid = %s::UUID",
        (lineage.clause_uuid,),
    ).fetchone()[0]
    assert count == 2


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE RED ANCHOR — the same histories, the same schema, no guard
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.requires_cluster
def test_red_anchor_without_the_guard_every_refused_history_is_accepted(red_conn: Any) -> None:
    """PL-2 as a measurement taken in this run, not a claim about a run somebody did once.

    Migrations 0001-0049a, the identical files, into a database that never received 0141 or 0146.
    Six histories this suite refuses are written here without complaint. If the guard is ever
    deleted the green tests fail and this one keeps passing; if the guard is ever hollowed into a
    no-op the green tests fail. There is no edit that satisfies both halves except a guard that
    refuses.
    """
    lineage = _lineage(red_conn)
    _seed_parent(red_conn, lineage, sev_max=5, blood_size=7)

    # sev_max 5 -> 0 and blood_size 7 -> 0, the CF-56 history itself
    _write_version(
        red_conn,
        lineage,
        gen=1,
        commit_label="c1",
        parent=lineage.commit("c0"),
        sev_max=0,
        blood_size=0,
        root_label="b",
    )
    # a re-rooting at unchanged size
    _write_version(
        red_conn,
        lineage,
        gen=2,
        commit_label="c2",
        parent=lineage.commit("c1"),
        sev_max=0,
        blood_size=0,
        root_label="rerooted",
    )
    # an UPDATE that lowers what is left
    red_conn.execute(
        "UPDATE mainline.clause_version SET sev_max = 0, blood_size = 0 "
        "WHERE clause_uuid = %s::UUID AND gen = 0",
        (lineage.clause_uuid,),
    )
    # a self-parented version
    other = _lineage(red_conn)
    _write_version(
        red_conn,
        other,
        gen=0,
        commit_label="c0",
        parent=other.commit("c0"),
        sev_max=0,
        blood_size=0,
        root_label="a",
    )
    # a parent and a shrinking child in one statement
    third = _lineage(red_conn)
    both = _VERSION_SQL.strip() + ", " + _VERSION_SQL.split("VALUES", 1)[1].strip()
    red_conn.execute(
        both,
        _version_params(
            third,
            gen=0,
            commit_label="c0",
            parent=None,
            sev_max=5,
            blood_size=7,
            root_label="a",
        )
        + _version_params(
            third,
            gen=1,
            commit_label="c1",
            parent=third.commit("c0"),
            sev_max=0,
            blood_size=0,
            root_label="b",
        ),
    )

    surviving = red_conn.execute(
        "SELECT gen, sev_max, blood_size FROM mainline.clause_version "
        "WHERE clause_uuid = %s::UUID ORDER BY gen",
        (lineage.clause_uuid,),
    ).fetchall()
    assert [tuple(r) for r in surviving] == [(0, 0, 0), (1, 0, 0), (2, 0, 0)], (
        "the unguarded database refused something. It applies the same 0001-0049a files and no "
        "guard, so either a guard leaked into the foundation band or the fixture is wrong — and "
        "either way the red baseline this suite rests on is no longer a measurement."
    )
    assert (
        red_conn.execute(
            "SELECT count(*) FROM mainline.clause_version WHERE clause_uuid = %s::UUID",
            (third.clause_uuid,),
        ).fetchone()[0]
        == 2
    ), "the one-statement bypass did not land in the unguarded database"


@pytest.mark.requires_cluster
def test_red_anchor_the_guard_is_absent_from_the_unguarded_database(red_conn: Any) -> None:
    """The red anchor is only evidence if it is genuinely unguarded."""
    names = {
        r[0]
        for r in red_conn.execute(
            """
            SELECT DISTINCT trigger_name FROM information_schema.triggers
             WHERE event_object_schema = 'mainline' AND event_object_table = 'clause_version'
            """
        ).fetchall()
    }
    assert TRIGGER_NAME not in names, (
        f"{TRIGGER_NAME} is attached in the database that was built without 0146"
    )
