# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The contract ``mainline.identity_assignment`` owes its consumers, asserted against a cluster.

``0140a_fn_cbm_account_guard.sql`` was written before its table existed.  Its ``asg``
CTE selects ``g.ancestor_clause_uuid``, filters ``g.commit_id = cid``, groups by
ancestor and evaluates ``bool_or(g.relation = 'split' | 'merge' | 'matched')``; the
trigger that attaches it, ``0145a``, refused with ``42P01`` for as long as no migration
created the relation.  ``0049d_identity_assignment.sql`` is that migration and
``0145f_trg_identity_assignment_append_only.sql`` is its append-only weld.

WHAT THIS FILE ADDS THAT THE CBM SUITE DOES NOT
-----------------------------------------------
``tests/integration/algorithms/cbm/`` is the *behavioural* acceptance test and it is the
stronger one: ``_cbm_sql_support.stood_in_objects()`` resolves each stand-in against the
real tree by content, so the moment ``0049d`` landed, ``full_stack()`` dropped
``_pending_dependency.sql`` and all 106 cases re-ran against this DDL with no edit to a
test file.  What that suite cannot say is *which* property of the table it depended on.
It exercises ``'matched'``, ``'split'``, ``'merge'`` and ``'absent'`` and never once
touches ``UPDATE``, because the derivation it tests does not issue one.

So this file pins the four things a future edit could break while the CBM suite stayed
green — the column set, the primary key over the coalesced descendant, the closed
``relation`` domain *including* ``'absent'``, and the append-only refusal — and it pins
them by shape and by SQLSTATE rather than by reading the migration back and comparing it
with itself.

THE STACK IS MINIMAL, DEPENDENCY-CLOSED, AND MADE OF REAL MIGRATIONS
--------------------------------------------------------------------
Six files, applied forward from a clean database in filename order.  Not the whole tree:
through the deployment runner the tree still halts at ``0121_trg_check_materialised``
because ``mainline_ops.outbox`` has no producer, so a test that required 261 files to
apply would be asserting another worker's schedule rather than this table's contract.
Not a hand-written twin either — every statement here comes out of
``verticals/mainline/db/migrations`` and the file names are listed literally, because
their numbers are *granted* by ``migrations.allocation.toml`` and resolving them by
content would make a file that quietly drifted out of its band invisible here.

Measured on CockroachDB CCL v26.2.5, 2026-08-10: the six apply clean in this order.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
MIGRATIONS: Final[Path] = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"

PRODUCER: Final[str] = "0049d_identity_assignment.sql"
WELD: Final[str] = "0145f_trg_identity_assignment_append_only.sql"

#: The minimal dependency-closed stack, in apply order.  ``0024`` is ``fk_commit``'s
#: target, ``0028`` is ``fk_ancestor_clause``'s, and ``0107`` creates the kernel's
#: ``fn_refuse_mutation`` that the weld attaches.  Filename order and dependency order
#: agree, which is the property MR-5's lexicographic runner relies on.
STACK: Final[tuple[str, ...]] = (
    "0001a_schema_mainline.sql",
    "0024_commit_obj.sql",
    "0028_clause.sql",
    PRODUCER,
    "0107_fn_refuse_mutation.sql",
    WELD,
)

#: ``(column, data_type, is_nullable)`` in ordinal order, as ``information_schema``
#: reports it on v26.2.5.  CockroachDB renders ``STRING`` as ``text`` and ``BYTES`` as
#: ``bytea``; the migration is written in the CockroachDB spellings and the catalogue
#: answers in the PostgreSQL ones, which is why this table is transcribed from a live
#: cluster rather than from the DDL.
EXPECTED_COLUMNS: Final[tuple[tuple[str, str, str], ...]] = (
    ("site_id", "uuid", "NO"),
    ("commit_id", "bytea", "NO"),
    ("ancestor_clause_uuid", "uuid", "NO"),
    ("descendant_clause_uuid", "uuid", "YES"),
    ("relation", "text", "NO"),
    ("stage", "text", "NO"),
    ("score", "double precision", "YES"),
    ("margin", "double precision", "YES"),
    ("policy_sha256", "bytea", "NO"),
    ("computed_by", "text", "NO"),
    ("computed_at", "timestamp with time zone", "NO"),
    ("descendant_key", "uuid", "NO"),
)

