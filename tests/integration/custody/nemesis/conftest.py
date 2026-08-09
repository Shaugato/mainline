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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
BUNDLE_PATH = REPO_ROOT / "evidence" / "reference-ledger" / "bundle.json"

# The attack functions and the matrix writer live beside this file. They are not test
# modules and pytest will not collect them, so the directory goes on sys.path explicitly
# rather than relying on the rootdir-relative import mode staying what it is today.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

for _source_root in (
    REPO_ROOT / "packages" / "trappoint-jcs" / "src",
    REPO_ROOT / "packages" / "trappoint-ledger" / "src",
    REPO_ROOT / "packages" / "trappoint-verify" / "src",
):
    if _source_root.is_dir() and str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

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
# THE REDUCED FIXTURE SCHEMA
# =======================================================================================
#
# `verticals/mainline/db/migrations/**` is the datamodel lead's exclusive territory and is
# the authoritative DDL. This is a REDUCTION of it to the objects the fifteen attacks
# touch, so a disposable node stands up in a second rather than applying 200+ migrations
# that pull in enums, seeds, vector indexes and half the recall schema.
#
# THE REDUCTION IS GUARDED, NOT PROMISED. `test_ledger_attacks.py::
# test_fixture_names_the_same_constraints_as_the_migrations` reads BOTH this string and the
# migration files and fails if the constraint names on the three ledger tables diverge.
# Those names are an interface — CU-2's retry predicate matches on `ledger_leaf_pkey` and
# `ledger_linear` — and a fixture that drifted would let attacks pass against names the
# database does not use.
#
# WHAT IS REDUCED, and why each reduction is safe for what these attacks assert:
#
#   * `mainline.permit`, `blocking_check`, `disposition`, `permit_clause` keep only the
#     columns the merge gate reads. A13's assertion is that the gate REFUSES, that the
#     bypass SUCCEEDS after DISABLE TRIGGER, and that check 11 sees the difference — none
#     of which depends on the columns removed.
#   * `fn_permit_merge_gate` keeps step 1 (re-derive the open obligation count from the base
#     tables and refuse when the projection disagrees) and drops steps 2-4. Step 1 is the
#     mechanism A13 disables; the others refuse different writes and have their own lanes.
#   * `clause_blame_closure` drops the FK to `clause_version` and the inverted index. A10
#     attacks `max_severity`, and check 14 reads generations and severities only.
#   * `ledger_node` is absent: every Merkle proof in this lane is recomputed in Python from
#     the leaf hashes actually present, which is what a stranger's verifier does.
#   * The vertical's enum types are created here because `permit_event.from_state` needs
#     one; the values are copied from migration 0011 and 0013.

