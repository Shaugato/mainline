# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Tier-3 schema suite for the RLS band — migrations 0180-0199 (``dm-views-rls``).

Four tables carry row-level security, and each is here for a different reason:

* ``mainline.permit`` and ``mainline.change_request`` — site scoping across a fleet, plus the
  S22 write set that keeps the gate from locking itself out;
* ``mainline.disposition`` — ``peer_blind``, which is the reason RLS is in this system at all.
  It binds a person who legitimately holds ``SELECT`` and stops "I'll sign what Dave signed".
  Access control doing epistemics;
* ``mainline_meas.standing`` — ``standing_blind``, ``USING (false)``: not "your own row", nothing
  at all, because M10's peer-prediction channel is defeated by a participant who can see the
  scoring.

And two tables on which enabling RLS is FORBIDDEN — ``mainline_ops.outbox`` and
``mainline_ops.site_register_signal``. CDC queries are not supported on RLS-enabled tables and
FAIL, so enabling RLS there would not harden anything; it would stop the event spine at the next
changefeed restart, which stops the blame-closure projector, which makes every gate read a stale
projection. A negative assertion beside the positive ones.

**SEC-1, before anything below is read.** RLS is tenancy hygiene and information partitioning. It
is NOT tamper-evidence and NOT a defence against a privileged operator: admin bypasses it, CDC
ignores it, ``TRUNCATE`` / ``BACKUP`` / ``RESTORE`` / replication all bypass it, and a role may
carry ``BYPASSRLS``. **The ledger is the rogue-DBA control.** Nothing in this file should be cited
for a claim wider than that.

The finding this suite exists to pin
------------------------------------
S22 and §11.3 both describe a missing write policy's symptom as ``42501``. Measured against
CockroachDB CCL v26.2.5 on 2026-08-10, that is **true for INSERT and false for UPDATE**: a
``USING`` clause filters, only a ``WITH CHECK`` violation raises, so dropping ``gate_write``
produces **no error and zero rows updated**. In this schema ``fn_check_materialised`` then returns
normally with ``open_blocking`` still zero, and ``gate_closed_when_issued`` passes vacuously —
a missing UPDATE policy silently disarms the central invariant.
``test_cf22_dropping_the_update_policy_is_silent_not_refused`` asserts the DANGEROUS behaviour
deliberately, because a test written to expect ``42501`` would fail honestly today and be
"repaired" tomorrow by relaxing it, at which point the finding is gone.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from trappoint_testkit import pinned_image

psycopg = pytest.importorskip("psycopg", reason="psycopg 3 is required to talk to CockroachDB")
yaml = pytest.importorskip("yaml", reason="PyYAML is required to read RLS-MATRIX.yaml")

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "verticals" / "mainline" / "db"
MIGRATIONS_DIR = DB_DIR / "migrations"
MATRIX_PATH = DB_DIR / "RLS-MATRIX.yaml"

MR5_FILENAME = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE") or pinned_image(Path(__file__))
CONTAINER_NAME = "mainline-test-rls"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 20.0
DOCKER_RUN_TIMEOUT_S = 180.0

QA_OBJECTS = ("v_disposition_profile", "v_standing_components", "v_my_record")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The matrix, and a parser for the SQL that renders it
# ══════════════════════════════════════════════════════════════════════════════════════════════


def load_matrix() -> dict[str, Any]:
    return yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))


MATRIX = load_matrix()


def declared_policies() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for table in MATRIX["tables"]:
        for policy in table["policies"]:
            entry = dict(policy)
            entry["table"] = table["table"]
            out.append(entry)
    return out


def declared_tables() -> list[dict[str, Any]]:
    return list(MATRIX["tables"])