#: ``0140a`` reads the relation keyed by commit; the third key column is the nil-coalesced
#: descendant, which is what lets ``'absent'`` — whose ``descendant_clause_uuid`` is NULL —
#: be a key at all.
PRIMARY_KEY: Final[tuple[str, ...]] = ("commit_id", "ancestor_clause_uuid", "descendant_key")

#: The closed set.  ``'absent'`` is in the domain and is deliberately in NO bucket of
#: ``0140a``'s five-way classification: an ancestor declared absent with no residue row
#: makes the account short and ``CONSTRAINT cbm_balances`` refuses it at ``23514``.
#: Removing it from this domain would make that refusal unreachable, so it is asserted
#: here as a value the table ACCEPTS.
LEGAL_RELATIONS: Final[tuple[str, ...]] = ("matched", "split", "merge", "absent")

NIL_UUID: Final[uuid.UUID] = uuid.UUID("00000000-0000-0000-0000-000000000000")

#: Pinned as a literal, not read out of ``0107``.  A test that read the message from the
#: migration and compared it with itself would pass for any string, including an empty one.
APPEND_ONLY_MESSAGE: Final[str] = "MAINLINE: this table is append-only; write a new row"

_CLUSTER_ENV: Final[tuple[str, ...]] = (
    "TRAPPOINT_DSN",
    "LOCAL_DSN",
    "MAINLINE_TEST_DSN",
    "COCKROACH_URL",
    "CRDB_URL",
)

# ── statement splitting ───────────────────────────────────────────────────────────────
#
# Deliberately named ``_split_sql`` and deliberately local.  ``0107`` is a ``$$ … $$``
# PL/pgSQL body full of semicolons, so the splitter must be dollar-quote aware; and
# pytest's prepend import mode puts every collected test directory on ``sys.path``, so
# importing another suite's ``_cbm_sql_support`` from here would bind this file's
# correctness to whether that directory happened to be collected.

_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def _split_sql(sql: str) -> list[str]:
    """Split *sql* on top-level semicolons, respecting comments, strings and ``$$`` bodies."""
    out: list[str] = []
    start = index = 0
    size = len(sql)
    while index < size:
        char = sql[index]
        if char == "-" and sql.startswith("--", index):
            end = sql.find("\n", index)
            index = size if end == -1 else end + 1
        elif char == "'":
            index += 1
            while index < size:
                if sql[index] == "'":
                    if sql.startswith("''", index):
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
        elif char == "$":
            match = _DOLLAR_TAG.match(sql, index)
            if match is None:
                index += 1
                continue
            tag = match.group(0)
            end = sql.find(tag, match.end())
            index = size if end == -1 else end + len(tag)
        elif char == ";":
            out.append(sql[start:index])
            index += 1
            start = index
        else:
            index += 1
    out.append(sql[start:])
    return [part for part in out if _has_code(part)]


def _has_code(fragment: str) -> bool:
    return bool(re.sub(r"--[^\n]*", " ", fragment).strip())


# ── fixtures ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def cluster_dsn() -> str:
    """A CockroachDB v26.2 to build the stack in, or a skip that names how to get one.

    A skip, not a fake.  PL-1 wants a stranger to reproduce the proof on their own
    machine, and the first thing a stranger meets is this message.
    """
    for name in _CLUSTER_ENV:
        value = os.environ.get(name)
        if value:
            return value
    pytest.skip(
        "no CockroachDB v26.2 reachable: set one of "
        f"{', '.join(_CLUSTER_ENV)}. For a local single node — `docker compose up -d crdb` "
        "then TRAPPOINT_DSN=postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable. "
        "This contract is NOT verified by a skipped run."
    )


