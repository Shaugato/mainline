# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Tier-3 schema suite for the three producers of migrations 0090, 0099 and 0099a.

These three tables had their consumers written first and nobody wrote the ``CREATE TABLE``.
The cost was not theoretical. Measured on 2026-08-10, ``trappoint migrate up`` applied 155
of 261 files and refused ``0121_trg_check_materialised`` with ``[42P01] relation
"mainline_ops.outbox" does not exist`` — file 156 of 261, forward-only, so the 105 files
below the halt had never been executed by the runner a deployment uses.

What this file asserts, and why each part is here rather than somewhere else:

* **The projection actually happened.** ``test_one_blocking_check_projects_the_counter…``
  is the payload. It inserts ONE ``mainline.blocking_check`` against a draft permit and
  reads back three consequences of the single weld ``0121`` puts on that table:
  ``permit.open_blocking`` incremented, ``permit.gate_epoch`` incremented, and exactly one
  ``mainline_ops.outbox`` row carrying ``kind = 'check_opened'`` and
  ``subject_id = check_id``. Before ``0099`` existed, ``scripts/proof/gate_refusal.py``
  had to write ``open_blocking`` by hand and say so in its evidence file. The sentence this
  test licenses is not "the gate refused" but "**the trigger projected the counter, emitted
  the CDC signal, bumped the epoch, and the gate refused**", and every clause of it is a
  value read out of the database below.

* **The two negatives.** ``mainline_ops.outbox`` and ``mainline_ops.site_register_signal``
  carry NO row-level security and NO row-level-TTL-breaking append-only weld. Both are
  absences, and an absence decays silently unless something checks. ``test_mi_rls.py``
  asserts the RLS half against the cluster; this file asserts it against the cluster AND
  against the migration tree, because the failure mode is a future ``ALTER TABLE … ENABLE
  ROW LEVEL SECURITY`` that passes review, and a file-level scan is what sees that coming.

* **``v_fixity_coverage`` over real rows.** Applying ``0163`` proves the view compiles.
  Selecting from it is the test. In particular a **scopeless** patrol class must report
  ``not_checked_ratio = NULL`` and not ``0.0``: NULL means "the question does not apply,
  nothing was in scope", ``0.0`` means "everything in scope was checked", and coalescing
  the two reports a scope predicate that stopped matching as perfect coverage.

**SEC-1 applies here as everywhere.** Nothing below is a tamper-evidence claim. The outbox
is Class A operational transport (§12); the evidentiary record is the ``blocking_check``
row, the disposition and the ledger.

Running it
----------
Needs a CockroachDB v26.2. Resolved from the session ``dsn`` fixture in
``tests/integration/schema/conftest.py``, then ``$TRAPPOINT_DSN`` / ``$LOCAL_DSN`` /
``$MAINLINE_TEST_DSN`` / ``$COCKROACH_URL`` / ``$CRDB_URL``, and **skips with a reason**
rather than faking anything. The cluster tier builds its own database, applies the whole
tree into it and drops it at teardown: these are DDL-and-trigger assertions and they may
not run against a schema some other suite is mutating.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)

# The apply fixture walks the whole migration tree once per session. That is well inside the
# repository's 120 s per-item budget on the local node (measured ~70 s for 271 files on
# 2026-08-10), but the budget is a wall-clock one and a loaded machine is not a test failure.
pytestmark = pytest.mark.timeout(600)

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "verticals" / "mainline" / "db"
MIGRATIONS_DIR = DB_DIR / "migrations"

#: MR-5: four digits, at most one lowercase letter, a lower_snake slug, ``.sql``, no second dot.
MR5_FILENAME = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")

#: The three files this suite is the contract test for.
PRODUCER_FILES: tuple[str, ...] = (
    "0090_patrol_run.sql",
    "0099_outbox.sql",
    "0099a_site_register_signal.sql",
)

#: The three files that could not apply until the producers above existed. Written out rather
#: than derived: the point of the list is that each name was in a measured failure.
CONSUMER_FILES: tuple[str, ...] = (
    "0121_trg_check_materialised.sql",
    "0163_v_fixity_coverage.sql",
    "0198x_no_rls_on_cdc_sources.sql",
)

#: RLS-MATRIX.yaml `rls_forbidden`, spelled here so this file's negatives do not depend on
#: another file's parser to know what they are asserting about.
CDC_SOURCES: tuple[str, ...] = ("outbox", "site_register_signal")

DSN_ENV_NAMES: tuple[str, ...] = (
    "TRAPPOINT_DSN",
    "LOCAL_DSN",
    "MAINLINE_TEST_DSN",
    "COCKROACH_URL",
    "CRDB_URL",
)


def _sql(name: str) -> str:
    """One migration's text, verbatim."""
    return (MIGRATIONS_DIR / name).read_text(encoding="utf-8")


def _code(name: str) -> str:
    """One migration's text with comments removed — what the platform actually reads."""
    from trappoint_migrate.sqltext import strip_sql_comments

    return strip_sql_comments(_sql(name))


