# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The schema tier's shared harness: markers, a cluster, an isolation primitive, three assertions.

`docs/leads/datamodel.md` §5 sizes this tier and names its isolation primitive:

> Isolation primitive is a fresh `site_id` per test against one long-lived cluster
> (`pytest-xdist` safe). Migration and RLS suites are `@pytest.mark.schema` and run
> serialised on a disposable container, pinned to `cockroachdb/cockroach:v26.2` by
> digest — never the `testcontainers` default, which is v24.1.1 and predates triggers.

Four things live here and nothing else does.

**1 · The markers.** ``mi``, ``schema`` and ``shape``. The repository runs pytest with
``--strict-markers``, so an unregistered marker is a *collection error*, and a collection
error in this directory takes the whole tier down — which is exactly what happened
between 2026-08-09 and this file landing: ``scripts/mi_ratchet.py red`` reported *cannot
determine* (exit 2) rather than a colour, because ``test_mi_foundation.py`` used
``@pytest.mark.shape`` and nothing had registered it. The ratchet deliberately did not
monkey-patch them in; silently registering another worker's markers converts a visible
build defect into an invisible one.

**2 · The cluster.** ``dsn`` and ``pool``, session-scoped, resolved from the environment
and **skipped cleanly** when there is none. PL-1: every milestone's proof must run on a
stranger's machine with no credential of ours, and a suite that errors because the
founder's cluster is unreachable has stopped distinguishing "the gate refused" from
"there was no gate".

**3 · The isolation primitive.** ``site`` mints a fresh ``site_id`` per test. Fresh, not
shared and not cleaned up: ``mainline.site`` is the authoritative source for every
projected ``site_role`` / ``site_code`` / ``tenant_id`` in the schema (DM-3), and rows
that reference it are append-only, so *teardown by deletion is not available*. A new
identity per test is the only isolation that works against an append-only schema, and it
is what makes ``pytest-xdist`` safe here.

**4 · Three assertions that are claims, not helpers.** ``assert_ledger_dense``,
``assert_no_fork`` and ``assert_counter_fidelity`` each state one of this system's
load-bearing sentences in SQL. They live here because they are the sentences the whole
tier repeats, and a sentence re-typed per test file is a sentence that drifts.

Nothing in this file creates a schema. The migration tree owns that; a conftest that
applied DDL would be a second, undeclared migration path.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = REPO_ROOT / "compose.yaml"

#: The MAINLINE namespace for deterministic identities (DM-12). Seeds are ``uuid5`` of
#: this namespace and a natural key; *test* identities are deliberately ``uuid4``, because
#: the point of the isolation primitive is that two runs never collide.
MAINLINE_NS = uuid.UUID("6f4d1a1e-9f52-5a3c-9d9a-2a7a4f3c1b00")

#: Identifier shape for anything these helpers interpolate into SQL. There is no
#: placeholder for an identifier, so a name that is not `lower_snake` (optionally
#: schema-qualified) is refused before it reaches a statement rather than escaped.
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")

_MI_MARKER = (
    'mi("MIxx"): this test witnesses invariant MIxx. Read by scripts/mi_ratchet.py, which '
    "treats the marker — and NOT an miNN token in a function name — as the author claiming "
    "to prove it."
)
_SCHEMA_MARKER = (
    "schema: touches DDL or RLS; runs serialised against a disposable cluster rather than "
    "against the shared one."
)
_SHAPE_MARKER = (
    "shape: asserts DDL shape from information_schema / SHOW CREATE rather than behaviour. "
    "Cheap, and the first thing to look at when a behaviour test fails."
)

_MARKERS = (
    ("mi", _MI_MARKER),
    ("schema", _SCHEMA_MARKER),
    ("shape", _SHAPE_MARKER),
)


def pytest_configure(config: pytest.Config) -> None:
    """Register this tier's markers so --strict-markers does not fail collection."""
    for name, description in _MARKERS:
        config.addinivalue_line("markers", f"{name}: {description}")


# ── The cluster ───────────────────────────────────────────────────────────────────────


def _ident(name: str, *, what: str) -> str:
    if _IDENT.match(name) is None:
        raise ValueError(
            f"{what}={name!r} is not a lower_snake identifier. These helpers interpolate "
            "identifiers into SQL because SQL has no placeholder for one, so the shape is "
            "checked rather than trusted."
        )
    return name


