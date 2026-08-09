# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The schema fingerprint, the trigger definitions, and the cluster's own consistency check.

Three of the eight ``custodian_attestation`` kinds are read out of the database itself:
``schema_fingerprint``, ``trigger_definitions`` and ``inspect_database``. All three are
built here, over a :class:`SqlSource` Protocol, so the algorithms are testable without a
cluster and the driver never appears on this package's import path.

WHY THE NORMALISATION IS THE WHOLE ALGORITHM
--------------------------------------------
``SHOW CREATE ALL TABLES`` guarantees CREATE-before-ALTER ordering and **nothing else**
— in particular it does not guarantee intra-category ordering, so a naive digest over
its output differs between two consecutive computations against an unchanged database.
A fingerprint that flickers is strictly worse than no fingerprint: it produces alarm
fatigue and then it gets switched off. So every row is whitespace-collapsed and every
category is sorted **before** hashing, and :func:`stable_schema_fingerprint` computes
the digest twice and refuses if the two disagree. That refusal is K2 exit criterion 6,
and it is asserted rather than assumed on every single run, not only in CI.

WHY THIS IS NOT A SECOND FINGERPRINT
-------------------------------------
``trappoint_migrate.attest.fingerprint`` computes the same digest at migration-apply
time. If the patrol's digest and the runner's digest were computed differently, the
drift alarm would be comparing two different questions and answering neither. They
share ``collapse_whitespace`` — one implementation of the primitive — and
``tests/test_fingerprint_stability.py::test_matches_the_migration_runner_byte_for_byte``
drives *both* implementations over one identical row set and asserts the digests are
equal, with no cluster and no driver. Two callers, one answer, proven offline.

