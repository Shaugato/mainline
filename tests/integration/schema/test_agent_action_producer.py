# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The producer contract for ``mainline_meas.agent_action`` — migrations 0089 and 0149a.

Three views were written against this table before the table existed. ``0164_v_agent_actions``,
``0165_v_gate_latency_daily`` and ``0166_v_txn_restart_daily`` each carry
``requires: 0089 mainline_meas.agent_action`` in a header committed before the ``CREATE TABLE``
was authored, and each of the three refused ``[42P01] relation "mainline_meas.agent_action" does
not exist`` against the tree until 0089 landed. This file is the assertion that the producer
satisfies its consumers rather than merely existing.

**Applying is necessary; SELECTing from the view is the test.** A table that applies and then
produces a wrong flag on the surface three views publish is a worse defect than a table that
does not apply, because the first one is invisible. So every cluster test here seeds real rows
and reads a real view back, and the three flags the surface publishes —
``v_agent_actions.outcomes_modelled``, ``v_gate_latency_daily.measurement_complete`` and
``v_txn_restart_daily.outcomes_modelled`` — are each driven false by a seeded row that *should*
drive them false, not merely observed true on an empty table. A fail-closed flag that has never
been red asserts nothing.

Two shapes are pinned here because a consumer depends on them and a reasonable-looking edit
would break it silently:

* ``latency_ms`` is ``INT4``. 0165 computes ``round(avg(a.latency_ms)::NUMERIC, 1)``; on
  CockroachDB v26.2.5 ``avg()`` over an integer returns DECIMAL and the two-argument
  ``round(DECIMAL, INT)`` exists. Widening the column to FLOAT8 routes the call to the
  one-argument FLOAT8 ``round()``, which takes no precision argument, and the view stops
  applying. ``test_latency_is_int4_because_the_view_rounds_a_decimal`` is that guard.
* ``sqlstate`` carries **no** CHECK. Constraining it to the five modelled codes would make the
  database refuse to record any refusal nobody had modelled, which would pin
  ``unmodelled_refusals`` and ``unmodelled`` — the two most actionable numbers on the audit
  surface — at zero by construction. ``test_an_unmodelled_sqlstate_is_recorded_not_refused`` is
  that guard, and it is deliberately a test that an *absent* constraint stays absent.

Running it
----------
The static tier needs no cluster. The cluster tier resolves a CockroachDB v26.2 from
``$TRAPPOINT_DSN`` / ``$LOCAL_DSN`` / ``$MAINLINE_TEST_DSN`` / ``$COCKROACH_URL`` / ``$CRDB_URL``,
then probes ``127.0.0.1:26257`` (the node ``docker compose up -d crdb`` publishes), and **skips
with a reason naming the command to run** if there is none. It never spawns a container: the
producer wave shares one local node, and a suite that starts its own is a suite that races the
others for the port.

Each cluster test gets a **fresh database** carrying a nine-file stack taken verbatim from the
migration tree — schemas 0001a/0002/0003, the substrate refusal function 0107, the producer
0089, its weld 0149a, and the three consumers. No stand-in DDL is executed anywhere in this
file; if a stack file changes under it, this suite is what notices. A fresh database per test is
the isolation primitive because every view here aggregates over the *whole* table, so one test's
rows are the next test's wrong answer.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"

PRODUCER = "0089_agent_action.sql"
WELD = "0149a_trg_agent_action_append_only.sql"
CONSUMERS: tuple[str, ...] = (
    "0164_v_agent_actions.sql",
    "0165_v_gate_latency_daily.sql",
    "0166_v_txn_restart_daily.sql",
)

#: The three views those files create, in the same order. Closed, so that a relation name
#: reaching a statement in this file can be checked against a literal rather than escaped.
CONSUMER_VIEWS: tuple[str, ...] = (
    "v_agent_actions",
    "v_gate_latency_daily",
    "v_txn_restart_daily",
)