def _tree_code() -> dict[str, str]:
    """Every migration in the tree, comment-stripped, keyed by filename."""
    from trappoint_migrate.sqltext import strip_sql_comments

    return {
        path.name: strip_sql_comments(path.read_text(encoding="utf-8"))
        for path in MIGRATIONS_DIR.iterdir()
        if path.is_file() and MR5_FILENAME.match(path.name)
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STATIC TIER — needs no cluster. These are assertions about the FILES.
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.shape
@pytest.mark.mi("MI22")
@pytest.mark.parametrize("name", PRODUCER_FILES)
def test_each_producer_file_exists_and_carries_exactly_one_statement(name: str) -> None:
    """MR-5. One top-level statement per file, or the runner's attestation is per-what?"""
    from trappoint_migrate.discovery import statement_count

    path = MIGRATIONS_DIR / name
    assert path.is_file(), f"{name} does not exist — the consumers have no producer again"
    assert statement_count(_sql(name)) == 1, (
        f"{name} carries more than one top-level statement. The lock file records one sha256 "
        f"and one fingerprint per FILE, so a second statement is a schema change nothing attests."
    )


@pytest.mark.shape
@pytest.mark.mi("MI22")
def test_the_outbox_declares_no_column_family() -> None:
    """§4.1 law 11. CDC queries FAIL on multi-family tables, so the absence is load-bearing.

    Asserted against the comment-stripped text rather than the cluster because the cluster
    answer — ``SHOW CREATE`` emitting no ``FAMILY`` clause — is a consequence of this one, and
    the edit that would break it is made here.
    """
    code = _code("0099_outbox.sql")
    assert "FAMILY" not in code.upper(), (
        "0099_outbox.sql declares a column family. CDC queries are not supported on "
        "multi-family tables and this is the one changefeed-query source in the deployment: "
        "splitting the families does not slow the feed down, it stops it."
    )


@pytest.mark.shape
@pytest.mark.mi("MI22")
def test_the_outbox_declares_the_thirty_day_ttl_expiration_expression() -> None:
    """TTL allowlist entry 1 of 3, and the only reason the append-only weld is omitted."""
    code = _code("0099_outbox.sql")
    assert "ttl_expiration_expression" in code, (
        "0099_outbox.sql no longer declares a row-level TTL. If the TTL is deliberately gone, "
        "the append-only weld argument in its header changes with it — the two are one decision."
    )
    assert "expires_at" in code and "INTERVAL '30 days'" in code


@pytest.mark.shape
@pytest.mark.mi("MI22")
def test_the_outbox_kind_column_carries_no_check_constraint() -> None:
    """§5.10's fourteen kinds are a COMMENT, and 0101 inserts a fifteenth.

    Measured on CockroachDB CCL v26.2.5, 2026-08-10: a CHECK transcribed from that comment
    refuses ``'check_opened'`` with ``23514``. Under 0121's AFTER INSERT weld that refusal
    aborts the INSERT into ``mainline.blocking_check``, so no obligation could be raised
    against any permit in the deployment — the central mechanism of the product, disabled by
    a constraint transcribed from a comment.
    """
    code = _code("0099_outbox.sql")
    checks = re.findall(r"CHECK\s*\((?:[^()]|\([^()]*\))*\)", code, flags=re.IGNORECASE)
    offenders = [c for c in checks if re.search(r"\bkind\b", c, flags=re.IGNORECASE)]
    assert offenders == [], (
        f"0099_outbox.sql constrains `kind`: {offenders}. 0101_fn_check_materialised inserts "
        f"'check_opened', which §5.10's comment does not list, so the enumeration is already "
        f"incomplete against this repository's own code."
    )
    assert "'check_opened'" in _code("0101_fn_check_materialised.sql"), (
        "0101 no longer emits 'check_opened'. That is not a failure of this file, but the "
        "argument above rests on it and the two must be re-read together."
    )


@pytest.mark.shape
@pytest.mark.mi("MI22")
@pytest.mark.parametrize("table", CDC_SOURCES)
def test_no_migration_enables_row_level_security_on_a_cdc_source(table: str) -> None:
    """The negative, asserted against the TREE — which is where the change would be made.

    ``test_mi_rls.py`` asserts it against a cluster. Both are needed: a tree scan sees a
    policy that was written but has not been applied anywhere yet, and a cluster probe sees
    a policy applied by something outside the tree.
    """
    qualified = rf"mainline_ops\s*\.\s*{table}\b"
    enable = re.compile(rf"ALTER\s+TABLE\s+{qualified}[\s\S]{{0,80}}ROW\s+LEVEL\s+SECURITY", re.I)
    policy = re.compile(rf"CREATE\s+POLICY[\s\S]{{0,200}}?ON\s+{qualified}", re.I)
    offenders = [
        name for name, code in _tree_code().items() if enable.search(code) or policy.search(code)
    ]
    assert offenders == [], (
        f"mainline_ops.{table} is given row-level security by {offenders}. CDC queries are not "
        f"supported on RLS-enabled tables and FAIL, and CDC messages are not filtered by RLS in "
        f"any case — so this buys no confidentiality and stops the event spine at the next "
        f"changefeed restart, which is a stopped projector, which is MI22 on every gate."
    )


@pytest.mark.shape
@pytest.mark.mi("MI22")
def test_no_migration_welds_a_delete_refusal_to_the_outbox() -> None:
    """Ruling D5. The weld that is right for ``agent_action`` is WRONG here.

    Measured on CockroachDB CCL v26.2.5, 2026-08-10: a ``BEFORE DELETE … RAISE`` trigger on
    this table is ACCEPTED by the platform and then refuses ``DELETE FROM
    mainline_ops.outbox`` with ``P0001``. The row-level TTL job deletes expired rows by
    issuing DELETEs, so the weld would make the TTL job fail on every pass, forever, while
    looking exactly like the welds that are correct on the append-only tables.
    """
    weld = re.compile(
        r"CREATE\s+TRIGGER[\s\S]{0,200}?BEFORE\s+DELETE[\s\S]{0,80}?"
        r"ON\s+mainline_ops\s*\.\s*outbox\b",
        re.IGNORECASE,
    )
    offenders = [name for name, code in _tree_code().items() if weld.search(code)]
    assert offenders == [], (
        f"{offenders} welds a BEFORE DELETE refusal to mainline_ops.outbox. The TTL job deletes "
        f"expired rows; this trigger makes it fail forever. The durable record is the "
        f"blocking_check row, not the signal that announced it."
    )


@pytest.mark.shape
@pytest.mark.mi("MI21")
def test_patrol_run_declares_no_row_level_ttl() -> None:
    """§4.1 law 13: zero row-level TTL in schema ``mainline``, forever.

    A patrol run is the record of an inspection that did or did not happen — precisely the
    class of document the Crimes (Document Destruction) Act 2006 (Vic) is about.
    """
    code = _code("0090_patrol_run.sql").lower()
    assert "ttl_expiration_expression" not in code and "ttl_expire" not in code
    assert "ttl_job_cron" not in code


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLUSTER TIER
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Applied:
    """A database with the whole tree applied into it, and what did not apply."""

    dsn: str
    database: str
    blocked: list[tuple[str, str, str]]

    def connect(self) -> Any:
        return psycopg.connect(self.dsn, autocommit=True)


def _split(text: str) -> list[str]:
    """Top-level statements of one file, dollar-quote and string aware."""
    from trappoint_migrate.sqltext import strip_sql_comments

    body = strip_sql_comments(text)
    out: list[str] = []
    cur: list[str] = []
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "$":
            match = re.compile(r"\$(?:[A-Za-z_]\w*)?\$").match(body, i)
            if match is not None:
                tag = match.group(0)
                close = body.find(tag, match.end())
                end = n if close == -1 else close + len(tag)
                cur.append(body[i:end])
                i = end
                continue
        if ch == "'":
            cur.append(ch)
            i += 1
            while i < n:
                if body[i] == "'":
                    if i + 1 < n and body[i + 1] == "'":
                        cur.append("''")
                        i += 2
                        continue
                    cur.append("'")
                    i += 1
                    break
                cur.append(body[i])
                i += 1
            continue
        if ch == ";":
            statement = "".join(cur).strip()
            if statement:
                out.append(statement)
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out


@pytest.fixture(scope="session")
def ops_cluster(request: pytest.FixtureRequest) -> str:
    """The node this tier talks to, or a skip that names how to get one.

    Prefers the shared session ``dsn`` fixture — one node per run, a database per suite
    (producer-completion D11). Nobody here spawns a container: ten suites each starting their
    own is how a machine runs out of memory and the failure gets read as a schema defect.
    """
    try:
        shared = request.getfixturevalue("dsn")
    except Exception:  # noqa: BLE001 — a skipped fixture is not an error here, it is a fallback
        shared = None
    if isinstance(shared, str) and shared:
        return shared
    for name in DSN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    pytest.skip(
        "no CockroachDB v26.2 reachable. Set TRAPPOINT_DSN, e.g. "
        "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable after "
        "`docker compose up -d crdb`. A skipped run verifies no producer."
    )


@pytest.fixture(scope="session")
def applied(ops_cluster: str) -> Iterator[Applied]:
    """A fresh database with the whole tree applied, continue-on-error, dropped at teardown.

    Continue-on-error and not fail-fast, deliberately. This suite owns three files; a file
    another domain has in flight must not make these assertions unrunnable, and it must not
    make them pass silently either. ``test_the_producers_and_their_consumers_all_apply``
    asserts on the six files this wave is about and PRINTS the rest, which is the same
    division ``test_mi_rls.py`` draws for the RLS band.
    """
    from psycopg.conninfo import make_conninfo

    database = f"mainline_ops_producer_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(ops_cluster, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")
    dsn = make_conninfo(ops_cluster, dbname=database)

    blocked: list[tuple[str, str, str]] = []
    paths = sorted(
        (p for p in MIGRATIONS_DIR.iterdir() if p.is_file() and MR5_FILENAME.match(p.name)),
        key=lambda p: p.name.removesuffix(".sql"),
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in paths:
            for statement in _split(path.read_text(encoding="utf-8")):
                try:
                    conn.execute(statement)
                except psycopg.Error as exc:
                    blocked.append((path.name, exc.sqlstate or "?", str(exc).splitlines()[0]))

    print(
        f"\n[ops-producer] database: {database}\n"
        f"[ops-producer] applied {len(paths)} files, {len(blocked)} statements blocked"
    )
    try:
        yield Applied(dsn=dsn, database=database, blocked=blocked)
    finally:
        with psycopg.connect(ops_cluster, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(applied: Applied) -> Iterator[Any]:
    connection = applied.connect()
    try:
        yield connection
    finally:
        connection.close()


def _constraint_of(error: Any) -> str | None:
    """The constraint name a refusal names, read from the diagnostic and not from the message.

    MEASURED on CockroachDB CCL v26.2.5, 2026-08-10, and worth writing down because it decides
    how every DM-10 assertion in this tier has to be spelled. A ``23514`` message text carries
    the **expression**, not the name::

        failed to satisfy CHECK constraint (op IN ('add':::STRING, 'remove':::STRING, …))

    while ``error.diag.constraint_name`` carries ``'site_register_signal_op_known'``. A test
    that greps the message therefore fails against a schema whose constraints ARE named — the
    exact wrong direction for a rule whose point is that the name is the courtroom exhibit.
    A ``23505`` message, by contrast, does quote the index name.
    """
    diagnostic = getattr(error, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _sha(*parts: str) -> bytes:
    import hashlib

    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode())
    return digest.digest()


def _seed_site(conn: Any) -> uuid.UUID:
    """A fresh site. The isolation primitive for this whole tier — append-only, never cleaned."""
    site_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver) "
        "VALUES (%s, %s, %s, %s, 1)",
        (site_id, f"ops-{site_id.hex[:10]}", f"ops_{site_id.hex[:10]}", uuid.uuid4()),
    )
    return site_id


