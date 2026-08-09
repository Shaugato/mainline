# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Custody of the custodian, end to end: eight kinds, one Object-Locked object, one leaf.

What this file is for, in one sentence: **an unrun custodian patrol must never be
reportable as a clean one**, and every assertion below is that sentence in a different
place.

The suite is in three layers, deliberately, because they fail for different reasons and
a reader needs to know which one broke.

1. **Schema agreement, no cluster.** The ``kind`` vocabulary in the Python and the
   ``kind_known`` CHECK in migration ``0078`` are read out of the two files and compared.
   The vocabulary is closed precisely because every value is produced by one program in
   this repository — adding a kind means adding a collector, and a collector nobody wrote
   a migration for is a collector nobody reviewed — so the duplication has to be
   mechanically prevented from drifting.
2. **The whole patrol, with fakes.** Eight collectors, an in-memory Object Lock that
   asserts the exact call shape the live path will make (``COMPLIANCE``, a retention
   date in the future, a store that reports back its own digest), and a recording ledger
   sink. This layer runs everywhere and is where the ordering guarantee —
   *object before row* — is proven.
3. **The live cluster.** Skips with a stated reason when no DSN is set. It proves the
   two things that only a real ``SHOW CREATE ALL …`` can: that the fingerprint is stable
   across two consecutive computations against a real schema (K2 exit criterion 6), and
   that ``mainline.custodian_attestation`` genuinely refuses a malformed attestation
   rather than merely being documented to.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_0078 = REPO_ROOT / "verticals/mainline/db/migrations/0078_custodian_attestation.sql"
PATROL_ROOT = REPO_ROOT / "verticals/mainline/packages/mainline-custody-patrol"
FIXTURES = PATROL_ROOT / "tests" / "fixtures"

for _source_root in (
    PATROL_ROOT / "src",
    REPO_ROOT / "packages" / "trappoint-jcs" / "src",
    REPO_ROOT / "packages" / "trappoint-migrate" / "src",
):
    if _source_root.is_dir() and str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from mainline_custody_patrol import (  # noqa: E402
    ATTESTATION_KINDS,
    COMPLIANCE,
    INSERT_CUSTODIAN_ATTESTATION_SQL,
    LEDGER_ENTRY_KIND,
    CollectionRefused,
    CustodyPatrol,
    FixtureCcloud,
    FixtureCloudControlPlane,
    InMemoryObjectStore,
    ObjectStoreRefused,
    k2_migration_attestation,
    stable_schema_fingerprint,
)
from mainline_custody_patrol.fingerprint import FetchOutcome  # noqa: E402

from trappoint_jcs import canonicalise_payload  # noqa: E402

WINDOW_FROM = datetime(2026, 8, 9, 13, 0, 0, tzinfo=UTC)
WINDOW_TO = datetime(2026, 8, 9, 13, 15, 0, tzinfo=UTC)

DSN_ENV_NAMES = ("MAINLINE_TEST_DSN", "TRAPPOINT_DSN", "COCKROACH_URL", "CRDB_URL")


# =======================================================================================
# 1 — the vocabulary is one vocabulary
# =======================================================================================


def _kinds_in_migration() -> tuple[str, ...]:
    text = MIGRATION_0078.read_text(encoding="utf-8")
    body = text[text.index("CREATE TABLE") :]
    match = re.search(r"CONSTRAINT kind_known CHECK \(kind IN \((.*?)\)\)", body, re.DOTALL)
    assert match, "0078 no longer carries a `kind_known` CHECK in the shape this test reads"
    # `[a-z0-9_]`, not `[a-z_]`: `s3_object_lock` carries a digit, and a regex that
    # silently dropped it would let the two vocabularies diverge by exactly one kind —
    # which is what this test caught the first time it ran.
    return tuple(re.findall(r"'([a-z0-9_]+)'", match.group(1)))


def test_the_python_kind_vocabulary_is_the_migrations_kind_vocabulary():
    assert set(ATTESTATION_KINDS) == set(_kinds_in_migration())
    assert len(ATTESTATION_KINDS) == 8


