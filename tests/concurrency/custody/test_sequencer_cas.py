# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Sixteen sequencers, one site, and a log that is still dense and fork-free.

The claim this lane exists to make executable is the one the custody lead states plainly:

    *The lease is a PERFORMANCE mechanism, not a CORRECTNESS one. Correctness is the two
    constraints in migration 0073, which hold at any isolation level and with no lease at
    all.*

So the headline test **deliberately does not take the lease**. Sixteen threads select
overlapping batches by anti-join and append them concurrently, and the resulting log must
still be dense ``0..n-1``, must contain every intake row exactly once, and must have a
link chain that recomputes from genesis. If that only worked because one writer was
elected, the sentence above would be false and the whole custody argument would rest on a
row in ``mainline_ops`` that an adversary can rewrite.

A second test proves the election separately, and a third pins the race down to two
transactions so the CAS is observed rather than inferred: two writers both read
``max(seq) = -1``, both insert at ``seq 0``, and exactly one survives — with an error the
appender's retry predicate recognises by name.

The lane refuses any DSN whose host is not ``localhost``/``127.0.0.1``, and skips with a
reason naming what was missing when no cluster can be found. A skipped run proves nothing:
this is a database property and nothing in process can stand in for it.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pytest

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
from mainline_sequencer import lease as lease_mod  # noqa: E402
from mainline_sequencer import sink as sink_mod  # noqa: E402

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:latest-v26.2")
CONTAINER_NAME = "mainline-sequencer-concurrency"
READY_TIMEOUT_S = 120.0
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "[::1]"})

