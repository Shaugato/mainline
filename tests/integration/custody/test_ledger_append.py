# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The append against a real CockroachDB: idempotence, and CU-1's linearity refusal.

Two properties here are *database* properties and no in-process double can stand in for
either: replaying a batch inserts nothing new because ``ledger_leaf_entry_unique`` says
so, and a forged ``prev_link_hash`` is refused by ``ledger_linear`` — the constraint that
gives the append **refusal depth 2** and makes a fork physically impossible rather than
merely unlikely.

The lane refuses any DSN whose host is not ``localhost``/``127.0.0.1``. It writes to a
throwaway database and it is the sequencer's own suite, so it is a milder version of the
nemesis harness's problem: a test that can reach production is itself an attack surface.

Nothing here is green by absence. When no cluster can be found the lane skips with a
message naming which of the three discovery routes was missing, and a skipped run proves
nothing — which is exactly what the message says.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest
from trappoint_testkit import pinned_image

REPO_ROOT = Path(__file__).resolve().parents[3]
SEQUENCER = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-sequencer"
FIXTURE_DDL = SEQUENCER / "tests" / "fixture_ddl.sql"

for _source_root in (
    SEQUENCER / "src",
    REPO_ROOT / "packages" / "trappoint-jcs" / "src",
    REPO_ROOT / "packages" / "trappoint-ledger" / "src",
):
    if _source_root.is_dir() and str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)

from mainline_sequencer import append as append_mod  # noqa: E402
from mainline_sequencer import batch as batch_mod  # noqa: E402
from mainline_sequencer import sink as sink_mod  # noqa: E402

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE") or pinned_image(Path(__file__))
CONTAINER_NAME = "mainline-sequencer-integration"
READY_TIMEOUT_S = 120.0
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "[::1]"})

DRAND = (
    "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971 31088494 "
    "7d045d05caf218eff9f7bafe0acb452b94a8c369d138ce23c4807b4b62ce46c7"
)
NIST = (
    "2.0 2.29255654 "
    "d7a6237ed272c6c48bfa16552709fa2c564448e263906af4ba6a740aacef3cd4"
    "0431e945cdfcfc855f321c14056ac89a94b47b50472cc92aab890ceafa42baad"
)


# ── The algebra: real where it exists, and explicit about where it does not ────────────

trappoint_chain = pytest.importorskip(
    "trappoint_ledger.chain",
    reason="packages/trappoint-ledger (custody worker 3) supplies the link-chain step; the "
    "sequencer does not re-implement it, so this lane cannot run without it",
)
trappoint_tree = pytest.importorskip(
    "trappoint_ledger.merkle.tree",
    reason="packages/trappoint-ledger (custody worker 3) supplies the RFC 6962 tree",
)


class SequencingAlgebra:
    """The real link chain and the real RFC 6962 tree; the note text only if it exists.

    ``trappoint_ledger.chain.link_hash`` and ``trappoint_ledger.merkle.tree.MerkleTree``
    are used as shipped — so every leaf, node and root this lane writes is the real
    thing, and the ``ledger_linear`` and density assertions below are about the real
    chain rather than about a double's arithmetic.

    ``trappoint_ledger.checkpoint.build_body`` (custody worker 4) had not landed when this
    lane was written. Where it is absent the note text is assembled here from
    ``spec/wire/checkpoint.md`` §3 and §4 — three mandatory lines then the extension lines
    — which is string assembly against a frozen specification, not a second implementation
    of anything hashed. **No assertion in this file reads the note text**: the wire format
    has its own conformance vector in that document's §10, which is where it belongs.
    """

    def __init__(self) -> None:
        self._build_body = None
        try:
            from trappoint_ledger.checkpoint import build_body
        except ImportError:
            print("[custody] note text assembled locally: trappoint_ledger.checkpoint absent")
        else:
            self._build_body = build_body

    def link_hash(self, prev_link_hash: bytes, leaf_hash: bytes) -> bytes:
        return trappoint_chain.link_hash(prev_link_hash, leaf_hash)

    def extend(self, existing_leaf_hashes, new_leaf_hashes):
        batch = trappoint_tree.MerkleTree(list(existing_leaf_hashes)).extend(list(new_leaf_hashes))
        return append_mod.TreeDelta(
            root_hash=bytes(batch.root),
            nodes=tuple(
                (int(n.coord.level), int(n.coord.index), bytes(n.digest))
                for n in batch.created_nodes
            ),
        )

    def checkpoint_body(self, origin, tree_size, root_hash, extensions) -> str:
        if self._build_body is not None:
            return self._build_body(origin, tree_size, root_hash, extensions)
        lines = [origin, str(tree_size), base64.b64encode(root_hash).decode("ascii")]
        lines.extend(f"{name}: {value}" for name, value in extensions)
        # The note text ends in U+000A and excludes the separating blank line (§2).
        return "\n".join(lines) + "\n"


