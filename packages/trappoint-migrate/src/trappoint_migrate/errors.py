# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Failure vocabulary for the migration runner.

Every exception here is a *decision*, not a surprise. The runner has exactly three
ways to stop — the tree is inconsistent with what was applied, the lock is held, or a
statement failed — and each of them names the thing a human has to look at next.

The SQLSTATE contract this file honours is normative in ``spec/errors.md``: ``40001``
is the only retryable code, and nothing in this package retries anything else.
"""

from __future__ import annotations

__all__ = [
    "AttestationDrift",
    "BootstrapMissing",
    "ClusterUnreachable",
    "DirtyMigration",
    "LockUnavailable",
    "MigrateError",
    "MigrationTreeInvalid",
    "SchemaJobFailed",
    "StatementFailed",
    "UsageError",
]


class MigrateError(Exception):
    """Base class: something the runner refused to do, with a reason a human can act on."""


class UsageError(MigrateError):
    """The invocation itself was wrong. Exit code 2, never 1.

    Kept distinct because a wrapper script that cannot tell "you typed it wrong" from
    "the database refused" will retry the first one forever.
    """


class ClusterUnreachable(MigrateError):
    """No connection could be opened.

    Kept distinct from every other failure because "there was no database" and "the
    database said no" are different sentences, and a lane that reported them the same
    way would let an unreachable cluster masquerade as a refusal — which, in a
    red-before-green suite, is exactly the confusion that makes red meaningless.
    """


class BootstrapMissing(MigrateError):
    """The ``trappoint`` schema is absent, so there is nowhere to record the attempt.

    The runner never creates its own bookkeeping implicitly. A migration applied
    against a database whose ledger tables did not exist is a migration with no record,
    and the whole point of this runner is that the record is written in the same
    connection discipline as the change.
    """


class LockUnavailable(MigrateError):
    """Another migrator holds the lease.

    CockroachDB has no advisory locks, so ``trappoint.schema_lock`` is a real table
    with a real lease. This is refused rather than waited on: two concurrent migration
    streams against one cluster is an operational error, not a queueing problem.
    """


class DirtyMigration(MigrateError):
    """A previous run left a version in ``applying`` or ``dirty`` state.

    Forward progress is refused until a human resolves it with
    ``trappoint migrate force <version> --incident <id>``. A dirty schema is a custody
    event (research/06-build/schema-migrations.md §11.1), which is why clearing it
    requires an incident identifier and writes an attestation row.
    """


class MigrationTreeInvalid(MigrateError):
    """The files on disk disagree with what the database says was applied.

    Three shapes, all fatal and all the same class of problem — the migration stream is
    not the stream that produced this schema:

    * a file's SHA-256 changed after it was applied;
    * a new file sorts *before* the last applied file (an insertion into history);
    * an applied version has no file at all.
    """


class StatementFailed(MigrateError):
    """A DDL statement was refused by the database.

    Carries the SQLSTATE and the message verbatim. The statement is attempted exactly
    once: it is not retried, not on ``40001`` either, because a DDL statement in
    CockroachDB starts a background job and "did it happen" is answered by ``SHOW
    JOBS``, not by trying again.
    """

    def __init__(self, version: str, sqlstate: str | None, message: str) -> None:
        """Record the version, the SQLSTATE and the database's own message, verbatim."""
        self.version = version
        self.sqlstate = sqlstate
        self.message = message
        super().__init__(f"{version}: [{sqlstate or 'no-sqlstate'}] {message}")


class SchemaJobFailed(MigrateError):
    """A schema-change job reached a terminal state other than success.

    The statement returned; the job did not. Advancing the version here would record a
    migration that the cluster is still reverting.
    """


class AttestationDrift(MigrateError):
    """The live schema fingerprint disagrees with the attestation chain head.

    Either something changed the schema outside this runner, or the chain has been
    edited. Both are the same alarm and neither is a warning.
    """
