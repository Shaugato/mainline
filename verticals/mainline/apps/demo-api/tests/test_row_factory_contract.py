# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The row-factory contract: the same code, through BOTH row factories, agreeing.

THE DEFECT THIS FILE EXISTS FOR, AND WHY NO EXISTING TEST SAW IT.

``db.connection()`` opens every production connection with ``psycopg.rows.dict_row``.
``tests/test_gate_run.py`` opens its connections with ``psycopg.connect(..., autocommit=
False)`` — psycopg's default ``tuple_row``. So the suite exercised one row factory and the
Lambda ran the other, and the one contract that spanned them was never asserted by anybody.

What that cost, measured against the pinned local node on 2026-08-12::

    scenario.resolve(db.connection(...))
    psycopg.errors.InvalidTextRepresentation: error in argument for $2:
      could not parse "check_id" as type uuid: uuid: incorrect UUID length: check_id

``scenario.resolve`` unpacked its row into eight names. Unpacking a ``dict`` yields its
KEYS, so ``check_id`` became the seven-letter string ``"check_id"`` and was bound as ``$2``
of the next statement. Character for character the 500 that
``evidence/deploy/acceptance.json`` recorded against the emulated Function URL, and the
reason the headline demo beat did not answer.

WHY THIS FILE ASSERTS BOTH DIRECTIONS RATHER THAN THE NEW ONE.

A test that only ever runs under one factory is what created the defect, so proving the
modules now work under ``dict_row`` would reproduce the original mistake with the operands
swapped. Every claim below is made twice — once through the REAL production factory
(``db.connection()``, not a hand-rolled imitation of it) and once through ``tuple_row`` —
and then the two answers are required to be EQUAL on every field that is a function of what
the database said. Factory-agnostic, not merely flipped.

WHY NAME-KEYED ACCESS WAS NOT THE FIX, MEASURED RATHER THAN ASSUMED.

``test_a_dict_row_would_silently_collapse_these_result_sets`` reads
``cursor.description`` for the statements involved: CockroachDB names all ten columns of
``gate_run._FINGERPRINT_SQL`` ``count``, and both ``encode(...)`` columns of the two
merge-record statements ``encode``. A ``dict`` row keeps one key per NAME, so those result
sets lose columns with no error to notice — ten values arriving as one. Position is the only
convention under which those statements are readable at all, which is why the fix asks the
CURSOR for tuples rather than renaming the columns.

THE FIXTURE DATABASE IS THIS FILE'S OWN.

``w_w1_rowfactory``, seeded by ``scripts/proof/gate_refusal.py`` — the repository's own
seeder, so this suite and the central proof drive one history rather than two that can
drift. It is rebuilt when the demo subject is missing, consumed, or **no longer covered by
a live exposure receipt**: that last condition is deliberate, because the seeded receipt
expires two hours after it is written and a database adopted the next morning makes beat 4
skip for a reason that is about the fixture and not about the gate. The shared
``tests/conftest.py`` has the same weakness and is a different worker's file; this one
guards itself rather than waiting.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row, tuple_row

pytestmark = pytest.mark.requires_cluster

_HERE = Path(__file__).resolve()
_APP_SRC = _HERE.parents[1] / "src"
if str(_APP_SRC) not in sys.path:  # the app is not installed as a distribution yet
    sys.path.insert(0, str(_APP_SRC))

from mainline_demo_api import db as db_mod  # noqa: E402
from mainline_demo_api import gate_run as gate_run_mod  # noqa: E402
from mainline_demo_api import scenario as scenario_mod  # noqa: E402
from mainline_demo_api import transitions as transitions_mod  # noqa: E402
from mainline_demo_api.gate_run import gate_run  # noqa: E402
from mainline_demo_api.scenario import ResolvedScenario, positional, resolve  # noqa: E402
from mainline_demo_api.transitions import handle_transition  # noqa: E402

DEFAULT_DSN = "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable&connect_timeout=10"
SCRATCH_DB = os.environ.get("MAINLINE_W1_DATABASE", "w_w1_rowfactory")

#: The external reference ``scripts/proof/gate_refusal.py::seed_history`` gives its permit.
_DEMO_EXTERNAL_REF = "PTW-PROOF-1"