class StandInSigner:
    """Not a signature. ``packages/trappoint-ledger`` owns the KMS and local P-256 signers.

    Named so that nothing which reaches the database from this lane can be mistaken for a
    checkpoint signature: ``log_sig`` starts with the ASCII bytes ``NOT-A-SIGNATURE``.
    """

    def sign(self, body: bytes) -> bytes:
        return b"NOT-A-SIGNATURE:" + hashlib.sha256(body).digest()

    def public_key_spki_der(self) -> bytes:
        return b"NOT-A-KEY"


@lru_cache(maxsize=1)
def algebra():
    """The fully-real algebra when it exists; otherwise real parts plus a local note text.

    Cached so the provenance is announced once rather than once per worker thread, and so
    sixteen sequencers share one stateless instance instead of re-importing behind each
    other.
    """
    try:
        return append_mod.default_algebra()
    except append_mod.LedgerAlgebraUnavailable as exc:
        print(f"[custody] partial algebra: {exc}")
        return SequencingAlgebra()


def checkpoint_inputs(site: str) -> append_mod.CheckpointInputs:
    return append_mod.CheckpointInputs(
        origin=f"mainline.example/site/{site}",
        payload_ver=1,
        canon_src_sha256=hashlib.sha256(b"canon_v1 stand-in").digest(),
        drand=DRAND,
        nist=NIST,
    )


# ── Cluster discovery ──────────────────────────────────────────────────────────────────


@dataclass
class Cluster:
    dsn: str
    provenance: str


def refuse_remote(dsn: str) -> None:
    """Refuse any DSN that is not a local, disposable cluster.

    This suite inserts into ``mainline.ledger_*``. A ledger lane that can reach a real
    deployment writes into the evidentiary record from a test runner, which is worse than
    a failing test by every measure that matters here.
    """
    from psycopg.conninfo import conninfo_to_dict

    host = str(conninfo_to_dict(dsn).get("host", "")).strip()
    if host not in LOCAL_HOSTS:
        raise RuntimeError(
            f"refusing to run the ledger append lane against host {host!r}. This suite "
            "writes leaves and checkpoints; it runs against a disposable single-node "
            "CockroachDB on localhost only."
        )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(dsn: str, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
        except psycopg.Error:
            time.sleep(1.0)
        else:
            return True
    return False


def _docker(args: list[str], *, timeout: float):
    try:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _start_docker(name: str) -> Cluster | None:
    if shutil.which("docker") is None:
        return None
    probe = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=10.0)
    if probe is None or probe.returncode != 0:
        return None
    _docker(["rm", "-f", name], timeout=20.0)
    port = _free_port()
    started = _docker(
        [
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"{port}:26257",
            CRDB_IMAGE,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
        ],
        timeout=600.0,
    )
    if started is None or started.returncode != 0:
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on port {port}")
    _docker(["rm", "-f", name], timeout=20.0)
    return None


