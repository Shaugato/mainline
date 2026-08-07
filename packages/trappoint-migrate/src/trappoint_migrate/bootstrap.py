# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The ``trappoint`` bootstrap schema: three tables, outside the numbered sequence.

Kernel ruling **D6**. The runner owns its own bookkeeping in a schema called
``trappoint``, created by ``trappoint migrate bootstrap`` and never by a numbered
migration. Keeping it out of the sequence has two consequences worth stating:
ARCHITECTURE.md §18's numbering stays exactly as written, and the runner can record an
attempt *before* migration ``0001`` exists — which is the only way the first migration
in a repository can be recorded at all.

The DDL lives here, in Python, rather than in a ``.sql`` file. That is not a shortcut:
these statements are issued by the tool that also enforces the one-statement-per-file
rule, and a ``.sql`` file in the migrations tree that is not part of the versioned
stream would be a file the tool would have to special-case forever.

**Why three tables and not one.**

``schema_migration`` records intent-then-outcome, so a crash between the two leaves a
row saying ``applying`` rather than leaving nothing. That row is the dirty marker, and
forward progress is refused while it exists.

``schema_lock`` is a REAL lock table. CockroachDB has no advisory locks, so there is no
session-scoped mutex to borrow; the lease is a row with an expiry, taken over only
after it has actually expired.

``schema_attestation`` is a ledger, and it is built the way every ledger in this
repository is built: **gap-free by compare-and-swap, never by a sequence**. Three
mechanisms, deliberately overlapping:

* ``schema_attestation_pkey PRIMARY KEY (ordinal)``
* ``attestation_chain_linear UNIQUE (prev_ordinal)``
* ``attestation_chain_dense CHECK (ordinal = prev_ordinal + 1)``

Two concurrent appends that both read head ``N`` both compute ``N+1``, so one commits
and the other gets ``23505``. Measured against CockroachDB v26.2.5 the exhibit is
``schema_attestation_pkey`` — the primary key is what the writer meets first — and
``attestation_chain_linear`` is the mechanism that still refuses when the dense CHECK is
removed. The overlap is stated rather than hidden because the honest claim is *"this
refuses at depth 2"*, not *"this constraint is what refuses"*.

Together they buy the sentence that matters: **a gap in this table means a row was
deleted.** A sequence would have made a gap mean nothing — a rolled-back transaction
consumes a value, and ``unique_rowid()`` is not dense by construction.
"""

from __future__ import annotations

from typing import Any

import psycopg

from .db import fetch_all

__all__ = [
    "BOOKKEEPING_TABLES",
    "BOOTSTRAP_STATEMENTS",
    "GENESIS_FINGERPRINT",
    "SCHEMA",
    "bootstrap",
    "is_bootstrapped",
]

SCHEMA = "trappoint"

# The three bookkeeping tables. A constant, so `is_bootstrapped` compares against a
# number a reader can trace to a list rather than against a bare literal.
BOOKKEEPING_TABLES: tuple[str, ...] = ("schema_migration", "schema_lock", "schema_attestation")

# The chain's origin. Thirty-two zero bytes is a legal SHA-256-shaped value that no
# fingerprint computation can produce by accident, so "this row is the genesis" is a
# fact about the value rather than a fact about the ordinal.
GENESIS_FINGERPRINT = b"\x00" * 32

BOOTSTRAP_STATEMENTS: tuple[tuple[str, str], ...] = (
    (
        "schema",
        "CREATE SCHEMA IF NOT EXISTS trappoint",
    ),
    (
        "schema_migration",
        """
CREATE TABLE IF NOT EXISTS trappoint.schema_migration (
    tree            STRING    NOT NULL,
    version         STRING    NOT NULL,
    filename        STRING    NOT NULL,
    sha256          BYTES     NOT NULL,
    state           STRING    NOT NULL,
    applied_by      STRING    NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ NULL,
    job_ids         STRING[]  NOT NULL DEFAULT ARRAY[]::STRING[],
    failure         STRING    NULL,
    failure_sqlstate STRING   NULL,
    forced_incident STRING    NULL,
    CONSTRAINT schema_migration_pkey PRIMARY KEY (tree, version),
    CONSTRAINT state_known CHECK (state IN ('applying', 'applied', 'dirty')),
    CONSTRAINT sha_is_sha256 CHECK (length(sha256) = 32),
    CONSTRAINT dirty_names_a_failure CHECK ((state = 'dirty') = (failure IS NOT NULL)),
    CONSTRAINT applied_is_finished CHECK ((state = 'applied') = (finished_at IS NOT NULL))
)
""".strip(),
    ),
    (
        "schema_lock",
        """
