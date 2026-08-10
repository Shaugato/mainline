# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The nemesis lane's cluster, its refusal to leave localhost, and its seeded fixture.

This suite performs destructive ``UPDATE``s, ``DELETE``s, ``DROP CONSTRAINT``s and
``DISABLE TRIGGER``s against a ledger. That is the point — an attack harness that only
attacks a mock has proven that the mock is weak. It also means **a nemesis suite that can
reach production is itself a T1 attack surface**, so :func:`refuse_remote` refuses any DSN
whose host is not ``localhost`` or ``127.0.0.1``, and it refuses *before* the connection is
opened rather than after.

Every test gets its own throwaway database. Fifteen attacks that shared one would be fifteen
attacks whose outcomes depend on their order, and an attack matrix generated from an
order-dependent run is a matrix of one run rather than of fifteen attacks.

**Nothing here is green by absence.** When no cluster can be found the lane skips with a
message naming the three discovery routes and saying, in as many words, that the attack
matrix produced without it would be a list of expectations rather than a record of
detections.

**This file holds fixtures and hooks, and nothing a test module needs to import.** The
reduced fixture DDL, :class:`~nemesis_harness.NemesisContext` and
:class:`~nemesis_harness.OutcomeRecorder` live in ``nemesis_harness.py`` beside this one,
because ``conftest`` is not a name any module may safely import: pytest binds every one of
the repository's conftest files to that same bare top-level name and the last one loaded
wins. See ``nemesis_harness.py``'s docstring for the run that measured it.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
BUNDLE_PATH = REPO_ROOT / "evidence" / "reference-ledger" / "bundle.json"

# The attack functions, the matrix writer and the shared harness live beside this file.
# They are not test modules and pytest will not collect them, so the directory goes on
# sys.path explicitly rather than relying on the rootdir-relative import mode staying what
# it is today.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

for _source_root in (
    REPO_ROOT / "packages" / "trappoint-jcs" / "src",
    REPO_ROOT / "packages" / "trappoint-ledger" / "src",
    REPO_ROOT / "packages" / "trappoint-verify" / "src",
):
    if _source_root.is_dir() and str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from nemesis_harness import (  # noqa: E402 - the sys.path insert above must run first
    FIXTURE_DDL,
    NemesisContext,
    OutcomeRecorder,
)

psycopg = pytest.importorskip(
    "psycopg",
    reason="psycopg 3 is required to attack a CockroachDB; `uv sync` installs it. The "
    "attack matrix is generated from a RUN, so without a driver there is no run and no "
    "matrix — only spec/custody/attacks.yaml, which records what we EXPECT.",
)

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:v26.2.5")
CONTAINER_NAME = "mainline-custody-nemesis"
READY_TIMEOUT_S = 120.0
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "[::1]"})

#: Where the run's outcomes are written, and what `matrix.py` reads to build the matrix.
RUN_RECORD = REPO_ROOT / "evidence" / "custody-nemesis-run.json"


# =======================================================================================
# Cluster discovery, and the refusal that makes this lane safe to own
# =======================================================================================


@dataclass
class Cluster:
    dsn: str
    provenance: str


class RemoteDsnRefused(RuntimeError):
    """Raised when a DSN names a host this suite must never be pointed at."""


def refuse_remote(dsn: str) -> None:
    """Refuse any DSN whose host is not ``localhost``/``127.0.0.1``.

    This is the guard `docs/leads/custody.md` §6.8 requires, and it is checked before a
    socket is opened. The nemesis suite deletes ledger leaves, renumbers them, rewrites the
    blame closure and disables the merge gate. Pointed at a real deployment it would not be
    a failing test; it would be the attack.
    """
    from psycopg.conninfo import conninfo_to_dict

    try:
        host = str(conninfo_to_dict(dsn).get("host", "")).strip()
    except psycopg.Error as exc:  # a DSN we cannot parse is a DSN we cannot clear
        raise RemoteDsnRefused(f"refusing an unparseable DSN: {exc}") from exc
    if host not in LOCAL_HOSTS:
        raise RemoteDsnRefused(
            f"refusing to run the nemesis suite against host {host!r}. This suite performs "
            "destructive UPDATEs, DELETEs, DROP CONSTRAINTs and DISABLE TRIGGERs on the "
            "custody ledger. It runs against a disposable single-node CockroachDB on "
            "localhost only — a nemesis suite that can reach production IS a T1 attack "
            "surface."
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


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
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
            "NO ATTACK WAS EXECUTED AND NO DETECTION WAS OBSERVED BY A SKIPPED RUN — the "
            "matrix such a run could produce would be spec/custody/attacks.yaml with a "
            "different layout, which is a list of expectations, not a record."
        )
    refuse_remote(found.dsn)
    return found


@pytest.fixture(scope="session")
def cluster(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Cluster]:
    found = discover_cluster(tmp_path_factory.mktemp("crdb"))
    print(f"[nemesis] cluster: {found.provenance}")
    yield found
    proc = found.__dict__.get("_proc")
    if proc is not None:
        proc.terminate()
    elif found.provenance.startswith("docker"):
        _docker(["rm", "-f", CONTAINER_NAME], timeout=30.0)


