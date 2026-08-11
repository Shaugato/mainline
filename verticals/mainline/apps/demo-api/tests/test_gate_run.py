# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The gate run, against a real migrated CockroachDB node.

These are not unit tests and are not pretending to be. Every assertion below is about what
a database did: the SQLSTATE it raised, the constraint it named, whether the name was
reported or parsed out of a message, and whether the rows were where they started
afterwards. A mock would assert that this worker's code agrees with this worker's code.

THE HARNESS lives in this module rather than in ``conftest.py`` because ``w4`` owns two
test files and not the conftest; ``test_transitions.py`` imports ``w4_database`` from here,
which pytest's default ``prepend`` import mode makes possible because the tests directory is
on ``sys.path``.

Its fixtures are named ``w4_database`` and ``w4_conn`` rather than ``demo_database`` and
``conn`` because ``w3-api-core-reads`` declares fixtures of the latter two names, with
different shapes, in ``tests/conftest.py``. A module-level fixture shadows a conftest one,
so the collision would have been silent rather than broken — and a silent shadow is exactly
the kind of thing that becomes a two-hour debugging session when somebody later deletes the
local definition. The two harnesses should converge on the conftest once it settles; that is
recorded as a cross-domain note rather than smuggled in.

THE SEED comes from ``scripts/proof/gate_refusal.py``, imported by path. That file already
builds the smallest history in which the claim is decidable and it is the artefact the
repository's central proof runs on; re-implementing a 300-line seeder here would create a
second history that could drift from the proven one. What the demo API needs is exactly
what that proof needs, which is the point.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
import pytest

# `requires_cluster` only. `verticals/mainline/apps/demo-api/pyproject.toml` runs with
# --strict-markers and registers exactly that one, so `integration` — which the repository
# root registers — would fail collection here. The narrower config wins because it is the
# one pytest resolves from this directory.
pytestmark = pytest.mark.requires_cluster

_HERE = Path(__file__).resolve()
_APP_SRC = _HERE.parents[1] / "src"
if str(_APP_SRC) not in sys.path:  # the app is not installed as a distribution yet
    sys.path.insert(0, str(_APP_SRC))

from mainline_demo_api import scenario as scenario_mod  # noqa: E402
from mainline_demo_api.gate_run import (  # noqa: E402
    ADMISSION_SQLSTATE,
    CF01_EXHIBIT,
    CF01_SQLSTATE,
    CF03_EXHIBIT,
    CF03_SQLSTATE,
    GATE_RUN_SCHEMA_ID,
    gate_run,
)