def _start_local_binary(tmp: Path) -> Cluster | None:
    binary = shutil.which("cockroach")
    if binary is None:
        return None
    port, http_port = _free_port(), _free_port()
    proc = subprocess.Popen(
        [
            binary,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
            f"--listen-addr=127.0.0.1:{port}",
            f"--http-addr=127.0.0.1:{http_port}",
        ],
        cwd=str(tmp),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        found = Cluster(dsn=dsn, provenance=f"local `cockroach` binary on port {port}")
        found.__dict__["_proc"] = proc
        return found
    proc.terminate()
    return None


def discover_cluster(tmp: Path, container: str) -> Cluster:
    for name in ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL"):
        value = os.environ.get(name)
        if value:
            refuse_remote(value)
            return Cluster(dsn=value, provenance=f"${name}")
    found = _start_local_binary(tmp) or _start_docker(container)
    if found is None:
        pytest.skip(
            "SKIP(no-cluster): no CockroachDB v26.2 reachable. Set MAINLINE_TEST_DSN to a "
            "LOCAL cluster, or put `cockroach` on PATH, or start the Docker daemon so the "
            f"lane can run `docker run {CRDB_IMAGE} start-single-node --insecure`. "
            "IDEMPOTENCE AND ledger_linear ARE NOT VERIFIED BY A SKIPPED RUN — both are "
            "database refusals and nothing in process can stand in for them."
        )
    refuse_remote(found.dsn)
    return found


def fixture_statements() -> list[str]:
    """Split the fixture DDL into statements, comments removed first.

    The header explains the reduction at length and its prose contains semicolons, so a
    naive split produces English where SQL was expected. Comments go first, then the
    split — no statement body contains a semicolon inside a literal.
    """
    body = "\n".join(line.split("--")[0] for line in FIXTURE_DDL.read_text("utf-8").splitlines())
    return [statement.strip() for statement in body.split(";") if statement.strip()]


def apply_fixture(dsn: str) -> None:
    statements = fixture_statements()
    with psycopg.connect(dsn, autocommit=True) as conn:
        for statement in statements:
            conn.execute(statement)


@pytest.fixture(scope="module")
def ledger_dsn(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    cluster = discover_cluster(tmp_path_factory.mktemp("crdb"), CONTAINER_NAME)
    owns_docker = cluster.provenance.startswith("docker")
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    database = f"mainline_seq_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")
    parts = conninfo_to_dict(cluster.dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)
    apply_fixture(dsn)
    print(f"\n[custody] cluster: {cluster.provenance}\n[custody] database: {database}")
    try:
        yield dsn
    finally:
        with psycopg.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")
        proc = cluster.__dict__.get("_proc")
        if proc is not None:
            proc.terminate()
        if owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=20.0)


@pytest.fixture
def conn(ledger_dsn: str):
    connection = psycopg.connect(ledger_dsn, autocommit=True)
    connection.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
    try:
        yield connection
    finally:
        connection.close()


@dataclass(frozen=True)
class Log:
    """One test's own site, so the lane needs no cleanup and no ordering.

    A site is a log. Giving each test its own is cheaper than a database per test and
    stronger than truncating between tests: nothing this suite writes can be observed by
    anything else in it, so a failure is never a consequence of what ran before.
    """

    site: str
    other: str

    @property
    def checkpoint(self) -> append_mod.CheckpointInputs:
        return checkpoint_inputs(self.site)


@pytest.fixture
def log(conn) -> Log:
    site = f"blk-{uuid.uuid4().hex[:10]}"
    other = f"blk-{uuid.uuid4().hex[:10]}"
    conn.execute(
        "INSERT INTO mainline.site (site_code, site_role) VALUES (%s, %s), (%s, %s)",
        (site, site.replace("-", "_"), other, other.replace("-", "_")),
    )
    conn.execute(
        "INSERT INTO mainline_ops.sequencer_lease (site_code, holder, epoch, expires_at) "
        "VALUES (%s, 'provisioning', 0, now())",
        (site,),
    )
    return Log(site=site, other=other)


def seed_intake(conn, count: int, *, site: str) -> list[batch_mod.IntakeRow]:
    """Write *count* intake rows through the real sink path (canonicalisation included)."""
    for index in range(count):
        sink_mod.record_intake(
            conn,
            site_code=site,
            entry_kind="disposition",
            subject_id=uuid.uuid4(),
            actor="auth0|4f2c",
            actor_kind="human",
            payload={"entry_kind": "disposition", "site_code": site, "n": index},
        )
    return list(batch_mod.unsequenced(conn, site_code=site, limit=count))