The reason this module holds its own copy of the assembly (rather than calling the
runner's) is capability, not taste: the runner's entry point takes a live
``psycopg.Connection`` and this package is a Lambda that must also run its algorithms
over recorded rows in a test. The equality test is what makes the duplication safe, and
it fails the build the day either side drifts.

GT-05 AND THE CLAIM THAT SOFTENS IN THE SAME COMMIT
----------------------------------------------------
``pg_get_triggerdef()`` was confirmed present on CockroachDB CCL v26.2.5 on 2026-08-07
(``trappoint migrate attest`` reported ``grade strong``); behaviour on CockroachDB Cloud
Standard, whose SQL identity differs, is **not** verified. Where it is absent this
module falls back to ``SHOW CREATE TABLE``, which loses per-trigger granularity, and
records ``granularity = "coarse"`` **in the attested data** — so verifier check 11
reports ``PASS(coarse)`` and the claim softens in the same artefact rather than
silently keeping its stronger wording.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol, runtime_checkable

from trappoint_migrate.sqltext import collapse_whitespace

__all__ = [
    "DEFAULT_SCHEMA_PREFIXES",
    "INSPECT_ENABLE_STATEMENT",
    "FetchOutcome",
    "FingerprintUnstable",
    "InspectReport",
    "PsycopgSqlSource",
    "SchemaFingerprint",
    "SqlSource",
    "TriggerDefinitions",
    "inspect_database",
    "schema_fingerprint",
    "stable_schema_fingerprint",
    "trigger_definitions",
]

# Domain separation between the parts, byte-identical to
# `trappoint_migrate.attest`: moving a statement from one category to another must not
# leave the digest unchanged.
_PART_SEPARATOR: Final = b"\x1e"
_LABEL_SEPARATOR: Final = b"\x1f"

#: ``LIKE`` patterns naming the schemas whose routines are covered. ``mainline%`` also
#: matches ``mainline_ops``, ``mainline_meas``, ``mainline_audit`` and ``mainline_qa``,
#: which is intended: a trigger function moved into a neighbouring schema must not fall
#: out of the fingerprint. ``trappoint%`` covers the kernel's own procedures
#: (``trappoint.merge_permit()``, ruling D6) — omit them and the merge procedure could be
#: replaced without changing the attestation, which is precisely the self-attesting-gate
#: claim.
#:
#: This tuple MUST equal ``trappoint_migrate.runner.DEFAULT_SCHEMA_PREFIXES``. The
#: patrol's digest and the runner's digest are compared against each other, and two
#: different schema selections make that comparison meaningless; the equality is asserted
#: by ``tests/test_fingerprint_stability.py`` rather than left as a coincidence.
DEFAULT_SCHEMA_PREFIXES: Final[tuple[str, ...]] = ("mainline%", "trappoint%")

#: Measured against the published grammar: ``INSPECT`` is gated behind a session
#: variable. Attempted, and its outcome is recorded rather than assumed — a cluster
#: where the variable does not exist is a cluster where the statement is either
#: already ungated or absent, and both are facts the attestation should carry.
INSPECT_ENABLE_STATEMENT: Final = "SET enable_inspect_command = true"

_SHOW_STATEMENTS: Final[tuple[tuple[str, str], ...]] = (
    ("schemas", "SHOW CREATE ALL SCHEMAS"),
    ("types", "SHOW CREATE ALL TYPES"),
    ("tables", "SHOW CREATE ALL TABLES"),
)

_ROUTINE_SUPPORT_SQL: Final = """
SELECT proname FROM pg_catalog.pg_proc
WHERE proname IN ('pg_get_triggerdef', 'pg_get_functiondef')
"""

_TRIGGER_SQL: Final = """
SELECT t.tgname AS name, pg_get_triggerdef(t.oid) AS def
FROM pg_catalog.pg_trigger t
WHERE NOT t.tgisinternal
ORDER BY 1
"""

_TRIGGER_DETAIL_SQL: Final = """
SELECT t.tgname AS trigger_name,
       c.relname AS table_name,
       n.nspname AS schema_name,
       t.tgenabled AS enabled,
       pg_get_triggerdef(t.oid) AS definition
FROM pg_catalog.pg_trigger t
JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal
ORDER BY 3, 2, 1
"""

_SHOW_INSPECT_ERRORS_SQL: Final = "SHOW INSPECT ERRORS"


class FingerprintUnstable(RuntimeError):
    """Two consecutive computations of an unchanged schema disagreed.

    K2 exit criterion 6 inverted. The normalisation is insufficient for this
    CockroachDB build, and a fingerprint that is not stable cannot detect a change —
    which makes it worse than no fingerprint at all.
    """


@dataclass(frozen=True, slots=True)
class FetchOutcome:
    """The result of a statement that is *allowed* to be unavailable.

    Used only for probes — ``SET enable_inspect_command``, ``INSPECT DATABASE``,
    ``SHOW INSPECT ERRORS`` — where "this cluster does not have that" is a fact worth
    attesting rather than a failure worth crashing on. The SQLSTATE is carried so the
    attested document says *why*, and a reader can tell "not supported here" from
    "refused for this role".
    """

    rows: tuple[Mapping[str, Any], ...] | None
    sqlstate: str | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        """True when the statement ran."""
        return self.rows is not None


@runtime_checkable
class SqlSource(Protocol):
    """A read-only window onto the cluster, narrow enough to fake exactly.

    Two methods and no transaction control, because every statement this module issues
    is a read (``SET`` excepted, and that one is session-local). The patrol's *writes*
    go through :mod:`~mainline_custody_patrol.collect`'s sink, which holds the caller's
    transaction — a custodian attestation and its ledger leaf commit together or not at
    all.
    """

    def fetch(self, statement: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Run a read and return dict rows, raising on any database error."""
        ...

    def try_fetch(self, statement: str, params: Sequence[Any] = ()) -> FetchOutcome:
        """Run a read that is permitted to be unavailable; never raises on SQL error."""
        ...


@dataclass(frozen=True, slots=True)
class SchemaFingerprint:
    """One computation of the whole-schema digest.

    Attributes:
        digest: SHA-256 over the normalised parts, joined by the record separator.
        grade: ``strong`` when triggers and routines are inside the hash; ``weak`` when
            GT-05's fallback was taken and the hash covers tables, types and schemas
            only. The grade travels with the digest so a weak attestation is never
            indistinguishable from a strong one.
        parts: the category labels that contributed, in order.
        part_digests: label → hex digest of that category alone. Drift then *names the
            surface that moved* instead of reporting a single changed number, which is
            the difference between an alarm somebody acts on and one they mute.
        row_counts: label → how many normalised statements that category contributed.
    """

    digest: bytes
    grade: str
    parts: tuple[str, ...]
    part_digests: Mapping[str, str]
    row_counts: Mapping[str, int]

    @property
    def hex(self) -> str:
        """The digest as lowercase hex."""
        return self.digest.hex()


@dataclass(frozen=True, slots=True)
class TriggerDefinitions:
    """Every non-internal trigger, as the database reports it *now*.

    The self-attesting gate (verifier check 11). What the migrations *said* the gate
    would be is in ``trappoint.schema_attestation``; what the gate *is* is here. Attack
    A13 — ``ALTER TABLE … DISABLE TRIGGER`` followed by a merge — is the difference
    between the two, and it is only visible because both exist.
    """

    granularity: str
    """``per_trigger`` when ``pg_get_triggerdef()`` answered; ``coarse`` when the
    ``SHOW CREATE TABLE`` fallback was taken (GT-05)."""
    source: str
    triggers: tuple[Mapping[str, Any], ...]

    @property
    def row_count(self) -> int:
        """How many trigger definitions were captured."""
        return len(self.triggers)


@dataclass(frozen=True, slots=True)
class InspectReport:
    """The cluster's own consistency reporting, and whether it ran at all."""

    available: bool
    database: str
    statement: str
    enable_sqlstate: str | None
    errors: tuple[Mapping[str, Any], ...]
    unavailable_reason: str | None

    @property
    def row_count(self) -> int:
        """How many inspection errors were reported. Zero is a result; absent is not."""
        return len(self.errors)


def _rows_as_text(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Flatten dict rows to normalised single-line strings.

    Byte-identical to ``trappoint_migrate.attest._rows_as_text``: columns sorted by
    name, ``None`` dropped, values whitespace-collapsed, joined by ``" | "``, and empty
    rows omitted.
    """
    out: list[str] = []
    for row in rows:
        joined = " | ".join(
            collapse_whitespace(str(value)) for _, value in sorted(row.items()) if value is not None
        )
        if joined:
            out.append(joined)
    return out


def _part(label: str, rows: Sequence[str]) -> bytes:
    """One labelled, sorted category. Sorted because intra-category order is not stable."""
    body = "\n".join(sorted(rows))
    return label.encode("utf-8") + _LABEL_SEPARATOR + body.encode("utf-8")


def _routine_support(source: SqlSource) -> tuple[bool, bool]:
    """Probe for ``pg_get_triggerdef`` and ``pg_get_functiondef`` (GT-05).

    By catalogue lookup, never by calling the function with a dummy oid: a call that
    errored for the *wrong* reason would be read as absence, and "the feature is
    missing" is a claim this patrol writes into an attested document.
    """
    rows = source.fetch(_ROUTINE_SUPPORT_SQL)
    names = {str(row["proname"]) for row in rows}
    return "pg_get_triggerdef" in names, "pg_get_functiondef" in names


def schema_fingerprint(
    source: SqlSource,
    *,
    schema_prefixes: Sequence[str] = DEFAULT_SCHEMA_PREFIXES,
) -> SchemaFingerprint:
    """Compute the whole-schema fingerprint once.

    The categories are, in order: schemas, types, tables, then — where GT-05 allows —
    triggers and routines. ``SHOW CREATE ALL TABLES`` omits both triggers and routines,
    which is why the ``pg_catalog`` queries are mandatory rather than a nicety: without
    them the merge gate itself would sit outside the digest that exists to detect the
    merge gate being weakened.
    """
    parts: list[bytes] = []
    labels: list[str] = []
    part_digests: dict[str, str] = {}
    row_counts: dict[str, int] = {}

    def add(label: str, rows: Sequence[Mapping[str, Any]]) -> None:
        text = _rows_as_text(rows)
        blob = _part(label, text)
        parts.append(blob)
        labels.append(label)
        part_digests[label] = hashlib.sha256(blob).hexdigest()
        row_counts[label] = len(text)

    for label, statement in _SHOW_STATEMENTS:
        add(label, source.fetch(statement))

    has_triggerdef, has_functiondef = _routine_support(source)

    if has_triggerdef:
        add("triggers", source.fetch(_TRIGGER_SQL))

    if has_functiondef:
        predicate = " OR ".join(["n.nspname LIKE %s"] * len(schema_prefixes))
        statement = f"""
        SELECT p.proname AS name, pg_get_functiondef(p.oid) AS def
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        WHERE {predicate}
        ORDER BY 1
        """  # noqa: S608 - a fixed number of placeholders, never interpolated data
        add("routines", source.fetch(statement, list(schema_prefixes)))

    grade = "strong" if (has_triggerdef and has_functiondef) else "weak"
    return SchemaFingerprint(
        digest=hashlib.sha256(_PART_SEPARATOR.join(parts)).digest(),
        grade=grade,
        parts=tuple(labels),
        part_digests=part_digests,
        row_counts=row_counts,
    )


def stable_schema_fingerprint(
    source: SqlSource,
    *,
    schema_prefixes: Sequence[str] = DEFAULT_SCHEMA_PREFIXES,
) -> tuple[SchemaFingerprint, SchemaFingerprint]:
    """Compute the fingerprint twice and refuse if the two disagree.

    K2 exit criterion 6. Both computations are returned rather than one, because the
    evidence artefact records ``fingerprint_run_1`` and ``fingerprint_run_2``
    separately: stability that is *observed* and written down is a different claim from
    stability that a function asserted and then discarded the working for.

    Raises:
        FingerprintUnstable: the two digests differ.
    """
    first = schema_fingerprint(source, schema_prefixes=schema_prefixes)
    second = schema_fingerprint(source, schema_prefixes=schema_prefixes)
    if first.digest != second.digest:
        moved = sorted(
            label
            for label in set(first.part_digests) | set(second.part_digests)
            if first.part_digests.get(label) != second.part_digests.get(label)
        )
        raise FingerprintUnstable(
            "the schema fingerprint is not stable across two consecutive computations "
            f"({first.hex[:16]}… then {second.hex[:16]}…). Unstable categories: "
            f"{', '.join(moved) or 'none identified'}. The normalisation is insufficient "
            "for this CockroachDB build; a fingerprint that flickers cannot be used as a "
            "drift alarm, because the first false alarm is the last one anybody reads."
        )
    return first, second


def trigger_definitions(source: SqlSource) -> TriggerDefinitions:
    """Capture every non-internal trigger definition, or the coarse fallback (GT-05).

    The fallback is deliberately *worse* and deliberately *labelled*. ``SHOW CREATE
    TABLE`` renders a table's triggers inside its DDL, so the text is still captured,
    but per-trigger granularity is lost: a check that reports ``PASS`` off coarse text
    is making a weaker statement than one that reports ``PASS`` off
    ``pg_get_triggerdef()``, and the attested document says which.
    """
    has_triggerdef, _ = _routine_support(source)
    if has_triggerdef:
        rows = source.fetch(_TRIGGER_DETAIL_SQL)
        return TriggerDefinitions(
            granularity="per_trigger",
            source="pg_get_triggerdef",
            triggers=tuple(dict(row) for row in rows),
        )

    tables = _rows_as_text(source.fetch("SHOW CREATE ALL TABLES"))
    return TriggerDefinitions(
        granularity="coarse",
        source="SHOW CREATE ALL TABLES",
        triggers=tuple({"table_ddl": text} for text in sorted(tables) if "TRIGGER" in text.upper()),
    )


def inspect_database(source: SqlSource, *, database: str, as_of: str = "-10s") -> InspectReport:
    """Run the cluster's own index-consistency inspection and collect its findings.

    Two platform facts shape this, and both are handled rather than hoped past.
    ``INSPECT`` is gated behind ``enable_inspect_command``; the ``SET`` is attempted and
    its outcome recorded, because a build where the variable does not exist is a build
    where the statement is either ungated or absent and the attestation should say
    which. And ``INSPECT`` reports through ``SHOW INSPECT ERRORS`` rather than through
    its own result set, so the errors are read separately.

    ``AS OF SYSTEM TIME '-10s'`` keeps the inspection off the live conflict path.
    Ten seconds is well inside this cluster's measured ``gc.ttlseconds = 4500`` window
    (platform finding F2), so this is one of the few time-travel reads in the repository
    that is safe by a wide margin — and it is *still* a bounded one.

    An unavailable ``INSPECT`` produces ``available = False`` with the SQLSTATE and the
    reason, never an empty error list: zero findings and no inspection must never render
    the same way.
    """
    statement = f"INSPECT DATABASE {database} AS OF SYSTEM TIME '{as_of}'"
    enable = source.try_fetch(INSPECT_ENABLE_STATEMENT)
    ran = source.try_fetch(statement)
    if not ran.ok:
        return InspectReport(
            available=False,
            database=database,
            statement=statement,
            enable_sqlstate=enable.sqlstate,
            errors=(),
            unavailable_reason=(
                f"{ran.sqlstate or 'unknown-sqlstate'}: {ran.message or 'no message'}"
            ),
        )

    errors = source.try_fetch(_SHOW_INSPECT_ERRORS_SQL)
    if not errors.ok:
        return InspectReport(
            available=False,
            database=database,
            statement=statement,
            enable_sqlstate=enable.sqlstate,
            errors=(),
            unavailable_reason=(
                f"INSPECT ran but SHOW INSPECT ERRORS did not: "
                f"{errors.sqlstate or 'unknown-sqlstate'}: {errors.message or 'no message'}. "
                "An inspection whose findings cannot be read is not an inspection."
            ),
        )

    return InspectReport(
        available=True,
        database=database,
        statement=statement,
        enable_sqlstate=enable.sqlstate,
        errors=tuple(dict(row) for row in (errors.rows or ())),
        unavailable_reason=None,
    )


@dataclass(slots=True)
class PsycopgSqlSource:
    """A :class:`SqlSource` over a live ``psycopg`` connection.

    ``psycopg`` is imported inside the methods, never at module scope, so that
    ``import mainline_custody_patrol`` succeeds on a machine with no driver — which is
    the state ``tests/integration/custody/test_k2_exit.py`` checks for K2.6, and the
    state of any machine running only the offline unit tests.

    The connection **must** be in autocommit for :meth:`try_fetch` to be useful: a
    failed statement inside an open transaction aborts it, so a probe that is allowed
    to fail cannot share a transaction with the reads that follow it. This is asserted
    at construction rather than documented and hoped for.
    """

    connection: Any

    def __post_init__(self) -> None:
        """Refuse a connection whose failure mode would poison the probes."""
        if not getattr(self.connection, "autocommit", False):
            raise ValueError(
                "PsycopgSqlSource requires conn.autocommit = True. INSPECT and the "
                "enable_inspect_command SET are probes that are ALLOWED to fail; inside "
                "an open transaction the first failure aborts the transaction and every "
                "later read fails with 25P02, which would be reported as 'the schema "
                "could not be read' when the truth is 'one optional probe was refused'"
            )

    def fetch(self, statement: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Run a read and return dict rows. Database errors propagate, unretried."""
        from psycopg.rows import dict_row

        with self.connection.cursor(row_factory=dict_row) as cur:
            cur.execute(statement, list(params) or None)
            if cur.description is None:
                return []
            return [dict(row) for row in cur.fetchall()]

    def try_fetch(self, statement: str, params: Sequence[Any] = ()) -> FetchOutcome:
        """Run a read that is permitted to be unavailable, capturing the SQLSTATE."""
        import psycopg

        try:
            rows = self.fetch(statement, params)
        except psycopg.Error as exc:
            # Narrow by construction: `psycopg.Error` is the driver's own base class, so
            # this catches database refusals and nothing else. A bug in this module still
            # propagates, which is the distinction `BLE` exists to protect.
            return FetchOutcome(rows=None, sqlstate=exc.sqlstate, message=str(exc).strip()[:400])
        return FetchOutcome(rows=tuple(rows))
