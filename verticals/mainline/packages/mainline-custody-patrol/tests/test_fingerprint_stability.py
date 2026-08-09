# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""K2 exit criterion 6: the schema fingerprint is stable, and it is the runner's.

Two assertions carry this file, and neither is a tautology.

**Stability is tested against a source that genuinely reorders.** ``SHOW CREATE ALL
TABLES`` guarantees CREATE-before-ALTER ordering and nothing else, so the fake here
returns its rows in a *different order on every call* and shuffles the whitespace inside
them. A fingerprint that were computed naively fails this test; the sorted, collapsed
one does not. Asserting stability against a fake that returns identical rows twice would
assert nothing at all.

**The digest is the migration runner's digest, proven offline.**
``trappoint_migrate.attest.fingerprint`` computes the same quantity at apply time. If the
two differed, the drift alarm would compare two different questions and answer neither.
:func:`test_matches_the_migration_runner_byte_for_byte` drives *both* implementations
over one identical row set — through a fake connection, with no cluster — and asserts the
digests are equal.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]

for _source_root in (
    HERE.parent / "src",
    REPO_ROOT / "packages" / "trappoint-jcs" / "src",
    REPO_ROOT / "packages" / "trappoint-migrate" / "src",
):
    if _source_root.is_dir() and str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from mainline_custody_patrol.fingerprint import (  # noqa: E402
    DEFAULT_SCHEMA_PREFIXES,
    FetchOutcome,
    FingerprintUnstable,
    PsycopgSqlSource,
    inspect_database,
    schema_fingerprint,
    stable_schema_fingerprint,
    trigger_definitions,
)

SCHEMAS = [
    {"create_statement": "CREATE SCHEMA mainline"},
    {"create_statement": "CREATE SCHEMA mainline_ops"},
    {"create_statement": "CREATE SCHEMA mainline_meas"},
]
TYPES = [
    {"create_statement": "CREATE TYPE mainline.blame_state AS ENUM ('open','closed')"},
    {"create_statement": "CREATE TYPE mainline.control_delta AS ENUM ('weaken','hold')"},
]
TABLES = [
    {"create_statement": "CREATE TABLE mainline.permit (\n  permit_id UUID NOT NULL\n)"},
    {"create_statement": "CREATE TABLE mainline.ledger_leaf (\n  seq INT8 NOT NULL\n)"},
    {"create_statement": "CREATE TABLE mainline.custodian_attestation (\n  kind STRING\n)"},
]
TRIGGERS = [
    {"name": "trg_permit_merge_gate", "def": "CREATE TRIGGER trg_permit_merge_gate BEFORE UPDATE"},
    {"name": "trg_check_project", "def": "CREATE TRIGGER trg_check_project AFTER INSERT"},
]
ROUTINES = [
    {"name": "fn_permit_merge_gate", "def": "CREATE FUNCTION fn_permit_merge_gate() ..."},
    {"name": "fn_ledger_cas_append", "def": "CREATE FUNCTION fn_ledger_cas_append() ..."},
]
ROUTINE_SUPPORT_BOTH = [{"proname": "pg_get_triggerdef"}, {"proname": "pg_get_functiondef"}]


