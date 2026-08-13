# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``refusal.py`` gives the same answer whatever factory opened the connection.

THE DEFECT THIS FILE EXISTS FOR
-------------------------------
``mainline_demo_api.db.connection`` opens **every** production connection with
``psycopg.rows.dict_row`` (``db.py:309``). ``refusal._explain`` runs one statement whose
single projection is a bare function call, so CockroachDB v26.2.5 names the output column
after the function — ``explain_refusal`` — and under ``dict_row`` the row is a one-key
``dict``. The module read it as ``row[0]``, which is ``KeyError: 0``.

Measured on the local pinned node before the fix, in ``w_w1``::

    DESCRIPTION NAMES: ['explain_refusal']
    SHAPE: dict ['explain_refusal']
    row[0] -> KeyError: 0
    _explain through db.connection()      -> RAISED KeyError: 0
    refusal_payload through db.connection() -> RAISED KeyError: 0

``gate_run._record_refusal`` reaches it on beats 2 and 3 of every gate run and
``transitions._refused`` on every kernel refusal, so no path through the demo avoided it.
``evidence/deploy/acceptance.json`` records the two resulting 500s verbatim.

WHY EVERY CLAIM HERE IS MADE TWICE
----------------------------------
Once through :func:`mainline_demo_api.db.connection` — **the real production factory, not
a hand-rolled ``psycopg.connect(..., row_factory=dict_row)``**, which would only assert
that this file agrees with itself — and once through an explicit ``tuple_row``
connection. Then the two answers are required to be EQUAL. Proving only the direction that
was broken would reproduce the original mistake with the operands swapped: a suite that
only ever runs under one factory is exactly what let this defect ship.

The production caller sets ``conn.autocommit = False`` before a gate run
(``transitions._demo_gate_run``), and ``gate_run`` keeps that one transaction alive across
four beats while calling ``_explain`` three times inside it. :func:`_in_transaction`
mirrors that rather than opening a differently-configured connection, because the
``SAVEPOINT`` fence is only meaningful inside a transaction that has something to lose.

NOTHING HERE WRITES
-------------------
``trappoint.explain_refusal`` has no write statement in its body (``0119a``), and every
subject these tests name already exists in the seeded history. The two constraints used
are chosen so that both branches of :func:`refusal._explain` are exercised without an
INSERT: ``epoch_pin_permit`` reaches the decomposition and RETURNS a payload — the branch
that carried the defect — and ``identity_conserved_when_issued`` against a permit whose
projected counter is zero RAISES ``P0001``, which is the branch the ``SAVEPOINT`` exists
for.

THE RAISING CONSTRAINT, MEASURED — AND WHY IT IS NOT THE FLAGSHIP ANY MORE
-------------------------------------------------------------------------
This file used to name ``gate_closed_when_issued`` as the raising constraint, on the
stated premise that the seeded permit's ``open_blocking`` was 0. **The premise did not
rot: the WORLD under it was replaced, on purpose, and this file was not told.** The
fixture that built the permit used to mint one — a random uuid, ``state='draft'``, its one
blocking check already carrying a live ``applied`` disposition, therefore
``open_blocking = 0`` and ``gate_closed_when_issued`` genuinely unable to decompose.
``conftest.py`` was then rewritten to stop inventing a subject and to apply
``demo_world.sql`` + ``demo_permit.sql`` — the two files ``scripts/deploy/seed_demo.py``
puts into CockroachDB Cloud — and **the deployed world has an OPEN obligation**, because
an open obligation is what the demo is about. Measured side by side on 2026-08-13: the
parallel world's permit ``80c6bd4a-…`` ``draft`` ``open_blocking=0``, one check, one live
disposition; the deployed world's permit ``dec0de00-0006-…`` ``dispositioned``
``open_blocking=1``, one check, **zero** dispositions.

So the two tests below were not testing what they said from the moment the fixture became
honest, and nothing in the suite noticed for as long as no one ran it against a cluster.

``gate_closed_when_issued`` also cannot come back. ``gate_run.CF01_EXHIBIT`` *is* that
constraint, beat 2 of every gate run refuses on it, and ``test_gate_run.py`` requires
``open_blocking_projected >= 1`` on this same permit (``:667``) and a ``23514`` naming it
(``:678``). One permit cannot have that counter both non-zero for the demo and zero for
this file. The requirement here has always been *a permit whose projected counter is zero*
— the constraint name was only ever the instrument for reaching it — so the instrument
moves and the requirement does not.