CREATE TABLE IF NOT EXISTS trappoint.schema_lock (
    lock_name    STRING      NOT NULL,
    holder       STRING      NOT NULL,
    acquired_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    reason       STRING      NOT NULL,
    CONSTRAINT schema_lock_pkey PRIMARY KEY (lock_name),
    CONSTRAINT lease_runs_forward CHECK (expires_at > acquired_at)
)
""".strip(),
    ),
    (
        "schema_attestation",
        """
CREATE TABLE IF NOT EXISTS trappoint.schema_attestation (
    ordinal           INT8        NOT NULL,
    prev_ordinal      INT8        NOT NULL,
    kind              STRING      NOT NULL,
    tree              STRING      NOT NULL,
    version           STRING      NOT NULL,
    file_sha256       BYTES       NULL,
    fingerprint       BYTES       NOT NULL,
    prev_fingerprint  BYTES       NOT NULL,
    attestation_grade STRING      NOT NULL,
    job_ids           STRING[]    NOT NULL DEFAULT ARRAY[]::STRING[],
    applied_by        STRING      NOT NULL,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    incident_id       STRING      NULL,
    CONSTRAINT schema_attestation_pkey PRIMARY KEY (ordinal),
    CONSTRAINT attestation_chain_linear UNIQUE (prev_ordinal),
    CONSTRAINT attestation_chain_dense CHECK (ordinal = prev_ordinal + 1),
    CONSTRAINT kind_known CHECK (kind IN ('bootstrap', 'apply', 'attest', 'force')),
    CONSTRAINT grade_known CHECK (attestation_grade IN ('strong', 'weak')),
    CONSTRAINT force_cites_an_incident CHECK ((kind = 'force') = (incident_id IS NOT NULL)),
    CONSTRAINT fingerprint_is_sha256 CHECK (length(fingerprint) = 32),
    CONSTRAINT prev_fingerprint_is_sha256 CHECK (length(prev_fingerprint) = 32)
)
""".strip(),
    ),
)


def is_bootstrapped(conn: psycopg.Connection[Any]) -> bool:
    """Return whether all three bookkeeping tables exist.

    Partial is not bootstrapped. A cluster carrying ``schema_migration`` but not
    ``schema_attestation`` would apply migrations and record nothing about the schema
    they produced, which is the exact failure this runner exists to prevent.
    """
    rows = fetch_all(
        conn,
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name IN ('schema_migration', 'schema_lock', 'schema_attestation')
        """,
        (SCHEMA,),
    )
    return len(rows) == len(BOOKKEEPING_TABLES)


def bootstrap(
    conn: psycopg.Connection[Any],
    *,
    applied_by: str,
    schema_prefixes: tuple[str, ...],
) -> list[str]:
    """Create the bootstrap schema. Idempotent.

    Every statement is ``IF NOT EXISTS``, so running this against a cluster that is
    already bootstrapped is a no-op rather than an error — the command is on the
    critical path of every CI run and must not be a thing anyone has to guard.

    The genesis row records the **real** post-bootstrap fingerprint, not a placeholder.
    A genesis carrying the zero digest would make the very first ``attest`` report drift
    on a cluster nobody had touched, and an alarm that is wrong the first time it fires
    is an alarm nobody reads the second time. The zero digest is used for
    ``prev_fingerprint`` only, where its job is to be a value no computation can produce
    — so "this row is the origin" is a fact about the value rather than about the
    ordinal.

    Returns:
        The names of the objects the call ensured, in order.
    """
    from .attest import fingerprint  # local import: attest imports this module's genesis

    ensured: list[str] = []
    for name, statement in BOOTSTRAP_STATEMENTS:
        conn.execute(statement)
        ensured.append(name)

    computed = fingerprint(conn, schema_prefixes=schema_prefixes)

    # Written once, never again: `ON CONFLICT DO NOTHING` on the primary key means a
    # second bootstrap against the same cluster leaves the chain exactly as it was,
    # which is what makes `bootstrap` safe to re-run.
    conn.execute(
        """
        INSERT INTO trappoint.schema_attestation
            (ordinal, prev_ordinal, kind, tree, version,
             fingerprint, prev_fingerprint, attestation_grade, applied_by)
        VALUES (0, -1, 'bootstrap', '-', 'genesis', %s, %s, %s, %s)
        ON CONFLICT (ordinal) DO NOTHING
        """,
        (computed.digest, GENESIS_FINGERPRINT, computed.grade, applied_by),
    )
    ensured.append("genesis attestation")
    return ensured