@pytest.fixture(scope="module")
def migrated(cluster_dsn: str) -> Iterator[Any]:
    """A fresh database with :data:`STACK` applied forward from clean, dropped afterwards.

    Module-scoped: the six statements are the same for every test here, and building
    them once per test would multiply a DDL round trip that is already the slowest thing
    in this file.  Every test takes a fresh ``commit_id``/``clause_uuid`` instead, which
    is the isolation primitive this tier uses everywhere (a fresh identity, never a
    teardown, because the schema is append-only and deletion is not available).
    """
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    database = f"w_w2_contract_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(cluster_dsn, autocommit=True, connect_timeout=30) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    parts = conninfo_to_dict(cluster_dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)

    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=30) as conn:
            for name in STACK:
                path = MIGRATIONS / name
                assert path.is_file(), f"{name} is missing from {MIGRATIONS}"
                for statement in _split_sql(path.read_text(encoding="utf-8")):
                    try:
                        conn.execute(statement)
                    except psycopg.Error as exc:  # pragma: no cover - a red build, not a skip
                        pytest.fail(
                            f"{name} failed to apply into {database}: "
                            f"[{exc.sqlstate}] {exc}\n{statement.strip()[:800]}"
                        )
            print(f"\n[w2] {database}: applied {len(STACK)} migrations — {', '.join(STACK)}")
            yield conn
    finally:
        with psycopg.connect(cluster_dsn, autocommit=True, connect_timeout=30) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def ancestry(migrated: Any) -> tuple[uuid.UUID, bytes, uuid.UUID]:
    """One legal ``(site_id, commit_id, ancestor_clause_uuid)`` the FKs will accept."""
    site_id = uuid.uuid4()
    label = uuid.uuid4().hex
    commit_id = hashlib.sha256(f"w2/{label}".encode()).digest()
    migrated.execute(
        """
        INSERT INTO mainline.commit_obj
          (commit_id, site_id, gen, ref_name, author_sub, message,
           envelope, envelope_bytes, sig)
        VALUES (%s, %s, 1, 'site/marrindal/main', 'sub-principal-engineer',
                'w2 contract commit', '{}'::JSONB, %s, NULL)
        """,
        (commit_id, site_id, label.encode("utf-8")),
    )
    clause_uuid = uuid.uuid4()
    migrated.execute(
        """
        INSERT INTO mainline.clause
          (clause_uuid, site_id, birth_commit, activity_root, head_commit)
        VALUES (%s, %s, %s, 'ISOLATION-OF-STORED-ENERGY', %s)
        """,
        (clause_uuid, site_id, commit_id, commit_id),
    )
    return site_id, commit_id, clause_uuid


