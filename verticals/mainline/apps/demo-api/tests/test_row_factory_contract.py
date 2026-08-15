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

THE RATCHET IS THE WHOLE PACKAGE NOW, AND THE RULE IS "DECLARE", NOT "DON'T INHERIT".

The first version of the structural test banned ``conn.execute(...).fetchone()`` in three
named modules. That was right about those three and wrong as a general rule, because
``reads.py`` makes 43 name-keyed accesses across the twelve GET resources and ``health.py``
opens an explicit ``dict_row`` cursor: both inherit mapping rows deliberately and both are
correct. Banning the shape everywhere would have demanded twelve resources be rewritten to
buy nothing. So the rule the ratchet now enforces over EVERY module in
``mainline_demo_api`` is that each reading site DECLARES the convention it is written
against — ``scenario.positional()`` for position, an explicit ``row_factory=`` cursor or a
name-only read for name — and that no module may declare position at one statement and
nothing at another. That last clause is the one with a body count: it is exactly the state
``refusal.py`` was in on 2026-08-12.

The rule itself lives in ``scripts/qa/row_factory_ratchet.py`` and is imported from there
rather than re-implemented here, for the same reason this file drives the repository's own
seeder instead of its own: two copies of a rule are two rules. That script also runs
repo-wide with no cluster in ``tests/unit/test_row_factory_ratchet.py``, which is where the
package assertion below is repeated for the ``--crdb=none`` lane — this module is marked
``requires_cluster``, so on a laptop with no node the structural half would otherwise skip.

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
from trappoint_testkit.txn import from_dsn, run_txn

pytestmark = pytest.mark.requires_cluster

_HERE = Path(__file__).resolve()
_APP_SRC = _HERE.parents[1] / "src"
if str(_APP_SRC) not in sys.path:  # the app is not installed as a distribution yet
    sys.path.insert(0, str(_APP_SRC))

from mainline_demo_api import db as db_mod  # noqa: E402
from mainline_demo_api import gate_run as gate_run_mod  # noqa: E402
from mainline_demo_api.gate_run import gate_run  # noqa: E402
from mainline_demo_api.scenario import ResolvedScenario, positional, resolve  # noqa: E402
from mainline_demo_api.transitions import handle_transition  # noqa: E402
from test_gate_run import _fingerprint  # noqa: E402 - one definition of "what builds a database"

DEFAULT_DSN = "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable&connect_timeout=10"

#: The scratch database this file builds and adopts, named by a CONTENT FINGERPRINT.
#:
#: ``test_gate_run._fingerprint`` is IMPORTED rather than re-derived, and the asymmetry is
#: the point: two copies of "what builds a database" is how one of them goes stale, which is
#: the very failure the fingerprint exists to prevent. The import is the same shape
#: ``test_transitions.py`` already uses for ``w4_database`` — pytest's default ``prepend``
#: import mode puts this directory on ``sys.path``.
#:
#: WHY THIS NAME MOVED TOO. This file carried the identical hazard the RULING names in
#: ``test_gate_run.py``: a FIXED default, so two concurrent runs shared one database, and
#: :func:`_w1_built` ADOPTS a database whenever its demo subject still looks usable — which
#: means a database built from an older migration chain or an older ``gate_refusal.py`` was
#: indistinguishable from one built from this tree. Fixing one of two identical sites and
#: leaving the other would have left the measurement hazard exactly where it was found.
#: ``MAINLINE_W1_DATABASE`` is kept for the same reason ``MAINLINE_W4_DATABASE`` is: the
#: order and falsification harnesses set it to give a run a private database.
SCRATCH_DB = os.environ.get("MAINLINE_W1_DATABASE") or f"w_w1_rowfactory_{_fingerprint()}"

#: The external reference ``scripts/proof/gate_refusal.py::seed_history`` gives its permit.
_DEMO_EXTERNAL_REF = "PTW-PROOF-1"

#: The package the structural ratchet covers: every module, not a named three.
_PACKAGE_SRC = _APP_SRC / "mainline_demo_api"