def common_args(log: Log) -> dict:
    return {
        "site_code": log.site,
        "signer": StandInSigner(),
        "checkpoint": log.checkpoint,
        "algebra": algebra(),
    }


def test_issued_at_reproduces_the_wire_format_vector() -> None:
    """``spec/wire/receipt.md`` §2.1 fixes ``issued_at`` at RFC 3339 UTC, milliseconds, ``Z``.

    ``datetime.isoformat()`` emits six fractional digits or none, and a receipt whose
    ``issued_at`` renders differently on two machines canonicalises to different bytes and
    verifies against neither signature. The vector is the one in that document's §5.
    """
    moment = datetime.datetime(2026, 8, 7, 2, 11, 42, 310_000, tzinfo=datetime.UTC)
    assert sink_mod.rfc3339_millis(moment) == "2026-08-07T02:11:42.310Z"
    # Sub-millisecond precision truncates rather than rounds, and a non-UTC input is
    # converted rather than relabelled.
    melbourne = datetime.timezone(datetime.timedelta(hours=10))
    noisy = datetime.datetime(2026, 8, 7, 12, 11, 42, 310_999, tzinfo=melbourne)
    assert sink_mod.rfc3339_millis(noisy) == "2026-08-07T02:11:42.310Z"


# ── The tests ──────────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_emit_returns_a_receipt_shaped_exactly_as_the_wire_format_fixes(conn, log) -> None:
    """The SDR: eight named members, no extras, ``mmd_seconds = 60``.

    The receipt is what makes the ~60-second Maximum Merge Delay honest. A leaf that
    quietly never gets sequenced is invisible; a receipt whose leaf never appears is
    affirmative, portable proof of log misbehaviour held by the party we gave it to
    (attack A14, verifier check 15).

    The issuer is a double here on purpose: ``trappoint_ledger.receipt.issue_receipt``
    owns the canonicalisation, the signature and the key-ID derivation, and this test is
    about the object the sink hands it — not about re-testing the signature in a second
    place.
    """
    signed: list[tuple] = []

    def fake_issuer(receipt, signer):
        signed.append((dict(receipt), signer))
        return {"sdr_version": 1, "receipt": dict(receipt), "key_id": "e74111d1", "sig": "…"}

    sink = sink_mod.MainlineLedgerSink(
        conn=conn,
        site_code=log.site,
        origin=f"mainline.example/site/{log.site}",
        actor="auth0|4f2c",
        actor_kind="human",
        signer=StandInSigner(),
        issue=fake_issuer,
        clock=lambda: datetime.datetime(2026, 8, 7, 2, 11, 42, 310_000, tzinfo=datetime.UTC),
    )
    subject = uuid.uuid4()
    receipt = sink.emit("disposition", subject, {"site_code": log.site, "signer_rank": 4})

    obj = receipt.envelope["receipt"]
    assert set(obj) == {
        "typ",
        "entry_id",
        "leaf_hash",
        "site_code",
        "origin",
        "payload_ver",
        "issued_at",
        "mmd_seconds",
    }
    assert obj["typ"] == "MAINLINE-SDR-v1"
    assert obj["mmd_seconds"] == 60
    assert obj["issued_at"] == "2026-08-07T02:11:42.310Z"
    assert obj["site_code"] == log.site
    assert obj["origin"] == f"mainline.example/site/{log.site}"
    assert obj["leaf_hash"] == receipt.record.leaf_hash.hex()
    assert obj["entry_id"] == str(receipt.record.entry_id)
    assert isinstance(obj["payload_ver"], int)
    assert len(signed) == 1
    assert signed[0][1] is sink.signer, (
        "the receipt is signed by the SAME key that signs checkpoints for this origin, so "
        "verifying one needs no key material a verifier does not already hold"
    )

    stored = conn.execute(
        "SELECT subject_id, actor, actor_kind, entry_kind FROM mainline.ledger_intake "
        "WHERE entry_id = %s",
        (receipt.record.entry_id,),
    ).fetchone()
    assert stored == (subject, "auth0|4f2c", "human", "disposition")