#: The diagnosis printed when the dict_row path dies inside a module this worker does not
#: own. Recorded rather than worked around: `evidence/deploy/rowfactory-defect.json` names
#: it, and this test turns green the moment that one line is corrected.
_REFUSAL_BLOCKER = (
    "gate_run() raised {exc} through the PRODUCTION dict_row connection. The three modules "
    "this test's worker owns (scenario, gate_run, transitions) are factory-agnostic: the "
    "tuple_row half of every assertion in this file passes. The remaining positional row "
    "access in this package is mainline_demo_api/refusal.py:235:\n"
    "    return (row[0] if row and isinstance(row[0], dict) else None), None\n"
    "`_explain` runs `SELECT trappoint.explain_refusal(...)`, whose single column "
    "CockroachDB names `explain_refusal`, so under dict_row `row[0]` is KeyError: 0. Beats "
    "2 and 3 both reach it through refusal_payload(), so no path through the demo avoids "
    "it. The correction is one line: take the row's single VALUE rather than its index, "
    "e.g. via scenario.positional() as the other three modules now do. refusal.py is owned "
    "by no worker in this wave, and this worker's brief does not list it, so it was NOT "
    "edited. See evidence/deploy/rowfactory-defect.json -> blocking_finding."
)


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


def _repo_root() -> Path:
    for candidate in (_HERE, *_HERE.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    raise RuntimeError("no workspace root above this test file")


def _gate_refusal_module() -> ModuleType:
    """Import ``scripts/proof/gate_refusal.py`` by path — the repository's own seeder."""
    path = _repo_root() / "scripts" / "proof" / "gate_refusal.py"
    spec = importlib.util.spec_from_file_location("w1_gate_refusal_seed", path)
    if spec is None or spec.loader is None:  # pragma: no cover - a broken checkout
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: Ready means all four beats have something to do: the subject is in the one state from
#: which `merged` is a legal edge, an obligation is still open, and a LIVE exposure receipt
#: covers it. The receipt clause is the one the shared conftest lacks — without it a
#: database seeded two hours ago is adopted with a dead receipt, beat 4 skips, and the
#: verdict says NOT PROVEN about the fixture while appearing to say it about the gate.
_DEMO_READY_SQL = """
SELECT p.permit_id, p.site_id
  FROM mainline.permit p
 WHERE p.external_ref = %s
   AND p.state::STRING = 'dispositioned'
   AND p.open_blocking >= 1
   AND EXISTS (
         SELECT 1
           FROM mainline.blocking_check bc
          WHERE bc.permit_id = p.permit_id
            AND NOT EXISTS (SELECT 1 FROM mainline.disposition d
                             WHERE d.check_id = bc.check_id
                               AND d.retracted_by IS NULL
                               AND (d.expires_at IS NULL OR d.expires_at > now()))
            AND EXISTS (SELECT 1
                          FROM mainline.exposure_line l
                          JOIN mainline.exposure_receipt r ON r.receipt_id = l.receipt_id
                         WHERE l.check_id = bc.check_id
                           AND r.expires_at > now()))
"""


def _demo_ready(dsn: str) -> tuple[Any, Any] | None:
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
    return row[0], row[1]


@pytest.fixture(scope="session")
def w1_database() -> Iterator[str]:
    """A migrated database holding one demo history with a LIVE exposure receipt."""
    admin = _admin_dsn()
    try:
        psycopg.connect(admin, autocommit=True).close()
    except psycopg.OperationalError as exc:  # pragma: no cover - depends on the host
        pytest.skip(f"no CockroachDB at {admin.split('@')[-1].split('?')[0]}: {exc}")

    dsn = _scratch_dsn()
    rebuild = os.environ.get("MAINLINE_W1_REBUILD", "").strip() not in ("", "0", "false")

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
            conn.rollback()
            conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            proof.seed_history(conn)
            conn.commit()

    ready = _demo_ready(dsn)
    assert ready is not None, (
        f"{SCRATCH_DB} was rebuilt and the demo permit {_DEMO_EXTERNAL_REF} is still not in "
        "state 'dispositioned' with an open obligation under a live exposure receipt"
    )
    permit_id, site_id = ready

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
    os.environ["MAINLINE_DEMO_SIGNER_SUB"] = "proof.signer"
    os.environ["MAINLINE_DEMO_COUNTERSIGNER_SUB"] = "proof.countersigner"
    try:
        yield dsn
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def production_conn(w1_database: str) -> Iterator[psycopg.Connection[Any]]:
    """The REAL production connection: ``db.connection()``, not an imitation of it.

    Using the factory itself is the whole point. A test that re-opened a connection with
    ``row_factory=dict_row`` by hand would assert that this file agrees with itself; the
    thing that has to hold is that ``db.py``'s choice and these modules' statements agree,
    and only ``db.connection()`` carries ``db.py``'s choice.
    """
    conn = db_mod.connection(dsn=w1_database)
    try:
        yield conn
    finally:
        db_mod.close()


@pytest.fixture
def tuple_conn(w1_database: str) -> Iterator[psycopg.Connection[Any]]:
    """The factory the existing suite has always used, kept asserted rather than assumed."""
    with psycopg.connect(w1_database, autocommit=True, row_factory=tuple_row) as conn:
        yield conn


# ═══════════════════════════════════════════════════════════════════════════════════════
# the premise
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_production_connection_really_is_dict_row(
    production_conn: psycopg.Connection[Any],
) -> None:
    """Pin the premise every other test here depends on.

    ``db.py`` is not this worker's file and the choice is deliberate: ``reads.py`` makes 43
    ``row["name"]`` accesses across the twelve GET resources, so flipping ``db.py`` to
    ``tuple_row`` would trade one broken endpoint for twelve. If this assertion ever fails,
    the change that caused it owes those twelve resources an answer.
    """
    assert production_conn.row_factory is dict_row
    assert production_conn.autocommit is True
    row = production_conn.execute("SELECT 1 AS one").fetchone()
    assert isinstance(row, Mapping)
    assert row["one"] == 1


def test_a_dict_row_would_silently_collapse_these_result_sets(
    tuple_conn: psycopg.Connection[Any],
) -> None:
    """Measure why the fix reads by POSITION instead of renaming the columns.

    A ``dict`` row keeps one entry per column NAME. Where CockroachDB hands back repeated
    names, the row loses columns and says nothing — which is worse than the crash this file
    was written for, because a crash is visible.
    """
    permit = uuid.UUID(os.environ["MAINLINE_DEMO_PERMIT_ID"])
    collapsing = {
        "gate_run._FINGERPRINT_SQL": (gate_run_mod._FINGERPRINT_SQL, ()),
        "gate_run._MERGE_RECORD_SQL": (gate_run_mod._MERGE_RECORD_SQL, (permit,)),
    }
    for label, (sql, params) in collapsing.items():
        names = [d.name for d in (tuple_conn.execute(sql, params).description or ())]
        assert len(names) > len(set(names)), (
            f"{label} no longer returns duplicate column names ({names}). That is a fine "
            "thing to have changed, but this test is the record of WHY these statements "
            "are read positionally — update the reasoning in scenario.positional() rather "
            "than deleting the assertion."
        )


def test_no_statement_in_these_modules_inherits_the_connection_s_row_factory() -> None:
    """The ratchet: ``conn.execute(...).fetchone()`` is the defect shape, and it is banned.

    Structural rather than behavioural on purpose. The behavioural tests below only cover
    the statements a gate run happens to reach; this covers every statement in the three
    modules, including the ones only a 404 or a 422 path executes.
    """
    offenders: dict[str, list[str]] = {}
    for module in (scenario_mod, gate_run_mod, transitions_mod):
        path = Path(module.__file__ or "")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            outer = node.func
            if not (
                isinstance(outer, ast.Attribute)
                and outer.attr in ("fetchone", "fetchall", "fetchmany")
            ):
                continue
            inner = outer.value
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "execute"
            ):
                hits.append(f"{path.name}:{node.lineno}")
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, (
        "these fetches read whatever shape the CONNECTION was opened with, which is the "
        f"defect this file exists for: {offenders}. Route them through "
        "scenario.positional(conn, sql, params) so the statement declares the shape it is "
        "written against."
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# scenario.resolve — both factories, then equality
# ═══════════════════════════════════════════════════════════════════════════════════════


def _assert_resolved(resolved: ResolvedScenario) -> None:
    assert isinstance(resolved.check_id, uuid.UUID), (
        f"check_id is {resolved.check_id!r}. The literal string 'check_id' here is the "
        "original defect exactly: a dict unpacked into eight names yields its KEYS."
    )
    assert isinstance(resolved.receipt_id, uuid.UUID)
    assert resolved.state == "dispositioned"
    assert resolved.open_blocking >= 1
    assert resolved.open_derived >= 1
    assert isinstance(resolved.head_seq, int)
    assert isinstance(resolved.external_ref, str)
    assert resolved.external_ref == _DEMO_EXTERNAL_REF
    assert isinstance(resolved.site_code, str)


def test_resolve_through_the_production_connection(
    production_conn: psycopg.Connection[Any],
) -> None:
    _assert_resolved(resolve(production_conn))


def test_resolve_through_a_tuple_row_connection(tuple_conn: psycopg.Connection[Any]) -> None:
    _assert_resolved(resolve(tuple_conn))


def test_resolve_returns_the_same_answer_under_both_factories(
    production_conn: psycopg.Connection[Any], tuple_conn: psycopg.Connection[Any]
) -> None:
    """Agreement, not merely absence of an exception.

    Two runs that both succeed while disagreeing about which obligation is open would be a
    worse defect than the crash, and nothing above would have caught it.
    """
    assert resolve(production_conn).as_json() == resolve(tuple_conn).as_json()


def test_positional_does_not_mutate_the_connection_it_was_handed(
    production_conn: psycopg.Connection[Any],
) -> None:
    """The helper sets the factory on the CURSOR; ``reads.py`` still gets its dicts.

    A fix that flipped ``conn.row_factory`` in passing would have made the gate run work
    and broken every GET resource served afterwards on the same warm container.
    """
    before = production_conn.row_factory
    assert positional(production_conn, "SELECT 1, 2, 3").fetchone() == (1, 2, 3)
    assert production_conn.row_factory is before
    assert production_conn.execute("SELECT 4 AS four").fetchone() == {"four": 4}


# ═══════════════════════════════════════════════════════════════════════════════════════
# gate_run — both factories, then equality
# ═══════════════════════════════════════════════════════════════════════════════════════


def _stable(payload: dict[str, Any]) -> dict[str, Any]:
    """The part of a gate-run payload that is a function of what the DATABASE said.

    Run ids, wall clocks, elapsed milliseconds, the minted disposition id and the logical
    timestamps differ between any two runs by design, so comparing whole payloads would
    assert nothing. Everything below is required to be identical.
    """
    return {
        "verdict": payload["verdict"],
        "outcome": payload["outcome"],
        "failures": payload["failures"],
        "persisted": payload["persisted"],
        "subject": payload["subject"],
        "single_transaction": payload["transaction"]["single_transaction"],
        "isolation": payload["transaction"]["isolation"],
        "beats": [
            {
                "ordinal": beat["ordinal"],
                "name": beat["name"],
                "outcome": beat["outcome"],
                "sqlstate": beat["sqlstate"],
                "constraint": beat["constraint"],
                "constraint_source": beat["constraint_source"],
                "matched_expectation": beat["matched_expectation"],
                "refusal_sqlstate": (beat["refusal"] or {}).get("sqlstate"),
                "refusal_constraint": (beat["refusal"] or {}).get("constraint"),
            }
            for beat in payload["beats"]
        ],
        "persistence_identical": payload["persistence_check"]["identical"],
        "row_counts_before": payload["persistence_check"]["before"]["row_counts"],
        "row_counts_after": payload["persistence_check"]["after"]["row_counts"],
    }


def _run(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    """Play the four beats the way ``transitions._demo_gate_run`` does.

    ``db.connection()`` returns an autocommit connection and ``gate_run`` refuses one,
    because the four beats sharing ONE transaction is the property being demonstrated.
    ``transitions._demo_gate_run`` clears the flag before calling; this mirrors that rather
    than opening a differently-configured connection, so what is under test is the path the
    Function URL actually takes.
    """
    restore = conn.autocommit
    if conn.autocommit:
        conn.autocommit = False
    try:
        return gate_run(conn)
    except KeyError as exc:
        raise AssertionError(_REFUSAL_BLOCKER.format(exc=repr(exc))) from exc
    finally:
        conn.rollback()
        conn.autocommit = restore


def _assert_gate_run(payload: dict[str, Any]) -> None:
    assert payload["failures"] == [], payload["failures"]
    assert payload["verdict"] == "PROVEN"
    assert payload["outcome"] == "completed"
    assert payload["persisted"] is False
    assert payload["persistence_check"]["identical"] is True
    # Ten tables, not one. Under a dict row CockroachDB's ten `count` columns collapse to a
    # single key, so this length is the assertion that the collapse did not happen.
    assert len(payload["persistence_check"]["before"]["row_counts"]) == len(
        gate_run_mod._FINGERPRINT_TABLES
    )
    outcomes = [beat["outcome"] for beat in payload["beats"]]
    assert outcomes == ["read", "refused", "refused", "admitted"], outcomes
    assert payload["beats"][1]["sqlstate"] == gate_run_mod.CF01_SQLSTATE
    assert payload["beats"][2]["sqlstate"] == gate_run_mod.CF03_SQLSTATE
    assert payload["beats"][3]["sqlstate"] == gate_run_mod.ADMISSION_SQLSTATE
    # Seven values out of `_MERGE_RECORD_SQL`, whose two `encode` columns a dict row keeps
    # only one of. A collapsed row loses `permit_head_seq` off the end of the unpacking.
    record = payload["beats"][3]["observed"]["merge_record"]
    assert record is not None
    assert isinstance(record["clearance_digest"], str)
    assert isinstance(record["merged_commit"], str)
    assert record["clearance_digest"] != record["merged_commit"]
    assert isinstance(record["permit_head_seq"], int)


def test_gate_run_through_the_production_connection(
    production_conn: psycopg.Connection[Any],
) -> None:
    """The headline beat, through the factory the Lambda actually opens."""
    _assert_gate_run(_run(production_conn))


def test_gate_run_through_a_tuple_row_connection(tuple_conn: psycopg.Connection[Any]) -> None:
    _assert_gate_run(_run(tuple_conn))


def test_gate_run_returns_the_same_answer_under_both_factories(
    production_conn: psycopg.Connection[Any], tuple_conn: psycopg.Connection[Any]
) -> None:
    assert _stable(_run(production_conn)) == _stable(_run(tuple_conn))


def test_gate_run_still_refuses_an_autocommit_connection(
    production_conn: psycopg.Connection[Any],
) -> None:
    """The guard at ``gate_run.py`` survives the fix.

    ``db.connection()`` hands back an autocommit connection and the four beats must share
    one transaction, so the refusal is the only thing standing between a caller and a demo
    that silently committed its own attack beat.
    """
    assert production_conn.autocommit is True
    with pytest.raises(ValueError, match="NOT in autocommit"):
        gate_run(production_conn)


# ═══════════════════════════════════════════════════════════════════════════════════════
# the endpoint, end to end
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_demo_gate_run_endpoint_through_the_production_connection(
    production_conn: psycopg.Connection[Any],
) -> None:
    """``POST /v1/demo/gate-run``, from the resource key inward, on a dict_row connection.

    This is the call that returned 500 in ``evidence/deploy/acceptance.json``: the handler
    resolves the scenario, plays the beats and builds the envelope, all through the
    connection ``db.connection()`` opened.
    """
    try:
        status, payload = handle_transition(
            "demo_gate_run", {}, {"run_id": "w1-rowfactory-contract"}, production_conn
        )
    except KeyError as exc:
        raise AssertionError(_REFUSAL_BLOCKER.format(exc=repr(exc))) from exc
    finally:
        production_conn.rollback()
        production_conn.autocommit = True

    assert status == 200, payload
    assert payload["resource"] == "demo_gate_run"
    data = payload["data"]
    assert data["run_id"] == "w1-rowfactory-contract"
    assert data["verdict"] == "PROVEN", data["failures"]
    assert data["subject"]["blocking_check_id"] is not None
    assert data["subject"]["exposure_receipt_id"] is not None


def test_materialise_checks_reads_its_rows_through_either_factory(
    production_conn: psycopg.Connection[Any],
) -> None:
    """``transitions._materialise_checks`` unpacked two rows positionally as well.

    Driven at the demo subject, where the write guard answers 423 — which is exactly the
    behaviour worth pinning, since it proves the endpoint got far enough to resolve the
    scenario through this connection rather than dying on a row shape first.
    """
    permit = os.environ["MAINLINE_DEMO_PERMIT_ID"]
    try:
        status, payload = handle_transition(
            "materialise_checks", {"permit_id": permit}, {}, production_conn
        )
    finally:
        production_conn.rollback()
        production_conn.autocommit = True
    assert status == 423, payload
    assert payload["error"] == "demo_subject_write_protected"


def test_sign_disposition_resolves_its_check_row_through_either_factory(
    production_conn: psycopg.Connection[Any],
) -> None:
    """``_CHECK_SQL``'s four-name unpacking, reached through a dict_row connection.

    An unknown ``check_id`` is the shortest path that executes the statement and reads its
    result: a dict row would have raised before the 404 could be decided.
    """
    absent = uuid.uuid5(uuid.NAMESPACE_URL, "mainline/w1-rowfactory/absent-check")
    try:
        status, payload = handle_transition(
            "sign_disposition",
            {"check_id": str(absent)},
            {"rationale": "x" * 200},
            production_conn,
        )
    finally:
        production_conn.rollback()
        production_conn.autocommit = True
    assert status == 404, payload
    assert payload["error"] == "no_such_check"