@dataclass(frozen=True)
class Gated:
    """The smallest history in which a blocking check can be raised against a permit."""

    site_id: uuid.UUID
    site_role: str
    clause_uuid: uuid.UUID
    commit_id: bytes
    event_id: uuid.UUID
    permit_id: uuid.UUID


def _seed_gated_permit(conn: Any) -> Gated:
    """A clause version, a blame closure that bands it ``blood_major``, and a draft permit.

    Nothing here is helped past a trigger. ``fn_closure_guard`` demands the first closure
    generation be zero and ledgers the closure in the same transaction; ``fn_clause_version_guard``
    inspects the birth version; both run. The seed is minimal on purpose — it is the smallest
    history in which ``0121``'s weld has something to project onto.
    """
    from psycopg.types.json import Jsonb

    site_id = _seed_site(conn)
    site_role = f"ops_{site_id.hex[:10]}"
    commit_id = _sha("commit", str(site_id))
    clause_uuid, doc_id, event_id, permit_id = (uuid.uuid4() for _ in range(4))

    conn.execute(
        "INSERT INTO mainline.commit_obj (commit_id, site_id, gen, ref_name, author_sub, "
        "message, envelope, envelope_bytes) "
        "VALUES (%s, %s, 0, 'refs/heads/ops', 'ops.producer.test', 'seed', %s, %s)",
        (commit_id, site_id, Jsonb({"kind": "ops-producer-seed"}), b"{}"),
    )
    conn.execute(
        "INSERT INTO mainline.doc (doc_id, site_id, doc_code, title) VALUES (%s, %s, %s, %s)",
        (doc_id, site_id, f"OPS-{site_id.hex[:6].upper()}", "ops producer seed"),
    )
    conn.execute(
        "INSERT INTO mainline.clause (clause_uuid, site_id, birth_commit, activity_root) "
        "VALUES (%s, %s, %s, 'ops/isolation')",
        (clause_uuid, site_id, commit_id),
    )
    conn.execute(
        "INSERT INTO mainline.clause_version (clause_uuid, gen, commit_id, site_id, doc_id, "
        "activity_root, ordinal, raw_text, canon_text, canon_version, canon_sha256, anchor_set, "
        "control_delta, delta_basis, blood_root, blood_peaks, blood_size, sev_max) "
        "VALUES (%s, 0, %s, %s, %s, 'ops/isolation', 1, 'raw', 'canon', 1, %s, ARRAY['TAG-1'], "
        "'restate', 'lattice', %s, ARRAY[%s]::BYTES[], 1, 4)",
        (clause_uuid, commit_id, site_id, doc_id, _sha("canon"), _sha("blood"), _sha("peak")),
    )
    conn.execute(
        "INSERT INTO mainline.event (event_id, site_id, occurred_at, kind, title, narrative, "
        "source_object_key, source_sha256, severity_actual, severity_potential, severity_gate, "
        "severity_basis, canon_version) "
        "VALUES (%s, %s, now() - INTERVAL '10 days', 'incident', 'ops precursor', "
        "'A precursor that reaches the clause this permit relies on.', 's3://ops/1', %s, "
        "4, 4, 4, 'human_rated', 1)",
        (event_id, site_id, _sha("source", str(event_id))),
    )
    # max_severity 4 with virulence blood_major: 0038's `blood_needs_severity` and
    # `major_ancestry_is_at_least_major` are a matched pair, and 4 is the arming threshold.
    conn.execute(
        "INSERT INTO mainline.clause_blame_closure (clause_uuid, as_of_commit, closure_gen, "
        "site_id, ancestor_events, ancestor_count, max_severity, virulence, depth, truncated, "
        "computed_by, projector_ver) "
        "VALUES (%s, %s, 0, %s, ARRAY[%s]::UUID[], 1, 4, 'blood_major', 1, false, "
        "'tests/integration/schema/test_ops_producer.py', 'ops-1')",
        (clause_uuid, commit_id, site_id, event_id),
    )
    conn.execute(
        "INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, ref_name, "
        "horizon_at) VALUES (%s, %s, %s, %s, %s, now() + INTERVAL '30 days')",
        (
            permit_id,
            site_id,
            site_role,
            f"PTW-OPS-{permit_id.hex[:8].upper()}",
            f"refs/permits/ops-{permit_id.hex[:8]}",
        ),
    )
    return Gated(
        site_id=site_id,
        site_role=site_role,
        clause_uuid=clause_uuid,
        commit_id=commit_id,
        event_id=event_id,
        permit_id=permit_id,
    )