DEFAULT_DSN = "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable&connect_timeout=10"
SCRATCH_DB = os.environ.get("MAINLINE_W4_DATABASE", "w_w4_api_transitions")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _repo_root() -> Path:
    for candidate in (_HERE, *_HERE.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    raise RuntimeError("no workspace root above this test file")


def _admin_dsn() -> str:
    raw = (
        os.environ.get("MAINLINE_TEST_DSN")
        or os.environ.get("TRAPPOINT_DSN")
        or os.environ.get("COCKROACH_URL")
        or os.environ.get("CRDB_URL")
        or DEFAULT_DSN
    )
    if "connect_timeout" in raw:
        return raw
    return raw + ("&" if "?" in raw else "?") + "connect_timeout=10"


def _scratch_dsn() -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(_admin_dsn())
    return urlunsplit((parts.scheme, parts.netloc, f"/{SCRATCH_DB}", parts.query, parts.fragment))


def _gate_refusal_module() -> ModuleType:
    """Import ``scripts/proof/gate_refusal.py`` by path — the repository's own seeder."""
    path = _repo_root() / "scripts" / "proof" / "gate_refusal.py"
    spec = importlib.util.spec_from_file_location("w4_gate_refusal_seed", path)
    if spec is None or spec.loader is None:  # pragma: no cover - a broken checkout
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def seed_history_into(conn: psycopg.Connection[Any]) -> Any:
    """Seed one fresh demo history on *conn* and commit it. Returns the proof's History."""
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False
    conn.rollback()
    conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    history = _gate_refusal_module().seed_history(conn)
    conn.commit()
    if was_autocommit:
        conn.autocommit = True
    return history


#: The external reference ``scripts/proof/gate_refusal.py::seed_history`` gives its permit.
#: Selecting on it rather than on ``LIMIT 1`` is not fussiness: this suite deliberately
#: seeds MORE permits into the same database — the transitions are irreversible, so each
#: mutating test needs a subject of its own — and an unordered ``LIMIT 1`` picked one of
#: those on the second run, which made the demo permit look consumed. Measured, then fixed.
_DEMO_EXTERNAL_REF = "PTW-PROOF-1"

_DEMO_READY_SQL = """
SELECT p.permit_id, p.site_id, p.state::STRING, p.open_blocking
  FROM mainline.permit p
 WHERE p.external_ref = %s
"""


def _demo_ready(dsn: str) -> tuple[Any, Any] | None:
    """Return the demo permit if it is in the state the four beats need, else ``None``."""
    with psycopg.connect(dsn, autocommit=True) as probe:
        exists = probe.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'mainline' AND table_name = 'permit'"
        ).fetchone()
        if not (exists and exists[0]):
            return None
        row = probe.execute(_DEMO_READY_SQL, (_DEMO_EXTERNAL_REF,)).fetchone()
    if row is None:
        return None
    permit_id, site_id, state, open_blocking = row
    # `dispositioned` is the only state from which `merged` is a legal edge, and an open
    # obligation is what beats 2 and 3 are about. Anything else is a database whose demo
    # subject has been consumed, and a suite that ran against it would report NOT PROVEN
    # for a reason that is about the fixture rather than about the gate.
    if state != "dispositioned" or int(open_blocking) < 1:
        return None
    return permit_id, site_id