#: Applied in this order into a fresh database. Every entry is a real file from the migration
#: tree, read at run time — never a copy, never a stand-in.
STACK: tuple[str, ...] = (
    "0001a_schema_mainline.sql",
    "0002_schema_meas.sql",
    "0003_schema_audit.sql",
    "0107_fn_refuse_mutation.sql",
    PRODUCER,
    WELD,
    *CONSUMERS,
)

#: ARCHITECTURE.md §5.7, the block at line 1517, transcribed as ``column -> CockroachDB type``
#: exactly as ``SHOW COLUMNS`` reports it. Written out rather than derived from the DDL, because
#: a test that parses the file it is testing agrees with any edit to that file.
EXPECTED_COLUMNS: tuple[tuple[str, str, bool], ...] = (
    # (name, data_type, nullable)
    ("action_id", "UUID", False),
    ("agent_role", "STRING", False),
    ("tool", "STRING", False),
    ("transport", "STRING", False),
    ("model_id", "STRING", True),
    ("prompt_version", "STRING", True),
    ("subject_kind", "STRING", True),
    ("subject_id", "UUID", True),
    ("input_sha256", "BYTES", False),
    ("output_sha256", "BYTES", False),
    ("granted_scopes", "STRING[]", False),
    ("outcome", "STRING", False),
    ("sqlstate", "STRING", True),
    ("latency_ms", "INT4", True),
    ("at", "TIMESTAMPTZ", False),
)

#: §16: the five codes the invariant catalogue models, plus 0166's separately broken-out
#: ``42501``. Anything outside this set is what ``unmodelled_refusals`` counts.
MODELLED_SQLSTATES: frozenset[str] = frozenset({"40001", "23514", "23503", "23505", "P0001"})

#: A code deliberately outside the modelled set: ``58030`` is an I/O error, real and unmodelled.
UNMODELLED_SQLSTATE = "58030"

MR5_FILENAME = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")
HEADER_KEYS: tuple[str, ...] = ("MI", "I", "COUNSEL-GATED", "RATIONALE")

_BANNED_IDENTITY: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("CREATE SEQUENCE", re.compile(r"\bCREATE\s+SEQUENCE\b", re.IGNORECASE)),
    ("nextval(", re.compile(r"\bnextval\s*\(", re.IGNORECASE)),
    ("SERIAL", re.compile(r"\b(?:BIG|SMALL)?SERIAL[248]?\b", re.IGNORECASE)),
    ("unique_rowid(", re.compile(r"\bunique_rowid\s*\(", re.IGNORECASE)),
)

#: ``FAMILY`` is a reserved keyword on CockroachDB, so a bare column named ``family`` makes the
#: whole CREATE TABLE a syntax error. It is checked as a token rather than trusted, because the
#: failure it produces is a parse error hundreds of lines from the word that caused it.
_BARE_FAMILY = re.compile(r"^\s*family\s", re.IGNORECASE | re.MULTILINE)

_DIGEST_SQL = "decode(repeat('a1', 32), 'hex')"

#: Every value that varies is a placeholder; the only interpolation is `_DIGEST_SQL`, a
#: module constant, because there is no placeholder for a 32-byte literal that has to be
#: constructed server-side and no test datum reaches it.
INSERT_SQL = f"""
INSERT INTO mainline_meas.agent_action
  (agent_role, tool, transport, model_id, prompt_version,
   input_sha256, output_sha256, granted_scopes, outcome, sqlstate, latency_ms)
VALUES (%s, %s, %s, %s, %s, {_DIGEST_SQL}, {_DIGEST_SQL}, ARRAY['recall:read'], %s, %s, %s)
"""  # noqa: S608 - the only interpolated fragment is the module constant above


def _strip_sql_comments(text: str) -> str:
    """Remove ``--`` line comments and ``/* */`` blocks, leaving executable SQL only."""
    without_block = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return "\n".join(re.sub(r"--.*$", "", line) for line in without_block.splitlines())


def _header_comment(text: str) -> str:
    """The leading ``--`` comment block, which is the only window a header key may live in."""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            lines.append(line)
            continue
        break
    return "\n".join(lines)


