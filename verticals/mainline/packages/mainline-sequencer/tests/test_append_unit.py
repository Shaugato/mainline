# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""CU-2 in one file: what the CAS loop retries, and — the important half — what it does not.

The retry predicate is the most dangerous thirty lines in this package. Four constraints
on ``mainline.ledger_leaf`` raise ``23505`` and they are four different facts; a loop that
absorbed all of them would turn every detected duplicate and every foreign-key refusal
into a silent success. So the tests that matter here are the negative ones:
``test_other_unique_violations_escape_the_cas_loop`` and
``test_an_unnameable_unique_violation_escapes``.

``FakeAlgebra`` is a **stand-in, not an implementation**, and it is used here on purpose:
this file is about sequencing, not about hashing, and a unit test that dragged in the real
RFC 6962 tree would fail for two unrelated reasons. Its Merkle root is deliberately not
RFC 6962. The real ``packages/trappoint-ledger`` tree and link chain ARE exercised, against
a real CockroachDB, in ``tests/integration/custody/test_ledger_append.py`` and
``tests/concurrency/custody/test_sequencer_cas.py``; their correctness is worker 3's
property suite and is not restated anywhere in this domain.
"""

from __future__ import annotations

import base64
import hashlib
import random
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest
from mainline_sequencer import append
from mainline_sequencer.batch import IntakeRow

REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURE_DDL = Path(__file__).resolve().parent / "fixture_ddl.sql"

SITE = "blk-07"
ORIGIN = "mainline.example/site/blk-07"

DRAND = (
    "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971 31088494 "
    "7d045d05caf218eff9f7bafe0acb452b94a8c369d138ce23c4807b4b62ce46c7"
)
NIST = (
    "2.0 2.29255654 "
    "d7a6237ed272c6c48bfa16552709fa2c564448e263906af4ba6a740aacef3cd4"
    "0431e945cdfcfc855f321c14056ac89a94b47b50472cc92aab890ceafa42baad"
)


def checkpoint_inputs() -> append.CheckpointInputs:
    return append.CheckpointInputs(
        origin=ORIGIN,
        payload_ver=1,
        canon_src_sha256=bytes.fromhex(
            "260ed37ddc610f1fb94ddce98998fe4ae5ce883698ad5c7033839cd258dcd659"
        ),
        drand=DRAND,
        nist=NIST,
    )


def rows(count: int) -> tuple[IntakeRow, ...]:
    return tuple(
        IntakeRow(
            entry_id=UUID(int=index + 1),
            site_code=SITE,
            entry_kind="disposition",
            leaf_hash=hashlib.sha256(f"leaf-{index}".encode()).digest(),
            payload_ver=1,
            is_sandbox=False,
            actor="auth0|4f2c",
            actor_kind="human",
        )
        for index in range(count)
    )


# ── Doubles ────────────────────────────────────────────────────────────────────────────


class FakeAlgebra:
    """Stand-in for ``trappoint_ledger``. The Merkle root is deliberately not RFC 6962."""

    def link_hash(self, prev_link_hash: bytes, leaf_hash: bytes) -> bytes:
        return hashlib.sha256(prev_link_hash + leaf_hash).digest()

    def extend(self, existing_leaf_hashes, new_leaf_hashes):
        size = len(existing_leaf_hashes)
        root = hashlib.sha256(b"|".join(new_leaf_hashes) + str(size).encode()).digest()
        nodes = tuple(
            (1, size + i, hashlib.sha256(h).digest()) for i, h in enumerate(new_leaf_hashes)
        )
        return append.TreeDelta(root_hash=root, nodes=nodes)

    def checkpoint_body(self, origin, tree_size, root_hash, extensions) -> str:
        lines = [origin, str(tree_size), base64.b64encode(root_hash).decode("ascii")]
        lines.extend(f"{name}: {value}" for name, value in extensions)
        return "\n".join(lines) + "\n"


class FakeSigner:
    def sign(self, body: bytes) -> bytes:
        return b"DER:" + hashlib.sha256(body).digest()

    def public_key_spki_der(self) -> bytes:
        return b"SPKI"


class FakeUnique(psycopg.errors.UniqueViolation):
    """A ``23505`` whose pgwire constraint field and message are controlled separately.

    Both paths are exercised because CockroachDB's population of the constraint field is
    version-dependent and ``constraint_name_of`` falls back to the message.
    """

    def __init__(self, *, diag_name: str | None, message: str) -> None:
        super().__init__(message)
        self._diag_name = diag_name

    @property
    def diag(self):
        return SimpleNamespace(constraint_name=self._diag_name, sqlstate="23505")


class FakeSerialization(psycopg.errors.SerializationFailure):
    @property
    def diag(self):
        return SimpleNamespace(constraint_name=None, sqlstate="40001")


class FakeCursor:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self.rows: list[tuple] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params=None) -> None:
        self.db.maybe_raise(sql)
        self.db.statements.append((sql, params))
        self.rows = self.db.answer(sql, params)

    def executemany(self, sql: str, seq) -> None:
        self.db.maybe_raise(sql)
        for params in seq:
            self.db.statements.append((sql, params))
        self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    @property
    def rowcount(self) -> int:
        return len(self.rows)


class FakeDb:
    """A scripted connection. Nothing is parsed; answers are keyed on SQL fragments."""

    def __init__(self, *, head=None, already=(), leaf_hashes=(), errors=None) -> None:
        self.head = head
        self.already = list(already)
        self.leaf_hashes = list(leaf_hashes)
        self.errors: dict[str, list[BaseException | None]] = dict(errors or {})
        self.statements: list[tuple[str, object]] = []
        self.transactions = 0

    def maybe_raise(self, sql: str) -> None:
        for marker, queue in self.errors.items():
            if marker in sql and queue:
                failure = queue.pop(0)
                if failure is not None:
                    raise failure

    def answer(self, sql: str, params) -> list[tuple]:
        if "ORDER BY seq DESC" in sql:
            return [self.head] if self.head is not None else []
        if "SELECT leaf_hash" in sql:
            return [(value,) for value in self.leaf_hashes]
        if "entry_id = ANY" in sql:
            wanted = set(params[1])
            return [(e,) for e in self.already if e in wanted]
        return []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield self

    def inserted(self, table: str) -> list[tuple]:
        return [
            params
            for sql, params in self.statements
            if sql.strip().upper().startswith("INSERT") and table in sql
        ]


def run(db: FakeDb, *, batch=None, max_attempts=append.MAX_CAS_ATTEMPTS):
    return append.append_batch(
        db,
        site_code=SITE,
        rows=batch if batch is not None else rows(3),
        signer=FakeSigner(),
        checkpoint=checkpoint_inputs(),
        algebra=FakeAlgebra(),
        batch_id=UUID(int=99),
        max_attempts=max_attempts,
        sleep=lambda _seconds: None,
        rng=random.Random(7),
    )


# ── The happy path, so the negatives below are anchored to something that works ─────────


def test_a_fresh_log_starts_at_seq_zero_with_the_genesis_link() -> None:
    """CU-1: genesis is 32 zero bytes, not NULL.

    Under a nullable ``prev_link_hash`` every genesis row would be distinct to
    ``UNIQUE (site_code, prev_link_hash)`` and the first leaf would be the one position at
    which a fork was permitted.
    """
    db = FakeDb()
    result = run(db)

    leaves = db.inserted("mainline.ledger_leaf")
    assert [params[1] for params in leaves] == [0, 1, 2], "seq must be dense from zero"
    assert leaves[0][4] == append.GENESIS_LINK_HASH
    assert all(params[6] == UUID(int=99) for params in leaves), "batch_id tags every leaf"
    assert result.appended == 3
    assert result.tree_size == 3
    assert result.checkpoint_written is True


def test_the_link_chain_is_continued_from_the_head_never_restarted() -> None:
    head_link = hashlib.sha256(b"an existing head").digest()
    db = FakeDb(
        head=(41, head_link),
        leaf_hashes=[hashlib.sha256(f"old-{i}".encode()).digest() for i in range(42)],
    )

    result = run(db, batch=rows(2))
    leaves = db.inserted("mainline.ledger_leaf")

    assert [params[1] for params in leaves] == [42, 43]
    assert leaves[0][4] == head_link, "the first new leaf claims the observed head"
    assert leaves[1][4] == leaves[0][5], "prev_link_hash[i] == link_hash[i-1]"
    assert result.first_seq == 42


def test_the_checkpoint_carries_the_signed_body_and_both_beacons() -> None:
    db = FakeDb()
    result = run(db)
    (checkpoint,) = db.inserted("mainline.ledger_checkpoint")
    site, tree_size, root, body, beacon, log_sig, canon = checkpoint

    assert (site, tree_size) == (SITE, 3)
    assert root == result.root_hash
    assert log_sig == FakeSigner().sign(body.encode("utf-8"))
    assert body.splitlines()[3].startswith("canon: 1 ")
    assert beacon.obj["drand"]["round"] == 31088494
    assert beacon.obj["nist"]["pulse_index"] == 29255654
    assert len(canon) == 32


# ── The retry set: two constraints, and no more ────────────────────────────────────────


@pytest.mark.parametrize("constraint", sorted(append.CAS_RETRYABLE_CONSTRAINTS))
@pytest.mark.parametrize("in_diag", [True, False])
def test_contention_on_the_two_cas_constraints_is_retried(constraint, in_diag) -> None:
    """``ledger_leaf_pkey`` and ``ledger_linear`` are the ONLY retryable 23505s.

    Both discovery paths are covered: the pgwire constraint field when the server
    populates it, and the driver's message when it does not.
    """
    failure = FakeUnique(
        diag_name=constraint if in_diag else None,
        message=f'duplicate key value violates unique constraint "{constraint}"',
    )
    db = FakeDb(errors={"INSERT INTO mainline.ledger_leaf": [failure]})
    result = run(db)

    assert result.attempts == 2
    assert result.appended == 3
    assert db.transactions == 2, "the whole transaction is retried, never a statement"


def test_other_unique_violations_escape_the_cas_loop() -> None:
    """A 23505 on any other constraint reaches the caller. This is the load-bearing test.

    ``ledger_leaf_entry_unique`` means "this entry was already sequenced", which is a
    different fact from "somebody else got this position". Retrying it would turn a
    detected duplicate into a silent one, and the single legitimate retry in this
    repository would become a laundry for real refusals.
    """
    failure = FakeUnique(
        diag_name=append.IDEMPOTENCE_CONSTRAINT,
        message=f'duplicate key value violates unique constraint "{append.IDEMPOTENCE_CONSTRAINT}"',
    )
    db = FakeDb(errors={"INSERT INTO mainline.ledger_leaf": [failure]})

    with pytest.raises(psycopg.errors.UniqueViolation):
        run(db)
    assert db.transactions == 1, "it must not have been attempted twice"


def test_a_node_pkey_violation_escapes() -> None:
    """A settled interior hash written twice with different content is not contention."""
    failure = FakeUnique(
        diag_name="ledger_node_pkey",
        message='duplicate key value violates unique constraint "ledger_node_pkey"',
    )
    db = FakeDb(errors={"INSERT INTO mainline.ledger_node": [failure]})
    with pytest.raises(psycopg.errors.UniqueViolation):
        run(db)


def test_an_unnameable_unique_violation_escapes() -> None:
    """A retry keyed on an absent constraint name is a blanket retry in disguise."""
    failure = FakeUnique(diag_name=None, message="duplicate key value violates a unique constraint")
    assert append.constraint_name_of(failure) is None
    db = FakeDb(errors={"INSERT INTO mainline.ledger_leaf": [failure]})
    with pytest.raises(psycopg.errors.UniqueViolation):
        run(db)


def test_a_foreign_key_refusal_is_never_retried() -> None:
    """23503 on ``fk_intake`` is a leaf for an entry that does not exist, or for another site."""
    db = FakeDb(
        errors={
            "INSERT INTO mainline.ledger_leaf": [
                psycopg.errors.ForeignKeyViolation("insert violates foreign key constraint")
            ]
        }
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        run(db)
    assert db.transactions == 1


def test_serialization_failures_are_retried_within_the_bound() -> None:
    db = FakeDb(
        errors={"INSERT INTO mainline.ledger_leaf": [FakeSerialization("restart transaction")]}
    )
    assert run(db).attempts == 2


def test_the_loop_is_bounded_and_says_so_when_it_gives_up() -> None:
    contention = [
        FakeUnique(
            diag_name="ledger_leaf_pkey",
            message='duplicate key value violates unique constraint "ledger_leaf_pkey"',
        )
        for _ in range(append.MAX_CAS_ATTEMPTS)
    ]
    db = FakeDb(errors={"INSERT INTO mainline.ledger_leaf": contention})

    with pytest.raises(append.CasExhausted) as caught:
        run(db)
    message = str(caught.value)
    assert "was NOT appended" in message
    assert "two sequencers running" in message
    assert db.transactions == append.MAX_CAS_ATTEMPTS


def test_the_backoff_is_not_slept_after_the_final_attempt() -> None:
    slept: list[float] = []
    contention = [
        FakeUnique(
            diag_name="ledger_linear",
            message='duplicate key value violates unique constraint "ledger_linear"',
        )
        for _ in range(3)
    ]
    db = FakeDb(errors={"INSERT INTO mainline.ledger_leaf": contention})
    with pytest.raises(append.CasExhausted):
        append.append_batch(
            db,
            site_code=SITE,
            rows=rows(1),
            signer=FakeSigner(),
            checkpoint=checkpoint_inputs(),
            algebra=FakeAlgebra(),
            max_attempts=3,
            sleep=slept.append,
            rng=random.Random(1),
        )
    assert len(slept) == 2, "three attempts, two gaps"


# ── Idempotence ────────────────────────────────────────────────────────────────────────


def test_replaying_a_batch_writes_nothing_at_all() -> None:
    """Not even a checkpoint.

    ``ledger_checkpoint_pkey`` is ``(site_code, tree_size)``, so a second checkpoint at an
    unchanged size is either a duplicate or attack A7 (``checkpoint_swap``) — and the
    append path must not be the code that decides which.
    """
    batch = rows(3)
    db = FakeDb(
        head=(2, bytes(32)),
        leaf_hashes=[bytes(32)] * 3,
        already=[row.entry_id for row in batch],
    )
    result = run(db, batch=batch)

    assert result.appended == 0
    assert result.already_sequenced == 3
    assert result.checkpoint_written is False
    assert db.inserted("mainline.ledger_leaf") == []
    assert db.inserted("mainline.ledger_checkpoint") == []
    assert result.tree_size == 3


def test_a_partially_replayed_batch_appends_only_what_is_new() -> None:
    batch = rows(4)
    db = FakeDb(already=[batch[0].entry_id, batch[2].entry_id])
    result = run(db, batch=batch)

    appended = [params[2] for params in db.inserted("mainline.ledger_leaf")]
    assert appended == [batch[1].entry_id, batch[3].entry_id]
    assert result.appended == 2
    assert result.already_sequenced == 2


# ── Pure pieces ────────────────────────────────────────────────────────────────────────


def test_constraint_name_prefers_the_pgwire_field_over_the_message() -> None:
    exc = FakeUnique(
        diag_name="ledger_linear",
        message='duplicate key value violates unique constraint "something_else"',
    )
    assert append.constraint_name_of(exc) == "ledger_linear"


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("origin", "has a space/site/x", "space"),
        ("origin", "", "empty"),
        ("payload_ver", 0, "payload_ver"),
        ("canon_src_sha256", b"short", "not 32"),
        ("drand", "not a beacon", "drand:"),
        ("nist", "1.0 2.3 " + "a" * 128, "nist:"),
    ],
)
def test_a_checkpoint_a_stranger_could_not_verify_is_refused_before_any_write(
    field, value, fragment
) -> None:
    kwargs = {
        "origin": ORIGIN,
        "payload_ver": 1,
        "canon_src_sha256": bytes(32),
        "drand": DRAND,
        "nist": NIST,
        field: value,
    }
    with pytest.raises(append.CheckpointIncomplete, match=fragment):
        append.CheckpointInputs(**kwargs)


def test_the_extension_lines_are_in_the_order_the_wire_format_fixes() -> None:
    names = [name for name, _ in checkpoint_inputs().extensions()]
    assert names == ["canon", "drand", "nist"]


def test_the_beacon_column_is_derived_from_the_same_strings_as_the_signed_lines() -> None:
    """The JSONB column and the signed note cannot disagree about which round was quoted."""
    inputs = checkpoint_inputs()
    parsed = inputs.beacon_json()
    drand_line = dict(inputs.extensions())["drand"]
    assert str(parsed["drand"]["round"]) in drand_line
    assert parsed["drand"]["randomness"] in drand_line
    assert parsed["nist"]["output_value"] in dict(inputs.extensions())["nist"]


def test_default_algebra_names_what_is_missing_rather_than_degrading() -> None:
    """No silent fallback, and no re-implementation of an evidentiary hash."""
    try:
        algebra = append.default_algebra()
    except append.LedgerAlgebraUnavailable as exc:
        message = str(exc)
        assert "trappoint_ledger." in message, "the failure must NAME the missing symbol"
        assert any(
            symbol in message
            for symbol in ("chain.link_hash", "merkle.tree.MerkleTree", "checkpoint.build_body")
        )
    else:
        for operation in ("link_hash", "extend", "checkpoint_body"):
            assert callable(getattr(algebra, operation))


# ── The fixture is a reduction, and the reduction is guarded ────────────────────────────


def _table_block(text: str, qualified_name: str) -> str:
    """The DDL body of one table, with `--` comments removed.

    Comments are stripped first because the migrations carry inline rationale — `Derived
    in-txn (CU-2); never a sequence` — and a naive search for the statement terminator
    stops inside it, silently returning a block with no constraints in it and a guard
    that asserts nothing.
    """
    stripped = "\n".join(line.split("--")[0] for line in text.splitlines())
    marker = f"CREATE TABLE {qualified_name} ("
    start = stripped.index(marker)
    return stripped[start : stripped.index("\n);", start)]


def _constraint_names(block: str) -> set[str]:
    return set(re.findall(r"CONSTRAINT\s+([a-z_]+)", block))


@pytest.mark.parametrize(
    ("migration", "table"),
    [
        ("0072_ledger_intake.sql", "mainline.ledger_intake"),
        ("0073_ledger_leaf.sql", "mainline.ledger_leaf"),
        ("0074_ledger_node.sql", "mainline.ledger_node"),
        ("0075_ledger_checkpoint.sql", "mainline.ledger_checkpoint"),
        ("0079_sequencer_lease.sql", "mainline_ops.sequencer_lease"),
    ],
)
def test_fixture_names_the_same_constraints_as_the_migration(migration, table) -> None:
    """The fixture DDL may be a reduction; it may not drift on constraint NAMES.

    CU-2's retry predicate matches on constraint name, so ``ledger_leaf_pkey`` and
    ``ledger_linear`` are an interface and renaming one is a breaking change to
    ``mainline_sequencer.append``. A fixture that had drifted would let this package's
    tests pass against names the database does not use.
    """
    path = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations" / migration
    if not path.is_file():  # pragma: no cover - the migrations are committed
        pytest.skip(f"SKIP(no-migration): {path} is absent, so the fixture cannot be diffed")
    authoritative = _constraint_names(_table_block(path.read_text(encoding="utf-8"), table))
    reduced = _constraint_names(_table_block(FIXTURE_DDL.read_text(encoding="utf-8"), table))
    assert authoritative == reduced, (
        f"{table}: the fixture and migration {migration} disagree on constraint names; "
        f"only in migration {sorted(authoritative - reduced)}, "
        f"only in fixture {sorted(reduced - authoritative)}"
    )


def test_the_constraint_names_the_retry_predicate_uses_exist_in_the_migration() -> None:
    path = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations" / "0073_ledger_leaf.sql"
    if not path.is_file():  # pragma: no cover
        pytest.skip("SKIP(no-migration): 0073_ledger_leaf.sql is absent")
    block = _table_block(path.read_text(encoding="utf-8"), "mainline.ledger_leaf")
    names = _constraint_names(block)
    assert names >= append.CAS_RETRYABLE_CONSTRAINTS
    assert append.IDEMPOTENCE_CONSTRAINT in names
    assert append.IDEMPOTENCE_CONSTRAINT not in append.CAS_RETRYABLE_CONSTRAINTS