Measured 2026-08-13 against ``w3_demo_api_123396ff6486`` (fingerprint of the migration
chain plus ``demo_world.sql`` + ``demo_permit.sql`` at ``073dfea``), on the seed's one
permit ``dec0de00-0006-4000-8000-000000000001`` (``state='dispositioned'``,
``gate_epoch=1``), all six ``mainline.permit`` counter constraints (``0050:114-122``)::

    open_blocking          = 1   gate_closed_when_issued        -> RETURNS declarative
    open_residue           = 0   identity_conserved_when_issued -> RAISES  P0001
    open_conflicts         = 0   conflicts_resolved_when_issued -> RAISES  P0001
    open_warrants          = 0   no_open_warrant_when_issued    -> RAISES  P0001
    unmodelled_asset_count = 0   boundary_certified_when_issued -> RAISES  P0001
    unmet_floor_count      = 0   reading_floor_when_issued      -> RAISES  P0001

Five were available; ``open_residue`` is the one taken, because it is the one whose being
zero is a CLAIM THE DEMO MAKES rather than an accident of what nobody got round to
seeding. ``permit.open_residue`` is projected by ``fn_residue_counter`` over
``mainline.identity_residue`` (``0145b:54-56``); that table holds 0 rows in the seeded
database, and ``demo_world.sql`` §7 states the same thing about the commit it seeds —
*"Nothing in this world is residue"* — which is why its ``cbm_account`` is a balanced zero
a judge can be invited to confirm on camera. A counter the demo asserts is zero will not
drift the way the counter the demo exists to MOVE did.
:func:`test_the_counter_behind_the_raising_constraint_is_zero` pins the measurement so the
next drift names itself instead of arriving as a dict that is not ``None``.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row, tuple_row

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:  # pragma: no cover - conftest.py normally does this first
    sys.path.insert(0, str(_SRC))

from mainline_demo_api import db as db_mod  # noqa: E402
from mainline_demo_api import refusal as refusal_mod  # noqa: E402
from mainline_demo_api.refusal import Diagnosis, refusal_payload  # noqa: E402

pytestmark = pytest.mark.requires_cluster

#: The column CockroachDB v26.2.5 gives ``_EXPLAIN_SQL``'s single unaliased projection.
#: A MEASUREMENT, pinned by :func:`test_the_decomposition_column_is_named_after_the_function`
#: and deliberately NOT depended on by ``refusal.py`` — see the negative control below.
_MEASURED_COLUMN = "explain_refusal"

#: Reaches the decomposition against any permit that exists, whatever its counters say
#: (``0119a`` §3), so the branch that carried the defect runs without seeding anything.
_RETURNS = "epoch_pin_permit"

#: A real ``mainline.permit`` CHECK (``0050:115``) whose projected counter is measured
#: zero, so ``0119a`` refuses to decompose it with ``P0001`` rather than emit a plausible
#: reason set — the branch the ``SAVEPOINT`` fence exists to survive. Measured 2026-08-13:
#: ``open_residue = 0`` on the seeded permit, ``mainline.identity_residue`` empty. It is
#: NOT ``gate_closed_when_issued`` any more: that counter is 1, because it is the one the
#: demo's beat 2 refuses on. The module docstring carries all six measurements.
_RAISES = "identity_conserved_when_issued"

#: The counter ``_RAISES`` decomposes, and the statement that reads it. Written out rather
#: than interpolated so the column name is visible in the file that depends on it.
_RAISES_COUNTER = "open_residue"
_RAISES_COUNTER_SQL = "SELECT open_residue FROM mainline.permit WHERE permit_id = %s"

_ATTEMPT: dict[str, Any] = {"kind": "merge", "gate_epoch": 0}

#: Fixed so that equality between the two factories is over what the DATABASE said and
#: not over a freshly minted uuid4 and a clock read.
_OBSERVED_AT = "2026-08-13T00:00:00Z"
_REFUSAL_ID = "00000000-0000-4000-8000-00000000f1ed"

_KEYERROR_DIAGNOSIS = (
    "refusal._explain raised {exc}. That is the defect this file exists for: "
    "db.py:309 opens production connections with dict_row, the single column of "
    "refusal._EXPLAIN_SQL is named 'explain_refusal', and a positional read of a dict "
    "row is KeyError: 0. Route the statement through scenario.positional(conn, sql, "
    "params) and take the row's single VALUE."
)