#: Every module's reading convention, as this file requires it to be. The table is the
#: point: a NEW module added to the package fails the enumeration check below until
#: somebody decides which convention it is in and writes it down here. Each verdict is
#: computed from the module's own statements by `scripts/qa/row_factory_ratchet.py`, so an
#: entry cannot be a wish — it either matches what the code does or the test names both.
#:
#:   position  every reading site goes through `scenario.positional()`.
#:   name      rows are mappings: an explicit `row_factory=dict_row` cursor (health), or
#:             inherited from `db.connection()` and never indexed (reads, db).
#:   silent    the module issues no row-reading statement at all. Worth asserting rather
#:             than omitting: the day `app.py` grows a query, its convention becomes a
#:             decision, and this line is what forces someone to make it.
_EXPECTED_CONVENTIONS: dict[str, str] = {
    "__init__.py": "silent",
    "app.py": "silent",
    # ADDED 2026-08-13, deliberately, which is what this table exists to force. It reads
    # `mainline.signing_credential` through `scenario.positional()` at exactly one site —
    # the resolver that replaced the derived `_sha("cred", …)` constant. `position` is the
    # correct verdict and not merely the current one: the statement selects a single
    # `credential_id` column and the value is consumed by index, so a `dict_row` connection
    # would have made it the third `KeyError: 0` in this package rather than the first.
    "credentials.py": "position",
    "db.py": "name",
    # ADDED 2026-08-14 with the vocabulary resolver, and `position` is measured rather than
    # inherited: `defeaters.py:257` reads its one statement through `scenario.positional()`
    # and then indexes the row — `row[0]` for the code, `row[1]` for the digest. Under
    # `dict_row` that is the same `KeyError: 0` this file exists for, on the statement a
    # signature's `defeater_vocab_sha256` is read from, which would have made it the second
    # module to ship the defect after the one that named it.
    "defeaters.py": "position",
    "envelope.py": "silent",
    "gate_run.py": "position",
    "health.py": "name",
    # ADDED 2026-08-13 with the cost bound. Both are `silent` by measurement, not by
    # assumption: neither module issues a row-reading statement — they meter bytes and
    # requests in process. Recorded rather than omitted for the reason the header gives —
    # the day either grows a query, its convention becomes a decision, and this line is
    # what forces somebody to make it instead of inheriting whatever the connection offered.
    "logbudget.py": "silent",
    "ratelimit.py": "silent",
    "reads.py": "name",
    "refusal.py": "position",
    # ADDED 2026-08-14 with the 40001 retry loop. `silent` by measurement — zero reading
    # sites; the only `execute` in the file is the word inside a docstring explaining why a
    # retry wrapped around one statement inside an already-open transaction is not a retry.
    # It re-runs a CALLABLE from BEGIN and never reads a row itself, so it has no convention
    # to inherit and this line is what will force the question if it ever grows one.
    "retry.py": "silent",
    "scenario.py": "position",
    "static_site.py": "silent",
    # ADDED 2026-08-15 with the demo subject index, which is exactly the decision this
    # table exists to force. `name` is measured, not inherited: `subjects._row` does
    # `dict(conn.execute(...).fetchone())` and every value is then taken by COLUMN NAME —
    # `row["site_id"]`, `row["count"]` — off a connection whose row factory `db.py` sets.
    # Not one reading site indexes. That is the correct verdict as well as the current
    # one: nine of this module's ten statements select several columns and one selects a
    # window aggregate beside them, so reading by position would make the payload's
    # meaning depend on the order the SELECT list happens to be written in, and reordering
    # a SELECT list is the kind of edit nobody reviews twice.
    "subjects.py": "name",
    "transitions.py": "position",
}


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


def _by_path(name: str, path: Path) -> ModuleType:
    """Import a `scripts/` module by path — `scripts/` is deliberately not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - a broken checkout
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE execution: `dataclasses` resolves a class's own module out of
    # `sys.modules` while processing it, and a module that is not there yet fails with
    # `'NoneType' object has no attribute '__dict__'`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _gate_refusal_module() -> ModuleType:
    """Import ``scripts/proof/gate_refusal.py`` by path — the repository's own seeder."""
    return _by_path("w1_gate_refusal_seed", _repo_root() / "scripts" / "proof" / "gate_refusal.py")