def test_the_insert_names_only_columns_the_table_has():
    ddl = MIGRATION_0078.read_text(encoding="utf-8")
    columns = re.search(r"\(\s*(.*?)\)\s*;\s*$", ddl[ddl.index("CREATE TABLE") :], re.DOTALL)
    assert columns
    named = re.search(r"\((.*?)\)", INSERT_CUSTODIAN_ATTESTATION_SQL, re.DOTALL)
    assert named
    for column in (name.strip() for name in named.group(1).split(",")):
        assert re.search(rf"^\s+{column}\s", columns.group(1), re.MULTILINE), (
            f"the INSERT names `{column}`, which migration 0078 does not declare"
        )


# =======================================================================================
# 2 — the whole patrol, with fakes that assert the shape of the live call
# =======================================================================================


class RecordingSink:
    """A ledger sink that remembers. `emit` never raises; that is the Protocol's contract."""

    def __init__(self) -> None:
        self.events: list[tuple[str, UUID, Mapping[str, Any]]] = []

    def emit(self, kind: str, subject_id: UUID, payload: Mapping[str, Any]) -> object:
        self.events.append((kind, subject_id, dict(payload)))
        return None


class ScriptedSql:
    """A cluster that answers the three SQL-shaped collectors and nothing else."""

    ROWS: ClassVar[dict[str, list[dict[str, Any]]]] = {
        "SHOW CREATE ALL SCHEMAS": [{"create_statement": "CREATE SCHEMA mainline"}],
        "SHOW CREATE ALL TYPES": [{"create_statement": "CREATE TYPE mainline.t AS ENUM ('a')"}],
        "SHOW CREATE ALL TABLES": [
            {"create_statement": "CREATE TABLE mainline.permit ()"},
            {"create_statement": "CREATE TABLE mainline.custodian_attestation ()"},
        ],
    }

    def fetch(self, statement: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        normalised = " ".join(statement.split())
        if normalised in self.ROWS:
            return list(self.ROWS[normalised])
        if "proname IN" in normalised:
            return [{"proname": "pg_get_triggerdef"}, {"proname": "pg_get_functiondef"}]
        if "pg_get_triggerdef" in normalised:
            return [
                {
                    "trigger_name": "trg_permit_merge_gate",
                    "table_name": "permit",
                    "schema_name": "mainline",
                    "enabled": "O",
                    "definition": "CREATE TRIGGER trg_permit_merge_gate BEFORE UPDATE ...",
                    "name": "trg_permit_merge_gate",
                    "def": "CREATE TRIGGER trg_permit_merge_gate BEFORE UPDATE ...",
                }
            ]
        if "pg_get_functiondef" in normalised:
            assert list(params), "the routine query must be parameterised, never interpolated"
            return [{"name": "fn_permit_merge_gate", "def": "CREATE FUNCTION ..."}]
        raise AssertionError(f"unexpected statement: {normalised}")

    def try_fetch(self, statement: str, params: Sequence[Any] = ()) -> FetchOutcome:
        if "enable_inspect_command" in statement or statement.startswith("INSPECT DATABASE"):
            return FetchOutcome(rows=())
        if statement == "SHOW INSPECT ERRORS":
            return FetchOutcome(rows=())
        return FetchOutcome(rows=tuple(self.fetch(statement, params)))


def _patrol(**overrides: Any) -> tuple[CustodyPatrol, InMemoryObjectStore, RecordingSink]:
    store = InMemoryObjectStore(clock=lambda: WINDOW_TO)
    sink = RecordingSink()
    kwargs: dict[str, Any] = {
        "object_store": store,
        "clock": lambda: WINDOW_TO,
        "site_code": "SITE-TEST",
        "sink": sink,
        "sql": ScriptedSql(),
        "ccloud": FixtureCcloud(FIXTURES),
        "ccloud_source": f"fixtures:{FIXTURES}",
        "cloud": FixtureCloudControlPlane(FIXTURES),
        "cluster_id": "cl-custody-fixture",
        "kms_key_id": "arn:aws:kms:ap-southeast-2:000000000000:key/mainline-log",
        "evidence_bucket": "mainline-custody-site-test",
    }
    kwargs.update(overrides)
    return CustodyPatrol(**kwargs), store, sink


def test_all_eight_kinds_are_attested_stored_and_folded_into_the_ledger():
    patrol, store, sink = _patrol()

    run = patrol.run(window_from=WINDOW_FROM, window_to=WINDOW_TO)

    assert run.refusals == (), "\n".join(run.summary_lines())
    assert run.complete is True
    assert {a.kind for a in run.attestations} == set(ATTESTATION_KINDS)
    assert len(store.objects) == 8
    assert [kind for kind, _, _ in sink.events] == [LEDGER_ENTRY_KIND] * 8


def test_the_object_leaves_our_reach_under_compliance_before_the_row_names_it():
    patrol, store, _ = _patrol()
    run = patrol.run(window_from=WINDOW_FROM, window_to=WINDOW_TO)

    for call in store.calls:
        assert call["object_lock_mode"] == COMPLIANCE
        # Seven years, and the fake refuses a retention that is not in the future — the
        # property that makes the object indelible rather than merely stored.
        assert call["retain_until"] > WINDOW_TO + timedelta(days=365 * 6)

    for attestation in run.attestations:
        stored = store.objects[attestation.payload_object_key]
        assert stored == attestation.canon_bytes
        assert attestation.payload_object_key.startswith(f"custodian/{attestation.kind}/")


def test_the_row_digest_is_the_digest_of_the_object_the_row_names():
    import hashlib

    patrol, store, _ = _patrol()
    run = patrol.run(window_from=WINDOW_FROM, window_to=WINDOW_TO)

    for attestation in run.attestations:
        body = store.objects[attestation.payload_object_key]
        assert hashlib.sha256(body).digest() == attestation.payload_sha256
        # A row that named an object whose contents we could not vouch for would be a
        # citation to evidence rather than evidence.
        assert len(attestation.payload_sha256) == 32


def test_no_leaf_payload_carries_a_float():
    patrol, _, sink = _patrol()
    patrol.run(window_from=WINDOW_FROM, window_to=WINDOW_TO)

    for _kind, _subject, payload in sink.events:
        # CU-5: `canonicalise_payload` raises NonEvidentiaryNumber on any float. The
        # foreign document may contain one — CockroachDB Cloud and AWS wrote it — but the
        # bytes the Merkle leaf is taken over may not.
        canonicalise_payload(payload)
        assert payload["payload_ver"] == 1
        assert len(payload["payload_sha256"]) == 64


def test_the_window_shape_matches_what_the_kind_actually_covers():
    patrol, _, _ = _patrol()
    run = patrol.run(window_from=WINDOW_FROM, window_to=WINDOW_TO)
    by_kind = {a.kind: a for a in run.attestations}

    # Stream-shaped: a period, and a count.
    assert by_kind["ccloud_audit"].window_from == WINDOW_FROM
    assert by_kind["ccloud_audit"].window_to == WINDOW_TO
    assert by_kind["ccloud_audit"].row_count == 3
    assert by_kind["ccloud_backup"].row_count == 2

    # Snapshot-shaped: an instant. `window_ordered` admits `window_from = window_to`
    # deliberately, because inventing an end time for a statement about an instant is
    # exactly the invented value this band refuses everywhere else.
    for kind in ("kms_key_policy", "s3_object_lock", "schema_fingerprint"):
        assert by_kind[kind].window_from == by_kind[kind].window_to
    assert by_kind["kms_key_policy"].row_count is None


def test_subject_ids_are_deterministic_so_a_reference_run_regenerates():
    first, _, _ = _patrol()
    second, _, _ = _patrol()
    a = {x.kind: x.subject_id for x in first.run(window_from=WINDOW_FROM).attestations}
    b = {x.kind: x.subject_id for x in second.run(window_from=WINDOW_FROM).attestations}
    assert a == b


def test_a_missing_ccloud_field_is_a_hard_failure_and_the_run_says_so():
    patrol, _, _ = _patrol(ccloud=FixtureCcloud(FIXTURES / "renamed-field"))

    run = patrol.run(window_from=WINDOW_FROM, window_to=WINDOW_TO)

    audit = [r for r in run.refusals if r.kind == "ccloud_audit"]
    assert audit, "a renamed `entries` member must refuse, never default to zero rows"
    assert "CcloudFieldMissing" in audit[0].reason
    assert run.complete is False
    assert any("INCOMPLETE" in line for line in run.summary_lines())


def test_a_missing_capability_refuses_loudly_and_never_shrinks_the_set():
    patrol, _, _ = _patrol(cloud=None)

    run = patrol.run(window_from=WINDOW_FROM, window_to=WINDOW_TO)

    refused = {r.kind for r in run.refusals}
    assert refused == {"kms_key_policy", "s3_object_lock", "iam_snapshot"}
    assert len(run.attestations) == 5
    assert run.complete is False
    # A refusal is printed as loudly as a success. Seven-of-eight and eight-of-eight must
    # never render the same way.
    summary = "\n".join(run.summary_lines())
    assert summary.count("REFUSED") == 3
    assert "attested: 5/8" in summary


def test_the_evidence_store_refuses_anything_but_compliance():
    store = InMemoryObjectStore(clock=lambda: WINDOW_TO)
    with pytest.raises(ObjectStoreRefused, match="COMPLIANCE"):
        store.put_evidence(
            key="k",
            body=b"{}",
            object_lock_mode="GOVERNANCE",
            retain_until=WINDOW_TO + timedelta(days=1),
        )


def test_the_evidence_store_refuses_an_expired_retention():
    store = InMemoryObjectStore(clock=lambda: WINDOW_TO)
    with pytest.raises(ObjectStoreRefused, match="not in the future"):
        store.put_evidence(
            key="k",
            body=b"{}",
            object_lock_mode=COMPLIANCE,
            retain_until=WINDOW_TO - timedelta(seconds=1),
        )


def test_an_unknown_kind_cannot_be_attested_even_from_inside_the_package():
    patrol, _, _ = _patrol()
    with pytest.raises(CollectionRefused, match="kind vocabulary"):
        patrol._attest(  # the guard is the subject of the test
            kind="ccloud_audit_v2",
            document={"a": 1},
            row_count=None,
            window_from=WINDOW_TO,
            window_to=WINDOW_TO,
            source="test",
        )


# ---------------------------------------------------------------- K2.6, with fakes


class FakeLocator:
    def __init__(self, seq: int | None) -> None:
        self.seq = seq
        self.asked: list[tuple[str, bytes]] = []

    def seq_for_leaf_hash(self, site_code: str, leaf_hash: bytes) -> int | None:
        self.asked.append((site_code, leaf_hash))
        return self.seq


def test_the_k2_artefact_records_two_runs_and_the_leaf_they_entered():
    patrol, _, _ = _patrol()
    locator = FakeLocator(seq=41)

    document = k2_migration_attestation(patrol, at=WINDOW_TO, locator=locator)

    assert document["fingerprint_run_1"] == document["fingerprint_run_2"]
    assert document["chained_leaf_seq"] == 41
    assert document["grade"] == "strong"
    assert locator.asked[0][0] == "SITE-TEST"
    # The artefact must survive a JSON round trip unchanged: it is written to
    # evidence/ and read by the K2 exit test on another machine.
    assert json.loads(json.dumps(document)) == document


def test_an_unsequenced_leaf_refuses_rather_than_writing_a_null():
    patrol, _, _ = _patrol()
    with pytest.raises(CollectionRefused, match="receipt_orphan"):
        k2_migration_attestation(patrol, at=WINDOW_TO, locator=FakeLocator(seq=None))


def test_no_locator_is_a_refusal_because_chained_is_a_fact_about_the_database():
    patrol, _, _ = _patrol()
    with pytest.raises(CollectionRefused, match="LeafLocator"):
        k2_migration_attestation(patrol, at=WINDOW_TO, locator=None)


# =======================================================================================
# 3 — the live cluster. Skips with a reason; never green by absence.
# =======================================================================================


def _dsn() -> str | None:
    for name in DSN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


@pytest.fixture
def cluster() -> Any:
    dsn = _dsn()
    if not dsn:
        pytest.skip(
            "no cluster: set one of " + ", ".join(DSN_ENV_NAMES) + ". For a local "
            "single-node node — `cockroach start-single-node --insecure` — that is "
            "TRAPPOINT_DSN=postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable. "
            "This is a SKIP and not a pass: the schema fingerprint's stability against a "
            "REAL `SHOW CREATE ALL …` is K2 exit criterion 6, and a fake cannot prove it."
        )
    psycopg = pytest.importorskip(
        "psycopg",
        reason="psycopg 3 is required to reach a CockroachDB; `uv sync` installs it",
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


def _table_exists(conn: Any, schema: str, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema, table),
        )
        return cur.fetchone() is not None


@pytest.mark.requires_cluster
def test_the_schema_fingerprint_is_stable_against_a_real_show_create(cluster: Any):
    """K2 exit criterion 6, observed rather than asserted.

    ``SHOW CREATE ALL TABLES`` guarantees CREATE-before-ALTER ordering and nothing else.
    This is the only place the normalisation meets an implementation that is free to
    return its rows in whatever order it likes.
    """
    from mainline_custody_patrol import PsycopgSqlSource

    first, second = stable_schema_fingerprint(PsycopgSqlSource(cluster))

    assert first.digest == second.digest
    assert first.grade in {"strong", "weak"}
    assert set(first.parts) >= {"schemas", "types", "tables"}
    if first.grade == "weak":
        pytest.xfail(
            "GT-05: this cluster exposes neither pg_get_triggerdef nor pg_get_functiondef, "
            "so the fingerprint covers tables only and verifier check 11 must report "
            "PASS(coarse). The fingerprint is still stable — that is what was asserted "
            "above — but the claim it supports is the weaker one."
        )


@pytest.mark.requires_cluster
def test_the_table_refuses_a_malformed_attestation(cluster: Any):
    """The CHECKs on 0078 are load-bearing, so they are exercised rather than trusted."""
    import psycopg

    if not _table_exists(cluster, "mainline", "custodian_attestation"):
        pytest.skip(
            "mainline.custodian_attestation is absent: apply the migrations "
            "(`trappoint migrate up`) before running this lane. Skipping is honest here — "
            "the CHECKs cannot refuse anything if the table does not exist."
        )

    good = (
        "schema_fingerprint",
        WINDOW_FROM,
        WINDOW_TO,
        "custodian/schema_fingerprint/2026/08/09/deadbeef.json",
        bytes(range(32)),
        None,
        WINDOW_TO,
    )
    bad_rows = {
        "kind_known": ("not_a_kind", *good[1:]),
        "window_ordered": (good[0], WINDOW_TO, WINDOW_FROM, *good[3:]),
        "payload_sha256_is_sha256": (*good[:4], bytes(31), *good[5:]),
        "payload_object_key_stated": (*good[:3], "", *good[4:]),
        "row_count_non_negative": (*good[:5], -1, good[6]),
    }

    with cluster.cursor() as cur:
        cur.execute("BEGIN")
        cur.execute(INSERT_CUSTODIAN_ATTESTATION_SQL, good)
        assert cur.fetchone() is not None
        cur.execute("ROLLBACK")

    for constraint, params in bad_rows.items():
        with cluster.cursor() as cur:
            cur.execute("BEGIN")
            with pytest.raises(psycopg.errors.CheckViolation) as caught:
                cur.execute(INSERT_CUSTODIAN_ATTESTATION_SQL, params)
            # MEASURED PLATFORM FACT, 2026-08-10, CockroachDB CCL v26.2.5 (single node,
            # docker, insecure): the CheckViolation MESSAGE renders the predicate, not the
            # constraint name — "failed to satisfy CHECK constraint (window_to >=
            # window_from)". The name is carried in `exc.diag.constraint_name` and only
            # there. Written down because the first version of this test asserted on the
            # message and passed for the wrong reason would have been worse: it would have
            # matched whichever constraint happened to mention the same identifier.
            assert caught.value.sqlstate == "23514"
            assert caught.value.diag.constraint_name == constraint, (
                f"expected {constraint} to refuse this row; the database refused "
                f"{caught.value.diag.constraint_name} instead, which means the row was "
                f"malformed in a way this test did not intend"
            )
            cur.execute("ROLLBACK")


@pytest.mark.requires_cluster
def test_the_ledger_tables_carry_no_row_level_ttl(cluster: Any):
    """Silent expiry of an evidentiary row is document destruction by a scheduler.

    Crimes (Document Destruction) Act 2006 (Vic). The TTL allowlist is exactly three
    tables and no ``ledger_*`` or ``custodian_attestation`` table may become a fourth.
    """
    with cluster.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'mainline'
              AND (table_name LIKE 'ledger%' OR table_name = 'custodian_attestation')
            """
        )
        tables = [row[0] for row in cur.fetchall()]
    if not tables:
        pytest.skip("no ledger tables in this database; apply the migrations first")

    for table in tables:
        with cluster.cursor() as cur:
            # `table` comes from information_schema on the line above, never from a
            # caller and never from a model, so the interpolation is over a catalogue
            # name this connection just read back.
            cur.execute(f"SHOW CREATE TABLE mainline.{table}")
            ddl = " ".join(str(cur.fetchone()[1]).split())
        assert "ttl_expire_after" not in ddl.lower(), f"mainline.{table} carries a row-level TTL"
        assert "ttl_expiration_expression" not in ddl.lower()