@pytest.mark.requires_cluster
@pytest.mark.schema
@pytest.mark.mi("MI22")
def test_the_producers_and_their_consumers_all_apply(applied: Applied) -> None:
    """The six files this wave is about, applied in one forward pass.

    ``0121`` is the one that halted ``trappoint migrate up`` at file 156 of 261 on
    2026-08-10; ``0163`` and ``0198x`` are below the halt and had therefore never been
    executed by the deployment runner at all.
    """
    mine = set(PRODUCER_FILES) | set(CONSUMER_FILES)
    failures = [(n, s, m) for n, s, m in applied.blocked if n in mine]
    others = [(n, s, m) for n, s, m in applied.blocked if n not in mine]
    assert failures == [], (
        "the producer/consumer seam did not apply:\n"
        + "\n".join(f"  {n}: [{s}] {m}" for n, s, m in failures)
        + "\n\nOther files' failures in the same run (informational, not this suite's):\n"
        + "\n".join(f"  {n}: [{s}] {m}" for n, s, m in others)
    )


@pytest.mark.requires_cluster
@pytest.mark.schema
@pytest.mark.mi("MI02")
def test_one_blocking_check_projects_the_counter_bumps_the_epoch_and_emits_one_outbox_row(
    conn: Any,
) -> None:
    """THE PAYLOAD. One INSERT, three consequences, all of them the trigger's.

    Observed on CockroachDB CCL v26.2.5, 2026-08-10, in a database with the whole tree
    applied::

        PERMIT  before  state=draft open_blocking=0 gate_epoch=0
        PERMIT  after   state=draft open_blocking=1 gate_epoch=1
        OUTBOX  kind='check_opened'  subject_id == check_id  max_severity=4  payload={}
                expires_at - emitted_at = 30 days

    ``max_severity`` on the signal is **4** although the inserter supplied ``0``: the BEFORE
    INSERT projection ``fn_check_project`` (0120) overwrites ``severity`` from the blame
    closure first, and the AFTER INSERT weld reads the projected value. That is MI25 visible
    on the wire — the severity a signal carries is the closure's, never the caller's.
    """
    gated = _seed_gated_permit(conn)

    before = conn.execute(
        "SELECT state::STRING, open_blocking, gate_epoch FROM mainline.permit WHERE permit_id = %s",
        (gated.permit_id,),
    ).fetchone()
    assert before == ("draft", 0, 0), f"the permit did not start as an unblocked draft: {before}"
    signals_before = conn.execute("SELECT count(*) FROM mainline_ops.outbox").fetchone()[0]

    check_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.blocking_check (check_id, subject_kind, permit_id, site_id, "
        "clause_uuid, commit_id, precursor_event_id, origin, severity, virulence, closure_gen, "
        "evidence_summary) "
        "VALUES (%s, 'permit', %s, %s, %s, %s, %s, 'blame_ancestry', 0, 'routine', 0, %s)",
        (
            check_id,
            gated.permit_id,
            gated.site_id,
            gated.clause_uuid,
            gated.commit_id,
            gated.event_id,
            "Recalled precursor reaches the clause this permit relies on.",
        ),
    )

    after = conn.execute(
        "SELECT state::STRING, open_blocking, gate_epoch FROM mainline.permit WHERE permit_id = %s",
        (gated.permit_id,),
    ).fetchone()
    assert after[1] == before[1] + 1, (
        f"open_blocking did not move: {before[1]} -> {after[1]}. This counter is the scalar the "
        f"`gate_closed_when_issued` CHECK reads, so a projection that does not run is a gate "
        f"that passes vacuously — which is the failure mode MI22 names."
    )
    assert after[2] == before[2] + 1, (
        f"gate_epoch did not move: {before[2]} -> {after[2]}. The epoch is the other half of the "
        f"same weld: without the bump, the composite epoch pin cannot make attaching a precursor "
        f"to an issued subject physically impossible (MI07)."
    )

    signals = conn.execute(
        "SELECT kind, subject_id, site_id, max_severity, payload, "
        "expires_at - emitted_at, target_site, activity_root, score "
        "FROM mainline_ops.outbox WHERE subject_id = %s",
        (check_id,),
    ).fetchall()
    assert len(signals) == 1, (
        f"expected exactly one outbox signal for check {check_id}, got {len(signals)}. "
        f"Two signals is a trigger that fired twice; zero is a spine with nothing on it."
    )
    kind, subject_id, site_id, max_severity, payload, lifetime, target, root, score = signals[0]
    assert kind == "check_opened"
    assert str(subject_id) == str(check_id), "the signal names a different subject than the check"
    assert str(site_id) == str(gated.site_id), (
        "the signal's site_id is wrong. It is denormalised precisely because a CDC query cannot "
        "join, so a wrong value here is not recoverable by the consumer."
    )
    assert max_severity == 4, (
        f"the signal carries severity {max_severity}; the inserter supplied 0 and the blame "
        f"closure says 4. The projection is what makes severity a fact rather than a claim (MI25)."
    )
    assert payload == {}, "the payload is POINTERS AND DIGESTS ONLY; 0101 emits an empty object"
    assert lifetime == timedelta(days=30), f"the TTL horizon is not 30 days: {lifetime}"
    assert (target, root, score) == (None, None, Decimal(0)), (
        f"the nullable/defaulted columns did not take their declared defaults: "
        f"target_site={target} activity_root={root} score={score}"
    )

    total_after = conn.execute("SELECT count(*) FROM mainline_ops.outbox").fetchone()[0]
    assert total_after == signals_before + 1, (
        f"the whole table gained {total_after - signals_before} rows for one blocking check. "
        f"The weld is one AFTER INSERT trigger and it must emit exactly one signal."
    )