@pytest.fixture(scope="session")
def w4_database() -> Iterator[str]:
    """A migrated database holding one seeded demo history. Reused when it is still usable.

    Reused rather than rebuilt because applying 271 migrations costs ~50 s on this node and
    a suite that pays that on every invocation is a suite nobody runs twice. Rebuilt
    automatically when the demo subject is missing or consumed, and unconditionally with
    ``MAINLINE_W4_REBUILD=1``, so a stale scratch database is self-healing rather than a
    confusing red.
    """
    admin = _admin_dsn()
    try:
        psycopg.connect(admin, autocommit=True).close()
    except psycopg.OperationalError as exc:  # pragma: no cover - depends on the host
        pytest.skip(f"no CockroachDB at {admin.split('@')[-1].split('?')[0]}: {exc}")

    dsn = _scratch_dsn()
    rebuild = os.environ.get("MAINLINE_W4_REBUILD", "").strip() not in ("", "0", "false")

    with psycopg.connect(admin, autocommit=True) as probe:
        present = probe.execute(
            "SELECT count(*) FROM [SHOW DATABASES] WHERE database_name = %s", (SCRATCH_DB,)
        ).fetchone()
        usable = bool(present and present[0]) and not rebuild and _demo_ready(dsn) is not None
        if not usable:
            probe.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" CASCADE')
            probe.execute(f'CREATE DATABASE "{SCRATCH_DB}"')
            # 4500 is what CockroachDB Cloud Basic enforces. Pinning it locally keeps the
            # laptop from being more permissive than the cluster the demo will run on.
            probe.execute(
                f'ALTER DATABASE "{SCRATCH_DB}" CONFIGURE ZONE USING gc.ttlseconds = 4500'
            )

    if not usable:
        proof = _gate_refusal_module()
        with psycopg.connect(dsn, autocommit=True) as work:
            report = proof.apply_chain(
                work,
                dsn,
                _repo_root() / "verticals" / "mainline" / "db" / "migrations",
                _repo_root(),
            )
        if report.failures:
            pytest.skip(
                f"{len(report.failures)} of {report.files} migrations did not apply into "
                f"{SCRATCH_DB}; the gate objects may be absent. First: "
                f"{report.failures[0].version} [{report.failures[0].sqlstate}]"
            )
        with psycopg.connect(dsn, autocommit=False) as conn:
            seed_history_into(conn)

    ready = _demo_ready(dsn)
    assert ready is not None, (
        f"{SCRATCH_DB} was rebuilt and the demo permit {_DEMO_EXTERNAL_REF} is still not in "
        "state 'dispositioned' with an open obligation"
    )
    permit_id, site_id = ready
    signer, cosigner = "proof.signer", "proof.countersigner"

    # The API reads its subject from the environment with committed defaults; the seed this
    # suite drives is minted by the proof script, so the two are pointed at each other here
    # rather than by hand. That IS the mechanism scenario.py exists to provide.
    previous = {
        key: os.environ.get(key)
        for key in (
            "MAINLINE_DEMO_PERMIT_ID",
            "MAINLINE_DEMO_SITE_ID",
            "MAINLINE_DEMO_SIGNER_SUB",
            "MAINLINE_DEMO_COUNTERSIGNER_SUB",
        )
    }
    os.environ["MAINLINE_DEMO_PERMIT_ID"] = str(permit_id)
    os.environ["MAINLINE_DEMO_SITE_ID"] = str(site_id)
    os.environ["MAINLINE_DEMO_SIGNER_SUB"] = signer
    os.environ["MAINLINE_DEMO_COUNTERSIGNER_SUB"] = cosigner
    try:
        yield dsn
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def w4_conn(w4_database: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(w4_database, autocommit=False) as connection:
        yield connection


@pytest.fixture(scope="session")
def run_once(w4_database: str) -> dict[str, Any]:
    """One gate run, shared by the assertions about it. Runs the demo exactly as shipped."""
    with psycopg.connect(w4_database, autocommit=False) as connection:
        return gate_run(connection)


# ═══════════════════════════════════════════════════════════════════════════════════════
# the three beats the product is
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_gate_run_verdict_is_proven(run_once: dict[str, Any]) -> None:
    assert run_once["failures"] == [], run_once["failures"]
    assert run_once["verdict"] == "PROVEN"
    assert run_once["outcome"] == "completed"
    assert run_once["persisted"] is False
    assert run_once["schema_id"] == GATE_RUN_SCHEMA_ID


def test_beat_one_reads_both_counters(run_once: dict[str, Any]) -> None:
    beat = run_once["beats"][0]
    assert beat["name"] == "read"
    assert beat["outcome"] == "read"
    # The projected counter and the re-derived count are BOTH reported. Beat 3 exists
    # because they can disagree, so a payload that carried only one of them would have
    # nothing to show when they did.
    assert beat["observed"]["open_blocking_projected"] >= 1
    assert beat["observed"]["open_blocking_derived"] >= 1
    assert beat["observed"]["blocking_check_id"] is not None


def test_beat_two_is_23514_gate_closed_when_issued(run_once: dict[str, Any]) -> None:
    """CF-01. A plain CHECK, and the driver reports its name."""
    beat = run_once["beats"][1]
    assert beat["name"] == "merge"
    assert beat["outcome"] == "refused"
    assert beat["sqlstate"] == CF01_SQLSTATE == "23514"
    assert beat["constraint"] == CF01_EXHIBIT == "gate_closed_when_issued"
    assert beat["constraint_source"] == "reported"
    assert beat["matched_expectation"] is True
    # The message is the database's. If this API had composed it, it would read like
    # something a person wrote.
    assert "CHECK constraint" in beat["message"]
    assert beat["refusal"]["sqlstate"] == "23514"
    assert beat["refusal"]["constraint"] == "gate_closed_when_issued"
    assert beat["refusal"]["constraint_source"] == "reported"


def test_beat_two_refusal_names_the_open_obligation(run_once: dict[str, Any]) -> None:
    """The reason set comes from trappoint.explain_refusal, not from this worker."""
    refusal = run_once["beats"][1]["refusal"]
    assert refusal["diagnosis"] == "declarative"
    assert refusal["probe_calls"] == 0
    assert len(refusal["mus"]) >= 1
    atom = refusal["mus"][0]
    assert atom["kind"] == "obligation"
    assert atom["obligation_id"] == run_once["subject"]["blocking_check_id"]
    assert refusal["naa"]["kind"] == "dispose_obligations"
    assert refusal["naa"]["cardinality"] == len(refusal["mus"])
    assert refusal["naa_reason"] is None


def test_beat_three_is_p0001_fn_permit_merge_gate(run_once: dict[str, Any]) -> None:
    """CF-03 — the beat that separates the product from a CHECK constraint.

    The counter is forged to zero out of band, so ``gate_closed_when_issued`` is satisfied
    and would admit the merge. The gate re-derives the count anyway and refuses.
    """
    beat = run_once["beats"][2]
    assert beat["name"] == "projection_drift_attack"
    assert beat["observed"]["counter_forced_to"] == 0
    assert beat["observed"]["open_blocking_derived"] >= 1
    assert beat["outcome"] == "refused"
    assert beat["sqlstate"] == CF03_SQLSTATE == "P0001"
    assert beat["constraint"] == CF03_EXHIBIT == "mainline.fn_permit_merge_gate"
    # P0001 carries no constraint_name on this platform, so the exhibit was recovered from
    # the message the raising body wrote — a WEAKENED diagnosis, and it says so.
    assert beat["constraint_source"] == "parsed"
    assert beat["matched_expectation"] is True
    assert "re-derived open obligation count" in beat["message"]


def test_beat_four_admits_with_a_server_computed_clearance_digest(
    run_once: dict[str, Any],
) -> None:
    """A gate that always refuses is broken, not safe. This is the beat that rules that out."""
    beat = run_once["beats"][3]
    assert beat["name"] == "admit"
    assert beat["outcome"] == "admitted"
    assert beat["sqlstate"] == ADMISSION_SQLSTATE == "00000"
    assert beat["refusal"] is None
    assert beat["observed"]["open_blocking_after_signature"] == 0
    record = beat["observed"]["merge_record"]
    assert record is not None
    assert _HEX64.match(record["clearance_digest"]), record["clearance_digest"]
    assert record["permit_state"] == "merged"


# ═══════════════════════════════════════════════════════════════════════════════════════
# one transaction, and nothing left behind
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_all_four_beats_share_one_transaction(run_once: dict[str, Any]) -> None:
    """cluster_logical_timestamp() is constant within a transaction and moves between them."""
    txn = run_once["transaction"]
    assert txn["isolation"] == "SERIALIZABLE"
    assert txn["disposition"] == "rolled_back"
    assert txn["opened_logical_timestamp"] == txn["closed_logical_timestamp"]
    assert txn["single_transaction"] is True
    assert txn["retry_sqlstate"] is None


def _every_table_count(conn: psycopg.Connection[Any]) -> dict[str, int]:
    """count(*) for every base table in the vertical's schemas, in ONE statement."""
    tables = conn.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema IN ('mainline', 'mainline_meas', 'mainline_ops', 'trappoint') "
        "AND table_type = 'BASE TABLE' ORDER BY table_schema, table_name"
    ).fetchall()
    conn.rollback()
    assert tables, "no base tables — the migration chain did not apply into this database"
    # S608 on both lines below: the identifiers come from information_schema on a database
    # this fixture just built, not from a caller, and SQL has no parameter form for an
    # identifier. Interpolation is the only way to name a table, and these names are the
    # catalogue's own.
    union = " UNION ALL ".join(
        f'SELECT \'{schema}.{name}\' AS t, count(*) AS n FROM "{schema}"."{name}"'  # noqa: S608
        for schema, name in tables
    )
    rows = conn.execute(f"SELECT t, n FROM ({union}) ORDER BY t").fetchall()  # noqa: S608
    conn.rollback()
    return {row[0]: int(row[1]) for row in rows}