FIXTURE_DDL = """
CREATE SCHEMA IF NOT EXISTS mainline;
--
CREATE SCHEMA IF NOT EXISTS mainline_ops;
--
CREATE TYPE mainline.virulence_class AS ENUM ('routine', 'serious', 'blood_major', 'blood_fatal');
--
CREATE TYPE mainline.subject_state AS ENUM ('draft', 'proposed', 'permitted', 'merged', 'closed');
--
CREATE TABLE mainline.site (
  site_id      UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_code    STRING      NOT NULL,
  site_role    NAME        NOT NULL,
  tenant_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
  taxonomy_ver INT4        NOT NULL DEFAULT 1,
  opened_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT site_pk PRIMARY KEY (site_id),
  CONSTRAINT site_code_unique UNIQUE (site_code),
  CONSTRAINT site_role_unique UNIQUE (site_role),
  CONSTRAINT site_code_stated CHECK (site_code <> ''),
  CONSTRAINT site_code_is_lower_case CHECK (site_code = lower(site_code)),
  CONSTRAINT taxonomy_ver_positive CHECK (taxonomy_ver >= 1)
);
--
CREATE TABLE mainline.ledger_intake (
  entry_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_code   STRING      NOT NULL,
  entry_kind  STRING      NOT NULL,
  subject_id  UUID        NOT NULL,
  actor       STRING      NOT NULL,
  actor_kind  STRING      NOT NULL,
  payload     JSONB       NOT NULL,
  canon_bytes BYTES       NOT NULL,
  payload_ver INT2        NOT NULL,
  leaf_hash   BYTES       NOT NULL,
  is_sandbox  BOOL        NOT NULL DEFAULT false,
  hlc         DECIMAL     NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ledger_intake_pkey PRIMARY KEY (entry_id),
  CONSTRAINT intake_site_entry_unique UNIQUE (site_code, entry_id),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT actor_kind_known
    CHECK (actor_kind IN ('human', 'agent', 'service', 'external')),
  CONSTRAINT entry_kind_stated CHECK (entry_kind <> ''),
  CONSTRAINT actor_stated CHECK (actor <> ''),
  CONSTRAINT payload_ver_positive CHECK (payload_ver >= 1),
  CONSTRAINT canon_bytes_present CHECK (length(canon_bytes) > 0),
  CONSTRAINT leaf_hash_is_sha256 CHECK (length(leaf_hash) = 32),
  INDEX by_site_hlc (site_code, hlc ASC)
);
--
CREATE TABLE mainline.ledger_leaf (
  site_code      STRING NOT NULL,
  seq            INT8   NOT NULL,
  entry_id       UUID   NOT NULL,
  leaf_hash      BYTES  NOT NULL,
  prev_link_hash BYTES  NOT NULL,
  link_hash      BYTES  NOT NULL,
  batch_id       UUID   NOT NULL,
  CONSTRAINT ledger_leaf_pkey PRIMARY KEY (site_code, seq),
  CONSTRAINT ledger_linear UNIQUE (site_code, prev_link_hash),
  CONSTRAINT ledger_leaf_entry_unique UNIQUE (site_code, entry_id),
  CONSTRAINT fk_intake FOREIGN KEY (site_code, entry_id)
    REFERENCES mainline.ledger_intake (site_code, entry_id),
  CONSTRAINT seq_zero_based CHECK (seq >= 0),
  CONSTRAINT leaf_hash_is_sha256 CHECK (length(leaf_hash) = 32),
  CONSTRAINT prev_link_hash_is_sha256 CHECK (length(prev_link_hash) = 32),
  CONSTRAINT link_hash_is_sha256 CHECK (length(link_hash) = 32)
);
--
CREATE TABLE mainline.ledger_checkpoint (
  site_code        STRING      NOT NULL,
  tree_size        INT8        NOT NULL,
  root_hash        BYTES       NOT NULL,
  body             STRING      NOT NULL,
  beacon           JSONB       NOT NULL,
  log_sig          BYTES       NOT NULL,
  tsa_token        BYTES       NULL,
  s3_version       STRING      NULL,
  canon_src_sha256 BYTES       NOT NULL,
  admissible       BOOL        NOT NULL DEFAULT false,
  issued_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ledger_checkpoint_pkey PRIMARY KEY (site_code, tree_size),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT tree_size_non_negative CHECK (tree_size >= 0),
  CONSTRAINT root_hash_is_sha256 CHECK (length(root_hash) = 32),
  CONSTRAINT canon_src_is_sha256 CHECK (length(canon_src_sha256) = 32),
  CONSTRAINT body_stated CHECK (body <> ''),
  CONSTRAINT log_sig_present CHECK (length(log_sig) > 0),
  CONSTRAINT tsa_token_present_if_stated CHECK (tsa_token IS NULL OR length(tsa_token) > 0),
  CONSTRAINT s3_version_stated_if_present CHECK (s3_version IS NULL OR s3_version <> '')
);
--
CREATE TABLE mainline.cosignature (
  site_code    STRING      NOT NULL,
  tree_size    INT8        NOT NULL,
  witness_id   STRING      NOT NULL,
  trust_domain STRING      NOT NULL,
  adverse      BOOL        NOT NULL,
  sig          BYTES       NOT NULL,
  received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT cosignature_pkey PRIMARY KEY (site_code, tree_size, witness_id),
  CONSTRAINT fk_cp FOREIGN KEY (site_code, tree_size)
    REFERENCES mainline.ledger_checkpoint (site_code, tree_size),
  CONSTRAINT trust_domain_known
    CHECK (trust_domain IN ('regulator', 'insurer', 'union_hsr', 'external_auditor', 'operator')),
  CONSTRAINT operator_is_never_adverse
    CHECK (trust_domain <> 'operator' OR NOT adverse),
  CONSTRAINT witness_id_stated CHECK (witness_id <> ''),
  CONSTRAINT sig_present CHECK (length(sig) > 0)
);
--
CREATE TABLE mainline.clause_blame_closure (
  clause_uuid     UUID        NOT NULL,
  as_of_commit    BYTES       NOT NULL,
  closure_gen     INT8        NOT NULL,
  site_id         UUID        NOT NULL,
  ancestor_events UUID[]      NOT NULL,
  ancestor_count  INT4        NOT NULL,
  max_severity    INT2        NOT NULL,
  virulence       mainline.virulence_class NOT NULL,
  depth           INT4        NOT NULL,
  truncated       BOOL        NOT NULL DEFAULT false,
  computed_by     STRING      NOT NULL,
  projector_ver   STRING      NOT NULL,
  computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT clause_blame_closure_pk PRIMARY KEY (clause_uuid, as_of_commit, closure_gen),
  CONSTRAINT sev_range CHECK (max_severity BETWEEN 0 AND 5),
  CONSTRAINT gen_positive CHECK (closure_gen >= 0),
  CONSTRAINT depth_nonneg CHECK (depth >= 0),
  CONSTRAINT depth_within_cap CHECK (depth <= 64),
  CONSTRAINT ancestor_count_nonneg CHECK (ancestor_count >= 0),
  CONSTRAINT ancestor_count_within_cap CHECK (ancestor_count <= 512),
  CONSTRAINT truncation_is_declared
    CHECK (truncated = true OR (ancestor_count < 512 AND depth < 64)),
  CONSTRAINT count_matches_the_array
    CHECK (ancestor_count = coalesce(array_length(ancestor_events, 1), 0)),
  CONSTRAINT as_of_commit_is_sha256 CHECK (length(as_of_commit) = 32),
  CONSTRAINT computed_by_stated CHECK (computed_by <> ''),
  CONSTRAINT projector_ver_stated CHECK (projector_ver <> '')
);
--
CREATE TABLE mainline.permit (
  permit_id     UUID   NOT NULL DEFAULT gen_random_uuid(),
  site_code     STRING NOT NULL,
  state         mainline.subject_state NOT NULL DEFAULT 'draft',
  open_blocking INT8   NOT NULL DEFAULT 0,
  gate_epoch    INT8   NOT NULL DEFAULT 0,
  CONSTRAINT permit_pkey PRIMARY KEY (permit_id),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT open_blocking_nonneg CHECK (open_blocking >= 0)
);
--
CREATE TABLE mainline.blocking_check (
  check_id    UUID   NOT NULL DEFAULT gen_random_uuid(),
  permit_id   UUID   NOT NULL REFERENCES mainline.permit (permit_id),
  clause_uuid UUID   NOT NULL,
  severity    INT2   NOT NULL,
  origin      STRING NOT NULL,
  CONSTRAINT pk_blocking_check PRIMARY KEY (check_id),
  CONSTRAINT bc_severity_range CHECK (severity BETWEEN 0 AND 5)
);
--
CREATE TABLE mainline.disposition (
  disposition_id UUID        NOT NULL DEFAULT gen_random_uuid(),
  check_id       UUID        NOT NULL REFERENCES mainline.blocking_check (check_id),
  retracted_by   UUID        NULL,
  expires_at     TIMESTAMPTZ NULL,
  CONSTRAINT pk_disposition PRIMARY KEY (disposition_id)
);
--
CREATE TABLE mainline.permit_event (
  permit_id     UUID   NOT NULL,
  seq           INT8   NOT NULL,
  prev_seq      INT8   NOT NULL,
  from_state    mainline.subject_state NOT NULL,
  to_state      mainline.subject_state NOT NULL,
  subject_kind  STRING NOT NULL DEFAULT 'permit',
  actor_sub     STRING NOT NULL,
  payload       JSONB  NOT NULL,
  prev_digest   BYTES  NOT NULL,
  at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  chain_digest  BYTES  AS (digest(prev_digest || payload::STRING::BYTES, 'sha256')) STORED,
  CONSTRAINT permit_event_kind_pinned CHECK (subject_kind = 'permit'),
  CONSTRAINT permit_event_seq_ordered CHECK (seq > prev_seq AND prev_seq >= 0),
  CONSTRAINT permit_event_prev_digest_sized CHECK (length(prev_digest) = 32),
  CONSTRAINT permit_event_actor_stated CHECK (actor_sub <> ''),
  CONSTRAINT fk_permit_event_subject FOREIGN KEY (permit_id)
    REFERENCES mainline.permit (permit_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT pk_permit_event PRIMARY KEY (permit_id, seq),
  CONSTRAINT linear UNIQUE (permit_id, prev_seq)
);
--
CREATE FUNCTION mainline.fn_refuse_mutation() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='P0001',
    MESSAGE='MAINLINE: this table is append-only; write a new row';
END $$;
--
CREATE FUNCTION mainline.fn_permit_event_chain() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_existing INT8;
  v_expected BYTES;
BEGIN
  IF (NEW).seq = 0 THEN
    RETURN NEW;
  END IF;
  SELECT count(*) INTO v_existing
    FROM mainline.permit_event e0
   WHERE e0.permit_id = (NEW).permit_id;
  IF v_existing = 0 THEN
    RETURN NEW;
  END IF;
  SELECT e.chain_digest INTO v_expected
    FROM mainline.permit_event e
   WHERE e.permit_id = (NEW).permit_id
     AND e.seq = (NEW).prev_seq;
  IF v_expected IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no predecessor event for the declared prev_seq';
  END IF;
  IF v_expected IS DISTINCT FROM (NEW).prev_digest THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: prev_digest does not match the predecessor chain digest';
  END IF;
  RETURN NEW;
END $$;
--
CREATE FUNCTION mainline.fn_permit_merge_gate() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_subject   UUID;
  v_projected INT8;
  v_derived   INT8;
BEGIN
  v_subject   := (NEW).permit_id;
  v_projected := (NEW).open_blocking;
  SELECT count(*) INTO v_derived
    FROM mainline.blocking_check bc
   WHERE bc.permit_id = v_subject
     AND NOT EXISTS (
           SELECT 1 FROM mainline.disposition d
            WHERE d.check_id = bc.check_id
              AND d.retracted_by IS NULL
              AND (d.expires_at IS NULL OR d.expires_at > now()));
  IF v_derived <> 0 AND v_projected = 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: merge refused by mainline.fn_permit_merge_gate'
                || ' — re-derived open obligation count is '
                || v_derived::STRING || ' while the projected counter reads zero';
  END IF;
  IF v_derived <> 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: merge refused by mainline.fn_permit_merge_gate'
                || ' — ' || v_derived::STRING || ' open obligation(s) carry no live disposition';
  END IF;
  RETURN NEW;
END $$;
--
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON mainline.clause_blame_closure
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_refuse_mutation();
--
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON mainline.permit_event
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_refuse_mutation();
--
CREATE TRIGGER permit_event_chain BEFORE INSERT ON mainline.permit_event
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_permit_event_chain();
--
CREATE TRIGGER permit_merge_gate BEFORE UPDATE ON mainline.permit
  FOR EACH ROW WHEN ((NEW).state = 'merged' AND (OLD).state <> 'merged')
  EXECUTE FUNCTION mainline.fn_permit_merge_gate();
"""