@pytest.fixture(scope="session")
def reference_bundle() -> dict[str, Any]:
    if not BUNDLE_PATH.is_file():
        pytest.skip(
            f"SKIP(no-bundle): {BUNDLE_PATH.relative_to(REPO_ROOT).as_posix()} does not "
            "exist. Run `python evidence/reference-ledger/generate.py` first; the attacks "
            "run against a WORKING COPY of it and there is nothing to copy."
        )
    return json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))


# =======================================================================================
# The seeded, attackable ledger
# =======================================================================================


def _seed(ctx: NemesisContext) -> None:
    """Load the reference bundle's 72 leaves and 8 checkpoints into the fixture schema.

    The seeded ledger is *the same log* the committed bundle describes, which is what makes
    the attacks meaningful: every checkpoint in the database is a commitment that already
    left our control (it is timestamped, cosigned and committed to this repository), so a
    later rewrite of the leaves has to contradict something an outsider already holds.
    """
    import base64

    reference = ctx.reference
    site = ctx.site_code
    ctx.sql(
        "INSERT INTO mainline.site (site_code, site_role) VALUES (%s, %s)",
        (site, f"site_{site.replace('-', '_')}"),
    )

    # One multi-row INSERT per table rather than 144 round trips. The lane stands up a
    # fresh database for every attack — fifteen sequential attacks on a shared one would be
    # fifteen attacks whose outcomes depend on their order — so seeding cost is paid
    # fifteen times and a per-row loop pushes a two-second fixture past a two-minute test
    # timeout.
    intake_rows: list[Any] = []
    leaf_rows: list[Any] = []
    for index, leaf in enumerate(reference["leaves"]):
        intake_rows.extend(
            (
                leaf["entry_id"],
                site,
                leaf["entry_kind"],
                leaf["subject_id"],
                leaf["actor"],
                leaf["actor_kind"],
                json.dumps(leaf["payload"]),
                base64.b64decode(leaf["canon_bytes_b64"]),
                leaf["payload_ver"],
                bytes.fromhex(leaf["leaf_hash_hex"]),
                leaf["is_sandbox"],
                index,
            )
        )
        leaf_rows.extend(
            (
                site,
                leaf["seq"],
                leaf["entry_id"],
                bytes.fromhex(leaf["leaf_hash_hex"]),
                bytes.fromhex(leaf["prev_link_hash_hex"]),
                bytes.fromhex(leaf["link_hash_hex"]),
                leaf["batch_id"],
            )
        )
    count = len(reference["leaves"])
    # The only interpolation is a repeated literal placeholder group; every VALUE travels
    # as a bound parameter. S608 cannot see that, so it is silenced at the one line that
    # builds the text rather than blanket-disabled for the module.
    intake_sql = (
        "INSERT INTO mainline.ledger_intake "  # noqa: S608
        "(entry_id, site_code, entry_kind, subject_id, actor, actor_kind, payload, "
        " canon_bytes, payload_ver, leaf_hash, is_sandbox, hlc) VALUES "
        + ",".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * count)
    )
    leaf_sql = (
        "INSERT INTO mainline.ledger_leaf "  # noqa: S608
        "(site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id) VALUES "
        + ",".join(["(%s,%s,%s,%s,%s,%s,%s)"] * count)
    )
    ctx.sql(intake_sql, tuple(intake_rows))
    ctx.sql(leaf_sql, tuple(leaf_rows))

    canon_src = bytes.fromhex(reference["canon"]["canon_src_sha256"])
    for entry in reference["checkpoints"]:
        note = entry["note"]
        text, _, signatures = note.rpartition("\n\n")
        body = text + "\n"
        log_sig = b""
        for line in signatures.splitlines():
            if line.startswith("— " + reference["origin"] + " "):
                # A signature line's base64 decodes to `4-byte key ID || signature bytes`
                # (spec/wire/checkpoint.md §2), and `ledger_checkpoint.log_sig` stores the
                # SIGNATURE BYTES ONLY (§8). Keeping the key ID here would double it on
                # re-encode and every note would fail verification for a reason that has
                # nothing to do with the key.
                log_sig = base64.b64decode(line.rsplit(" ", 1)[1])[4:]
        token = entry["tsa_tokens"][0]["token_b64"] if entry["tsa_tokens"] else None
        ctx.sql(
            "INSERT INTO mainline.ledger_checkpoint "
            "(site_code, tree_size, root_hash, body, beacon, log_sig, tsa_token, "
            " canon_src_sha256, s3_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                site,
                entry["tree_size"],
                bytes.fromhex(entry["root_hex"]),
                body,
                json.dumps({"observed_at": entry["observed_at"]}),
                log_sig,
                base64.b64decode(token) if token else None,
                canon_src,
                f"v-{entry['tree_size']:06d}",
            ),
        )

    for cosig in reference["witness_cosignatures"]:
        ctx.sql(
            "INSERT INTO mainline.cosignature "
            "(site_code, tree_size, witness_id, trust_domain, adverse, sig) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                site,
                cosig["tree_size"],
                cosig["witness_id"],
                cosig["trust_domain"],
                cosig["adverse"],
                base64.b64decode(cosig["sig_line"].rsplit(" ", 1)[1])[4:],
            ),
        )

    site_id = ctx.sql("SELECT site_id FROM mainline.site WHERE site_code = %s", (site,))[0][0]
    for row in reference["closure_generations"]:
        severity = int(row["max_severity"])
        ctx.sql(
            "INSERT INTO mainline.clause_blame_closure "
            "(clause_uuid, as_of_commit, closure_gen, site_id, ancestor_events, "
            " ancestor_count, max_severity, virulence, depth, truncated, computed_by, "
            " projector_ver) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                row["clause_uuid"],
                bytes.fromhex(row["as_of_commit"]),
                row["closure_gen"],
                site_id,
                [],
                0,
                severity,
                "blood_fatal" if severity >= 5 else ("blood_major" if severity == 4 else "serious"),
                3,
                row["truncated"],
                "agent_projector",
                "closure/1",
            ),
        )

    # One permit with one undischarged obligation: the state A13 attacks, and the state the
    # gate must refuse before anybody disables anything.
    permit_id = ctx.sql(
        "INSERT INTO mainline.permit (site_code, state, open_blocking) "
        "VALUES (%s, 'permitted', 0) RETURNING permit_id",
        (site,),
    )[0][0]
    ctx.sql(
        "INSERT INTO mainline.blocking_check (permit_id, clause_uuid, severity, origin) "
        "VALUES (%s, %s, 5, 'blame_ancestry')",
        (permit_id, reference["closure_generations"][0]["clause_uuid"]),
    )
    ctx.sql(
        "INSERT INTO mainline.permit_event "
        "(permit_id, seq, prev_seq, from_state, to_state, actor_sub, payload, prev_digest) "
        # Genesis is `seq = 1, prev_seq = 0`, not `seq = 0`: the shipped CHECK
        # `(seq > prev_seq AND prev_seq >= 0)` makes seq = 0 unreachable, so the trigger's
        # genesis exemption is the "no prior row for this subject" branch, not the seq test.
        "VALUES (%s, 1, 0, 'draft', 'proposed', 'svc_gate', %s, %s)",
        (permit_id, json.dumps({"step": "opened"}), bytes(32)),
    )
    ctx.conn.commit()