def test_every_table_row_count_is_identical_across_a_gate_run(
    w4_conn: psycopg.Connection[Any],
) -> None:
    """The DONE-WHEN condition: a gate run leaves the database exactly as it found it.

    Every base table in every schema this vertical owns, not just the ten the payload's own
    fingerprint watches — because a claim that nothing persisted should be checked against
    everything, not against the list the code being checked chose.
    """
    before = _every_table_count(w4_conn)
    payload = gate_run(w4_conn)
    after = _every_table_count(w4_conn)

    assert payload["verdict"] == "PROVEN", payload["failures"]
    differing = {t: (before[t], after[t]) for t in before if before[t] != after[t]}
    assert differing == {}, f"rows persisted in {differing}"
    assert set(before) == set(after)
    assert len(before) >= 80, f"only {len(before)} tables counted; the chain looks incomplete"


def test_the_payload_proves_its_own_persistence_claim(run_once: dict[str, Any]) -> None:
    check = run_once["persistence_check"]
    assert check["identical"] is True
    assert check["before"] == check["after"]
    assert check["before"]["permit_row"]["state"] != "merged"
    assert check["before"]["permit_row"]["merged_commit"] is None
    assert "mainline.merge_record" in check["before"]["row_counts"]


def test_two_consecutive_runs_see_the_same_subject(w4_conn: psycopg.Connection[Any]) -> None:
    """No reset button, no session table, no cleanup sweeper — and none needed.

    The fifth judge sees exactly what the first did. This is the property that made all of
    that machinery unnecessary, so it is asserted rather than assumed.
    """
    first = gate_run(w4_conn)
    second = gate_run(w4_conn)
    assert first["subject"] == second["subject"]
    assert first["verdict"] == second["verdict"] == "PROVEN"
    assert first["run_id"] != second["run_id"]
    assert first["persistence_check"]["after"] == second["persistence_check"]["before"]