def _insert(
    conn: Any,
    ancestry: tuple[uuid.UUID, bytes, uuid.UUID],
    *,
    relation: str,
    descendant: uuid.UUID | None,
    stage: str = "S1",
    score: float | None = 1.0,
    margin: float | None = 1.0,
) -> None:
    """The exact column list ``_cbm_sql_support.insert_assignment`` writes."""
    site_id, commit_id, ancestor = ancestry
    conn.execute(
        """
        INSERT INTO mainline.identity_assignment
          (site_id, commit_id, ancestor_clause_uuid, descendant_clause_uuid, relation,
           stage, score, margin, policy_sha256, computed_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            site_id,
            commit_id,
            ancestor,
            descendant,
            relation,
            stage,
            score,
            margin,
            hashlib.sha256(b"identity-policy-v1").digest(),
            "agent_cartographer",
        ),
    )


# ── the tree, with no cluster ─────────────────────────────────────────────────────────


def test_the_producer_and_its_weld_are_in_the_tree() -> None:
    """Both files exist, in the bands their headers claim, and neither is a ``.up.sql``.

    A static check, so it runs on a machine with no cluster at all — and it is the one
    that fails first and most legibly if somebody renumbers either file out of its
    allocated band.
    """
    for name in (PRODUCER, WELD):
        assert (MIGRATIONS / name).is_file(), (
            f"{name} is missing from {MIGRATIONS}. `0145a_trg_cbm_account_guard.sql` "
            "refuses with 42P01 without it."
        )
        assert re.fullmatch(r"\d{4}[a-z]?_[a-z0-9_]+\.sql", name), f"{name} violates MR-5"

    assert PRODUCER < "0145a_trg_cbm_account_guard.sql", (
        "the table must sort before the trigger that welds its consumer: CockroachDB "
        "v26.2 resolves a CREATE TRIGGER's table reference at apply time"
    )
    assert WELD > "0107_fn_refuse_mutation.sql", (
        "the weld attaches mainline.fn_refuse_mutation, which 0107 creates"
    )


# ── shape ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.schema
def test_the_column_set_is_exactly_the_contract(migrated: Any) -> None:
    """Every column the consumers name, in order, with its type and nullability — and no more.

    Exact, not a superset.  A column the writer supplies and nothing derives is a place
    for a claim to hide, and ``0140a`` re-derives every COUNT precisely so that no
    writer-supplied number reaches a gate.
    """
    observed = tuple(
        (str(row[0]), str(row[1]), str(row[2]))
        for row in migrated.execute(
            """
            SELECT column_name, data_type, is_nullable
              FROM information_schema.columns
             WHERE table_schema = 'mainline' AND table_name = 'identity_assignment'
             ORDER BY ordinal_position
            """
        ).fetchall()
    )
    assert observed == EXPECTED_COLUMNS


@pytest.mark.schema
def test_descendant_key_is_the_nil_coalesced_descendant_and_is_stored(migrated: Any) -> None:
    """The generated column is computed by the database, never supplied.

    It is what makes ``'absent'`` — whose ``descendant_clause_uuid`` is NULL — a legal
    primary-key row, and it is STORED because a key column has to be materialised to be
    indexed.  A writer able to set it could put two verdicts for one ancestor under two
    different keys and defeat the idempotence the ``23505`` collision gives a re-run.
    """
    row = migrated.execute(
        """
        SELECT is_generated, generation_expression
          FROM information_schema.columns
         WHERE table_schema = 'mainline'
           AND table_name = 'identity_assignment'
           AND column_name = 'descendant_key'
        """
    ).fetchone()
    assert row is not None
    assert str(row[0]).upper() == "ALWAYS"
    expression = str(row[1]).lower().replace(" ", "")
    assert "coalesce(descendant_clause_uuid" in expression
    assert "00000000-0000-0000-0000-000000000000" in expression


@pytest.mark.schema
def test_the_primary_key_is_commit_ancestor_and_the_coalesced_descendant(migrated: Any) -> None:
    """``PRIMARY KEY (commit_id, ancestor_clause_uuid, descendant_key)``, in that order.

    The order is load-bearing and not cosmetic.  ``0140a`` asks one question per account
    write — every assignment row for one ``commit_id``, grouped by ancestor — so a
    commit-leading key answers it with a seek on the latency-critical merge path.
    """
    observed = tuple(
        str(row[0])
        for row in migrated.execute(
            """
            SELECT k.column_name
              FROM information_schema.table_constraints t
              JOIN information_schema.key_column_usage k
                ON k.constraint_name = t.constraint_name
               AND k.table_schema = t.table_schema
               AND k.table_name = t.table_name
             WHERE t.table_schema = 'mainline'
               AND t.table_name = 'identity_assignment'
               AND t.constraint_type = 'PRIMARY KEY'
             ORDER BY k.ordinal_position
            """
        ).fetchall()
    )
    assert observed == PRIMARY_KEY


# ── the relation domain ───────────────────────────────────────────────────────────────


@pytest.mark.schema
@pytest.mark.parametrize("relation", LEGAL_RELATIONS)
def test_every_legal_relation_is_accepted(
    migrated: Any, ancestry: tuple[uuid.UUID, bytes, uuid.UUID], relation: str
) -> None:
    """All four, including ``'absent'``.

    ``'absent'`` is the one a well-meaning edit would remove, because ``0140a`` gives it
    no bucket and it therefore looks like a value that does nothing.  It is not: it is
    how a matcher RECORDS the conclusion that an obligation is gone, and the account it
    leaves short is the refusal.  A schema that gave that conclusion nowhere to go would
    convert a finding into silence, and silence is indistinguishable from a crashed job.
    """
    descendant = None if relation == "absent" else uuid.uuid4()
    _insert(migrated, ancestry, relation=relation, descendant=descendant)

    _, commit_id, ancestor = ancestry
    stored = migrated.execute(
        """
        SELECT relation, descendant_key
          FROM mainline.identity_assignment
         WHERE commit_id = %s AND ancestor_clause_uuid = %s
        """,
        (commit_id, ancestor),
    ).fetchall()
    assert [str(row[0]) for row in stored] == [relation]
    expected_key = NIL_UUID if descendant is None else descendant
    assert uuid.UUID(str(stored[0][1])) == expected_key


@pytest.mark.schema
def test_a_relation_outside_the_closed_set_is_refused(
    migrated: Any, ancestry: tuple[uuid.UUID, bytes, uuid.UUID]
) -> None:
    """``23514`` on ``relation_closed``.

    ``'unmatched'`` is chosen on purpose: it is a legal ``identity_residue.reason`` and
    the mistake a reader who conflated the two tables would actually make.
    """
    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        _insert(migrated, ancestry, relation="unmatched", descendant=uuid.uuid4())
    assert caught.value.sqlstate == "23514"
    assert caught.value.diag.constraint_name == "relation_closed"


@pytest.mark.schema
def test_absent_may_not_name_a_descendant(
    migrated: Any, ancestry: tuple[uuid.UUID, bytes, uuid.UUID]
) -> None:
    """``23514`` on ``absent_has_no_descendant``.

    "This obligation is gone" and "this obligation went here" are contradictory claims,
    and a row asserting both would be counted as absent by the domain and read as placed
    by a human.
    """
    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        _insert(migrated, ancestry, relation="absent", descendant=uuid.uuid4())
    assert caught.value.sqlstate == "23514"
    assert caught.value.diag.constraint_name == "absent_has_no_descendant"


@pytest.mark.schema
def test_a_re_run_of_the_matcher_collides_rather_than_double_counting(
    migrated: Any, ancestry: tuple[uuid.UUID, bytes, uuid.UUID]
) -> None:
    """The same verdict twice is ``23505``, not two rows.

    ``0140a`` counts ANCESTORS and not rows, so a duplicate would not by itself unbalance
    an account — which is exactly why the guarantee has to be structural rather than
    arithmetic.  It is the property ``residue_unique`` gives ``0049``, restated over the
    coalesced descendant.
    """
    descendant = uuid.uuid4()
    _insert(migrated, ancestry, relation="matched", descendant=descendant)
    with pytest.raises(psycopg.errors.UniqueViolation) as caught:
        _insert(migrated, ancestry, relation="matched", descendant=descendant)
    assert caught.value.sqlstate == "23505"


# ── append-only ───────────────────────────────────────────────────────────────────────


@pytest.mark.schema
def test_an_update_is_refused_with_p0001(
    migrated: Any, ancestry: tuple[uuid.UUID, bytes, uuid.UUID]
) -> None:
    """The weld at ``0145f``, doing the thing it exists for.

    The attack it stops is one statement long.  ``0140a`` re-derives the six counters
    BEFORE INSERT on ``mainline.cbm_account``, so an account written against a truthful
    assignment set stays balanced whatever happens afterwards; one
    ``UPDATE … SET relation = 'matched' WHERE relation = 'absent'`` would therefore make
    every future account balance, leave every existing one untouched, and record nothing.
    """
    _insert(migrated, ancestry, relation="absent", descendant=None)
    _, commit_id, ancestor = ancestry
    with pytest.raises(psycopg.errors.RaiseException) as caught:
        migrated.execute(
            """
            UPDATE mainline.identity_assignment
               SET relation = 'matched'
             WHERE commit_id = %s AND ancestor_clause_uuid = %s
            """,
            (commit_id, ancestor),
        )
    assert caught.value.sqlstate == "P0001"
    assert APPEND_ONLY_MESSAGE in str(caught.value)

    survivor = migrated.execute(
        """
        SELECT relation FROM mainline.identity_assignment
         WHERE commit_id = %s AND ancestor_clause_uuid = %s
        """,
        (commit_id, ancestor),
    ).fetchone()
    assert survivor is not None
    assert str(survivor[0]) == "absent", "the refused UPDATE must not have partially applied"


@pytest.mark.schema
def test_a_delete_is_refused_with_p0001(
    migrated: Any, ancestry: tuple[uuid.UUID, bytes, uuid.UUID]
) -> None:
    """DELETE is welded too, and for a sharper reason than archival tidiness.

    Deleting an ``'absent'`` row does not merely remove evidence; it removes the row whose
    presence made the account short, so the next generation balances and the unaccounted
    obligation is gone without trace.  The unbalanced account was the alarm.
    """
    _insert(migrated, ancestry, relation="absent", descendant=None)
    _, commit_id, ancestor = ancestry
    with pytest.raises(psycopg.errors.RaiseException) as caught:
        migrated.execute(
            """
            DELETE FROM mainline.identity_assignment
             WHERE commit_id = %s AND ancestor_clause_uuid = %s
            """,
            (commit_id, ancestor),
        )
    assert caught.value.sqlstate == "P0001"
    assert APPEND_ONLY_MESSAGE in str(caught.value)

    remaining = migrated.execute(
        "SELECT count(*) FROM mainline.identity_assignment WHERE commit_id = %s",
        (commit_id,),
    ).fetchone()
    assert remaining is not None
    assert int(remaining[0]) == 1


# ── provenance ────────────────────────────────────────────────────────────────────────


@pytest.mark.schema
def test_the_derivation_provenance_cannot_be_left_blank(
    migrated: Any, ancestry: tuple[uuid.UUID, bytes, uuid.UUID]
) -> None:
    """I06: the inputs, method and version travel with the edge, or the row is refused.

    ``policy_sha256`` is D11 — the content hash of ``identity_policy-v1.toml`` on every
    row, so retro-tuning the matcher until a dropped obligation looks reasonable shows up
    as rows whose policy hash nobody can produce a file for.  A short hash and an empty
    ``computed_by``/``stage`` are the two ways to write a row that claims nothing, and
    both are ``23514``.
    """
    site_id, commit_id, ancestor = ancestry

    with pytest.raises(psycopg.errors.CheckViolation) as short_hash:
        migrated.execute(
            """
            INSERT INTO mainline.identity_assignment
              (site_id, commit_id, ancestor_clause_uuid, descendant_clause_uuid, relation,
               stage, score, margin, policy_sha256, computed_by)
            VALUES (%s, %s, %s, %s, 'matched', 'S1', 1.0, 1.0, %s, 'agent_cartographer')
            """,
            (site_id, commit_id, ancestor, uuid.uuid4(), b"too-short"),
        )
    assert short_hash.value.diag.constraint_name == "policy_sha256_is_sha256"

    with pytest.raises(psycopg.errors.CheckViolation) as blank_author:
        _insert(migrated, ancestry, relation="matched", descendant=uuid.uuid4(), stage="")
    assert blank_author.value.diag.constraint_name == "stage_stated"


@pytest.mark.schema
def test_score_and_margin_are_bounded_where_present(
    migrated: Any, ancestry: tuple[uuid.UUID, bytes, uuid.UUID]
) -> None:
    """[0, 1] or NULL, never a sentinel.

    NULL is legal because a ``'merge'`` arm or an ``'absent'`` verdict may have no
    meaningful runner-up; ``-1`` is not, because a sentinel is a number that later gets
    averaged.
    """
    _insert(migrated, ancestry, relation="merge", descendant=uuid.uuid4(), score=None, margin=None)

    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        _insert(migrated, ancestry, relation="matched", descendant=uuid.uuid4(), margin=-1.0)
    assert caught.value.diag.constraint_name == "margin_bounded"