def _ratchet() -> ModuleType:
    """Import ``scripts/qa/row_factory_ratchet.py`` — where the RULE lives.

    Imported rather than re-implemented. The structural claim this file makes about the
    eleven modules of ``mainline_demo_api`` and the claim the repo-wide scanner makes about
    the other 213 parsed files have to be the SAME claim, or the package could pass one and
    fail the other and nobody would know which was the rule.
    """
    return _by_path(
        "w2_row_factory_ratchet", _repo_root() / "scripts" / "qa" / "row_factory_ratchet.py"
    )


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
def _w1_built() -> tuple[str, str, str]:
    """Build (or adopt) the scratch database. Returns ``(dsn, permit_id, site_id)``.

    **Touches no environment variable.**

    Split out of :func:`w1_database` on 2026-08-13 because the two halves have different
    lifetimes and combining them was an ordering defect, measured and reproduced:

    * **Building** is expensive — 271 migrations, ~50 s — and belongs to the session.
    * **Saying which permit the demo is** is a statement about the database THE CURRENT
      TEST is talking to, and belongs to the current test.

    While both lived here, this fixture published ``MAINLINE_DEMO_PERMIT_ID`` and three
    siblings for the WHOLE session, and so did ``test_gate_run.py::w4_database`` — a
    different scratch database (``w_w4_api_transitions``) whose ``PTW-PROOF-1`` permit is a
    different ``uuid4`` (``scripts/proof/gate_refusal.py::seed_history`` mints one per
    seeding). Whichever ran LAST owned those four names for the rest of the session, so a
    test's connection and the environment describing it could name two different databases.
    Reproduced in three node ids, run in this order, 0.68 s::

        test_transitions.py::test_the_shared_connection_is_the_one_db_py_opens
        test_row_factory_contract.py::test_the_production_connection_really_is_dict_row
        test_transitions.py::test_the_request_after_a_gate_run_is_not_a_503
        -> assert 422 == 200          # ScenarioNotSeeded, w1's permit against w4's database

    and in the other direction under ``demo_suite_order.py shuffle --seed 7``, where six
    tests IN THIS FILE failed ``ScenarioNotSeeded: no mainline.permit with permit_id
    199adc10-… in this database`` — w4's permit, looked for in w1's database.

    The repair is NOT to pin the order. An order pin is a green that certifies itself, and
    the leaking state would still be there for the next reader to be surprised by.
    """
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
        # ONE whole transaction, retried on 40001 by the repository's ONE retry loop.
        #
        # CONTENDED, and the contention is not hypothetical. `seed_history` issues ~30
        # statements ending in two `permit_event` INSERTs that each read the previous
        # row's `chain_digest` and then UPDATE `mainline.permit` — a read-modify-write on
        # one row. `tests/concurrency/test_seed_permit_needs_retry.py` races that shape
        # against the LOCAL single-node node and gets 40001 in 6 of 6 races. This build
        # also runs while `test_gate_run.py`'s session-scoped `w4_database` may be
        # applying the same chain and the same seeder to a sibling database on the same
        # cluster, so the loser used to lose its whole history and report the rebuild as
        # a product failure.
        #
        # `from_dsn`, never a connection: `run_txn` opens a NEW connection per attempt so
        # a poisoned transaction is discarded rather than replayed into — spec/errors.md
        # §2.1. `row_factory` stays psycopg's default `tuple_row`, exactly as the
        # hand-opened connection here did, because `scripts/proof/gate_refusal.py` reads
        # its own rows by position.
        run_txn(from_dsn(dsn), proof.seed_history, subject_kind="permit")

    ready = _demo_ready(dsn)
    assert ready is not None, (
        f"{SCRATCH_DB} was rebuilt and the demo permit {_DEMO_EXTERNAL_REF} is still not in "
        "state 'dispositioned' with an open obligation under a live exposure receipt"
    )
    permit_id, site_id = ready
    return dsn, str(permit_id), str(site_id)