@pytest.mark.requires_cluster
@pytest.mark.schema
@pytest.mark.mi("MI22")
@pytest.mark.parametrize("table", CDC_SOURCES)
def test_neither_cdc_source_carries_row_level_security(conn: Any, table: str) -> None:
    """§4.1 law 11, asserted as the negative it is — this time against the live cluster.

    Read from ``pg_class`` rather than from ``SHOW CREATE``: RLS being ENABLED but not FORCED
    is a distinct and equally fatal state, and a text search for the word ``POLICY`` cannot
    tell the two apart.
    """
    row = conn.execute(
        "SELECT cl.relrowsecurity, cl.relforcerowsecurity FROM pg_class cl "
        "JOIN pg_namespace n ON n.oid = cl.relnamespace "
        "WHERE n.nspname = 'mainline_ops' AND cl.relname = %s",
        (table,),
    ).fetchone()
    assert row is not None, (
        f"mainline_ops.{table} does not exist. That is not an RLS result — it is the producer "
        f"gap this suite was written for, and a negative assertion against an absent table "
        f"asserts nothing."
    )
    assert row == (False, False), f"mainline_ops.{table} has RLS enabled/forced: {row}"
    policies = conn.execute(
        "SELECT policyname FROM pg_policies WHERE schemaname = 'mainline_ops' AND tablename = %s",
        (table,),
    ).fetchall()
    assert policies == [], f"mainline_ops.{table} carries policies: {policies}"


