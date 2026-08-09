# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Shared doubles. Every test in this package runs without a database, on purpose.

The gate's behaviour against a live cluster is the conformance suite's job; what is
asserted here is the CLIENT's contract — which code is retried, which is attempted once,
and how the exhibit is recovered — and that contract must be assertable on a laptop with
no container running, or it will not be asserted on every commit.

``FakeError`` subclasses ``psycopg.Error`` deliberately. ``retry.run_gate`` catches
``psycopg.Error`` and not ``Exception``, so a double that did not subclass it would
sail past the very clause under test and prove nothing.
"""

from __future__ import annotations

from collections.abc import Callable

import psycopg
import pytest


class FakeDiag:
    """The ``diag`` fields this client reads, set to what CockroachDB actually returns.

    ``context`` is ``None`` and ``source_function`` is a Go internal because that is
    what was MEASURED on v26.2.5 through psycopg 3.3.4 for a PL/pgSQL ``RAISE``. A
    double that supplied a PostgreSQL-style context stack would let a test pass on a
    recovery path this platform never exercises.
    """

    def __init__(self, constraint_name: str | None, message_primary: str | None) -> None:
        self.constraint_name = constraint_name
        self.message_primary = message_primary
        self.context = None
        self.source_function = "func397"


class FakeError(psycopg.Error):
    """A driver error carrying a chosen SQLSTATE and diagnostics."""

    def __init__(self, sqlstate: str, constraint: str | None, message: str) -> None:
        """Build an error with *sqlstate*, an optional constraint name and a message.

        The two attributes are set BEFORE ``super().__init__``: psycopg's ``Error``
        constructor reads ``self.sqlstate``, and this class overrides that with a
        property backed by ``_sqlstate``.
        """
        self._sqlstate = sqlstate
        self._diag = FakeDiag(constraint, message)
        super().__init__(message)

    @property
    def sqlstate(self) -> str:  # type: ignore[override]
        """The five-character code."""
        return self._sqlstate

    @property
    def diag(self) -> FakeDiag:  # type: ignore[override]
        """The diagnostics block."""
        return self._diag


@pytest.fixture
def make_error() -> Callable[..., FakeError]:
    """Return a factory for :class:`FakeError`."""

    def factory(sqlstate: str, constraint: str | None, message: str) -> FakeError:
        return FakeError(sqlstate, constraint, message)

    return factory