@pytest.fixture(scope="session")
def crdb_image() -> str:
    """The pinned CockroachDB image, read from the ONE version constant in compose.yaml.

    Never the ``testcontainers`` default. That default is v24.1.1, which predates
    triggers (v24.3) — a schema tier that silently ran against it would report every
    projection test as an error about a syntax the platform does not have, and nobody
    would learn that the tests were pointed at the wrong database.

    **Digest pinning, honestly.** The constant in ``compose.yaml`` is a *tag*. A digest
    invented here would be a lie committed to the repository, so the assertion activates
    the moment somebody records the real one: set ``CRDB_IMAGE_DIGEST`` (the same
    repository variable ``db.yml`` reads) and this fixture requires the image reference
    to carry it. ``TRAPPOINT_CRDB_IMAGE`` overrides the whole reference for a run against
    a mirror.
    """
    from trappoint_migrate.crdb import pinned_image

    override = os.environ.get("TRAPPOINT_CRDB_IMAGE")
    image = override or pinned_image(COMPOSE)
    expected = os.environ.get("CRDB_IMAGE_DIGEST")
    if expected and expected not in image:
        pytest.fail(
            f"CRDB_IMAGE_DIGEST is set to {expected!r} but the image reference is "
            f"{image!r}. Set TRAPPOINT_CRDB_IMAGE to the digest-pinned reference, or "
            "unset the variable — a digest that is declared and not used is worse than "
            "one that is absent."
        )
    if "v26.2" not in image and not override:
        pytest.fail(
            f"the pinned image is {image!r}. This tier asserts trigger, RLS and vector "
            "behaviour that CockroachDB acquired in v24.3 and v25.x; running it against "
            "anything older reports absent features as test errors."
        )
    return image


@pytest.fixture(scope="session")
def dsn() -> str:
    """The DSN for the schema tier, or a clean skip naming how to get one.

    A skip, not an error, and the reason says what to run. PL-1 wants a stranger to be
    able to reproduce the proof; the first thing a stranger meets is this message.
    """
    for name in ("TRAPPOINT_DSN", "LOCAL_DSN"):
        value = os.environ.get(name)
        if value:
            return value
    pytest.skip(
        "no cluster: set TRAPPOINT_DSN (or LOCAL_DSN). For a local single-node node — "
        "`docker compose up -d crdb` then "
        "TRAPPOINT_DSN=postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
    )


@pytest.fixture(scope="session")
def pool(dsn: str) -> Iterator[Any]:
    """One session-scoped connection pool. Autocommit, SERIALIZABLE, named.

    Autocommit because this tier's subject is *refusals*: a test asserts that a statement
    raises a particular SQLSTATE, and a shared open transaction would make the next
    statement fail with ``25P02`` — "current transaction is aborted" — which is a
    different refusal from the one under test and would quietly replace it.

    ``application_name`` is set so a hung suite is identifiable in ``SHOW SESSIONS``
    without guessing.
    """
    psycopg_pool = pytest.importorskip(
        "psycopg_pool", reason="psycopg[pool] is required; `uv sync` installs it"
    )
    connection_pool = psycopg_pool.ConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=4,
        open=False,
        kwargs={"autocommit": True, "application_name": "trappoint-schema-tier"},
    )
    connection_pool.open(wait=True, timeout=30)
    try:
        yield connection_pool
    finally:
        connection_pool.close()


# ── The isolation primitive ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Site:
    """One test's private site — the scope token every RLS policy compares against.

    ``materialised`` says whether a row was actually written to ``mainline.site``. It is
    False before migration ``0020a`` lands, and a test that needs the row asserts on this
    field rather than discovering the absence three statements later as a foreign-key
    violation it then has to interpret.
    """

    site_id: uuid.UUID
    site_code: str
    site_role: str
    tenant_id: uuid.UUID
    taxonomy_ver: int
    materialised: bool