#: The separator between statements in :data:`FIXTURE_DDL`. A bare ``;`` split would cut
#: every PL/pgSQL body in half, because a trigger function's body contains semicolons.
_DDL_SEPARATOR = "\n--\n"


def fixture_statements() -> list[str]:
    """Split the fixture DDL on its ``--`` separator lines.

    A ``;`` split would cut every PL/pgSQL body in half, so the separator is explicit.
    """
    chunks = FIXTURE_DDL.split(_DDL_SEPARATOR)
    return [chunk.strip().rstrip(";").strip() for chunk in chunks if chunk.strip()]


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


@dataclass
class NemesisContext:
    """One throwaway database, seeded from the reference bundle, ready to be attacked."""

    conn: Any
    dsn: str
    site_code: str
    reference: dict[str, Any]
    provenance: str
    live_triggerdefs: dict[str, str] = field(default_factory=dict)

    def sql(self, statement: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        cur = self.conn.cursor()
        cur.execute(statement, params)
        return cur.fetchall() if cur.description else []

    def capture_triggerdefs(self) -> dict[str, str]:
        """Read the live trigger definitions straight out of the catalogue — ENABLED ONLY.

        GT-05 is answered: ``pg_get_triggerdef()`` works on CockroachDB v26.2.5, so check 11
        keeps per-trigger granularity and never falls back to ``SHOW CREATE TABLE``.

        ``tgenabled = 'D'`` is excluded, and that exclusion is the whole of A13's detection.
        ``ALTER TABLE … DISABLE TRIGGER`` leaves the row in ``pg_trigger`` with its
        definition text untouched, so a check that read ``pg_get_triggerdef()`` alone would
        report a gate that has stopped running as present and correct — a verifier that
        passes because it did not look.
        """
        rows = self.sql(
            "SELECT c.relname || '.' || t.tgname, t.tgenabled, pg_get_triggerdef(t.oid) "
            "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE NOT t.tgisinternal"
        )
        self.live_triggerdefs = {
            str(name): str(definition) for name, enabled, definition in rows if str(enabled) != "D"
        }
        return self.live_triggerdefs


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


class OutcomeRecorder:
    """Collects one :class:`attacks.AttackOutcome` per attack and writes the run record.

    The matrix is generated from THIS, never from ``spec/custody/attacks.yaml``: the
    registry records what we expect, and an expectation printed as a result is the exact
    dishonesty the ATTACK-DEPTH artefact exists to remove.
    """

    def __init__(self) -> None:
        self.outcomes: dict[str, dict[str, Any]] = {}
        self.environment: dict[str, Any] = {}

    def record(self, outcome: Any) -> None:
        self.outcomes[outcome.id] = outcome.as_dict()

    def write(self) -> None:
        if not self.outcomes:
            return
        RUN_RECORD.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "attacks": [self.outcomes[key] for key in sorted(self.outcomes, key=_attack_sort_key)],
            "environment": self.environment,
            "schema_version": 1,
        }
        RUN_RECORD.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _attack_sort_key(attack_id: str) -> int:
    return int(attack_id.lstrip("A"))


_RECORDER = OutcomeRecorder()


@pytest.fixture(scope="session")
def recorder() -> OutcomeRecorder:
    return _RECORDER


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # noqa: ARG001
    """Write the run record, then regenerate the matrix from it.

    Written at session finish rather than per test so that a partial run produces a partial
    matrix that says which attacks did not run, instead of a matrix that silently omits
    them. ``matrix.py`` is what enforces the ATTACK-DEPTH rule over the result.
    """
    if not _RECORDER.outcomes:
        return
    _RECORDER.write()
    try:
        import matrix as matrix_module
    except ImportError:  # pragma: no cover — the module sits beside this file
        return
    matrix_module.write_matrix(RUN_RECORD, REPO_ROOT / "evidence" / "CUSTODY_ATTACK_MATRIX.md")