WORKERS = 16
ENTRIES = 160
BATCH = 8
ROUND_LIMIT = 200

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
    """Refuse anything that is not a local, disposable cluster.

    Sixteen threads writing leaves is a load generator. Pointed at a real deployment it
    would write into the evidentiary record from a test runner, which is a worse outcome
    than any failure this suite can report.
    """
    from psycopg.conninfo import conninfo_to_dict

    host = str(conninfo_to_dict(dsn).get("host", "")).strip()
    if host not in LOCAL_HOSTS:
        raise RuntimeError(
            f"refusing to run the sequencer concurrency lane against host {host!r}. "
            "It runs against a disposable single-node CockroachDB on localhost only."
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


def discover_cluster(tmp: Path) -> Cluster:
    for name in ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL"):
        value = os.environ.get(name)
        if value:
            refuse_remote(value)
            return Cluster(dsn=value, provenance=f"${name}")
    found = _start_local_binary(tmp) or _start_docker(CONTAINER_NAME)
    if found is None:
        pytest.skip(
            "SKIP(no-cluster): no CockroachDB v26.2 reachable. Set MAINLINE_TEST_DSN to a "
            "LOCAL cluster, or put `cockroach` on PATH, or start the Docker daemon so the "
            f"lane can run `docker run {CRDB_IMAGE} start-single-node --insecure`. "
            "DENSITY AND FORK-FREEDOM ARE NOT VERIFIED BY A SKIPPED RUN — they are "
            "properties of two database constraints under real concurrency."
        )
    refuse_remote(found.dsn)
    return found


def fixture_statements() -> list[str]:
    """Split the fixture DDL into statements, comments removed first."""
    body = "\n".join(line.split("--")[0] for line in FIXTURE_DDL.read_text("utf-8").splitlines())
    return [statement.strip() for statement in body.split(";") if statement.strip()]


@pytest.fixture(scope="module")
def ledger_dsn(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    cluster = discover_cluster(tmp_path_factory.mktemp("crdb"))
    owns_docker = cluster.provenance.startswith("docker")
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    database = f"mainline_cas_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")
    parts = conninfo_to_dict(cluster.dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)
    with psycopg.connect(dsn, autocommit=True) as conn:
        for statement in fixture_statements():
            conn.execute(statement)
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


def connect(dsn: str):
    conn = psycopg.connect(dsn, autocommit=True)
    conn.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
    return conn


@pytest.fixture
def site(ledger_dsn: str) -> str:
    """One site per test. A site is a log, so this is complete isolation for free."""
    code = f"blk-{uuid.uuid4().hex[:10]}"
    with connect(ledger_dsn) as conn:
        conn.execute(
            "INSERT INTO mainline.site (site_code, site_role) VALUES (%s, %s)",
            (code, code.replace("-", "_")),
        )
        conn.execute(
            "INSERT INTO mainline_ops.sequencer_lease (site_code, holder, epoch, expires_at) "
            "VALUES (%s, 'provisioning', 0, now())",
            (code,),
        )
    return code


def seed_intake(dsn: str, site: str, count: int) -> set[uuid.UUID]:
    written: set[uuid.UUID] = set()
    with connect(dsn) as conn:
        for index in range(count):
            record = sink_mod.record_intake(
                conn,
                site_code=site,
                entry_kind="disposition",
                subject_id=uuid.uuid4(),
                actor="auth0|4f2c",
                actor_kind="human",
                payload={"entry_kind": "disposition", "site_code": site, "n": index},
            )
            written.add(record.entry_id)
    return written


@dataclass
class WorkerTally:
    """What one sequencer thread observed. Every outcome is counted, none is swallowed."""

    appended: int = 0
    rounds: int = 0
    attempts: int = 0
    exhausted: int = 0
    escaped: list[str] = field(default_factory=list)


def drive(dsn: str, site: str) -> WorkerTally:
    """One sequencer, looping until the anti-join reports nothing outstanding.

    No lease is taken. That is the point of the test it serves.
    """
    tally = WorkerTally()
    shared_algebra = algebra()
    with connect(dsn) as conn:
        for _round in range(ROUND_LIMIT):
            rows = batch_mod.unsequenced(conn, site_code=site, limit=BATCH)
            if not rows:
                break
            tally.rounds += 1
            try:
                result = append_mod.append_batch(
                    conn,
                    site_code=site,
                    rows=rows,
                    signer=StandInSigner(),
                    checkpoint=checkpoint_inputs(site),
                    algebra=shared_algebra,
                )
            except append_mod.CasExhausted:
                # Documented: the rows stay unsequenced and the next round re-selects them.
                tally.exhausted += 1
            except psycopg.Error as exc:
                # Recorded rather than absorbed. The assertion below is that whatever
                # reached here is a refusal the design NAMES, not merely that the run
                # finished.
                tally.escaped.append(f"{type(exc).__name__}:{append_mod.constraint_name_of(exc)}")
            else:
                tally.appended += result.appended
                tally.attempts += result.attempts
    return tally


# ── The headline: correctness without the lease ────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.requires_cluster
def test_sixteen_sequencers_without_a_lease_still_produce_a_dense_fork_free_log(
    ledger_dsn, site
) -> None:
    """Correctness is ``ledger_leaf_pkey`` and ``ledger_linear``, not the lease.

    Sixteen threads, overlapping anti-join batches, no election. Afterwards:

    * ``seq`` is dense ``0..n-1`` — so verifier check 9 can treat a gap as tampering;
    * every intake row has exactly one leaf — no loss, no duplication;
    * no two leaves claim the same predecessor — attack A6 is physically impossible;
    * the link chain recomputes from genesis — verifier check 9's other half.
    """
    intake_ids = seed_intake(ledger_dsn, site, ENTRIES)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        tallies = list(pool.map(lambda _worker: drive(ledger_dsn, site), range(WORKERS)))

    appended = sum(t.appended for t in tallies)
    rounds = sum(t.rounds for t in tallies)
    attempts = sum(t.attempts for t in tallies)
    escaped = [item for t in tallies for item in t.escaped]
    print(
        f"[custody] workers={WORKERS} rounds={rounds} appended={appended} "
        f"cas_attempts={attempts} exhausted={sum(t.exhausted for t in tallies)} "
        f"escaped={escaped}"
    )

    assert appended == ENTRIES, "every row must be appended exactly once, by exactly one worker"
    for item in escaped:
        modelled = ("UniqueViolation:ledger_leaf_entry_unique", "SerializationFailure")
        assert item.startswith(modelled), (
            f"an unmodelled refusal escaped the appender: {item}. Every outcome of this "
            "lane must be one the design names."
        )

    with connect(ledger_dsn) as conn:
        leaves = conn.execute(
            "SELECT seq, entry_id, leaf_hash, prev_link_hash, link_hash "
            "FROM mainline.ledger_leaf WHERE site_code = %s ORDER BY seq",
            (site,),
        ).fetchall()

        assert [row[0] for row in leaves] == list(range(ENTRIES)), (
            "the sequence must be DENSE. A gap here would mean a gap can occur without "
            "tampering, and verifier check 9 would then assert nothing."
        )
        assert {row[1] for row in leaves} == intake_ids
        assert len({row[1] for row in leaves}) == len(leaves), "no entry may be sequenced twice"
        assert len({bytes(row[3]) for row in leaves}) == len(leaves), (
            "two leaves claiming one predecessor is a fork; ledger_linear refuses it"
        )

        previous = append_mod.GENESIS_LINK_HASH
        for _seq, _entry, leaf_hash, prev_link_hash, link_hash in leaves:
            assert bytes(prev_link_hash) == previous
            assert bytes(link_hash) == hashlib.sha256(previous + bytes(leaf_hash)).digest()
            previous = bytes(link_hash)

        sizes = [
            row[0]
            for row in conn.execute(
                "SELECT tree_size FROM mainline.ledger_checkpoint WHERE site_code = %s "
                "ORDER BY tree_size",
                (site,),
            ).fetchall()
        ]
        assert sizes == sorted(set(sizes)), "one checkpoint per tree size, strictly increasing"
        assert sizes[-1] == ENTRIES, "the last checkpoint must commit to the whole log"


# ── The CAS itself, pinned to two transactions so it cannot be inferred ────────────────


@pytest.mark.requires_cluster
def test_two_writers_that_both_read_max_seq_produce_exactly_one_leaf(ledger_dsn, site) -> None:
    """CU-2 observed rather than assumed, and the loser's error is one the loop knows by name.

    Both transactions derive ``seq = COALESCE(max(seq), -1) + 1 = 0`` and both claim the
    genesis predecessor. Exactly one survives, and the other is refused by a constraint
    the appender's retry predicate recognises — which is what makes the single retryable
    ``23505`` in this repository a genuine compare-and-swap rather than a hopeful one.
    """
    seed_intake(ledger_dsn, site, 2)
    with connect(ledger_dsn) as reader:
        rows = batch_mod.unsequenced(reader, site_code=site, limit=2)

    first = psycopg.connect(ledger_dsn, autocommit=False)
    second = psycopg.connect(ledger_dsn, autocommit=False)
    first.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
    second.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
    try:
        first.execute("SET statement_timeout = '15s'")
        second.execute("SET statement_timeout = '15s'")

        head_a = append_mod.read_head(first, site_code=site)
        head_b = append_mod.read_head(second, site_code=site)
        assert head_a.tree_size == head_b.tree_size == 0
        assert head_a.link_hash == append_mod.GENESIS_LINK_HASH

        statement = (
            "INSERT INTO mainline.ledger_leaf "
            "(site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id) "
            "VALUES (%s, 0, %s, %s, %s, %s, %s)"
        )
        first.execute(
            statement,
            (
                site,
                rows[0].entry_id,
                rows[0].leaf_hash,
                append_mod.GENESIS_LINK_HASH,
                hashlib.sha256(append_mod.GENESIS_LINK_HASH + rows[0].leaf_hash).digest(),
                uuid.uuid4(),
            ),
        )
        first.commit()

        loser: psycopg.Error | None = None
        try:
            second.execute(
                statement,
                (
                    site,
                    rows[1].entry_id,
                    rows[1].leaf_hash,
                    append_mod.GENESIS_LINK_HASH,
                    hashlib.sha256(append_mod.GENESIS_LINK_HASH + rows[1].leaf_hash).digest(),
                    uuid.uuid4(),
                ),
            )
            second.commit()
        except psycopg.Error as exc:
            loser = exc
            second.rollback()

        assert loser is not None, (
            "both transactions committed a leaf at seq 0. The sequence is not dense, a gap "
            "no longer means tampering, and verifier check 9 asserts nothing."
        )
        assert isinstance(
            loser, psycopg.errors.UniqueViolation | psycopg.errors.SerializationFailure
        ), f"the loser was refused by {type(loser).__name__}, which the CAS loop does not model"
        if isinstance(loser, psycopg.errors.UniqueViolation):
            name = append_mod.constraint_name_of(loser)
            assert name in append_mod.CAS_RETRYABLE_CONSTRAINTS, (
                f"the loser was refused by {name!r}, which is NOT in the retry set — the "
                "appender would have propagated it instead of re-deriving"
            )
    finally:
        first.close()
        second.close()

    with connect(ledger_dsn) as conn:
        assert conn.execute(
            "SELECT count(*) FROM mainline.ledger_leaf WHERE site_code = %s", (site,)
        ).fetchone() == (1,)


# ── The lease, proven separately because it is a separate claim ────────────────────────


@pytest.mark.requires_cluster
def test_the_lease_elects_exactly_one_holder(ledger_dsn, site) -> None:
    """Sixteen contenders, one winner, and the epoch advances exactly once.

    The losers return ``None`` rather than raising: standing down for one 15-second tick
    is an ordinary outcome, and a loser that retried inside its own invocation would be
    the second writer the lease exists to prevent.

    MEASURED, and the reason :func:`mainline_sequencer.lease.contend` exists: at this
    width CockroachDB refuses some contenders with ``40001 WriteTooOldError`` rather than
    with a zero-row result. That is the *undecided* class, and a lane that used bare
    ``acquire`` here would be asserting that an undecided transaction is a lost election.
    """

    def elect(index: int):
        with connect(ledger_dsn) as conn:
            return lease_mod.contend(conn, site_code=site, holder=f"holder-{index}", ttl_seconds=60)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        outcomes = list(pool.map(elect, range(WORKERS)))

    winners = [held for held in outcomes if held is not None]
    assert len(winners) == 1, f"{len(winners)} sequencers believe they hold one site's log"
    assert winners[0].epoch == 1, "the epoch advances by exactly one per successful election"

    with connect(ledger_dsn) as conn:
        observed, expired = lease_mod.observe(conn, site_code=site)
    assert observed.holder == winners[0].holder
    assert observed.epoch == 1
    assert expired is False


@pytest.mark.requires_cluster
def test_a_released_lease_is_taken_by_the_next_contender(ledger_dsn, site) -> None:
    """Release is an optimisation, and the epoch it leaves behind is what the next one beats."""
    with connect(ledger_dsn) as conn:
        with conn.transaction():
            held = lease_mod.acquire(conn, site_code=site, holder="first", ttl_seconds=60)
        assert held is not None

        with conn.transaction():
            assert lease_mod.acquire(conn, site_code=site, holder="second") is None

        assert lease_mod.release(conn, held) is True

        with conn.transaction():
            second = lease_mod.acquire(conn, site_code=site, holder="second")
        assert second is not None
        assert second.epoch == held.epoch + 1


def test_the_lane_refuses_a_remote_dsn() -> None:
    """Sixteen threads writing leaves is a load generator; it never points at a deployment."""
    with pytest.raises(RuntimeError, match="refusing to run"):
        refuse_remote("postgresql://user@mainline.aws-ap-southeast-1.cockroachlabs.cloud:26257/m")
    refuse_remote("postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable")