def strip_sql_comments(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        out.append("''")
                        i += 2
                        continue
                    out.append("'")
                    i += 1
                    break
                out.append(text[i])
                i += 1
            continue
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


_POLICY_RE = re.compile(
    r"CREATE\s+POLICY\s+(?P<name>[a-z0-9_]+)\s+ON\s+(?P<table>[a-z0-9_]+\.[a-z0-9_]+)\s+"
    r"AS\s+(?P<type>PERMISSIVE|RESTRICTIVE)\s+FOR\s+(?P<cmd>SELECT|INSERT|UPDATE|DELETE|ALL)\s+"
    r"TO\s+(?P<roles>[A-Za-z0-9_,\s]+?)\s*"
    r"(?:USING\s*\((?P<using>.*?)\)\s*)?"
    r"(?:WITH\s+CHECK\s*\((?P<check>.*?)\)\s*)?;",
    re.IGNORECASE | re.DOTALL,
)


def parse_policy_file(path: Path) -> dict[str, Any]:
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    match = _POLICY_RE.search(code)
    assert match is not None, f"{path.name}: could not parse a CREATE POLICY statement from it"
    roles = [r.strip() for r in match.group("roles").split(",") if r.strip()]
    return {
        "name": match.group("name"),
        "table": match.group("table"),
        "type": match.group("type").upper(),
        "command": match.group("cmd").upper(),
        "to": roles,
        "using": norm(match.group("using")),
        "with_check": norm(match.group("check")),
    }


def norm(expr: str | None) -> str | None:
    if expr is None:
        return None
    return " ".join(expr.split()).strip()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STATIC TIER — the matrix and the SQL that renders it must agree, exactly
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_matrix_file_exists_and_declares_four_tables() -> None:
    """RLS earns its place on a table only where two principals who both hold the privilege must
    see different rows. That is true of exactly four tables; adding a fifth is a decision, and a
    decision made by editing a YAML list is a decision this test makes visible."""
    assert MATRIX_PATH.exists()
    tables = [t["table"] for t in declared_tables()]
    assert tables == [
        "mainline.permit",
        "mainline.change_request",
        "mainline.disposition",
        "mainline_meas.standing",
    ], f"the matrix declares {tables}"


@pytest.mark.parametrize(
    "table", declared_tables(), ids=lambda t: t["table"] if isinstance(t, dict) else str(t)
)
def test_every_declared_table_forces_row_level_security(table: dict[str, Any]) -> None:
    """FORCE, on all four, without exception.

    Without it the table owner reads and writes past every policy — and, because a view evaluates
    its base-table access as its owner, that exemption is reachable by every view in
    ``mainline_audit`` and ``mainline_qa``. FORCE is what makes the partition total; the one
    named exception per table is ``view_owner_read``, which is a diffable, revocable object
    rather than an invisible exemption.
    """
    assert table["force"] is True
    for key in ("migration_enable", "migration_force"):
        path = MIGRATIONS_DIR / f"{table[key]}.sql"
        assert path.exists(), f"{table['table']}: {key} names a file that does not exist: {path}"
    enable = (MIGRATIONS_DIR / f"{table['migration_enable']}.sql").read_text(encoding="utf-8")
    force = (MIGRATIONS_DIR / f"{table['migration_force']}.sql").read_text(encoding="utf-8")
    assert f"ALTER TABLE {table['table']}\n  ENABLE ROW LEVEL SECURITY" in enable or (
        f"ALTER TABLE {table['table']} ENABLE ROW LEVEL SECURITY" in enable
    )
    assert f"ALTER TABLE {table['table']} FORCE ROW LEVEL SECURITY" in force


@pytest.mark.parametrize(
    "policy", declared_policies(), ids=lambda p: p["name"] if isinstance(p, dict) else str(p)
)
def test_every_declared_policy_has_a_file_that_renders_it_exactly(policy: dict[str, Any]) -> None:
    """The matrix is the declaration and the migration is its rendering. A rendering that has
    drifted from its declaration is two sources of truth, which is the class of failure the
    migration reconciliation of 2026-08-08 exists to end."""
    path = MIGRATIONS_DIR / f"{policy['migration']}.sql"
    assert path.exists(), f"{policy['name']}: no such migration {path}"
    parsed = parse_policy_file(path)
    assert parsed["name"] == policy["name"]
    assert parsed["table"] == policy["table"]
    assert parsed["type"] == policy["type"]
    assert parsed["command"] == policy["command"]
    declared_roles = [str(r) for r in policy["to"]]
    assert [r.lower() for r in parsed["to"]] == [r.lower() for r in declared_roles], (
        f"{policy['name']}: SQL names {parsed['to']}, matrix declares {declared_roles}"
    )
    assert parsed["using"] == norm(policy.get("using")), (
        f"{policy['name']}: USING drifted — SQL {parsed['using']!r} vs matrix "
        f"{norm(policy.get('using'))!r}"
    )
    assert parsed["with_check"] == norm(policy.get("with_check")), (
        f"{policy['name']}: WITH CHECK drifted — SQL {parsed['with_check']!r} vs matrix "
        f"{norm(policy.get('with_check'))!r}"
    )


def test_no_policy_expression_contains_a_subquery() -> None:
    """§4.1 law 10, and the v26.2 ``CREATE POLICY`` reference: policy expressions cannot contain
    a subexpression. This test is not redundant with the platform's own refusal — it also
    catches an expression that a future CockroachDB might ACCEPT, which is worse, because the
    design's whole scope argument rests on a denormalised role-name token rather than on a
    membership lookup a policy could be tempted to perform."""
    for policy in declared_policies():
        for key in ("using", "with_check"):
            expr = policy.get(key)
            if not expr:
                continue
            assert not re.search(r"\bSELECT\b", str(expr), re.IGNORECASE), (
                f"{policy['name']}.{key} contains a subquery: {expr!r}"
            )


def test_no_policy_expression_reads_a_session_variable() -> None:
    """A session variable is client-settable, and scoping on one would degrade RLS to an
    application-cooperative control against exactly the adversary it is meant to constrain.
    ``CURRENT_USER`` changes only via ``SET ROLE``, which succeeds only for granted roles, and
    the grant graph is alterable only by the provisioning service account."""
    for policy in declared_policies():
        for key in ("using", "with_check"):
            expr = str(policy.get(key) or "")
            assert "current_setting" not in expr.lower(), (
                f"{policy['name']}.{key} reads a session variable: {expr!r}"
            )


def test_every_role_named_by_a_policy_is_declared_in_the_matrix_role_list() -> None:
    """CockroachDB refuses ``TO <unknown role>`` at DDL time, but it ACCEPTS a role that exists
    and is simply the wrong one. Only an explicit list catches that."""
    known = {str(r) for r in MATRIX["roles_referenced"]} | {"PUBLIC"}
    for policy in declared_policies():
        for role in policy["to"]:
            assert str(role) in known, f"{policy['name']} names undeclared role {role!r}"


def test_the_scope_shape_is_the_documented_safe_one() -> None:
    """Every site-scoping policy is ``col = CURRENT_USER`` over a denormalised role-name token.
    Nothing cleverer is expressible, and anything cleverer that became expressible would be a
    membership lookup wearing a policy's clothes."""
    scopes = [p for p in declared_policies() if p["name"].endswith("site_scope")]
    assert len(scopes) == 2, "both gated subjects carry a site scope"
    for policy in scopes:
        assert norm(policy["using"]) == "site_role = CURRENT_USER"


def test_the_forbidden_tables_are_never_rls_enabled_anywhere_in_the_tree() -> None:
    """§4.1 law 11. ``mainline_ops.outbox`` is the one CDC-query source and
    ``site_register_signal`` is the mechanism-predicate watch source. CDC queries FAIL on
    RLS-enabled tables, so an ``ENABLE ROW LEVEL SECURITY`` on either is not a hardening — it is
    a fleet outage that passes schema review and detonates at the next changefeed restart."""
    forbidden = [t["table"] for t in MATRIX["rls_forbidden"]]
    assert forbidden == ["mainline_ops.outbox", "mainline_ops.site_register_signal"]
    for path in MIGRATIONS_DIR.iterdir():
        if not path.is_file() or not MR5_FILENAME.match(path.name):
            continue
        code = strip_sql_comments(path.read_text(encoding="utf-8"))
        for table in forbidden:
            assert not re.search(
                rf"ALTER\s+TABLE\s+{re.escape(table)}\s+(ENABLE|FORCE)\s+ROW\s+LEVEL\s+SECURITY",
                code,
                re.IGNORECASE,
            ), f"{path.name} enables RLS on {table}"


def test_every_forced_table_that_a_trigger_writes_carries_a_write_policy() -> None:
    """S22, as a static closure check over the matrix rather than as a memory.

    For each declared table, the set of commands covered by at least one PERMISSIVE policy must
    include every command a trigger or the gate issues against it. A SELECT-only matrix under
    FORCE is the exact configuration that locks the gate out of its own tables.
    """
    required = {
        "mainline.permit": {"SELECT", "INSERT", "UPDATE"},
        "mainline.change_request": {"SELECT", "INSERT", "UPDATE"},
        "mainline.disposition": {"SELECT", "INSERT", "UPDATE"},
        "mainline_meas.standing": {"SELECT", "INSERT"},
    }
    for table in declared_tables():
        covered = {p["command"] for p in table["policies"] if p["type"] == "PERMISSIVE"}
        missing = required[table["table"]] - covered
        assert missing == set(), (
            f"{table['table']} is FORCE ROW LEVEL SECURITY with no permissive policy for "
            f"{sorted(missing)}. That is S22: the default is DENY and the gate locks itself out."
        )


def test_the_gate_write_policy_names_both_writer_roles() -> None:
    """§11.3 writes ``TO agent_gate``. That is incomplete: ``fn_disposition_close`` and
    ``fn_disposition_retract_only`` UPDATE the same counters as ``svc_disposition``, because no
    trigger function in migrations 0100-0149 is ``SECURITY DEFINER``. Omitting the second role
    yields a system that opens permits and materialises checks and then fails at the moment a
    human signs something."""
    for name in ("gate_write", "cr_gate_write"):
        policy = next(p for p in declared_policies() if p["name"] == name)
        assert set(policy["to"]) == {"agent_gate", "svc_disposition"}, (
            f"{name} names {policy['to']}"
        )


def test_no_trigger_function_is_security_definer() -> None:
    """The premise the whole write-policy set rests on, asserted rather than assumed.

    If any projection trigger were ``SECURITY DEFINER`` it would execute as its owner and the
    invoking role would need no write policy at all — at which point half this band is dead
    weight and ``GRANTS.yaml``'s open-coupling note is stale. Recording the premise as a test
    means the day somebody takes that (better) option, this file says so.
    """
    hits = [
        path.name
        for path in MIGRATIONS_DIR.iterdir()
        if path.is_file()
        and MR5_FILENAME.match(path.name)
        and "SECURITY DEFINER" in strip_sql_comments(path.read_text(encoding="utf-8")).upper()
    ]
    assert hits == [], (
        f"these files declare SECURITY DEFINER: {hits}. If that is intended, the write policies "
        "in 0181g/0183g/0185f/0185g/0187d can lose their invoking roles and GRANTS.yaml's "
        "mainline_ops.outbox coupling note can be closed — but both must move together."
    )


def test_the_deferred_cycle_fk_is_the_last_file_in_the_tree() -> None:
    """0199 is the terminal allocated number; 0200 and above is UNALLOCATED and lint refuses it.
    The edge that could not be created earlier belongs at the only position that is after
    everything."""
    path = MIGRATIONS_DIR / "0199_exposure_receipt_fk_silence.sql"
    assert path.exists()
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    assert "ADD CONSTRAINT fk_silence FOREIGN KEY (silence_receipt_id)" in code
    assert "mainline_meas.silence_receipt (silence_receipt_id)" in code
    assert "ON UPDATE RESTRICT ON DELETE RESTRICT" in code
    last = max(
        (p.name for p in MIGRATIONS_DIR.iterdir() if p.is_file() and MR5_FILENAME.match(p.name)),
        key=lambda n: n.removesuffix(".sql"),
    )
    assert last == path.name, f"the last file in the tree is {last}, not the deferred cycle FK"


def test_no_file_claims_an_unallocated_number() -> None:
    """MR-6 lock 1 / MR-7: ``0200`` and above is UNALLOCATED, in either mode. A number space with
    no owner is exactly what produced two conventions."""
    strays = sorted(
        p.name
        for p in MIGRATIONS_DIR.iterdir()
        if p.is_file() and MR5_FILENAME.match(p.name) and int(p.name[:4]) >= 200
    )
    assert strays == [], f"files at or above 0200: {strays}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLUSTER TIER
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Cluster:
    dsn: str
    provenance: str
    proc: subprocess.Popen[bytes] | None = None
    owns_docker: bool = False


@dataclass
class Bound:
    dsn: str
    database: str
    blocked: list[tuple[str, str]]

    def connect(self, user: str | None = None) -> Any:
        from psycopg.conninfo import make_conninfo

        dsn = self.dsn if user is None else make_conninfo(self.dsn, user=user)
        return psycopg.connect(dsn, autocommit=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_until_ready(dsn: str, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
        except Exception:  # noqa: BLE001
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


def _from_env() -> Cluster | None:
    for name in ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN"):
        value = os.environ.get(name)
        if value:
            return Cluster(dsn=value, provenance=f"${name}")
    return None


def _from_local_binary(tmp: Path) -> Cluster | None:
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
        return Cluster(dsn=dsn, provenance=f"local `cockroach` binary on {port}", proc=proc)
    proc.terminate()
    return None


def _from_docker() -> Cluster | None:
    if shutil.which("docker") is None:
        return None
    probe = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=DOCKER_PROBE_TIMEOUT_S)
    if probe is None or probe.returncode != 0:
        return None
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    port = _free_port()
    started = _docker(
        [
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "-p",
            f"{port}:26257",
            CRDB_IMAGE,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
        ],
        timeout=DOCKER_RUN_TIMEOUT_S,
    )
    if started is None or started.returncode != 0:
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on {port}", owns_docker=True)
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    return None


def _split(text: str) -> list[str]:
    body = strip_sql_comments(text)
    out, cur, i, n = [], [], 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "$":
            m = re.compile(r"\$(?:[A-Za-z_]\w*)?\$").match(body, i)
            if m:
                tag = m.group(0)
                close = body.find(tag, m.end())
                end = n if close == -1 else close + len(tag)
                cur.append(body[i:end])
                i = end
                continue
        if ch == "'":
            cur.append(ch)
            i += 1
            while i < n:
                if body[i] == "'":
                    if i + 1 < n and body[i + 1] == "'":
                        cur.append("''")
                        i += 2
                        continue
                    cur.append("'")
                    i += 1
                    break
                cur.append(body[i])
                i += 1
            continue
        if ch == ";":
            s = "".join(cur).strip()
            if s:
                out.append(s)
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out


@pytest.fixture(scope="session")
def rls_cluster(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Cluster]:
    try:
        shared = request.getfixturevalue("dsn")
    except Exception:  # noqa: BLE001
        shared = None
    if isinstance(shared, str) and shared:
        yield Cluster(dsn=shared, provenance="the `dsn` fixture from tests/integration/schema")
        return
    found = _from_env() or _from_local_binary(tmp_path_factory.mktemp("crdb")) or _from_docker()
    if found is None:
        pytest.skip(
            "no CockroachDB v26.2 reachable. Provide a session `dsn` fixture, $MAINLINE_TEST_DSN, "
            f"a `cockroach` binary on PATH, or Docker for `docker run {CRDB_IMAGE}`. "
            "The RLS matrix is NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.proc is not None:
            found.proc.terminate()
        if found.owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


@pytest.fixture(scope="session")
def bound(rls_cluster: Cluster) -> Iterator[Bound]:
    """Apply the tree, then create ONE LOGIN USER PER ROLE UNDER TEST.

    Two things this fixture does deliberately, both of which are about not testing a mirage.

    1. **It does not test as ``root``.** Admin users bypass RLS entirely (v26.2 row-level-security
       reference), so a suite that connects as ``root`` and calls ``SET ROLE`` is asserting
       against a session that may never have been subject to a policy at all. Each probe
       therefore connects as its own non-admin login user which has been GRANTed the role.
    2. **It grants the table privileges itself.** ``GRANTS.yaml`` is applied by
       ``trappoint-migrate grants apply``, not by a migration (DM-7), and this suite is about
       RLS rather than about grants. Granting explicitly here means a policy failure cannot be
       mistaken for a missing privilege, and vice versa — the two layers stay separately
       falsifiable, which is the entire point of having three of them.
    """
    from psycopg.conninfo import make_conninfo

    database = f"mainline_rls_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(rls_cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")
    dsn = make_conninfo(rls_cluster.dsn, dbname=database)

    blocked: list[tuple[str, str]] = []
    paths = sorted(
        (p for p in MIGRATIONS_DIR.iterdir() if p.is_file() and MR5_FILENAME.match(p.name)),
        key=lambda p: p.name.removesuffix(".sql"),
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in paths:
            for statement in _split(path.read_text(encoding="utf-8")):
                try:
                    conn.execute(statement)
                except psycopg.Error as exc:
                    blocked.append((path.name, str(exc).splitlines()[0]))

        for user, role in PROBE_USERS.items():
            conn.execute(f"CREATE USER IF NOT EXISTS {user}")
            try:
                conn.execute(f"GRANT {role} TO {user}")
            except psycopg.Error as exc:  # a role a template has not created yet
                blocked.append(("probe-users", f"GRANT {role} TO {user}: {exc}"))
        # mainline_auditor is EXCLUDED from every blanket grant below, deliberately and by name.
        # It is the Managed-MCP identity, and GRANTS.yaml gives it SELECT on `mainline_audit`
        # and INSERT on exactly one measurement table — nothing in `mainline`, nothing in
        # `mainline_qa`, on any tier, ever (S13, S14). A fixture that handed it the same
        # convenience grants as the service roles would make the two negative assertions in
        # this file pass against a cluster where they could not possibly hold, which is the
        # single most misleading thing this suite could do.
        workers = sorted(set(PROBE_USERS.values()) - {"mainline_auditor"})
        conn.execute(
            "GRANT USAGE ON SCHEMA mainline, mainline_meas, mainline_ops TO " + ", ".join(workers)
        )
        for schema in ("mainline", "mainline_meas", "mainline_ops"):
            conn.execute(
                f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA {schema} TO "
                + ", ".join(workers)
            )
        conn.execute("GRANT USAGE ON SCHEMA mainline_audit TO mainline_auditor")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA mainline_audit TO mainline_auditor")

    print(
        f"\n[rls] cluster:  {rls_cluster.provenance}\n"
        f"[rls] database: {database}\n"
        f"[rls] applied {len(paths)} migrations, {len(blocked)} statements blocked"
    )
    try:
        yield Bound(dsn=dsn, database=database, blocked=blocked)
    finally:
        with psycopg.connect(rls_cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


#: login user -> role it is granted. Non-admin, so RLS actually applies to them.
PROBE_USERS: dict[str, str] = {
    "probe_gate": "agent_gate",
    "probe_disposer": "svc_disposition",
    "probe_signer": "signer",
    "probe_assay": "agent_assay",
    "probe_fleet": "fleet_hse",
    "probe_auditor": "mainline_auditor",
}


@pytest.fixture
def conn(bound: Bound) -> Iterator[Any]:
    connection = bound.connect()
    try:
        yield connection
    finally:
        connection.close()


RLS_FILES = (
    tuple(f"{t['migration_enable']}.sql" for t in declared_tables())
    + tuple(f"{t['migration_force']}.sql" for t in declared_tables())
    + tuple(f"{p['migration']}.sql" for p in declared_policies())
    + (
        "0180_disposition_peer_visible.sql",
        "0198x_no_rls_on_cdc_sources.sql",
        "0199_exposure_receipt_fk_silence.sql",
    )
)


@pytest.mark.requires_cluster
def test_the_rls_band_applies_cleanly(bound: Bound) -> None:
    """Every file this band owns applied. Failures in other bands are printed but not asserted —
    aborting on a foreign failure would make this suite unrunnable whenever any of the other
    seven domains has a file in flight, and skipping would make it green while proving nothing.
    """
    mine = [(n, e) for n, e in bound.blocked if n in set(RLS_FILES)]
    assert mine == [], (
        "files in the RLS band did not apply:\n"
        + "\n".join(f"  {n}: {e}" for n, e in mine)
        + "\n\nOther bands' failures in the same run (informational):\n"
        + "\n".join(f"  {n}: {e}" for n, e in bound.blocked if n not in set(RLS_FILES))
    )


@pytest.mark.requires_cluster
@pytest.mark.parametrize(
    "table", declared_tables(), ids=lambda t: t["table"] if isinstance(t, dict) else str(t)
)
def test_the_cluster_has_rls_enabled_and_forced(conn: Any, table: dict[str, Any]) -> None:
    schema, name = table["table"].split(".")
    row = conn.execute(
        "SELECT cl.relrowsecurity, cl.relforcerowsecurity FROM pg_class cl "
        "JOIN pg_namespace n ON n.oid = cl.relnamespace "
        "WHERE n.nspname = %s AND cl.relname = %s",
        (schema, name),
    ).fetchone()
    assert row is not None, f"{table['table']} does not exist"
    assert row == (True, True), (
        f"{table['table']}: (enabled, forced) is {row}. FORCE is what makes the owner — and "
        "therefore every view — subject to the same partition as everyone else."
    )


@pytest.mark.requires_cluster
def test_the_cluster_matches_the_declared_matrix(conn: Any) -> None:
    """No extra policy, no missing policy, no altered role list. DM-10: the policy name is the
    courtroom exhibit, and an exhibit nobody enumerated is an exhibit nobody can produce."""
    rows = conn.execute(
        "SELECT schemaname || '.' || tablename, policyname, permissive, cmd, roles "
        "FROM pg_policies ORDER BY 1, 2"
    ).fetchall()
    in_cluster = {(r[0], r[1]): (r[2].upper(), r[3].upper(), sorted(r[4])) for r in rows}
    declared = {
        (p["table"], p["name"]): (
            p["type"],
            p["command"],
            sorted(str(r).lower() for r in p["to"]),
        )
        for p in declared_policies()
    }
    assert set(in_cluster) == set(declared), (
        f"policy set drift.\n  only in cluster: {sorted(set(in_cluster) - set(declared))}\n"
        f"  only in matrix:  {sorted(set(declared) - set(in_cluster))}"
    )
    for key, expected in declared.items():
        actual = in_cluster[key]
        assert actual[0] == expected[0], (
            f"{key}: cluster says {actual[0]}, matrix declares {expected[0]}"
        )
        assert actual[1] == expected[1], (
            f"{key}: cluster applies it to {actual[1]}, matrix declares {expected[1]}"
        )
        assert actual[2] == expected[2], (
            f"{key}: cluster grants it to {actual[2]}, matrix declares {expected[2]}"
        )


@pytest.mark.requires_cluster
@pytest.mark.parametrize("table", [t["table"] for t in MATRIX["rls_forbidden"]])
def test_the_cdc_sources_have_no_row_level_security(conn: Any, table: str) -> None:
    """§4.1 law 11, asserted as the negative it is.

    CDC queries are not supported on RLS-enabled tables and FAIL. Enabling RLS on the outbox
    would not degrade the feed, it would stop it — and it would stop it at the next feed restart
    rather than at the ALTER, so the change and the outage are separated by however long the
    current feed happens to survive.
    """
    schema, name = table.split(".")
    row = conn.execute(
        "SELECT cl.relrowsecurity, cl.relforcerowsecurity FROM pg_class cl "
        "JOIN pg_namespace n ON n.oid = cl.relnamespace "
        "WHERE n.nspname = %s AND cl.relname = %s",
        (schema, name),
    ).fetchone()
    assert row is not None, f"{table} does not exist"
    assert row == (False, False), f"{table} has RLS enabled: {row}"
    policies = conn.execute(
        "SELECT policyname FROM pg_policies WHERE schemaname = %s AND tablename = %s",
        (schema, name),
    ).fetchall()
    assert policies == [], f"{table} carries policies: {policies}"


@pytest.mark.requires_cluster
def test_the_peer_visible_column_exists_and_defaults_closed(conn: Any) -> None:
    """DM-16. ``peer_blind`` reads ``peer_visible`` and §5.5 never defined it. The default is
    ``false`` — nothing is peer-visible until something makes it so — because a default of
    ``true`` would make the policy inert on every existing row while looking identical in
    ``SHOW CREATE``, which is the worst way for an information partition to fail."""
    row = conn.execute(
        "SELECT is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema = 'mainline' AND table_name = 'disposition' "
        "AND column_name = 'peer_visible'"
    ).fetchone()
    assert row is not None, "mainline.disposition.peer_visible does not exist"
    assert row[0] == "NO", (
        "peer_visible must be NOT NULL. A nullable projection has a third state nobody wrote a "
        "rule for, and `peer_visible = true` is NULL for it — indistinguishable at the read from "
        "false, which is a partition with an undocumented mode."
    )
    assert "false" in str(row[1]).lower()


# ── S22 / CF-22, and the measured asymmetry that S22 does not state ───────────────────────────


def _sqlstate_of(conn: Any, statement: str) -> str | None:
    """Run *statement* and return the SQLSTATE it refused with, or None if it succeeded.

    A helper rather than ``pytest.raises`` inside the loop because the assertion must be about
    the WHOLE set of objects — "every object in mainline_qa refused the MCP identity with 42501"
    — and a per-iteration raises() would stop at the first one, leaving the rest unprobed and the
    claim unproven for them.
    """
    try:
        conn.execute(statement)
    except psycopg.Error as exc:
        return exc.sqlstate
    return None


def _open_permit(conn: Any, *, site_role: str, ref: str) -> tuple[str, str]:
    permit_id, site_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, ref_name, "
        " horizon_at) VALUES (%s, %s, %s, %s, %s, now() + INTERVAL '1 day')",
        (permit_id, site_id, site_role, ref, f"refs/permits/{ref}"),
    )
    return permit_id, site_id


@pytest.mark.requires_cluster
def test_cf22_the_gate_transaction_survives_forced_rls(bound: Bound) -> None:
    """CF-22, positive half. With ``FORCE ROW LEVEL SECURITY`` active on ``mainline.permit``, the
    gate's own write path works: ``agent_gate`` opens the subject and moves its counters, and
    ``svc_disposition`` moves the same counters back — which is what ``fn_disposition_close``
    does from an AFTER INSERT trigger, as the invoking role, because nothing here is
    ``SECURITY DEFINER``.

    This is the reachable core of the gate transaction: the part RLS actually governs. The full
    merge procedure — receipt, exposure lines, checks, epoch pin — is the kernel's conformance
    corpus, which owns CF-22 proper. Asserting only what this band can construct is the honest
    boundary; claiming to have run the whole gate here would be claiming a fixture this file
    does not contain.
    """
    with bound.connect(user="probe_gate") as gate:
        permit_id, _ = _open_permit(
            gate, site_role="probe_gate", ref=f"CF22-{uuid.uuid4().hex[:6]}"
        )
        gate.execute(
            "UPDATE mainline.permit SET open_blocking = open_blocking + 1 WHERE permit_id = %s",
            (permit_id,),
        )
        assert gate.execute(
            "SELECT open_blocking FROM mainline.permit WHERE permit_id = %s", (permit_id,)
        ).fetchone() == (1,)

    with bound.connect(user="probe_disposer") as disposer:
        affected = disposer.execute(
            "UPDATE mainline.permit SET open_blocking = open_blocking - 1 WHERE permit_id = %s",
            (permit_id,),
        ).rowcount
        assert affected == 1, (
            "svc_disposition could not update the permit counter under forced RLS. That is S22 "
            "exactly: fn_disposition_close runs as this role and would fail at the moment a "
            "human signs something."
        )


@pytest.mark.requires_cluster
def test_cf22_dropping_the_insert_policy_refuses_with_42501(bound: Bound) -> None:
    """PL-2. The positive half above asserts nothing on its own — a transaction that would have
    succeeded with RLS switched off proves only that RLS was switched off. The pair is the
    assertion, and on the INSERT arm the refusal is loud and correct."""
    with bound.connect() as admin:
        admin.execute("DROP POLICY gate_insert ON mainline.permit")
    try:
        with (
            bound.connect(user="probe_gate") as gate,
            pytest.raises(psycopg.Error) as excinfo,
        ):
            _open_permit(gate, site_role="probe_gate", ref=f"NOPOL-{uuid.uuid4().hex[:6]}")
        assert excinfo.value.sqlstate == "42501", (
            f"expected 42501, got {excinfo.value.sqlstate}: {excinfo.value}"
        )
        assert "row-level security" in str(excinfo.value).lower()
    finally:
        with bound.connect() as admin:
            admin.execute(
                "CREATE POLICY gate_insert ON mainline.permit "
                "AS PERMISSIVE FOR INSERT TO agent_gate WITH CHECK (true)"
            )


@pytest.mark.requires_cluster
def test_cf22_dropping_the_update_policy_is_silent_not_refused(bound: Bound) -> None:
    """⚠ THE FINDING. Measured on CockroachDB CCL v26.2.5, 2026-08-10.

    S22 and §11.3 both say a missing write policy yields ``42501``. That is TRUE FOR INSERT and
    FALSE FOR UPDATE: a ``USING`` clause FILTERS and only a ``WITH CHECK`` violation on a NEW row
    RAISES, so with no UPDATE policy there is no visible row to update and there is nothing to
    refuse. The statement returns successfully having changed nothing.

    In this schema that is worse than a refusal. ``fn_check_materialised`` runs
    ``UPDATE mainline.permit SET open_blocking = open_blocking + 1`` and does not check that the
    update landed, so the trigger returns normally, the blocking check row exists, and
    ``open_blocking`` stays zero — after which
    ``gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0)`` passes vacuously
    and the permit merges carrying an open obligation.

    **This test asserts the dangerous behaviour on purpose.** Written as "expect 42501" it would
    fail honestly today and be repaired tomorrow by relaxing it into agreement with the platform,
    at which point the finding is gone. The durable fix is for the projection triggers to verify
    their own UPDATE affected a row and RAISE if it did not — P2's second half — which lives in
    migrations 0101, 0103 and 0104 and is recorded as a cross-domain note rather than patched
    from here.
    """
    with bound.connect(user="probe_gate") as gate:
        permit_id, _ = _open_permit(
            gate, site_role="probe_gate", ref=f"SILENT-{uuid.uuid4().hex[:6]}"
        )

    with bound.connect() as admin:
        admin.execute("DROP POLICY gate_write ON mainline.permit")
    try:
        with bound.connect(user="probe_disposer") as disposer:
            affected = disposer.execute(
                "UPDATE mainline.permit SET open_blocking = open_blocking + 1 WHERE permit_id = %s",
                (permit_id,),
            ).rowcount
        assert affected == 0, (
            "expected the UPDATE to match zero rows under a missing UPDATE policy; it matched "
            f"{affected}. If CockroachDB has started RAISING here instead, that is a PLATFORM "
            "CHANGE in our favour and this test should be rewritten to assert 42501 — with the "
            "⚠ blocks in RLS-MATRIX.yaml and 0181g updated in the same commit."
        )
        with bound.connect() as admin:
            assert admin.execute(
                "SELECT open_blocking FROM mainline.permit WHERE permit_id = %s", (permit_id,)
            ).fetchone() == (0,), "the counter moved despite the policy being absent"
    finally:
        with bound.connect() as admin:
            admin.execute(
                "CREATE POLICY gate_write ON mainline.permit "
                "AS PERMISSIVE FOR UPDATE TO agent_gate, svc_disposition "
                "USING (true) WITH CHECK (true)"
            )


@pytest.mark.requires_cluster
def test_dropping_the_service_read_policy_is_equally_silent(bound: Bound) -> None:
    """The same asymmetry reached through the SELECT policy rather than the UPDATE one.

    An UPDATE carrying a WHERE clause evaluates the SELECT policies too, so removing
    ``service_read`` makes the row invisible and the UPDATE matches nothing — with no error. That
    is why ``service_read`` is in this band at all: §11.3 lists only ``site_scope``,
    ``fleet_scope`` and the write policies, and a matrix built from that list alone would fail
    exactly here.
    """
    with bound.connect(user="probe_gate") as gate:
        permit_id, _ = _open_permit(
            gate, site_role="probe_gate", ref=f"NOREAD-{uuid.uuid4().hex[:6]}"
        )
    with bound.connect() as admin:
        admin.execute("DROP POLICY service_read ON mainline.permit")
    try:
        with bound.connect(user="probe_disposer") as disposer:
            affected = disposer.execute(
                "UPDATE mainline.permit SET open_blocking = open_blocking + 1 WHERE permit_id = %s",
                (permit_id,),
            ).rowcount
        assert affected == 0
    finally:
        with bound.connect() as admin:
            admin.execute(
                "CREATE POLICY service_read ON mainline.permit AS PERMISSIVE FOR SELECT "
                "TO agent_gate, svc_disposition, agent_recaller, agent_projector, "
                "agent_cartographer, agent_ingestor, agent_patroller, agent_fleet USING (true)"
            )


# ── the scopes and the partitions, exercised ──────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_site_scope_shows_a_site_reader_only_its_own_site(bound: Bound) -> None:
    """``USING (site_role = CURRENT_USER)`` over a projected NAME column. The reader's SQL role
    IS the scope token, and the token is not a value the inserter chooses."""
    ref = uuid.uuid4().hex[:6]
    with bound.connect() as admin:
        admin.execute("CREATE USER IF NOT EXISTS probe_site_a")
        admin.execute("CREATE USER IF NOT EXISTS probe_site_b")
        admin.execute("GRANT site_reader TO probe_site_a, probe_site_b")
        admin.execute("GRANT USAGE ON SCHEMA mainline TO site_reader")
        admin.execute("GRANT SELECT ON TABLE mainline.permit TO site_reader")
    with bound.connect(user="probe_gate") as gate:
        _open_permit(gate, site_role="probe_site_a", ref=f"SCOPE-A-{ref}")
        _open_permit(gate, site_role="probe_site_b", ref=f"SCOPE-B-{ref}")
    with bound.connect(user="probe_site_a") as reader:
        rows = reader.execute(
            "SELECT site_role FROM mainline.permit WHERE external_ref LIKE %s", (f"SCOPE-%{ref}",)
        ).fetchall()
    assert rows == [("probe_site_a",)], (
        f"site_reader probe_site_a saw {rows}; the scope token is CURRENT_USER and nothing else."
    )


@pytest.mark.requires_cluster
def test_fleet_scope_shows_a_fleet_reader_every_site(bound: Bound) -> None:
    """The one place in this matrix where an unscoped read is intended rather than conceded: a
    fleet safety function that can only see one site is not a fleet safety function."""
    ref = uuid.uuid4().hex[:6]
    with bound.connect() as admin:
        admin.execute("GRANT USAGE ON SCHEMA mainline TO fleet_hse")
        admin.execute("GRANT SELECT ON TABLE mainline.permit TO fleet_hse")
    with bound.connect(user="probe_gate") as gate:
        _open_permit(gate, site_role="probe_site_a", ref=f"FLEET-A-{ref}")
        _open_permit(gate, site_role="probe_site_b", ref=f"FLEET-B-{ref}")
    with bound.connect(user="probe_fleet") as reader:
        rows = reader.execute(
            "SELECT count(*) FROM mainline.permit WHERE external_ref LIKE %s", (f"FLEET-%{ref}",)
        ).fetchone()
    assert rows == (2,)


@pytest.mark.requires_cluster
def test_the_audit_views_can_see_through_forced_rls(bound: Bound) -> None:
    """The trap §11.3 does not mention, and the reason ``view_owner_read`` exists.

    A view evaluates RLS as its OWNER, and FORCE means the owner is not exempt. Without an owner
    policy, ``v_open_gate_summary`` returns ZERO ROWS over a table full of blocked permits — and
    zero rows on an audit surface is indistinguishable from a site with nothing wrong. That is
    the worst failure available to this band, because it is silent, plausible and reassuring.
    """
    ref = uuid.uuid4().hex[:6]
    with bound.connect(user="probe_gate") as gate:
        permit_id, _ = _open_permit(gate, site_role="probe_gate", ref=f"VIEW-{ref}")
        gate.execute(
            "UPDATE mainline.permit SET open_blocking = open_blocking + 3 WHERE permit_id = %s",
            (permit_id,),
        )
    with bound.connect() as admin:
        total = admin.execute(
            "SELECT coalesce(sum(open_blocking), 0) FROM mainline_audit.v_open_gate_summary"
        ).fetchone()
    assert total is not None, "the audit view returned no aggregate row at all"
    assert total[0] >= 3, (
        "the audit view reported no open blocking checks while the table holds three. Under "
        "FORCE ROW LEVEL SECURITY a view sees nothing unless its owner has a policy — check "
        "0181e view_owner_read."
    )


@pytest.mark.requires_cluster
def test_standing_blind_shows_a_signer_nothing_at_all(bound: Bound) -> None:
    """Not "your own row" — ``USING (false)``, nothing.

    M10's peer-prediction channel is defeated by a participant who can see the scoring, so a
    signer reading their own standing through the operational role would degrade the mechanism
    while looking like a privacy feature. SEC-3 condition (4) is served by
    ``mainline_qa.v_my_record`` under a different role, in a different schema, with a ledger
    entry attached.
    """
    if any("standing" in e for _, e in bound.blocked):
        pytest.fail(
            "mainline_meas.standing is absent from the applied tree (band 0090-0099z, "
            "dm-periphery). standing_blind cannot be exercised until it lands; this suite does "
            "not skip past an unverified partition."
        )
    with bound.connect() as admin:
        admin.execute("GRANT USAGE ON SCHEMA mainline_meas TO signer, agent_assay")
        admin.execute("GRANT SELECT, INSERT ON TABLE mainline_meas.standing TO signer, agent_assay")
        admin.execute(
            "GRANT SELECT, INSERT ON TABLE mainline_meas.person_measure_policy TO agent_assay"
        )
        policy_id = str(uuid.uuid4())
        admin.execute(
            "INSERT INTO mainline_meas.person_measure_policy (policy_id, measure_class, "
            " instrument_sha256, instrument_title, approved_by_sub, approved_at, "
            " notice_given_at, notice_sha256, notice_jurisdiction, effective_from) "
            "VALUES (%s, 'standing', %s, 'WHS QA Policy', 'officer', '2026-01-01', "
            " '2025-12-01', %s, 'AU-VIC', '2026-02-01')",
            (policy_id, b"\x11" * 32, b"\x22" * 32),
        )
        admin.execute(
            "INSERT INTO mainline_meas.standing (actor_sub, hazard_class, window_from, "
            " policy_id, policy_effective_from, s, components) "
            "VALUES ('probe_signer', 'isolation', '2026-03-01', %s, '2026-02-01', 1.0, "
            " '{\"W\": 1.0}'::JSONB)",
            (policy_id,),
        )
    with bound.connect(user="probe_signer") as signer:
        rows = signer.execute("SELECT count(*) FROM mainline_meas.standing").fetchone()
    assert rows == (0,), (
        f"a signer saw {rows} standing rows. standing_blind is RESTRICTIVE USING (false): the "
        "intended set is empty, including the signer's own row."
    )
    with bound.connect(user="probe_assay") as assay:
        rows = assay.execute("SELECT count(*) FROM mainline_meas.standing").fetchone()
    assert rows == (1,), "agent_assay computes the measure and must be able to read it back"


@pytest.mark.requires_cluster
def test_the_qa_schema_is_unreachable_from_the_mcp_identity(bound: Bound) -> None:
    """S14, as the negative assertion §17 says the nightly surface test must carry.

    No MCP service account is ever issued for ``mainline_qa``, on any tier, ever — a Managed-MCP
    account for per-named-person distributions is the single worst credential this system could
    issue. The control is the ABSENCE of the grant, so the test is the absence of the reach, and
    it walks every object in the schema rather than sampling one.
    """
    with bound.connect() as admin:
        present = {
            r[0]
            for r in admin.execute(
                "SELECT table_name FROM information_schema.views WHERE table_schema = 'mainline_qa'"
            ).fetchall()
        }
    assert present, "mainline_qa holds no views; the negative assertion would be vacuous"
    outcomes: dict[str, str | None] = {}
    for view in sorted(present):
        with bound.connect(user="probe_auditor") as auditor:
            # S608: `view` comes from information_schema on our own cluster, and an identifier
            # cannot be a bind parameter. The point of the loop is to walk EVERY object rather
            # than sample one, because S14 is a claim about the schema and not about a view.
            outcomes[view] = _sqlstate_of(
                auditor,
                f"SELECT 1 FROM mainline_qa.{view} LIMIT 1",  # noqa: S608
            )
    read_anyway = sorted(v for v, state in outcomes.items() if state is None)
    assert read_anyway == [], (
        f"mainline_auditor READ {read_anyway}. S14 is absolute: no MCP service account is ever "
        "issued for mainline_qa, on any tier, ever."
    )
    wrong_code = {v: s for v, s in outcomes.items() if s != "42501"}
    assert wrong_code == {}, (
        f"mainline_qa refused mainline_auditor with the wrong SQLSTATE: {wrong_code}"
    )
    assert set(outcomes) == present
    assert sorted(present) == sorted(QA_OBJECTS), (
        f"mainline_qa holds {sorted(present)}; the declared set is {sorted(QA_OBJECTS)}. An "
        "unenumerated view here is a per-named-person surface nobody reviewed."
    )


@pytest.mark.requires_cluster
def test_the_mcp_identity_cannot_read_the_business_schema_either(bound: Bound) -> None:
    """The auditor reads ``mainline_audit`` views and nothing else. This is a GRANT-layer
    assertion and it is in this file because the RLS matrix lists ``mainline_auditor`` in
    ``fleet_scope``, and a reader could take that listing for a reach it does not have."""
    with (
        bound.connect(user="probe_auditor") as auditor,
        pytest.raises(psycopg.Error) as excinfo,
    ):
        auditor.execute("SELECT 1 FROM mainline.disposition LIMIT 1")
    assert excinfo.value.sqlstate == "42501"


@pytest.mark.requires_cluster
def test_hold_blocks_delete_is_restrictive_and_unconditional_on_the_change_request(
    conn: Any,
) -> None:
    """Two shapes, one argument. The permit's DELETE policy is conditional on ``under_hold``
    because that column exists and carries the legal hold; the change request has no such column,
    so inventing one to make the mirror pretty would be adding a hold flag nothing maintains.
    The honest mirror is ``USING (false)`` — which is also the stronger of the two."""
    rows = {
        (r[0], r[1]): (r[2], r[3], r[4])
        for r in conn.execute(
            "SELECT tablename, policyname, permissive, cmd, qual FROM pg_policies "
            "WHERE cmd = 'DELETE'"
        ).fetchall()
    }
    permit = rows[("permit", "hold_blocks_delete")]
    assert permit[0].upper() == "RESTRICTIVE"
    assert "under_hold" in (permit[2] or "")
    cr = rows[("change_request", "cr_delete_never")]
    assert cr[0].upper() == "RESTRICTIVE"
    assert (cr[2] or "").strip().lower() in {"false", "(false)"}
    disposition = rows[("disposition", "disposition_delete_never")]
    assert disposition[0].upper() == "RESTRICTIVE"
    assert (disposition[2] or "").strip().lower() in {"false", "(false)"}