@pytest.mark.requires_cluster
def test_intake_stores_the_exact_bytes_that_were_hashed(conn, log) -> None:
    """``leaf_hash = SHA-256(0x00 ‖ canon_bytes)``, computed by the client and reproducible.

    ``sha256(payload::STRING)`` in SQL is not: CockroachDB's ``sha256()`` returns hex TEXT
    and ``JSONB`` reorders keys, so the value would be one no third party can recompute.
    """
    record = sink_mod.record_intake(
        conn,
        site_code=log.site,
        entry_kind="merge",
        subject_id=uuid.uuid4(),
        actor="agent_gate",
        actor_kind="agent",
        payload={"site_code": log.site, "entry_kind": "merge", "open_blocking": 0},
    )
    canon_bytes, leaf_hash, payload_ver = conn.execute(
        "SELECT canon_bytes, leaf_hash, payload_ver FROM mainline.ledger_intake "
        "WHERE entry_id = %s",
        (record.entry_id,),
    ).fetchone()
    assert bytes(canon_bytes) == record.canon_bytes
    assert hashlib.sha256(b"\x00" + bytes(canon_bytes)).digest() == bytes(leaf_hash)
    assert payload_ver == record.payload_ver
    assert bytes(canon_bytes).startswith(b'{"entry_kind"'), "JCS fixes the member order"


@pytest.mark.requires_cluster
def test_a_float_never_reaches_the_ledger(conn, log) -> None:
    """CU-5: no evidentiary quantity is a binary float, and the refusal is at the door."""
    from trappoint_jcs import NonEvidentiaryNumber

    with pytest.raises(NonEvidentiaryNumber):
        sink_mod.record_intake(
            conn,
            site_code=log.site,
            entry_kind="check_open",
            subject_id=uuid.uuid4(),
            actor="agent_gate",
            actor_kind="agent",
            payload={"site_code": log.site, "severity": 4.5},
        )
    outstanding = conn.execute(
        "SELECT count(*) FROM mainline.ledger_intake WHERE site_code = %s", (log.site,)
    ).fetchone()
    assert outstanding == (0,), "the refusal happens before the INSERT, not after it"


@pytest.mark.requires_cluster
def test_replaying_a_batch_inserts_nothing_new(conn, log) -> None:
    """Idempotence without a lock, because CockroachDB has no advisory locks.

    ``UNIQUE (site_code, entry_id)`` is what makes a re-run safe, and the appender's
    in-transaction anti-join is what turns "safe" into "a genuine no-op" — no leaf, no
    node and no checkpoint, because a second checkpoint at an unchanged tree size is
    either a duplicate or attack A7, and this path must not be the code that decides which.
    """
    rows = seed_intake(conn, 6, site=log.site)
    args = common_args(log)

    first = append_mod.append_batch(conn, rows=rows, **args)
    assert first.appended == 6
    assert first.checkpoint_written is True

    replay = append_mod.append_batch(conn, rows=rows, **args)
    assert replay.appended == 0
    assert replay.already_sequenced == 6
    assert replay.checkpoint_written is False

    counts = conn.execute(
        "SELECT (SELECT count(*) FROM mainline.ledger_leaf WHERE site_code = %s), "
        "       (SELECT count(*) FROM mainline.ledger_checkpoint WHERE site_code = %s)",
        (log.site, log.site),
    ).fetchone()
    assert counts == (6, 1)

    assert batch_mod.unsequenced(conn, site_code=log.site, limit=64) == (), (
        "the anti-join must report nothing outstanding once every row has a leaf"
    )