def test_concurrent_runs_do_not_collide(w4_database: str) -> None:
    """Two runs interleaved on two connections. Neither sees the other's writes."""
    with (
        psycopg.connect(w4_database, autocommit=False) as one,
        psycopg.connect(w4_database, autocommit=False) as two,
    ):
        a = gate_run(one)
        b = gate_run(two)
    assert a["verdict"] == "PROVEN", a["failures"]
    assert b["verdict"] == "PROVEN", b["failures"]
    assert a["subject"] == b["subject"]


# ═══════════════════════════════════════════════════════════════════════════════════════
# the contract, and the scenario
# ═══════════════════════════════════════════════════════════════════════════════════════


def _contract() -> dict[str, Any]:
    return json.loads((_HERE.parents[1] / "contracts" / "gate-run.schema.json").read_text("utf-8"))


def test_payload_satisfies_the_governing_contract_structurally(run_once: dict[str, Any]) -> None:
    """Required members, closed enums and the invariants the contract declares.

    Hand-written rather than delegated because ``jsonschema`` is not installed in this
    workspace (measured: ``ModuleNotFoundError`` on 2026-08-10). The next test runs the
    real validator the day it is, and skips honestly until then, so this one is a floor and
    not a substitute.
    """
    contract = _contract()
    definition = contract["$defs"]["gate_run"]
    for key in definition["required"]:
        assert key in run_once, f"payload is missing required member {key!r}"
    assert set(run_once) <= set(definition["properties"]), (
        f"payload carries members the contract forbids: "
        f"{sorted(set(run_once) - set(definition['properties']))}"
    )

    assert run_once["outcome"] in contract["$defs"]["gate_run"]["properties"]["outcome"]["enum"]
    assert run_once["verdict"] in contract["$defs"]["gate_run"]["properties"]["verdict"]["enum"]
    assert (run_once["failures"] == []) == (run_once["verdict"] == "PROVEN")

    beat_props = contract["$defs"]["beat"]["properties"]
    outcomes = contract["$defs"]["beat_outcome"]["enum"]
    names = beat_props["name"]["enum"]
    assert len(run_once["beats"]) == 4
    for ordinal, beat in enumerate(run_once["beats"], start=1):
        assert beat["ordinal"] == ordinal
        assert beat["name"] == names[ordinal - 1]
        assert beat["outcome"] in outcomes
        assert set(beat) == set(beat_props), sorted(set(beat) ^ set(beat_props))
        # The contract's own conditional: refused <-> a refusal payload is present.
        assert (beat["outcome"] == "refused") == (beat["refusal"] is not None)
        if beat["refusal"] is not None:
            assert beat["constraint_source"] in ("reported", "parsed")
            _assert_wire_refusal(beat["refusal"])