def _diagnosis(constraint: str) -> Diagnosis:
    """A refusal carrying *constraint* as a reported exhibit."""
    return Diagnosis("23514", constraint, "reported", f"refused by mainline.{constraint}")


@contextmanager
def _in_transaction(conn: psycopg.Connection[Any]) -> Iterator[psycopg.Connection[Any]]:
    """Put *conn* in the state a gate run puts it in, and leave nothing behind.

    ``transitions._demo_gate_run`` clears autocommit and ``gate_run`` then holds one
    transaction open across four beats. The rollback is unconditional: every statement
    these tests issue is a read, so there is nothing to keep, and a test that left a
    transaction open would poison the session-scoped fixture for everything after it.
    """
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.autocommit = was_autocommit


@pytest.fixture
def production_conn(conn: psycopg.Connection[Any]) -> psycopg.Connection[Any]:
    """The connection ``db.connection()`` really hands a Lambda. Premise, not decoration."""
    assert conn.row_factory is dict_row, (
        f"db.connection() no longer opens with dict_row (got {conn.row_factory!r}). "
        "Everything in this file is about the mismatch between that factory and a "
        "statement read by position; if the factory changed, reads.py's name-keyed "
        "accesses changed with it and this file needs rewriting, not deleting."
    )
    return conn


@pytest.fixture
def tuple_conn(demo_dsn: str) -> Iterator[psycopg.Connection[Any]]:
    """The same database through psycopg's default row factory."""
    with psycopg.connect(demo_dsn, autocommit=False, row_factory=tuple_row) as other:
        yield other
        other.rollback()


@pytest.fixture
def permit_id(seed: dict[str, str]) -> str:
    """The seeded permit — a subject that EXISTS.

    ``0119a`` refuses with ``P0001`` to diagnose a refusal against a row that does not,
    so a made-up uuid would exercise the raising branch and never reach the defect.
    """
    return seed["permit_id"]


# ═══════════════════════════════════════════════════════════════════════════════════════
# the premise, and the negative control that keeps it a premise rather than a dependency
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_decomposition_column_is_named_after_the_function(
    production_conn: psycopg.Connection[Any], permit_id: str
) -> None:
    """THE NEGATIVE CONTROL, part one: fail loudly if that column is ever renamed.

    Read off ``refusal._EXPLAIN_SQL`` itself, so this pins the statement the module runs
    and not a re-typed copy of it. It asserts a fact about CockroachDB, which is why it is
    allowed to fail: if a later version, or an added ``AS`` clause, changes the name, the
    RECORD OF WHY this row is read by position must be updated deliberately rather than
    drifting. Nothing in ``refusal.py`` breaks when it changes — part two proves that.
    """
    from psycopg.types.json import Jsonb

    with _in_transaction(production_conn) as live:
        cursor = live.cursor(row_factory=tuple_row).execute(
            refusal_mod._EXPLAIN_SQL,
            ("permit", permit_id, _RETURNS, Jsonb(_ATTEMPT)),
        )
        names = [column.name for column in cursor.description or []]

    assert names == [_MEASURED_COLUMN], (
        f"refusal._EXPLAIN_SQL now returns columns {names}, not ['{_MEASURED_COLUMN}']. "
        "That single unaliased projection being named after the function is the "
        "measurement that made a positional read of a dict_row row KeyError: 0, and it "
        "is written down in refusal.py's docstring and in "
        "evidence/deploy/rowfactory-defect.json. Update the reasoning in both rather "
        "than deleting this assertion."
    )


def test_the_answer_does_not_depend_on_that_column_name(
    production_conn: psycopg.Connection[Any], permit_id: str
) -> None:
    """THE NEGATIVE CONTROL, part two: rename the column and demand the same answer.

    This is what makes the fix a fix rather than a rewrite of the bug. Keying the row by
    ``row["explain_refusal"]`` would also have stopped the ``KeyError`` — and would have
    made ``refusal.py`` depend on a name CockroachDB chose for it, which the sibling
    statements in ``gate_run`` prove is not safe to depend on (``_FINGERPRINT_SQL``
    returns ten columns CockroachDB names ``count``, and a dict row keeps one). Position
    is the convention precisely because it survives this test.
    """
    from psycopg.types.json import Jsonb

    args = ("permit", permit_id, _RETURNS, Jsonb(_ATTEMPT))
    aliased = f"{refusal_mod._EXPLAIN_SQL} AS renamed_on_purpose"

    with _in_transaction(production_conn) as live:
        as_written = (
            live.cursor(row_factory=tuple_row).execute(refusal_mod._EXPLAIN_SQL, args).fetchone()
        )
        renamed_cursor = live.cursor(row_factory=tuple_row).execute(aliased, args)
        renamed_names = [column.name for column in renamed_cursor.description or []]
        renamed = renamed_cursor.fetchone()

    assert renamed_names == ["renamed_on_purpose"], renamed_names
    assert as_written is not None and renamed is not None
    assert as_written[0] == renamed[0], (
        "the decomposition changed when the column was renamed, which can only mean "
        "something on this path is reading the row by NAME. refusal.py must read the "
        "row's single value positionally."
    )