@pytest.mark.requires_cluster
def test_ledger_linear_refuses_a_forged_predecessor(conn, log) -> None:
    """CU-1, refusal depth 2: two leaves cannot both claim the same predecessor.

    This is attack A6 (`fork`) at the row level. The primary key would already refuse a
    second leaf at the same ``seq``; ``ledger_linear`` refuses a second leaf at a
    *different* ``seq`` that claims the same head — which is the shape a forger reaches
    for once they have noticed the primary key.
    """
    append_mod.append_batch(conn, rows=seed_intake(conn, 3, site=log.site), **common_args(log))
    head = append_mod.read_head(conn, site_code=log.site)
    claimed = bytes(
        conn.execute(
            "SELECT prev_link_hash FROM mainline.ledger_leaf WHERE site_code = %s AND seq = 1",
            (log.site,),
        ).fetchone()[0]
    )

    smuggled = sink_mod.record_intake(
        conn,
        site_code=log.site,
        entry_kind="disposition",
        subject_id=uuid.uuid4(),
        actor="rogue",
        actor_kind="service",
        payload={"site_code": log.site, "entry_kind": "disposition", "forged": True},
    )
    with pytest.raises(psycopg.errors.UniqueViolation) as caught:
        conn.execute(
            "INSERT INTO mainline.ledger_leaf "
            "(site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                log.site,
                head.tree_size + 5,
                smuggled.entry_id,
                smuggled.leaf_hash,
                claimed,
                hashlib.sha256(claimed + smuggled.leaf_hash).digest(),
                uuid.uuid4(),
            ),
        )
    assert append_mod.constraint_name_of(caught.value) == "ledger_linear"


@pytest.mark.requires_cluster
def test_only_one_genesis_leaf_can_exist_per_site(conn, log) -> None:
    """Genesis is 32 zero bytes, not NULL, and that is why the constraint bites at seq 0.

    Under a nullable ``prev_link_hash`` every genesis row would be distinct to the UNIQUE
    index and the first leaf would be the one position at which a fork was allowed.
    """
    append_mod.append_batch(conn, rows=seed_intake(conn, 2, site=log.site), **common_args(log))
    rival = sink_mod.record_intake(
        conn,
        site_code=log.site,
        entry_kind="disposition",
        subject_id=uuid.uuid4(),
        actor="rogue",
        actor_kind="service",
        payload={"site_code": log.site, "entry_kind": "disposition", "rival_genesis": True},
    )
    with pytest.raises(psycopg.errors.UniqueViolation) as caught:
        conn.execute(
            "INSERT INTO mainline.ledger_leaf "
            "(site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id) "
            "VALUES (%s, 900, %s, %s, %s, %s, %s)",
            (
                log.site,
                rival.entry_id,
                rival.leaf_hash,
                append_mod.GENESIS_LINK_HASH,
                hashlib.sha256(append_mod.GENESIS_LINK_HASH + rival.leaf_hash).digest(),
                uuid.uuid4(),
            ),
        )
    assert append_mod.constraint_name_of(caught.value) == "ledger_linear"