def _statement_count(text: str) -> int:
    code = _strip_sql_comments(text)
    masked = re.sub(r"'(?:[^']|'')*'", "''", code)
    return len([part for part in masked.split(";") if part.strip()])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STATIC TIER — no cluster required.
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("name", [PRODUCER, WELD])
def test_the_file_exists_and_matches_the_one_filename_convention(name: str) -> None:
    path = MIGRATIONS_DIR / name
    assert path.is_file(), f"{name} is absent; three views name it in `requires:`"
    assert MR5_FILENAME.match(name) is not None, (
        f"{name} is not `NNNN[a-z]_lower_snake_slug.sql` (MR-5). A second dot in a migration "
        "filename makes the whole directory undiscoverable to the runner."
    )


@pytest.mark.parametrize("name", [PRODUCER, WELD])
@pytest.mark.parametrize("key", HEADER_KEYS)
def test_the_header_answers_every_mandatory_key_exactly_once(name: str, key: str) -> None:
    header = _header_comment((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    hits = re.findall(rf"^--[ \t]*{re.escape(key)}:", header, re.MULTILINE)
    assert len(hits) == 1, (
        f"{name}: {len(hits)} '-- {key}:' line(s) in the leading comment block. "
        "ARCHITECTURE.md §18 and DM-8/DM-17 require exactly one; scripts/mi_ratchet.py "
        "projects owning_migrations out of the MI line and refuses anything else."
    )


@pytest.mark.parametrize("name", [PRODUCER, WELD])
def test_the_header_cites_mi01_and_the_allegation_firewall(name: str) -> None:
    """MI01 because the table is evidentiary; I15 because it carries a role and never a person.

    0164's own header already cites both over this table. A producer that cited neither would
    leave its consumer's claim unattributed to anything in the tree.
    """
    header = _header_comment((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    assert "MI01" in header, f"{name}: MI01 (evidentiary tables are append-only) is not cited"
    assert "I15" in header, (
        f"{name}: I15 (the allegation firewall) is not cited. It is the reason this table "
        "carries `agent_role` — a machine — and no column keyed on a named human."
    )


@pytest.mark.parametrize("name", [PRODUCER, WELD])
def test_exactly_one_top_level_statement(name: str) -> None:
    count = _statement_count((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    assert count == 1, (
        f"{name}: {count} statements. CockroachDB DDL is not transactional across statements, "
        "so a failure part-way leaves a half-applied file and a dirty marker nobody can diagnose."
    )


@pytest.mark.parametrize("name", [PRODUCER, WELD])
def test_no_banned_identity_construct_and_no_bare_family_column(name: str) -> None:
    code = _strip_sql_comments((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    for label, pattern in _BANNED_IDENTITY:
        assert pattern.search(code) is None, (
            f"{name}: {label} is banned tree-wide. A gap in a sequence is ambiguous, and this "
            "is a ledger in which a gap has to MEAN tampering."
        )
    assert _BARE_FAMILY.search(code) is None, (
        f"{name}: a bare `family` column. FAMILY is a reserved keyword on CockroachDB and the "
        "parse error it produces names a line far from the word that caused it."
    )


def test_gen_random_uuid_is_the_identity_source() -> None:
    code = _strip_sql_comments((MIGRATIONS_DIR / PRODUCER).read_text(encoding="utf-8"))
    assert "gen_random_uuid()" in code, (
        "the primary key must default to gen_random_uuid(); it is the only identity source "
        "left once sequences, SERIAL and unique_rowid() are banned."
    )


def test_the_producer_sorts_before_its_weld_and_before_every_consumer() -> None:
    """The runner applies ``sorted(root.iterdir())`` and is forward-only.

    ``CREATE TRIGGER`` and ``CREATE VIEW`` both resolve their table at apply time on v26.2.5, so
    a producer that sorted after either would refuse ``42P01`` and stop the chain dead.
    """
    for later in (WELD, *CONSUMERS):
        assert later > PRODUCER, f"{PRODUCER} must sort before {later} in the apply order"


@pytest.mark.parametrize("name", CONSUMERS)
def test_every_consumer_still_names_this_producer_in_requires(name: str) -> None:
    """The number is pre-committed by the consumers, not chosen by the producer."""
    header = _header_comment((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    assert "0089 mainline_meas.agent_action" in header, (
        f"{name} no longer declares `requires: 0089 mainline_meas.agent_action`. If the "
        "dependency moved, 0089's band and this suite both need to move with it."
    )


def test_the_weld_reuses_the_substrate_refusal_function() -> None:
    code = _strip_sql_comments((MIGRATIONS_DIR / WELD).read_text(encoding="utf-8"))
    assert "mainline.fn_refuse_mutation()" in code, (
        "the weld must call the substrate's fn_refuse_mutation (0107). A vertical copy is a "
        "second place for the append-only refusal message to drift, and a message that differs "
        "between two tables is a message an operator learns to ignore."
    )
    assert re.search(r"BEFORE\s+UPDATE\s+OR\s+DELETE", code, re.IGNORECASE) is not None, (
        "the weld must fire BEFORE UPDATE OR DELETE; an AFTER trigger lets the row change first."
    )


def test_the_producer_declares_no_check_on_sqlstate() -> None:
    """An absent constraint, asserted to stay absent.

    §16 models five refusal codes and 0166 breaks out a sixth. Constraining ``sqlstate`` to that
    set would make the database refuse to RECORD a refusal nobody modelled, which pins
    ``unmodelled_refusals`` (0164) and ``unmodelled`` (0166) at zero by construction — the exact
    shape of a metric that lies.
    """
    code = _strip_sql_comments((MIGRATIONS_DIR / PRODUCER).read_text(encoding="utf-8"))
    for statement in re.findall(r"CHECK\s*\((?:[^()]|\([^()]*\))*\)", code, re.IGNORECASE):
        assert "sqlstate" not in statement.lower(), (
            f"a CHECK constrains `sqlstate`: {statement}. An unmodelled SQLSTATE must arrive as "
            "evidence, not as a lost write."
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLUSTER TIER — everything below needs a real CockroachDB v26.2.
# ══════════════════════════════════════════════════════════════════════════════════════════════

_DSN_ENV: tuple[str, ...] = (
    "TRAPPOINT_DSN",
    "LOCAL_DSN",
    "MAINLINE_TEST_DSN",
    "COCKROACH_URL",
    "CRDB_URL",
)
_DEFAULT_LOCAL = "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"


def _reachable(dsn: str) -> bool:
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except Exception:  # noqa: BLE001 — any failure here means "not this one"
        return False
    return True


@pytest.fixture(scope="session")
def producer_dsn() -> str:
    """A reachable cluster DSN, or a skip whose reason names the command that provides one."""
    for name in _DSN_ENV:
        value = os.environ.get(name)
        if value and _reachable(value):
            return value
    if _reachable(_DEFAULT_LOCAL):
        return _DEFAULT_LOCAL
    pytest.skip(
        "no CockroachDB v26.2 reachable. Start the shared local node — "
        "`docker compose up -d crdb` — or set TRAPPOINT_DSN. This suite never spawns its own "
        "container: the producer wave shares one node and a second one races it for the port."
    )


@pytest.fixture
def conn(producer_dsn: str) -> Iterator[Any]:
    """A fresh database carrying the nine-file stack, dropped at teardown.

    Fresh per test, because every view under test aggregates over the WHOLE table and
    ``group_count`` is a global count — one test's rows are the next test's wrong answer.
    """
    from psycopg.conninfo import make_conninfo

    database = f"w3_agent_action_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(producer_dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")
    dsn = make_conninfo(producer_dsn, dbname=database)
    try:
        connection = psycopg.connect(dsn, autocommit=True)
        try:
            for name in STACK:
                connection.execute((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
            yield connection
        finally:
            connection.close()
    finally:
        with psycopg.connect(producer_dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


def _insert(
    conn: Any,
    *,
    agent_role: str = "agent_gate",
    tool: str = "permit_merge_gate",
    transport: str = "pgwire",
    model_id: str | None = None,
    prompt_version: str | None = None,
    outcome: str = "ok",
    sqlstate: str | None = None,
    latency_ms: int | None = 10,
) -> None:
    conn.execute(
        INSERT_SQL,
        (agent_role, tool, transport, model_id, prompt_version, outcome, sqlstate, latency_ms),
    )


def _rows(conn: Any, sql: str) -> list[dict[str, Any]]:
    cur = conn.execute(sql)
    columns = [description.name for description in cur.description or []]
    return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def _select_view(conn: Any, view: str) -> list[dict[str, Any]]:
    """``SELECT *`` from one of the three consumers, by name.

    SQL has no placeholder for a relation name, so the name is *checked against the closed
    tuple this module declares* rather than escaped — the same discipline
    ``tests/integration/schema/conftest.py`` applies to every identifier it interpolates.
    """
    if view not in CONSUMER_VIEWS:
        raise ValueError(f"{view!r} is not one of {CONSUMER_VIEWS}")
    return _rows(conn, f"SELECT * FROM mainline_audit.{view}")  # noqa: S608 - closed tuple


# ── the shape ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.schema
@pytest.mark.shape
def test_the_column_set_is_exactly_the_architecture_block(conn: Any) -> None:
    observed = [
        (name, data_type, bool(nullable))
        for name, data_type, nullable, *_ in conn.execute(
            "SHOW COLUMNS FROM mainline_meas.agent_action"
        ).fetchall()
    ]
    assert observed == list(EXPECTED_COLUMNS), (
        "the column set drifted from ARCHITECTURE.md §5.7. Three views select these columns by "
        f"name.\n  observed: {observed}\n  expected: {list(EXPECTED_COLUMNS)}"
    )


@pytest.mark.schema
@pytest.mark.shape
def test_latency_is_int4_because_the_view_rounds_a_decimal(conn: Any) -> None:
    """0165 computes ``round(avg(latency_ms)::NUMERIC, 1)``.

    ``avg()`` over an integer returns DECIMAL on v26.2.5 and the two-argument
    ``round(DECIMAL, INT)`` exists. Over FLOAT8 the call resolves to the one-argument
    ``round(FLOAT8)``, which takes no precision argument, and 0165 stops applying — so this is
    not a taste assertion, it is the consumer's precondition.
    """
    data_type = conn.execute(
        "SELECT data_type FROM [SHOW COLUMNS FROM mainline_meas.agent_action] "
        "WHERE column_name = 'latency_ms'"
    ).fetchone()[0]
    assert data_type == "INT4", f"latency_ms is {data_type}; 0165 requires an integer type"
    _insert(conn, latency_ms=41)
    _insert(conn, latency_ms=42)
    mean = conn.execute("SELECT mean_latency_ms FROM mainline_audit.v_agent_actions").fetchone()[0]
    assert str(mean) == "41.5", f"mean_latency_ms is {mean!r}; the DECIMAL rounding path broke"


@pytest.mark.schema
@pytest.mark.shape
def test_both_access_paths_the_consumers_need_are_declared(conn: Any) -> None:
    names = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT index_name FROM [SHOW INDEXES FROM mainline_meas.agent_action]"
        ).fetchall()
    }
    assert {"agent_action_pk", "by_role_time", "by_subject"} <= names, (
        f"indexes are {sorted(names)}; by_role_time serves 0165's role filter and 0166's "
        "per-role grouping, by_subject serves one subject's history"
    )


# ── the CHECK domains ─────────────────────────────────────────────────────────────────────────


@pytest.mark.schema
@pytest.mark.mi("MI01")
@pytest.mark.parametrize(
    ("transport", "admitted"),
    [
        ("pgwire", True),
        ("mcp", True),
        ("bedrock", True),
        ("ccloud", True),
        ("s3", True),
        ("smoke_signal", False),
        ("PGWIRE", False),
        ("", False),
    ],
)
def test_the_transport_domain_admits_five_values_and_refuses_the_rest(
    conn: Any, transport: str, admitted: bool
) -> None:
    if admitted:
        _insert(conn, transport=transport)
        return
    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        _insert(conn, transport=transport)
    assert caught.value.diag.sqlstate == "23514"
    assert caught.value.diag.constraint_name == "agent_action_transport_known"


@pytest.mark.schema
@pytest.mark.mi("MI01")
@pytest.mark.parametrize(
    ("outcome", "admitted"),
    [
        ("ok", True),
        ("refused", True),
        ("error", True),
        ("abstained", True),
        ("failed", False),
        ("OK", False),
        ("", False),
    ],
)
def test_the_outcome_domain_admits_four_values_and_refuses_the_rest(
    conn: Any, outcome: str, admitted: bool
) -> None:
    if admitted:
        _insert(conn, outcome=outcome)
        return
    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        _insert(conn, outcome=outcome)
    assert caught.value.diag.sqlstate == "23514"
    assert caught.value.diag.constraint_name == "agent_action_outcome_known"


@pytest.mark.schema
def test_an_empty_role_or_tool_is_refused(conn: Any) -> None:
    """``agent_role`` is the grouping column of two views; an empty one is an unlabelled group."""
    with pytest.raises(psycopg.errors.CheckViolation) as role:
        _insert(conn, agent_role="")
    assert role.value.diag.constraint_name == "agent_action_role_present"
    with pytest.raises(psycopg.errors.CheckViolation) as tool:
        _insert(conn, tool="")
    assert tool.value.diag.constraint_name == "agent_action_tool_present"


@pytest.mark.schema
def test_a_digest_that_is_not_thirty_two_bytes_is_refused(conn: Any) -> None:
    """A 20-byte value in a column named ``sha256`` is another algorithm wearing this one's name."""
    short = INSERT_SQL.replace(_DIGEST_SQL, "decode(repeat('a1', 16), 'hex')", 1)
    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        conn.execute(short, ("agent_gate", "t", "pgwire", None, None, "ok", None, 1))
    assert caught.value.diag.constraint_name == "agent_action_input_digest_len"


@pytest.mark.schema
def test_a_negative_latency_is_refused_and_an_absent_one_is_not(conn: Any) -> None:
    """NULL is meaningful and is not zero: 0165 counts ``latency_ms IS NULL`` as ``unmeasured``."""
    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        _insert(conn, latency_ms=-1)
    assert caught.value.diag.constraint_name == "agent_action_latency_nonnegative"
    _insert(conn, latency_ms=None)
    assert (
        conn.execute(
            "SELECT count(*) FROM mainline_meas.agent_action WHERE latency_ms IS NULL"
        ).fetchone()[0]
        == 1
    )


# ── the weld ──────────────────────────────────────────────────────────────────────────────────


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_an_update_is_refused_with_p0001(conn: Any) -> None:
    """0164's header cites MI01 over this table. 0149a is what makes that sentence true."""
    _insert(conn, outcome="refused", sqlstate="23514")
    with pytest.raises(psycopg.errors.RaiseException) as caught:
        conn.execute("UPDATE mainline_meas.agent_action SET outcome = 'ok'")
    assert caught.value.diag.sqlstate == "P0001", (
        f"UPDATE refused with {caught.value.diag.sqlstate}, not P0001"
    )
    assert (
        conn.execute("SELECT outcome FROM mainline_meas.agent_action").fetchone()[0] == "refused"
    ), "the row changed despite the refusal"


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_a_delete_is_refused_with_p0001(conn: Any) -> None:
    _insert(conn)
    with pytest.raises(psycopg.errors.RaiseException) as caught:
        conn.execute("DELETE FROM mainline_meas.agent_action")
    assert caught.value.diag.sqlstate == "P0001"
    assert conn.execute("SELECT count(*) FROM mainline_meas.agent_action").fetchone()[0] == 1


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_insert_is_still_admitted_under_the_weld(conn: Any) -> None:
    """Append-only means the ledger grows, not that the ledger is hard to write."""
    for index in range(3):
        _insert(conn, tool=f"tool_{index}")
    assert conn.execute("SELECT count(*) FROM mainline_meas.agent_action").fetchone()[0] == 3


# ── the consumers, read back ──────────────────────────────────────────────────────────────────


@pytest.mark.schema
def test_an_unmodelled_sqlstate_is_recorded_not_refused(conn: Any) -> None:
    _insert(conn, outcome="error", sqlstate=UNMODELLED_SQLSTATE)
    stored = conn.execute("SELECT sqlstate FROM mainline_meas.agent_action").fetchone()[0]
    assert stored == UNMODELLED_SQLSTATE
    assert stored not in MODELLED_SQLSTATES


@pytest.mark.schema
def test_an_unmodelled_sqlstate_makes_v_agent_actions_report_not_modelled(conn: Any) -> None:
    """The headline assertion of this file, and the flag is driven BOTH ways.

    A fail-closed flag that has only ever been observed true asserts nothing about the failure
    it exists to report.
    """
    _insert(conn, tool="modelled", outcome="refused", sqlstate="23514")
    _insert(conn, tool="retryable", outcome="error", sqlstate="40001")
    _insert(conn, tool="unmodelled", outcome="error", sqlstate=UNMODELLED_SQLSTATE)

    by_tool = {
        row["tool"]: row for row in _rows(conn, "SELECT * FROM mainline_audit.v_agent_actions")
    }
    assert set(by_tool) == {"modelled", "retryable", "unmodelled"}

    assert by_tool["modelled"]["modelled_refusals"] == 1
    assert by_tool["modelled"]["unmodelled_refusals"] == 0
    assert by_tool["modelled"]["outcomes_modelled"] is True

    assert by_tool["retryable"]["retryable"] == 1
    assert by_tool["retryable"]["unmodelled_refusals"] == 0
    assert by_tool["retryable"]["outcomes_modelled"] is True

    assert by_tool["unmodelled"]["unmodelled_refusals"] == 1, (
        f"58030 was not counted as unmodelled: {by_tool['unmodelled']}"
    )
    assert by_tool["unmodelled"]["outcomes_modelled"] is False, (
        "an SQLSTATE nobody modelled left outcomes_modelled true — the most actionable number "
        "on the audit surface is reporting a green it has not earned"
    )
    assert all(row["group_count"] == 3 for row in by_tool.values())
    assert all(row["rows_complete"] is True for row in by_tool.values())


@pytest.mark.schema
def test_a_null_sqlstate_is_never_counted_as_a_refusal(conn: Any) -> None:
    """``outcome = 'ok'`` normally carries no SQLSTATE, and NULL must not read as unmodelled."""
    _insert(conn, outcome="ok", sqlstate=None)
    row = _rows(conn, "SELECT * FROM mainline_audit.v_agent_actions")[0]
    assert row["retryable"] == 0
    assert row["modelled_refusals"] == 0
    assert row["unmodelled_refusals"] == 0
    assert row["outcomes_modelled"] is True


@pytest.mark.schema
def test_v_gate_latency_daily_measures_the_gate_and_reports_an_untimed_action(conn: Any) -> None:
    """0165's filter, its buckets and its fail-closed completeness flag, in one seeded world."""
    _insert(conn, tool="permit_merge_gate", outcome="ok", latency_ms=42)
    _insert(conn, tool="permit_merge_gate", outcome="ok", latency_ms=310)
    _insert(conn, tool="permit_merge_gate", outcome="refused", sqlstate="23514", latency_ms=55)
    _insert(conn, tool="permit_merge_gate", outcome="error", sqlstate="40001", latency_ms=1200)
    _insert(conn, tool="disposition_sign", outcome="abstained", latency_ms=None)
    _insert(conn, tool="disposition_sign", outcome="error", sqlstate="58030", latency_ms=77)
    # Neither of these is the gate on pgwire, so 0165 must not see either of them.
    _insert(conn, agent_role="agent_recaller", tool="recall_search", transport="mcp")
    _insert(conn, agent_role="agent_gate", tool="recall_search", transport="mcp")

    by_tool = {
        row["tool"]: row for row in _rows(conn, "SELECT * FROM mainline_audit.v_gate_latency_daily")
    }
    assert set(by_tool) == {"permit_merge_gate", "disposition_sign"}, (
        "0165 must filter to agent_role = 'agent_gate' AND transport = 'pgwire'; it saw "
        f"{sorted(by_tool)}"
    )

    gate = by_tool["permit_merge_gate"]
    assert (gate["n"], gate["ok"], gate["refused"], gate["errored"], gate["abstained"]) == (
        4,
        2,
        1,
        1,
        0,
    )
    assert (gate["min_ms"], gate["max_ms"]) == (42, 1200)
    assert str(gate["mean_ms"]) == "401.8", f"mean_ms is {gate['mean_ms']!r}"
    assert (gate["over_250ms"], gate["over_1000ms"], gate["over_5000ms"]) == (2, 1, 0)
    assert gate["unmeasured"] == 0
    assert gate["measurement_complete"] is True

    signing = by_tool["disposition_sign"]
    assert signing["n"] == 2
    assert signing["unmeasured"] == 1
    assert signing["measurement_complete"] is False, (
        "a group containing an action nobody timed reported measurement_complete true — a mean "
        "over the subset that happened to be instrumented, published as if it were the whole"
    )
    assert all(row["group_count"] == 2 for row in by_tool.values())
    assert all(row["rows_complete"] is True for row in by_tool.values())


@pytest.mark.schema
def test_v_txn_restart_daily_separates_a_restart_from_a_refusal(conn: Any) -> None:
    """§16: ``40001`` is the ONLY retryable code, and retrying anything else is the defect."""
    _insert(conn, outcome="error", sqlstate="40001")
    _insert(conn, outcome="refused", sqlstate="23514")
    _insert(conn, outcome="refused", sqlstate="23503")
    _insert(conn, outcome="refused", sqlstate="23505")
    _insert(conn, outcome="refused", sqlstate="P0001")
    _insert(conn, outcome="error", sqlstate="42501")
    _insert(conn, outcome="error", sqlstate=UNMODELLED_SQLSTATE)
    _insert(conn, agent_role="agent_recaller", tool="recall_search", transport="mcp")

    by_role = {
        row["agent_role"]: row
        for row in _rows(conn, "SELECT * FROM mainline_audit.v_txn_restart_daily")
    }
    assert set(by_role) == {"agent_gate", "agent_recaller"}

    gate = by_role["agent_gate"]
    assert gate["attempts"] == 7
    assert gate["restarts"] == 1
    assert gate["refused_check"] == 1
    assert gate["refused_fk"] == 1
    assert gate["refused_unique"] == 1
    assert gate["refused_raise"] == 1
    assert gate["insufficient_privilege"] == 1, (
        "42501 must stay broken out; it is the S22 missing-write-policy signature and calling "
        "it unmodelled buries the most diagnosable failure this deployment has"
    )
    assert gate["unmodelled"] == 1
    assert gate["outcomes_modelled"] is False

    recaller = by_role["agent_recaller"]
    assert recaller["attempts"] == 1
    assert recaller["unmodelled"] == 0
    assert recaller["outcomes_modelled"] is True


@pytest.mark.schema
def test_every_consumer_view_is_selectable_on_an_empty_table(conn: Any) -> None:
    """An empty producer must produce an empty view, not an error.

    0165's header reads an empty result as "the gate is not running", which is only a readable
    answer if the SELECT succeeds.
    """
    for view in CONSUMER_VIEWS:
        assert _select_view(conn, view) == []


@pytest.mark.schema
@pytest.mark.mi("MI01")
def test_no_view_reads_a_column_the_producer_does_not_have(conn: Any) -> None:
    """The seam, asserted from the database rather than from the files.

    A view that resolved at CREATE time and then lost a column would fail here and nowhere else
    until an operator opened the audit surface.
    """
    _insert(conn)
    for view in CONSUMER_VIEWS:
        assert len(_select_view(conn, view)) == 1, f"{view} lost the only seeded row"