@pytest.mark.requires_cluster
@pytest.mark.schema
@pytest.mark.shape
@pytest.mark.mi("MI22")
def test_the_outbox_landed_single_family_with_the_ttl_the_platform_accepted(conn: Any) -> None:
    """What the platform actually stored, read back rather than assumed.

    On CockroachDB CCL v26.2.5 the storage parameter is accepted and echoed as
    ``WITH (ttl = 'on', ttl_expiration_expression = 'expires_at', schema_locked = true)`` —
    ``ttl = 'on'`` added by the platform, ``schema_locked`` a v26.2 default on every table in
    this tree. If a future release refuses the parameter, this test fails loudly rather than
    letting a table that silently keeps every signal forever pass as the one that expires them.
    """
    create = conn.execute("SHOW CREATE TABLE mainline_ops.outbox").fetchone()[1]
    assert "ttl_expiration_expression = 'expires_at'" in create, create
    assert "CONSTRAINT pk_outbox PRIMARY KEY" in create, "DM-10: the primary key must be named"

    # `SHOW CREATE` concatenates the table definition and 0198x's COMMENT, and that comment
    # contains the word "single-family" while EXPLAINING why there are none. A substring test
    # over the whole blob therefore reports a family that is not there, on the one table whose
    # comment argues hardest that it has none. Bound the search to the definition.
    definition = create.split("COMMENT ON", 1)[0]
    assert re.search(r"\bFAMILY\b", definition, flags=re.IGNORECASE) is None, (
        f"mainline_ops.outbox landed with column families, which makes a CDC query on it fail:\n"
        f"{definition}"
    )