@pytest.mark.requires_cluster
def test_an_entry_cannot_be_smuggled_into_another_sites_tree(conn, log) -> None:
    """The composite FK is strictly stronger than the single-column one §5.6 specified.

    Under ``REFERENCES ledger_intake (entry_id)`` a leaf's ``site_code`` is a value the
    SEQUENCER asserts, and a value the writer asserts is not a fact. With
    ``(site_code, entry_id)`` a leaf can only ever join the tree of the site its own
    intake row declared: cross-site smuggling is ``23503``, from every writer, forever.
    """
    foreign = sink_mod.record_intake(
        conn,
        site_code=log.other,
        entry_kind="disposition",
        subject_id=uuid.uuid4(),
        actor="auth0|4f2c",
        actor_kind="human",
        payload={"site_code": log.other, "entry_kind": "disposition"},
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as caught:
        conn.execute(
            "INSERT INTO mainline.ledger_leaf "
            "(site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id) "
            "VALUES (%s, 0, %s, %s, %s, %s, %s)",
            (
                log.site,
                foreign.entry_id,
                foreign.leaf_hash,
                append_mod.GENESIS_LINK_HASH,
                hashlib.sha256(append_mod.GENESIS_LINK_HASH + foreign.leaf_hash).digest(),
                uuid.uuid4(),
            ),
        )
    assert append_mod.constraint_name_of(caught.value) == "fk_intake"


@pytest.mark.requires_cluster
def test_the_link_chain_recomputes_across_several_batches(conn, log) -> None:
    """Verifier check 9, run against the rows the sequencer actually wrote.

    Three separate appends, so the head is re-read and the chain is *continued* rather
    than recomputed from genesis — which is the case a genesis-anchored implementation
    would get wrong and this assertion would catch.
    """
    args = common_args(log)
    total = 0
    for size in (3, 1, 4):
        result = append_mod.append_batch(conn, rows=seed_intake(conn, size, site=log.site), **args)
        assert result.appended == size
        total += size

    leaves = conn.execute(
        "SELECT seq, leaf_hash, prev_link_hash, link_hash FROM mainline.ledger_leaf "
        "WHERE site_code = %s ORDER BY seq",
        (log.site,),
    ).fetchall()
    assert [row[0] for row in leaves] == list(range(total)), "dense 0..n-1"

    previous = append_mod.GENESIS_LINK_HASH
    for _seq, leaf_hash, prev_link_hash, link_hash in leaves:
        assert bytes(prev_link_hash) == previous
        assert bytes(link_hash) == hashlib.sha256(previous + bytes(leaf_hash)).digest()
        previous = bytes(link_hash)

    sizes = [
        row[0]
        for row in conn.execute(
            "SELECT tree_size FROM mainline.ledger_checkpoint WHERE site_code = %s "
            "ORDER BY tree_size",
            (log.site,),
        ).fetchall()
    ]
    assert sizes == [3, 4, 8]


@pytest.mark.requires_cluster
def test_the_node_table_holds_every_completed_interior_node_exactly_once(conn, log) -> None:
    """Three appends, and ``ledger_node`` ends up identical to a single-shot rebuild.

    Two facts are asserted at once. The interior hashes the sequencer persisted across
    three separate transactions are exactly those a tree built in one go holds — so the
    node table is a faithful cache of the derivation, not an artefact of how the batches
    happened to be split. And no coordinate was written twice: a settled perfect-subtree
    hash never changes, which is the only reason ``mainline.ledger_node`` can be
    append-only with a primary key on ``(site_code, level, idx)`` and no ``UPDATE`` grant
    anywhere.
    """
    args = common_args(log)
    for size in (5, 2, 3):
        append_mod.append_batch(conn, rows=seed_intake(conn, size, site=log.site), **args)

    stored = {
        (int(level), int(idx)): bytes(digest)
        for level, idx, digest in conn.execute(
            "SELECT level, idx, hash FROM mainline.ledger_node WHERE site_code = %s",
            (log.site,),
        ).fetchall()
    }
    leaf_hashes = [
        bytes(row[0])
        for row in conn.execute(
            "SELECT leaf_hash FROM mainline.ledger_leaf WHERE site_code = %s ORDER BY seq",
            (log.site,),
        ).fetchall()
    ]
    assert len(leaf_hashes) == 10

    rebuilt = trappoint_tree.MerkleTree(leaf_hashes)
    expected = {
        (node.coord.level, node.coord.index): bytes(node.digest)
        for node in rebuilt.nodes()
        if node.coord.level >= 1
    }
    assert stored == expected

    latest_root = conn.execute(
        "SELECT root_hash FROM mainline.ledger_checkpoint WHERE site_code = %s "
        "ORDER BY tree_size DESC LIMIT 1",
        (log.site,),
    ).fetchone()[0]
    assert bytes(latest_root) == rebuilt.root, (
        "the newest checkpoint must commit to the root of the whole log, and that root "
        "must be reproducible from the leaves alone — which is what a stranger does"
    )


def test_the_lane_refuses_a_remote_dsn() -> None:
    """A ledger lane that can reach a real deployment is itself an attack surface.

    Asserted rather than trusted, because the guard's whole value is that it fires on a
    DSN somebody pasted in without thinking. This one needs no cluster and never skips.
    """
    for remote in (
        "postgresql://user@mainline-prod.aws-ap-southeast-1.cockroachlabs.cloud:26257/main",
        "postgresql://root@10.0.4.19:26257/defaultdb",
    ):
        with pytest.raises(RuntimeError, match="refusing to run"):
            refuse_remote(remote)
    refuse_remote("postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable")
    refuse_remote("postgresql://root@localhost:26257/defaultdb?sslmode=disable")