def _assert_wire_refusal(refusal: dict[str, Any]) -> None:
    """Check a refusal payload against ``spec/wire/refusal.schema.json`` — the normative file.

    Read from disk rather than transcribed, so the day the specification gains a required
    member this fails instead of continuing to pass against a copy of the old one.
    """
    wire = json.loads((_repo_root() / "spec" / "wire" / "refusal.schema.json").read_text("utf-8"))
    for key in wire["required"]:
        assert key in refusal, f"refusal payload is missing required member {key!r}"
    # `additionalProperties: false` — a member the specification does not declare would be
    # rejected by the console's validator as a contract violation, not ignored.
    assert wire["additionalProperties"] is False
    extra = set(refusal) - set(wire["properties"])
    assert extra == set(), f"refusal payload carries undeclared members {sorted(extra)}"

    assert refusal["class"] == "gate"
    assert refusal["sqlstate"] in wire["properties"]["sqlstate"]["enum"]
    assert refusal["constraint_source"] in wire["properties"]["constraint_source"]["enum"]
    assert refusal["diagnosis"] in wire["properties"]["diagnosis"]["enum"]
    assert re.match(wire["properties"]["constraint"]["pattern"], refusal["constraint"])
    assert 1 <= len(refusal["message"]) <= wire["properties"]["message"]["maxLength"]
    assert 1 <= len(refusal["mus"]) <= wire["properties"]["mus"]["maxItems"]
    uuid.UUID(refusal["refusal_id"])
    # naa null <-> naa_reason non-null, and a declarative diagnosis consumes no probe budget.
    assert (refusal["naa"] is None) == (refusal["naa_reason"] is not None)
    if refusal["diagnosis"] == "declarative":
        assert refusal["probe_calls"] == 0
    if refusal["diagnosis"] == "none":
        assert refusal["naa"] is None


def test_payload_validates_against_the_json_schema(run_once: dict[str, Any]) -> None:
    """The real validator, when the workspace has one."""
    jsonschema = pytest.importorskip(
        "jsonschema",
        reason=(
            "jsonschema is not a workspace dependency; the structural check above is what "
            "runs today and this turns green the day it is added"
        ),
    )
    contract = _contract()
    validator = jsonschema.Draft202012Validator(contract["$defs"]["gate_run"])
    errors = sorted(validator.iter_errors(run_once), key=lambda e: list(e.absolute_path))
    assert errors == [], "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)


def test_scenario_identifiers_are_derived_not_remembered() -> None:
    """The seed and the API agree because both can recompute, not because both copied."""
    for name, literal in scenario_mod.EXPECTED.items():
        assert str(scenario_mod.demo_uuid(name)) == literal, name
    assert str(scenario_mod.DEMO_NAMESPACE) == "c82d4e5f-961f-590a-95bb-7ea3db2858db"


def test_scenario_env_override_wins() -> None:
    other = uuid.uuid4()
    built = scenario_mod.from_env({"MAINLINE_DEMO_PERMIT_ID": str(other)})
    assert built.permit_id == other
    assert built.site_id == scenario_mod.demo_uuid("site")  # untouched
    assert len(built.merged_commit) == 32  # mainline.permit_commit_sized


def test_scenario_not_seeded_is_not_a_refusal(w4_conn: psycopg.Connection[Any]) -> None:
    absent = scenario_mod.Scenario(
        permit_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        clause_uuid=uuid.uuid4(),
        event_id=uuid.uuid4(),
        signer_sub="nobody",
        countersigner_sub="nobody",
        merged_commit=b"\x00" * 32,
    )
    with pytest.raises(scenario_mod.ScenarioNotSeeded) as raised:
        gate_run(w4_conn, absent)
    assert "MAINLINE_DEMO_PERMIT_ID" in str(raised.value)


def test_gate_run_refuses_an_autocommit_connection(w4_database: str) -> None:
    """The four beats share one transaction. A connection that cannot hold one is refused."""
    with (
        psycopg.connect(w4_database, autocommit=True) as connection,
        pytest.raises(ValueError, match="autocommit"),
    ):
        gate_run(connection)