@pytest.fixture
def w1_database(_w1_built: tuple[str, str, str]) -> Iterator[str]:
    """The scratch DSN, with the environment pointed at ITS subject for THIS test only.

    Function-scoped deliberately — see :func:`_w1_built` for the ordering defect that made
    it so. It opens no connection of its own: the identifiers were read out of the database
    once, by the session-scoped build, and a re-read here would cost one connection per
    test — 0.23 s against this node over IPv4 and **10.2 s** over a DSN spelled ``localhost``
    (docs/ci/demo-suite-order.md §5.1). Publishing four strings is not worth a round trip.

    ``os.environ`` directly rather than ``monkeypatch``: this fixture is imported by nothing
    and requested by name, so the restore order is this fixture's own ``finally``, whereas a
    ``monkeypatch`` here would interleave with the ``monkeypatch`` a test may itself request
    and the two undos would race for the same four names.
    """
    dsn, permit_id, site_id = _w1_built

    previous = {
        key: os.environ.get(key)
        for key in (
            "MAINLINE_DEMO_PERMIT_ID",
            "MAINLINE_DEMO_SITE_ID",
            "MAINLINE_DEMO_SIGNER_SUB",
            "MAINLINE_DEMO_COUNTERSIGNER_SUB",
        )
    }
    os.environ["MAINLINE_DEMO_PERMIT_ID"] = permit_id
    os.environ["MAINLINE_DEMO_SITE_ID"] = site_id
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
    # `# rowshape:` is the ratchet's fourth way of declaring a convention, and this is the
    # one statement in the package's tests that needs it: the whole point here is to read
    # the connection's OWN shape without asking a cursor to override it, which is
    # indistinguishable, structurally, from forgetting to. Declaring it keeps the
    # isinstance() below an assertion ABOUT the premise rather than a guess at it.
    row = production_conn.execute("SELECT 1 AS one").fetchone()  # rowshape: name
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
    """The ratchet, over EVERY module in ``mainline_demo_api``: declare, or be named.

    Structural rather than behavioural on purpose. The behavioural tests below cover only
    the statements a gate run happens to reach; this covers every statement in all eleven
    modules, including the ones only a 404 or a 422 path executes.

    Widened from the original three (``scenario``, ``gate_run``, ``transitions``) because
    the original rule — ban ``conn.execute(...).fetchone()`` — is false as a general
    statement about this package. ``reads.py`` and ``health.py`` inherit mapping rows on
    purpose and are right to. What is banned is reading a row in a shape nobody declared:
    indexing an inherited row by position, reading one row both ways, contradicting a
    declaration, or declaring position at one statement and nothing at the next.
    """
    ratchet = _ratchet()
    report = ratchet.scan([_PACKAGE_SRC])
    scanned = sorted(Path(path).name for path in report.conventions)
    modules = sorted(path.name for path in _PACKAGE_SRC.glob("*.py"))
    assert scanned == modules, (
        f"the scanner saw {scanned} but the package holds {modules}. A structural claim "
        "over a set the scanner did not actually read is the failure mode this whole file "
        "exists to prevent, so the coverage is asserted before the verdict is."
    )
    assert report.findings == [], "\n".join(
        [
            (
                f"{len(report.findings)} statement(s) in mainline_demo_api read a row in a "
                "shape nobody declared. Each is named with its file, its line and its "
                "correction:"
            ),
            *(finding.render() for finding in report.ordered()),
            "",
            (
                "The rule is scripts/qa/row_factory_ratchet.py. db.connection() opens "
                "row_factory=dict_row, so a statement that does not say what it expects "
                "gets whatever the caller chose - which is how refusal.py:235 became "
                "KeyError: 0 on beats 2 and 3 of every gate run, and how scenario.resolve "
                "bound the seven-letter string 'check_id' as a uuid."
            ),
        ]
    )


def test_every_module_in_the_package_is_in_a_named_row_convention() -> None:
    """Enumeration, so a new module cannot arrive without a convention.

    ``test_no_statement_...`` above proves nothing is WRONG. This proves nothing is
    UNCLASSIFIED, which is a different and weaker-looking claim that happens to be the one
    with the history: ``refusal.py`` never chose a convention, and the reason nobody
    noticed is that no test ever asked it to.
    """
    ratchet = _ratchet()
    report = ratchet.scan([_PACKAGE_SRC])
    measured = {
        Path(path).name: convention.verdict for path, convention in report.conventions.items()
    }
    assert measured == _EXPECTED_CONVENTIONS, (
        "the package's row-reading conventions have moved.\n"
        f"  measured: {dict(sorted(measured.items()))}\n"
        f"  expected: {dict(sorted(_EXPECTED_CONVENTIONS.items()))}\n"
        "A module that changed from 'silent' grew its first query and must now say how it "
        "reads it. A module that changed to 'mixed' declares position at one statement and "
        "nothing at another - that is refusal.py's 2026-08-12 state and the failure above "
        "will name the line. A module missing from the measured side was deleted; one "
        "missing from the expected side is new. Update this table deliberately."
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
    # Declared, and declared as the OTHER convention on purpose. This test is the one place
    # in the package where reading position and name off one connection two lines apart is
    # the assertion rather than the bug, and `# rowshape:` is how the ratchet is told which
    # of the two a statement means. It is a declaration, not a suppression: change `name`
    # to `position` here and the ratchet fails with `declared_shape_contradicted`.
    assert production_conn.execute("SELECT 4 AS four").fetchone() == {"four": 4}  # rowshape: name


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

    There is deliberately no ``except KeyError`` here. One used to exist, to turn the known
    ``refusal.py:235`` blocker into a legible sentence while that line was somebody else's
    file. The line is fixed. Keeping the wrapper would now convert any genuine regression
    into a prose assertion about a defect that no longer exists — which is worse than the
    raw exception, because the raw exception carries a traceback pointing at the statement
    that actually failed. Let the KeyError be a KeyError.
    """
    restore = conn.autocommit
    if conn.autocommit:
        conn.autocommit = False
    try:
        return gate_run(conn)
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

    Unwrapped, for the reason ``_run`` gives: the blocker this used to translate is fixed,
    and a translation layer over a fixed defect only hides the next one.
    """
    try:
        status, payload = handle_transition(
            "demo_gate_run", {}, {"run_id": "w1-rowfactory-contract"}, production_conn
        )
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