class ReorderingSqlSource:
    """A fake cluster that answers correctly and never in the same order twice.

    This is the adversary the normalisation exists for. It also mangles the *internal*
    whitespace of each statement on every call, because ``SHOW CREATE`` formatting is
    not stable across CockroachDB versions either, and a fingerprint that changed when a
    formatter changed would be an alarm nobody reads.
    """

    def __init__(
        self,
        *,
        tables: list[dict[str, Any]] | None = None,
        routine_support: list[dict[str, Any]] | None = None,
    ) -> None:
        self.tables = list(TABLES if tables is None else tables)
        self.routine_support = (
            ROUTINE_SUPPORT_BOTH if routine_support is None else list(routine_support)
        )
        self.calls = 0
        self.statements: list[str] = []
        # PER-STATEMENT counters, not one global counter. A single counter advances by the
        # same amount on every run, so `counter % len(rows)` would land on the SAME
        # rotation each time and the fake would quietly stop reordering — which would make
        # the stability test pass against an implementation that does not sort. Observed:
        # with one counter, deleting `sorted()` from `_part` leaves this file green.
        self.per_statement: dict[str, int] = {}

    def _spin(self, key: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        nth = self.per_statement[key]
        offset = nth % len(rows)
        rotated = rows[offset:] + rows[:offset]
        if nth % 3 == 2:
            rotated = list(reversed(rotated))
        return [
            {
                key_: ("  ".join(str(value).split()) if nth % 2 else str(value))
                for key_, value in row.items()
            }
            for row in rotated
        ]

    def fetch(self, statement: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        self.statements.append(statement.strip())
        self.calls += 1
        normalised = " ".join(statement.split())
        self.per_statement[normalised] = self.per_statement.get(normalised, 0) + 1
        if normalised == "SHOW CREATE ALL SCHEMAS":
            return self._spin(normalised, SCHEMAS)
        if normalised == "SHOW CREATE ALL TYPES":
            return self._spin(normalised, TYPES)
        if normalised == "SHOW CREATE ALL TABLES":
            return self._spin(normalised, self.tables)
        if "pg_get_triggerdef" in normalised and "pg_proc" not in normalised:
            return self._spin(normalised, TRIGGERS)
        if "pg_get_functiondef" in normalised and "pg_proc p" in normalised:
            assert list(params) == list(DEFAULT_SCHEMA_PREFIXES)
            return self._spin(normalised, ROUTINES)
        if "proname IN" in normalised:
            return list(self.routine_support)
        raise AssertionError(f"unexpected statement: {normalised}")

    def try_fetch(self, statement: str, params: Sequence[Any] = ()) -> FetchOutcome:
        return FetchOutcome(rows=tuple(self.fetch(statement, params)))


class DriftingSqlSource(ReorderingSqlSource):
    """A cluster whose schema genuinely changes between two reads."""

    def fetch(self, statement: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        rows = super().fetch(statement, params)
        if " ".join(statement.split()) == "SHOW CREATE ALL TABLES":
            self.tables = [*self.tables, {"create_statement": f"CREATE TABLE t{self.calls} ()"}]
        return rows


class ProbeRefusingSqlSource(ReorderingSqlSource):
    """A cluster where ``INSPECT`` is not available, reported with its SQLSTATE."""

    def try_fetch(self, statement: str, params: Sequence[Any] = ()) -> FetchOutcome:
        if "INSPECT" in statement or "enable_inspect_command" in statement:
            return FetchOutcome(
                rows=None, sqlstate="0A000", message="unimplemented: INSPECT is not supported"
            )
        return FetchOutcome(rows=tuple(self.fetch(statement, params)))


# ----------------------------------------------------------------------- stability


def test_the_fingerprint_is_stable_against_a_source_that_reorders_every_call():
    source = ReorderingSqlSource()
    first, second = stable_schema_fingerprint(source)

    assert first.digest == second.digest
    assert first.grade == "strong"
    assert first.parts == ("schemas", "types", "tables", "triggers", "routines")
    # Proof the fake actually did reorder: ten reads happened across the two runs.
    assert source.calls >= 10


def test_stability_is_asserted_not_assumed_and_names_the_category_that_moved():
    with pytest.raises(FingerprintUnstable) as caught:
        stable_schema_fingerprint(DriftingSqlSource())

    message = str(caught.value)
    assert "not stable across two consecutive computations" in message
    assert "tables" in message


def test_a_real_change_moves_the_digest_and_only_the_category_it_touched():
    baseline = schema_fingerprint(ReorderingSqlSource())
    changed = schema_fingerprint(
        ReorderingSqlSource(
            tables=[*TABLES, {"create_statement": "CREATE TABLE mainline.new_table ()"}]
        )
    )

    assert baseline.digest != changed.digest
    assert baseline.part_digests["tables"] != changed.part_digests["tables"]
    assert baseline.part_digests["schemas"] == changed.part_digests["schemas"]
    assert baseline.part_digests["triggers"] == changed.part_digests["triggers"]


def test_the_grade_softens_in_the_data_when_gt05_is_unavailable():
    source = ReorderingSqlSource(routine_support=[])
    computed = schema_fingerprint(source)

    assert computed.grade == "weak"
    assert computed.parts == ("schemas", "types", "tables")
    # A weak attestation must never be indistinguishable from a strong one, which is why
    # the grade travels with the digest instead of being decided by the reader.
    assert "triggers" not in computed.part_digests


# ------------------------------------------------- one answer, not two: the runner


def test_matches_the_migration_runner_byte_for_byte():
    """The patrol's digest and ``trappoint migrate``'s digest are the same number.

    Driven through a fake ``psycopg`` connection so the equality is provable with no
    cluster, no driver behaviour and no credentials. If this ever fails, the drift alarm
    has silently started comparing two different questions.
    """
    attest = pytest.importorskip(
        "trappoint_migrate.attest",
        reason=(
            "trappoint_migrate is not importable (it needs psycopg), so the patrol's "
            "fingerprint cannot be compared with the migration runner's. This is a SKIP "
            "and not a pass: without it, nothing proves the two agree."
        ),
    )
    runner = pytest.importorskip("trappoint_migrate.runner")

    rows_for = {
        "SHOW CREATE ALL SCHEMAS": SCHEMAS,
        "SHOW CREATE ALL TYPES": TYPES,
        "SHOW CREATE ALL TABLES": TABLES,
    }

    class FakeCursor:
        def __init__(self, statement: str, params: Any) -> None:
            self.statement = " ".join(statement.split())
            self.params = params

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, statement: str, params: Any = None) -> None:
            self.statement = " ".join(statement.split())
            self.params = params

        def fetchall(self) -> list[dict[str, Any]]:
            if self.statement in rows_for:
                return list(rows_for[self.statement])
            if "proname IN" in self.statement:
                return list(ROUTINE_SUPPORT_BOTH)
            if "pg_get_triggerdef" in self.statement and "pg_proc p" not in self.statement:
                return list(TRIGGERS)
            if "pg_get_functiondef" in self.statement:
                return list(ROUTINES)
            raise AssertionError(f"unexpected statement: {self.statement}")

    class FakeConnection:
        def cursor(self, **_: Any) -> FakeCursor:
            return FakeCursor("", None)

    class StableOrderSource:
        def fetch(self, statement: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
            normalised = " ".join(statement.split())
            if normalised in rows_for:
                return list(rows_for[normalised])
            if "proname IN" in normalised:
                return list(ROUTINE_SUPPORT_BOTH)
            if "pg_get_triggerdef" in normalised and "pg_proc p" not in normalised:
                return list(TRIGGERS)
            if "pg_get_functiondef" in normalised:
                assert list(params) == list(DEFAULT_SCHEMA_PREFIXES)
                return list(ROUTINES)
            raise AssertionError(f"unexpected statement: {normalised}")

        def try_fetch(self, statement: str, params: Sequence[Any] = ()) -> FetchOutcome:
            return FetchOutcome(rows=tuple(self.fetch(statement, params)))

    # The schema selection must match too: two different selections make the comparison
    # meaningless even when the assembly agrees.
    assert tuple(DEFAULT_SCHEMA_PREFIXES) == tuple(runner.DEFAULT_SCHEMA_PREFIXES)

    theirs = attest.fingerprint(FakeConnection(), schema_prefixes=DEFAULT_SCHEMA_PREFIXES)
    ours = schema_fingerprint(StableOrderSource(), schema_prefixes=DEFAULT_SCHEMA_PREFIXES)

    assert ours.digest == theirs.digest
    assert ours.grade == theirs.grade
    assert ours.parts == theirs.parts


# ------------------------------------------------------------ triggers and INSPECT


def test_trigger_definitions_are_per_trigger_when_gt05_holds():
    captured = trigger_definitions(ReorderingSqlSource())
    assert captured.granularity == "per_trigger"
    assert captured.source == "pg_get_triggerdef"
    assert captured.row_count == len(TRIGGERS)


def test_the_coarse_fallback_is_labelled_rather_than_silently_weaker():
    source = ReorderingSqlSource(
        routine_support=[],
        tables=[
            {"create_statement": "CREATE TABLE mainline.permit (); CREATE TRIGGER trg_x ..."},
            {"create_statement": "CREATE TABLE mainline.site ()"},
        ],
    )
    captured = trigger_definitions(source)

    # The claim softens IN THE SAME ARTEFACT: check 11 reads `granularity` and reports
    # PASS(coarse) rather than keeping its stronger wording.
    assert captured.granularity == "coarse"
    assert captured.source == "SHOW CREATE ALL TABLES"
    assert captured.row_count == 1


def test_an_unavailable_inspect_reports_why_and_not_zero_findings():
    report = inspect_database(ProbeRefusingSqlSource(), database="mainline")

    assert report.available is False
    assert report.row_count == 0
    assert report.unavailable_reason is not None
    assert "0A000" in report.unavailable_reason
    # Zero findings and no inspection must never render the same way.
    assert report.errors == ()


def test_inspect_collects_findings_when_the_cluster_supports_it():
    class InspectingSource(ReorderingSqlSource):
        def try_fetch(self, statement: str, params: Sequence[Any] = ()) -> FetchOutcome:
            if "enable_inspect_command" in statement:
                return FetchOutcome(rows=())
            if statement.startswith("INSPECT DATABASE"):
                return FetchOutcome(rows=())
            if statement == "SHOW INSPECT ERRORS":
                return FetchOutcome(rows=({"job_id": 1, "error_type": "missing_secondary_index"},))
            return FetchOutcome(rows=tuple(self.fetch(statement, params)))

    report = inspect_database(InspectingSource(), database="mainline")

    assert report.available is True
    assert report.row_count == 1
    assert "AS OF SYSTEM TIME '-10s'" in report.statement


# ------------------------------------------------------------------ driver adapter


def test_the_psycopg_adapter_refuses_a_connection_that_would_poison_its_probes():
    class NotAutocommit:
        autocommit = False

    with pytest.raises(ValueError, match="autocommit"):
        PsycopgSqlSource(NotAutocommit())