@pytest.mark.requires_cluster
@pytest.mark.schema
@pytest.mark.mi("MI21")
def test_v_fixity_coverage_reports_a_scopeless_class_as_null_and_not_as_zero(conn: Any) -> None:
    """The distinction 0163 exists to preserve, over rows this test wrote.

    ``NULL`` means "the question does not apply — nothing was in scope". ``0.0`` means
    "everything in scope was checked". Coalescing them reports a scope predicate that stopped
    matching as perfect coverage, which is the failure this whole view is aimed at.

    Observed, 2026-08-10::

        ('L0', runs=1, unfinished=0, scopeless=0, 100/89/11, ratio=0.1100, complete=False)
        ('L1', runs=2, unfinished=1, scopeless=0,  20/10/0,  ratio=0.0000, complete=False)
        ('L2', runs=1, unfinished=0, scopeless=1,   0/0/0,   ratio=None,   complete=False)
    """
    from psycopg.types.json import Jsonb

    site_id = _seed_site(conn)
    now = datetime.now(UTC)

    def run(
        patrol_class: str,
        schedule: str,
        occurrence: datetime,
        in_scope: int,
        checked: int,
        not_checked: int,
        *,
        finished: bool = True,
    ) -> None:
        conn.execute(
            "INSERT INTO mainline.patrol_run (run_id, site_id, patrol_class, schedule_id, "
            "occurrence_ts, scope_pred, n_in_scope, n_checked, n_not_checked, as_of_hlc, "
            "started_at, finished_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                uuid.uuid4(),
                site_id,
                patrol_class,
                schedule,
                occurrence,
                Jsonb({"pred": "site", "class": patrol_class}),
                in_scope,
                checked,
                not_checked,
                Decimal("1755000000000000000.0000000001"),
                occurrence,
                (occurrence + timedelta(minutes=20)) if finished else None,
            ),
        )

    run("L0", "sch-a", now - timedelta(days=3), 100, 89, 11)
    run("L1", "sch-b", now - timedelta(days=2), 10, 10, 0)
    run("L1", "sch-b", now - timedelta(days=1), 10, 0, 0, finished=False)
    run("L2", "sch-c", now - timedelta(days=4), 0, 0, 0)

    rows = conn.execute(
        "SELECT patrol_class, runs, unfinished_runs, scopeless_runs, in_scope, checked, "
        "not_checked, not_checked_ratio, coverage_complete "
        "FROM mainline_audit.v_fixity_coverage WHERE site_id = %s ORDER BY patrol_class",
        (site_id,),
    ).fetchall()
    by_class = {str(r[0]): r for r in rows}
    assert set(by_class) == {"L0", "L1", "L2"}, f"the view grouped differently: {rows}"

    l0 = by_class["L0"]
    assert (l0[1], l0[2], l0[3]) == (1, 0, 0)
    assert l0[7] == Decimal("0.1100"), (
        f"11 unchecked out of 100 in scope is 0.1100 to four places, not {l0[7]}. The rounding is "
        f"a size decision (the 10 KiB MCP response cap); the NUMERIC widening is a correctness "
        f"one — sum() over INT8 returns DECIMAL on v26.2.5 and FLOAT8 does not compile."
    )
    assert l0[8] is False, "89 of 100 checked is not complete coverage"

    l1 = by_class["L1"]
    assert l1[1] == 2 and l1[2] == 1, f"the unfinished run was not counted: {l1}"
    assert l1[7] == Decimal("0.0000"), (
        f"L1 checked everything it accounted for, so its ratio is exactly 0.0000, not {l1[7]}. "
        f"This is the value the scopeless case must NOT be confused with."
    )
    assert l1[8] is False, (
        "a class with an unfinished run may not report coverage_complete — the flag fails closed"
    )

    l2 = by_class["L2"]
    assert l2[3] == 1, f"the scopeless run was not counted as scopeless: {l2}"
    assert l2[7] is None, (
        f"a scopeless patrol class reported {l2[7]!r} rather than NULL. NULL means 'nothing was "
        f"in scope'; 0.0 means 'everything in scope was checked'. A class whose ratio is NULL and "
        f"whose scopeless_runs equals its runs is a patrol that has been declaring nothing in "
        f"scope for ninety days, and reporting that as perfect coverage is the defect."
    )
    assert l2[8] is False, "an empty scope is not complete coverage; the flag fails closed"