@pytest.fixture
def site(pool: Any) -> Site:
    """A fresh ``site_id`` per test. The isolation primitive for the whole tier.

    Fresh and never cleaned up, and both halves are deliberate. ``mainline.site`` is the
    authoritative source DM-3 introduced so that ``site_role``, ``site_code`` and
    ``tenant_id`` have a table behind them instead of being trusted from an inserter;
    everything that cites a site is append-only, so deleting the row at teardown is not
    available even in principle. A new identity per test is therefore the only isolation
    that works here — and it is what makes this tier ``pytest-xdist`` safe, because two
    workers can never mint the same one.

    ``tenant_id`` is derived from ``site_id`` by ``uuid5`` rather than being random, so a
    failure message that shows one shows the other.
    """
    site_id = uuid.uuid4()
    short = site_id.hex[:8]
    record = Site(
        site_id=site_id,
        site_code=f"TST-{short.upper()}",
        # NAME, not STRING: RLS compares site_role to CURRENT_USER (DM-3), and a role
        # name is lower_snake.
        site_role=f"site_{short}",
        tenant_id=uuid.uuid5(MAINLINE_NS, f"tenant:{site_id}"),
        taxonomy_ver=1,
        materialised=False,
    )

    with pool.connection() as conn:
        if not _relation_exists(conn, "mainline", "site"):
            return record
        conn.execute(
            """
            INSERT INTO mainline.site
                (site_id, site_code, site_role, tenant_id, taxonomy_ver, opened_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                record.site_id,
                record.site_code,
                record.site_role,
                record.tenant_id,
                record.taxonomy_ver,
                "2026-08-05T00:00:00Z",
            ),
        )
    return Site(**{**record.__dict__, "materialised": True})


def _relation_exists(conn: Any, schema: str, name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, name),
    ).fetchone()
    return row is not None


# ── Three assertions that are claims ──────────────────────────────────────────────────


def assert_ledger_dense(
    conn: Any,
    *,
    table: str,
    subject_column: str,
    subject: object,
    seq_column: str = "seq",
    first: int = 1,
) -> None:
    """Assert one subject's sequence numbers are ``first..n`` with no gap.

    **This is the sentence the whole ledger design exists to make true.** The ledger is
    gap-free by compare-and-swap — ``UNIQUE (subject, prev_seq)`` — and not by a sequence,
    because a CockroachDB sequence is allowed to leave gaps: a rolled-back transaction
    consumes a value. Under a sequence a gap means *nothing*; under CAS, **a gap MEANS
    tampering**, and that sentence is the whole evidentiary value of the ledger.

    So this helper is not a convenience. It is the assertion that the sentence still
    holds, and ``trappoint migrate lint``'s ban on ``CREATE SEQUENCE`` is the other half
    of the same claim.
    """
    _ident(table, what="table")
    _ident(subject_column, what="subject_column")
    _ident(seq_column, what="seq_column")
    rows = conn.execute(
        f"SELECT {seq_column} FROM {table} WHERE {subject_column} = %s ORDER BY 1",  # noqa: S608
        (subject,),
    ).fetchall()
    observed = [int(row[0]) for row in rows]
    expected = list(range(first, first + len(observed)))
    assert observed == expected, (
        f"{table} is not dense for {subject_column}={subject!r}: got {observed}, expected "
        f"{expected}. The ledger is gap-free by CAS, so a gap is not a curiosity — it "
        "means a row was deleted."
    )


def assert_no_fork(
    conn: Any,
    *,
    table: str,
    subject_column: str,
    subject: object,
    prev_column: str = "prev_seq",
) -> None:
    """Assert the chain for one subject is linear: no ``prev`` value claimed twice, one head.

    A fork is the failure a dense check cannot see. Two rows that both cite predecessor
    ``N`` produce a tree, not a chain, and every count over the table then depends on
    which branch the reader walked. The database refuses this with
    ``UNIQUE (subject, prev_seq)``; this asserts the refusal is still installed, and it
    checks the head count too, because a linear chain with two heads is not a chain.
    """
    _ident(table, what="table")
    _ident(subject_column, what="subject_column")
    _ident(prev_column, what="prev_column")
    rows = conn.execute(
        f"""
        SELECT {prev_column}, count(*) AS n FROM {table}
        WHERE {subject_column} = %s
        GROUP BY 1 HAVING count(*) > 1
        """,  # noqa: S608
        (subject,),
    ).fetchall()
    assert rows == [], (
        f"{table} forks for {subject_column}={subject!r}: {rows} — a predecessor claimed "
        "twice makes the history a tree, and every count over it depends on which branch "
        "the reader walked."
    )


def assert_counter_fidelity(
    conn: Any,
    *,
    subject_table: str,
    subject_key: str,
    subject: object,
    counter_column: str,
    source_table: str,
    source_key: str,
    source_predicate: str = "TRUE",
) -> None:
    """Assert a projected counter equals a recount of the table it projects from.

    **P2 as an assertion.** Every column a gate reads is written by a trigger from a
    named authoritative table, so a counter column is never an input — and the only way
    to know the projection is still faithful is to recompute it from the source and
    compare. A counter that has drifted is worse than an absent one: the gate keeps
    refusing or keeps admitting, confidently, on a number nothing produced.

    *source_predicate* is a fixed SQL fragment from the calling test, never data. It is
    how a partial counter ("open checks", not "checks") is expressed.
    """
    _ident(subject_table, what="subject_table")
    _ident(subject_key, what="subject_key")
    _ident(counter_column, what="counter_column")
    _ident(source_table, what="source_table")
    _ident(source_key, what="source_key")

    projected_row = conn.execute(
        f"SELECT {counter_column} FROM {subject_table} WHERE {subject_key} = %s",  # noqa: S608
        (subject,),
    ).fetchone()
    assert projected_row is not None, (
        f"no row in {subject_table} for {subject_key}={subject!r}; a projection over a "
        "missing subject is a refusal, not a zero"
    )
    recount_row = conn.execute(
        f"SELECT count(*) FROM {source_table} "  # noqa: S608
        f"WHERE {source_key} = %s AND ({source_predicate})",
        (subject,),
    ).fetchone()
    projected = int(projected_row[0])
    recounted = int(recount_row[0]) if recount_row is not None else 0
    assert projected == recounted, (
        f"{subject_table}.{counter_column} = {projected} but {source_table} holds "
        f"{recounted} matching row(s) for {subject_key}={subject!r}. The counter is a "
        "projection of that table; a drifted projection means the gate is deciding on a "
        "number nothing produced."
    )