def test_the_counter_behind_the_raising_constraint_is_zero(
    production_conn: psycopg.Connection[Any], permit_id: str
) -> None:
    """THE PRECONDITION, measured — so the next drift names itself.

    Two tests below need ``0119a`` to REFUSE to decompose ``_RAISES``, and it refuses
    exactly when the counter behind that constraint is null or non-positive
    (``0119a:189``). That is a fact about the SEED, not about this file, and when it
    changed the two tests failed with ``assert {...} is not None`` — a message that names
    neither the counter nor the seed. This one does.

    It is the same instrument as the two negative controls above: a measurement pinned as
    a premise, allowed to fail, and updated deliberately rather than by drift. It reads
    and writes nothing, in keeping with the module docstring.
    """
    with _in_transaction(production_conn) as live:
        cursor = live.cursor(row_factory=tuple_row)
        row = cursor.execute(_RAISES_COUNTER_SQL, (permit_id,)).fetchone()

    assert row is not None, f"no permit {permit_id}"
    assert row[0] == 0, (
        f"mainline.permit.{_RAISES_COUNTER} is {row[0]}, not 0, on the seeded permit, so "
        f"trappoint.explain_refusal will now DECOMPOSE {_RAISES!r} instead of refusing to "
        "(0119a:189). The two tests below need a constraint whose projected counter is "
        "zero; the constraint NAME is only the instrument for reaching that state. "
        "Re-measure all six permit counters against the seeded permit, move _RAISES to "
        "one that is genuinely zero, and record the measurement and its date in this "
        "file's docstring — do NOT weaken the assertions below, and do NOT reshape the "
        "seed to restore this number."
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# _explain — both factories, then equality
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_explain_through_the_production_connection(
    production_conn: psycopg.Connection[Any], permit_id: str
) -> None:
    """The call that returned 500. Through the factory a Lambda really has."""
    with _in_transaction(production_conn) as live:
        try:
            explained, why_not = refusal_mod._explain(live, "permit", permit_id, _RETURNS, _ATTEMPT)
        except (KeyError, IndexError, TypeError) as exc:
            raise AssertionError(_KEYERROR_DIAGNOSIS.format(exc=repr(exc))) from exc

    assert why_not is None, f"the decomposition was declined: {why_not}"
    assert isinstance(explained, dict), f"expected a decomposition object, got {explained!r}"
    assert explained["constraint"] == _RETURNS
    assert explained["subject_id"] == permit_id
    assert explained["diagnosis"] == "declarative"
    assert explained["mus"], "a decomposition with an empty reason set explains nothing"


def test_explain_through_a_tuple_row_connection(
    tuple_conn: psycopg.Connection[Any], permit_id: str
) -> None:
    """The direction that always worked. Asserted so a fix cannot swap the breakage over."""
    explained, why_not = refusal_mod._explain(tuple_conn, "permit", permit_id, _RETURNS, _ATTEMPT)
    assert why_not is None, f"the decomposition was declined: {why_not}"
    assert isinstance(explained, dict)
    assert explained["diagnosis"] == "declarative"


def test_explain_returns_the_same_answer_under_both_factories(
    production_conn: psycopg.Connection[Any],
    tuple_conn: psycopg.Connection[Any],
    permit_id: str,
) -> None:
    """THE CONTRACT. Every field of the answer is a function of what the database said."""
    with _in_transaction(production_conn) as live:
        try:
            through_production = refusal_mod._explain(live, "permit", permit_id, _RETURNS, _ATTEMPT)
        except (KeyError, IndexError, TypeError) as exc:
            raise AssertionError(_KEYERROR_DIAGNOSIS.format(exc=repr(exc))) from exc

    through_tuples = refusal_mod._explain(tuple_conn, "permit", permit_id, _RETURNS, _ATTEMPT)

    assert through_production == through_tuples, (
        "refusal._explain gives two different answers to the same question depending on "
        "which factory opened the connection. The statement must declare the shape it is "
        "written against; it must not inherit one."
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# refusal_payload — the wire payload, both factories, then equality
# ═══════════════════════════════════════════════════════════════════════════════════════


def _payload(conn: psycopg.Connection[Any], permit_id: str, constraint: str) -> dict[str, Any]:
    return refusal_payload(
        conn,
        _diagnosis(constraint),
        subject_kind="permit",
        subject_id=permit_id,
        gate_epoch=1,
        attempt=_ATTEMPT,
        observed_at=_OBSERVED_AT,
        refusal_id=_REFUSAL_ID,
    )


def test_refusal_payload_through_the_production_connection(
    production_conn: psycopg.Connection[Any], permit_id: str
) -> None:
    """What ``gate_run`` puts in beat 2 and beat 3, built on the production path."""
    with _in_transaction(production_conn) as live:
        try:
            payload = _payload(live, permit_id, _RETURNS)
        except (KeyError, IndexError, TypeError) as exc:
            raise AssertionError(_KEYERROR_DIAGNOSIS.format(exc=repr(exc))) from exc

    assert payload["diagnosis"] == "declarative", (
        "the payload fell back to honest incompleteness, which means _explain returned "
        f"nothing: {payload['mus']}"
    )
    assert payload["sqlstate"] == "23514"
    assert payload["constraint"] == _RETURNS
    assert payload["constraint_source"] == "reported"
    assert payload["refusal_id"] == _REFUSAL_ID
    assert payload["observed_at"] == _OBSERVED_AT
    assert payload["spec_version"] == refusal_mod.SPEC_VERSION


@pytest.mark.parametrize("constraint", [_RETURNS, _RAISES])
def test_refusal_payload_returns_the_same_answer_under_both_factories(
    production_conn: psycopg.Connection[Any],
    tuple_conn: psycopg.Connection[Any],
    permit_id: str,
    constraint: str,
) -> None:
    """Both branches of _explain, both factories, and the payloads must be identical.

    ``_RAISES`` is included because the branch that returns early on ``psycopg.Error``
    never touched the defective line and could therefore agree across factories while the
    branch that mattered did not. Asserting only the branch that was broken would leave
    the other free to break next.

    This case is worth reading alongside the drift it survived: while ``_RAISES`` named a
    constraint whose counter had stopped being zero, this parametrisation ran BOTH of its
    cases through the decomposition and exercised the early-return branch not at all — and
    it stayed green throughout, because equality across factories held either way. A green
    parametrised case is not evidence that both of its parameters mean what they say.
    """
    with _in_transaction(production_conn) as live:
        try:
            through_production = _payload(live, permit_id, constraint)
        except (KeyError, IndexError, TypeError) as exc:
            raise AssertionError(_KEYERROR_DIAGNOSIS.format(exc=repr(exc))) from exc

    through_tuples = _payload(tuple_conn, permit_id, constraint)

    assert through_production == through_tuples, (
        f"the refusal payload for {constraint!r} differs between the production factory "
        "and tuple_row. This payload is what a judge reads; it may not depend on how the "
        "connection was opened."
    )


def test_the_declined_branch_declines_identically_under_both_factories(
    production_conn: psycopg.Connection[Any],
    tuple_conn: psycopg.Connection[Any],
    permit_id: str,
) -> None:
    """``0119a`` raises on drift; both factories must hear the same refusal to explain.

    ``_RAISES`` is ``identity_conserved_when_issued`` because ``mainline.permit
    .open_residue`` was measured 0 on the seeded permit on 2026-08-13 while
    ``open_blocking`` was 1 — see the module docstring for all six counters, and
    :func:`test_the_counter_behind_the_raising_constraint_is_zero` for the machine-checked
    form of that premise.
    """
    with _in_transaction(production_conn) as live:
        production_answer = refusal_mod._explain(live, "permit", permit_id, _RAISES, _ATTEMPT)

    tuple_answer = refusal_mod._explain(tuple_conn, "permit", permit_id, _RAISES, _ATTEMPT)

    explained, why_not = production_answer
    assert explained is None
    assert why_not is not None, "the raising branch did not raise"
    assert "not reproducible" in why_not or "drift" in why_not, (
        f"the seeded permit's counter is no longer zero, so {_RAISES!r} no longer "
        f"exercises the raising branch: {why_not!r}"
    )
    assert production_answer == tuple_answer


# ═══════════════════════════════════════════════════════════════════════════════════════
# the two properties a fix could quietly destroy
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_savepoint_fence_survives_a_raise_inside_one_open_transaction(
    production_conn: psycopg.Connection[Any], permit_id: str
) -> None:
    """``gate_run`` holds ONE transaction across four beats and calls ``_explain`` in it.

    ``0119a`` raises rather than emit a plausible reason set, and an unfenced raise would
    abort that transaction — turning a refusal the demo is supposed to SHOW into a lost
    run. Three calls in one transaction, the middle one raising, and the transaction has
    to still be usable afterwards.

    The middle call raises because ``mainline.permit.open_residue`` was measured 0 on the
    seeded permit on 2026-08-13, which is what makes ``0119a`` refuse to decompose
    ``_RAISES``. If that counter moves, this test stops fencing anything and
    :func:`test_the_counter_behind_the_raising_constraint_is_zero` says so first.
    """
    with _in_transaction(production_conn) as live:
        first = refusal_mod._explain(live, "permit", permit_id, _RETURNS, _ATTEMPT)
        declined = refusal_mod._explain(live, "permit", permit_id, _RAISES, _ATTEMPT)
        third = refusal_mod._explain(live, "permit", permit_id, _RETURNS, _ATTEMPT)

        assert declined[0] is None and declined[1] is not None
        assert first == third, "the transaction did not survive the raise intact"

        survived = live.cursor(row_factory=tuple_row).execute("SELECT 1").fetchone()
        assert survived == (1,), (
            "the transaction is unusable after a declined decomposition, so the SAVEPOINT "
            "fence is gone. gate_run keeps one transaction open across four beats and "
            "calls _explain inside it three times."
        )


def test_building_a_refusal_leaves_the_connection_handing_out_dicts(
    production_conn: psycopg.Connection[Any], permit_id: str
) -> None:
    """A warm container's next GET must still get dicts.

    One connection is reused across invocations, so a refusal that left the connection on
    ``tuple_row`` would break every one of ``reads.py``'s name-keyed accesses served after
    it. ``positional`` sets the factory on the CURSOR and mutates nothing.
    """
    with _in_transaction(production_conn) as live:
        _payload(live, permit_id, _RETURNS)

    assert production_conn.row_factory is dict_row
    assert production_conn.execute("SELECT 4 AS four").fetchone() == {"four": 4}


# ═══════════════════════════════════════════════════════════════════════════════════════
# the ratchet, over this one file
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_no_statement_in_refusal_inherits_the_connection_s_row_factory() -> None:
    """``conn.execute(...).fetch*()`` is the defect shape, and it is banned here.

    Structural rather than behavioural, and deliberately narrower than the package-wide
    ratchet: this file's behavioural tests only cover the statements a refusal happens to
    reach, and a statement added to ``refusal.py`` tomorrow would be covered by nothing
    until this fails.
    """
    path = Path(refusal_mod.__file__ or "")
    tree = ast.parse(path.read_text(encoding="utf-8"))

    offenders = [
        f"{path.name}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("fetchone", "fetchall", "fetchmany")
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Attribute)
        and node.func.value.func.attr == "execute"
        and not (
            isinstance(node.func.value.func.value, ast.Name)
            and node.func.value.func.value.id == "cursor"
        )
    ]

    assert offenders == [], (
        f"these fetches read whatever shape the CONNECTION was opened with: {offenders}. "
        "Route them through scenario.positional(conn, sql, params) so the statement "
        "declares the shape it is written against."
    )


def test_the_production_module_still_routes_through_positional() -> None:
    """The ratchet above bans a shape; this one requires the replacement to be present.

    A ratchet that only bans ``conn.execute(...).fetchone()`` is satisfied by deleting the
    statement. This asserts the module actually imports and uses the shared helper, so
    ``refusal.py`` cannot drift back to a private copy of it that skips the reasoning in
    ``scenario.positional``'s docstring.
    """
    from mainline_demo_api import scenario

    source = Path(refusal_mod.__file__ or "").read_text(encoding="utf-8")
    assert "from .scenario import positional" in source
    assert refusal_mod.positional is scenario.positional, (
        "refusal.positional is not scenario.positional. Three copies of a two-line helper "
        "are three places for it to drift."
    )
    assert db_mod.connection is not None  # the factory under test is still db.connection