@pytest.mark.requires_cluster
@pytest.mark.schema
@pytest.mark.mi("MI21")
def test_the_occurrence_key_absorbs_an_at_least_once_redelivery(conn: Any) -> None:
    """EventBridge Scheduler is at-least-once, and §5.8 says so on the constraint itself.

    The producer's only insert ends ``ON CONFLICT (site_id, schedule_id, occurrence_ts) DO
    NOTHING``, so this key is not merely a de-duplicator — it is the arbiter that statement
    needs in order to plan at all.
    """
    from psycopg.types.json import Jsonb

    site_id = _seed_site(conn)
    occurrence = datetime.now(UTC) - timedelta(days=1)
    params = (
        site_id,
        "L1",
        "sched-at-least-once",
        occurrence,
        Jsonb({"pred": "site"}),
        7,
        7,
        0,
        Decimal("1755000000000000000.0000000001"),
        occurrence,
    )
    statement = (
        "INSERT INTO mainline.patrol_run (site_id, patrol_class, schedule_id, occurrence_ts, "
        "scope_pred, n_in_scope, n_checked, n_not_checked, as_of_hlc, started_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    )
    conn.execute(statement, params)
    with pytest.raises(psycopg.Error) as excinfo:
        conn.execute(statement, params)
    assert excinfo.value.sqlstate == "23505", excinfo.value
    assert "patrol_run_occurrence_unique" in str(excinfo.value), (
        f"the redelivery was refused by something other than the occurrence key: {excinfo.value}"
    )

    conn.execute(
        "INSERT INTO mainline.patrol_run (site_id, patrol_class, schedule_id, occurrence_ts, "
        "scope_pred, n_in_scope, n_checked, n_not_checked, as_of_hlc, started_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (site_id, schedule_id, occurrence_ts) DO NOTHING RETURNING run_id",
        params,
    )
    assert (
        conn.execute(
            "SELECT count(*) FROM mainline.patrol_run WHERE site_id = %s AND schedule_id = %s",
            (site_id, "sched-at-least-once"),
        ).fetchone()[0]
        == 1
    ), "the producer's ON CONFLICT arbiter did not resolve to this key"


@pytest.mark.requires_cluster
@pytest.mark.schema
@pytest.mark.mi("MI21")
def test_a_patrol_may_not_account_for_more_than_it_declared_in_scope(conn: Any) -> None:
    """The conservation law, in the direction the consumer needs it.

    The producer enforces equality (``PatrolAccount.balanced()``); the schema enforces ``<=``,
    which equality implies. The looser form is deliberate: ``finished_at`` is nullable and
    0163 counts ``unfinished_runs``, so a two-phase writer must be able to open a run whose
    accounting has not closed yet. What neither may do is report a coverage ratio above 1.0.
    """
    from psycopg.types.json import Jsonb

    site_id = _seed_site(conn)
    with pytest.raises(psycopg.Error) as excinfo:
        conn.execute(
            "INSERT INTO mainline.patrol_run (site_id, patrol_class, schedule_id, occurrence_ts, "
            "scope_pred, n_in_scope, n_checked, n_not_checked, as_of_hlc, started_at) "
            "VALUES (%s, 'L0', 'sched-over', now(), %s, 1, 1, 1, 1.0, now())",
            (site_id, Jsonb({"pred": "site"})),
        )
    assert excinfo.value.sqlstate == "23514", excinfo.value
    assert _constraint_of(excinfo.value) == "patrol_run_account_within_scope", excinfo.value

    with pytest.raises(psycopg.Error) as negative:
        conn.execute(
            "INSERT INTO mainline.patrol_run (site_id, patrol_class, schedule_id, occurrence_ts, "
            "scope_pred, n_in_scope, n_checked, n_not_checked, as_of_hlc, started_at) "
            "VALUES (%s, 'L0', 'sched-neg', now(), %s, 1, -1, 0, 1.0, now())",
            (site_id, Jsonb({"pred": "site"})),
        )
    assert negative.value.sqlstate == "23514", negative.value
    assert _constraint_of(negative.value) == "patrol_run_counts_nonneg", negative.value


@pytest.mark.requires_cluster
@pytest.mark.schema
@pytest.mark.mi("MI22")
def test_the_watch_source_takes_three_operations_and_no_fourth(conn: Any) -> None:
    """§5.9. A predicate over a register set is falsified by an add, a remove or a change.

    A fourth verb would be a fourth falsification rule nobody wrote, and every consumer would
    evaluate it silently as "no match" — which is a `mechanism_absent` disposition that never
    gets revoked, which is the exhibit this table exists to invert.
    """
    from psycopg.types.json import Jsonb

    site_id = _seed_site(conn)
    for op in ("add", "remove", "change"):
        conn.execute(
            "INSERT INTO mainline_ops.site_register_signal (site_id, register, key, op, payload) "
            "VALUES (%s, 'vessel_register', 'V-101', %s, %s)",
            (site_id, op, Jsonb({"digest": "sha256:0"})),
        )
    with pytest.raises(psycopg.Error) as excinfo:
        conn.execute(
            "INSERT INTO mainline_ops.site_register_signal (site_id, register, key, op, payload) "
            "VALUES (%s, 'vessel_register', 'V-101', 'archive', %s)",
            (site_id, Jsonb({})),
        )
    assert excinfo.value.sqlstate == "23514", excinfo.value
    assert _constraint_of(excinfo.value) == "site_register_signal_op_known", excinfo.value
    assert (
        conn.execute(
            "SELECT count(*) FROM mainline_ops.site_register_signal WHERE site_id = %s", (site_id,)
        ).fetchone()[0]
        == 3
    )