@pytest.fixture
def nemesis(cluster: Cluster, reference_bundle: dict[str, Any]) -> Iterator[NemesisContext]:
    """A private, seeded, disposable database — one per test."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    refuse_remote(cluster.dsn)
    database = f"nemesis_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    params = conninfo_to_dict(cluster.dsn)
    params["dbname"] = database
    dsn = make_conninfo(**params)
    refuse_remote(dsn)

    conn = psycopg.connect(dsn, autocommit=True)
    try:
        # One round trip for the whole schema. The `--` separator lines are SQL comments,
        # so the constant is valid multi-statement SQL as written, and CockroachDB applies
        # the twenty-one objects in a single implicit transaction (measured: ~50 ms against
        # v26.2.5, versus ~4 s statement by statement). Fifteen attacks each get a private
        # database, so this cost is paid fifteen times per run.
        conn.execute(FIXTURE_DDL)
        ctx = NemesisContext(
            conn=conn,
            dsn=dsn,
            site_code=reference_bundle["site_code"],
            reference=reference_bundle,
            provenance=cluster.provenance,
        )
        _seed(ctx)
        ctx.capture_triggerdefs()
        yield ctx
    finally:
        conn.close()
        with psycopg.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


# =======================================================================================
# The run record — what the matrix is generated FROM
# =======================================================================================
#
# :class:`OutcomeRecorder` itself lives in ``nemesis_harness.py``; what belongs here is the
# one session-long instance and the hook that writes it out. `RUN_RECORD` is passed to
# `write()` rather than read from inside it, so the recorder holds the shape of the record
# and this file — the half that knows it is inside a pytest session — holds where the
# session's evidence lands.


_RECORDER = OutcomeRecorder()


@pytest.fixture(scope="session")
def recorder() -> OutcomeRecorder:
    """The one recorder every attack in this session reports into."""
    return _RECORDER


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # noqa: ARG001
    """Write the run record, then regenerate the matrix from it.

    Written at session finish rather than per test so that a partial run produces a partial
    matrix that says which attacks did not run, instead of a matrix that silently omits
    them. ``matrix.py`` is what enforces the ATTACK-DEPTH rule over the result.
    """
    if not _RECORDER.outcomes:
        return
    _RECORDER.write(RUN_RECORD)
    try:
        import matrix as matrix_module
    except ImportError:  # pragma: no cover — the module sits beside this file
        return
    matrix_module.write_matrix(RUN_RECORD, REPO_ROOT / "evidence" / "CUSTODY_ATTACK_MATRIX.md")
