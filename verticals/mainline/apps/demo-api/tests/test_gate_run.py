# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
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

EVERY TRANSACTION THIS FILE COMMITS, AND WHAT GUARDS IT
--------------------------------------------------------
Two, and both are now run by :func:`trappoint_testkit.txn.run_txn` over
``trappoint_core.retry.run_gate`` — the WHOLE transaction, from ``BEGIN``, on a connection
opened for that attempt and thrown away if it loses:

* :func:`seed_history_into` — ~30 statements ending in two ``permit_event`` rows that read
  the previous ``chain_digest`` and then move the permit's head. It used to take a
  connection and commit; it now takes a DSN, because a retry handed an already-open
  connection retries inside the transaction that just failed, which ``spec/errors.md`` §2.1
  names as the mistake.
* :func:`_reissue` — a receipt and its lines, cloned from the receipt that displayed the
  obligation. It used to carry a hand-rolled three-attempt loop keyed on the psycopg
  EXCEPTION CLASS; that loop is deleted. One taxonomy, specified and spied on, beats two.

Everything else here is either DDL on an autocommit connection (``DROP``/``CREATE
DATABASE``, ``CONFIGURE ZONE``, the migration chain — CockroachDB restarts an implicit
transaction server-side, and DDL inside a multi-statement transaction can fail at ``COMMIT``
even when every statement succeeded), or a probe that reads and rolls back. Neither is a
multi-statement unit for a retry to be OF.

THE ROW FACTORY, AND WHY THIS FILE IS SPLIT IN TWO ALONG IT
-----------------------------------------------------------
Until 2026-08-13 every connection below was ``psycopg.connect(dsn, autocommit=…)`` —
psycopg's default ``tuple_row``. ``db.py:309`` opens every production connection with
``row_factory=dict_row``. So this suite exercised one row factory and the Lambda ran the
other, and ``evidence/deploy/rowfactory-defect.json`` names lines 249 and 256 of THIS file
as the precise reason nothing caught it: the one contract spanning the two paths was never
asserted by anybody, and a ``KeyError: 0`` reached a judge as a 500.

Every connection here now answers one question explicitly, and the answer differs by what
the test is claiming:

* **A claim about PRODUCTION behaviour** — anything that calls :func:`gate_run` — takes its
  connection from :func:`mainline_demo_api.db.connection`, the real factory, carrying
  ``db.py``'s own choice. Re-opening with ``row_factory=dict_row`` by hand would only
  assert that this file agrees with itself; it is ``db.py``'s choice and these statements
  that have to agree. ``db.connection()`` returns an AUTOCOMMIT connection and ``gate_run``
  refuses one, because the four beats sharing ONE transaction is the property being
  demonstrated — so :func:`_demo_gate_run_connection` clears the flag exactly the way
  ``transitions._demo_gate_run`` does, rather than opening a differently-configured
  connection, and what is under test is the path the Function URL actually takes.
* **A claim about the FIXTURE, or a probe of the database itself** — reading the demo
  subject, counting databases, applying the chain, seeding, proving the receipt table is
  append-only — keeps ``tuple_row``, now spelled out rather than inherited from psycopg's
  default, because those statements are read by POSITION and several of them return a
  column CockroachDB names ``count``. Each such connection carries a comment saying so.

``_every_table_count`` sits across the line: it runs on the production connection but reads
by position, so it asks the CURSOR for tuples the way ``scenario.positional()`` does. That
is the production convention for exactly this situation and it makes the helper correct
under either factory rather than under the one it happens to be handed.

THE SECOND WORLD, AND WHY ONE WAS NOT ENOUGH
--------------------------------------------
Everything described above runs on ``w4_database`` — the history ``scripts/proof/gate_refusal.py``
seeds. That is the right world for the beats' *mechanics*, and it is the wrong world for the
question "does the thing we deployed work", because **it is not the world that is deployed**.
``scripts/deploy/seed_demo.py`` applies ``verticals/mainline/db/seeds/demo/demo_world.sql``
and ``demo_permit.sql`` to CockroachDB Cloud; the proof seeder applies neither.

That difference had a price, measured on 2026-08-13. ``gate_run`` derived
``signer_credential_id`` as ``sha256(b"cred" + b"signer")``; the deployed seed enrols
``digest('mainline-demo/credential/demo.signer', 'sha256')``. Beat 4 therefore failed
``23503 disposition_signer_credential_id_fkey`` in front of a judge, the run answered
``200`` carrying its own verdict as ``NOT PROVEN`` — and the twenty tests above stayed
green, because the seeder they use called the same private helper the code did. **A test
that cannot disagree with the code it tests proves nothing.**

Re-measured on this tree with the derivation deliberately planted back into ``gate_run.py``:

    POST /v1/demo/gate-run → 200, verdict NOT PROVEN
    beat 4 admit  outcome=refused  sqlstate=23503  constraint=disposition_signer_credential_id_fkey
    $ pytest tests/test_gate_run.py -q     →  20 passed, 1 skipped

Twenty green against a demo that was broken. So the last section of this file runs the four
beats **a second time, in the other world**: against ``conftest.demo_dsn`` — a database built
by applying the two seed FILES the deployment applies — and **through** :func:`app.handler`
rather than by calling :func:`gate_run` directly, so the router, the dispatcher,
``_demo_gate_run``'s connection handling and the envelope are all inside the assertion. The
plant above turns that section red; that is the whole reason it exists.

It carries its own negative control rather than relying on a human to plant one:
:func:`test_the_admission_is_a_green_this_database_could_have_refused` substitutes the
derived value for the resolved one on the same seeded database and requires the ``23503``
back. A green whose red is never exhibited is a green nobody has checked.
"""

from __future__ import annotations

import ast
import contextlib
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import re
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import psycopg
import pytest
from psycopg.rows import tuple_row
from trappoint_testkit.txn import from_dsn, run_txn

# `requires_cluster` only. `verticals/mainline/apps/demo-api/pyproject.toml` runs with
# --strict-markers and registers exactly that one, so `integration` — which the repository
# root registers — would fail collection here. The narrower config wins because it is the
# one pytest resolves from this directory.
pytestmark = pytest.mark.requires_cluster

_HERE = Path(__file__).resolve()
_APP_SRC = _HERE.parents[1] / "src"
if str(_APP_SRC) not in sys.path:  # the app is not installed as a distribution yet
    sys.path.insert(0, str(_APP_SRC))

from mainline_demo_api import app, ratelimit  # noqa: E402
from mainline_demo_api import db as demo_db  # noqa: E402
from mainline_demo_api import gate_run as gate_run_mod  # noqa: E402
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
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _repo_root() -> Path:
    for candidate in (_HERE, *_HERE.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    raise RuntimeError("no workspace root above this test file")


#: The name this file gives the scratch database, minus the fingerprint.
_SCRATCH_PREFIX = "w_w4_api_transitions"


#: ``scripts/deploy/seed_demo.py``'s ``SEED_FILES``, parsed out of its SOURCE.
#:
#: Parsed rather than imported, and that is the cheaper of two correct options here.
#: ``conftest._deployer()`` imports the module to get this list and has to put the
#: repository root on ``sys.path`` and take it off again to do so — a session-wide change
#: its own docstring spends fourteen lines justifying. This file only needs the list of
#: NAMES, so it reads the assignment instead, exactly as
#: ``test_credentials.py::test_the_seed_file_list_is_the_deployment_s_own`` does. If the
#: assignment is ever renamed or computed, this raises rather than silently fingerprinting
#: a shorter list.
def _seed_files() -> tuple[str, ...]:
    """Return the seed file names ``scripts/deploy/seed_demo.py`` applies, in order."""
    source = (_repo_root() / "scripts" / "deploy" / "seed_demo.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AnnAssign | ast.Assign):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if "SEED_FILES" in names and node.value is not None:
                return tuple(ast.literal_eval(node.value))
    raise RuntimeError(
        "scripts/deploy/seed_demo.py declares no literal SEED_FILES, so this fixture "
        "cannot fingerprint what the deployment seeds and would adopt a database built "
        "from a seed it never read"
    )


def _fingerprint() -> str:
    """SHA-256 over everything that BUILDS this database: migrations, seeds, and the seeder.

    **THE MEASUREMENT HAZARD THIS CLOSES, AND WHY IT IS A FINGERPRINT AND NOT A UUID.**
    Until this change the name was ``os.environ.get("MAINLINE_W4_DATABASE",
    "w_w4_api_transitions")`` — a FIXED default. Two concurrent runs therefore shared one
    database, and :func:`w4_database` adopts a database whenever its demo subject still
    looks usable, so an adopted database built from an older copy of the migration chain or
    the seeder was indistinguishable from one built from this tree. That is not a
    hypothetical: ``docs/ci/demo-suite-order.md`` §4 records ``w_w4_api_transitions``
    growing monotonically across runs to 834 ``mainline.permit`` rows, and one published
    "unstable" list was corrupted by exactly this class of cross-run sharing.

    ``uuid4``/``token_hex`` would fix the collision and **lose** the adoption that makes
    this suite runnable twice in a minute — and, worse, would make it impossible to notice
    that a seed edit had been read against a stale database, because every run would build
    a new one and none would ever be wrong. The fingerprint fixes the collision AND makes
    the staleness unreachable: a changed input is a changed name, and a changed name is a
    rebuild. The pattern is the repository's own, three files away
    (``conftest._fingerprint``, ``conftest.demo_database``), and it is followed rather than
    re-invented.

    THREE INPUTS, and the third is this world's difference from ``conftest``'s. The
    migrations and ``SEED_FILES`` are in the digest for the reasons ``conftest`` gives.
    ``scripts/proof/gate_refusal.py`` is in it because THIS database is not seeded from the
    seed files at all — :func:`seed_history_into` builds it by calling that script's
    ``seed_history``, so it is this world's seeder, and leaving it out would leave the one
    input most likely to move unfingerprinted. ``SEED_FILES`` stays in the digest anyway
    because ``test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds`` reads
    both worlds in one assertion, so an edit to either must not be readable against a
    stale copy of the other.
    """
    digest = hashlib.sha256()
    root = _repo_root()
    migrations = root / "verticals" / "mainline" / "db" / "migrations"
    for path in sorted(migrations.glob("*.sql"), key=lambda p: p.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    seeds = root / "verticals" / "mainline" / "db" / "seeds" / "demo"
    for name in _seed_files():
        digest.update(name.encode("utf-8"))
        digest.update((seeds / name).read_bytes())
    seeder = root / "scripts" / "proof" / "gate_refusal.py"
    digest.update(seeder.name.encode("utf-8"))
    digest.update(seeder.read_bytes())
    return digest.hexdigest()[:12]


#: The scratch database this file builds and adopts. The ``MAINLINE_W4_DATABASE`` override
#: is KEPT: ``scripts/qa/demo_suite_falsification.py:499`` and
#: ``scripts/qa/demo_suite_order.py`` both set it to give a run a private database, and
#: removing it would silently re-collide the very harnesses that measure contamination.
SCRATCH_DB = os.environ.get("MAINLINE_W4_DATABASE") or f"{_SCRATCH_PREFIX}_{_fingerprint()}"


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


def seed_history_into(dsn: str) -> Any:
    """Seed one fresh demo history into *dsn* as ONE retried transaction. Returns a History.

    **A DSN AND NOT A CONNECTION, WHICH IS THE WHOLE CHANGE.** ``seed_history`` issues
    roughly thirty statements — a site, a clause version, a recall run with its Proof of
    Exhausted Recall, a boundary certificate, an exposure receipt with its lines, and two
    ``permit_event`` rows each of which READS the previous row's ``chain_digest`` and then
    moves the permit's head. That is a read-modify-write over one subject, and under
    ``SERIALIZABLE`` the loser of a race with any other writer is ``40001``. It used to
    commit with no retry at all.

    :func:`trappoint_testkit.txn.run_txn` retries the WHOLE transaction, from ``BEGIN``, on
    a connection nothing else has touched — which is why this function may not accept one.
    ``spec/errors.md`` §2.1 names the alternative as the mistake: a statement replayed into
    a transaction CockroachDB has already aborted is not a retry of anything, and every
    replay would meet the same ``40001`` until the budget ran out. The retry loop itself is
    ``trappoint_core.retry.run_gate`` — imported, never re-written, because a second loop
    would be a second SQLSTATE taxonomy and the one nobody spies on would win the day they
    disagreed.

    ``row_factory`` is psycopg's default ``tuple_row``, spelled out by omission the same way
    the previous call site left it: ``scripts/proof/gate_refusal.py`` reads its own rows by
    POSITION, and its connection is its contract rather than ``db.py``'s.
    """
    proof = _gate_refusal_module()
    return run_txn(from_dsn(dsn), proof.seed_history, subject_kind="permit")


#: The external reference ``scripts/proof/gate_refusal.py::seed_history`` gives its permit.
#: Selecting on it rather than on ``LIMIT 1`` is not fussiness: this suite deliberately
#: seeds MORE permits into the same database — the transitions are irreversible, so each
#: mutating test needs a subject of its own — and an unordered ``LIMIT 1`` picked one of
#: those on the second run, which made the demo permit look consumed. Measured, then fixed.
_DEMO_EXTERNAL_REF = "PTW-PROOF-1"

#: Everything the four beats need, read at ONE moment: the subject, the counter, the open
#: obligation, and — the part this fixture used to omit — the LIVE exposure receipt that
#: displayed that obligation.
#:
#: WHY THE RECEIPT IS IN THE READINESS PREDICATE AND NOT MERELY IN THE SEED.
#: ``scenario._RECEIPT_SQL`` requires ``r.expires_at > now()``, so with no live receipt
#: ``resolved.receipt_id`` is ``None`` and ``gate_run.py`` SKIPS beat 4 — the admission —
#: which makes the verdict ``NOT PROVEN``. ``seed_history`` issues its receipt with a
#: two-hour window, which is a correct TTL for a fresh run and a time bomb for a REUSED
#: database: this fixture adopts a scratch database whenever the demo permit is still in
#: state ``dispositioned`` with an open obligation, and both of those survive the receipt.
#: Measured on 2026-08-12: ``w_w4_api_transitions`` had been seeded on 2026-08-10T22:06Z
#: with a receipt that expired 2026-08-11T00:16:29Z, and five tests in this module were red
#: with ``observed outcome='skipped'`` — a FIXTURE failure reported as a product failure.
#:
#: The permit ordering prefers a subject that is still gate-ready. ``seed_history`` gives
#: EVERY permit it seeds the same ``external_ref``, so a database that was seeded twice
#: holds two candidates and an unordered ``fetchone()`` may pick the consumed one.
_DEMO_SUBJECT_SQL = """
WITH subject AS (
  SELECT p.permit_id, p.site_id, p.state::STRING AS state, p.open_blocking
    FROM mainline.permit p
   WHERE p.external_ref = %s
   ORDER BY (p.state::STRING = 'dispositioned' AND p.open_blocking >= 1) DESC, p.permit_id
   LIMIT 1
), obligation AS (
  SELECT s.permit_id, bc.check_id
    FROM subject s
    JOIN mainline.blocking_check bc ON bc.permit_id = s.permit_id
   WHERE NOT EXISTS (SELECT 1 FROM mainline.disposition d
                      WHERE d.check_id = bc.check_id
                        AND d.retracted_by IS NULL
                        AND (d.expires_at IS NULL OR d.expires_at > now()))
   ORDER BY bc.check_id
   LIMIT 1
)
SELECT s.permit_id,
       s.site_id,
       s.state,
       s.open_blocking,
       o.check_id,
       (SELECT r.receipt_id
          FROM mainline.exposure_receipt r
          JOIN mainline.exposure_line l ON l.receipt_id = r.receipt_id
         WHERE r.permit_id = o.permit_id
           AND l.check_id = o.check_id
           AND r.expires_at > now()
         ORDER BY r.issued_at DESC
         LIMIT 1) AS live_receipt_id,
       (SELECT max(r.expires_at)
          FROM mainline.exposure_receipt r
          JOIN mainline.exposure_line l ON l.receipt_id = r.receipt_id
         WHERE r.permit_id = o.permit_id
           AND l.check_id = o.check_id) AS receipt_horizon,
       now() AS observed_at
  FROM subject s
  LEFT JOIN obligation o ON o.permit_id = s.permit_id
"""


@dataclass(frozen=True, slots=True)
class DemoSubject:
    """What the demo permit looks like at one instant, and whether four beats can run on it."""

    permit_id: uuid.UUID
    site_id: uuid.UUID
    state: str
    open_blocking: int
    check_id: uuid.UUID | None
    live_receipt_id: uuid.UUID | None
    #: The latest ``expires_at`` of ANY receipt bound to the open obligation — i.e. the
    #: wall-clock instant after which beat 4 begins skipping. ``None`` when no receipt ever
    #: displayed this obligation.
    receipt_horizon: _dt.datetime | None
    observed_at: _dt.datetime

    @property
    def gate_ready(self) -> bool:
        """Beats 1-3: a client claim of ``dispositioned`` over an obligation still open.

        ``dispositioned`` is the only state from which ``merged`` is a legal edge, and an
        open obligation is what beats 2 and 3 are about. Anything else is a database whose
        demo subject has been CONSUMED.
        """
        return (
            self.state == "dispositioned" and self.open_blocking >= 1 and self.check_id is not None
        )

    @property
    def beat_four_ready(self) -> bool:
        """Beat 4 as well: a disposition's FK lands on ``(check_id, receipt_id)``."""
        return self.gate_ready and self.live_receipt_id is not None

    def why_not(self) -> str:
        """One sentence naming the first unmet condition, and what fixes it."""
        if self.state != "dispositioned":
            return f"state={self.state!r}, not 'dispositioned' — the demo subject is consumed"
        if self.open_blocking < 1:
            return f"open_blocking={self.open_blocking}, so beats 2 and 3 have nothing to refuse"
        if self.check_id is None:
            return "every blocking_check on this permit already carries a live disposition"
        horizon = (
            "never issued" if self.receipt_horizon is None else self.receipt_horizon.isoformat()
        )
        return (
            "no LIVE exposure receipt displays the open obligation (latest expires_at "
            f"{horizon}, now {self.observed_at.isoformat()}), so gate_run skips beat 4 and "
            "the verdict is NOT PROVEN. Re-issue a receipt or rebuild with "
            "MAINLINE_W4_REBUILD=1"
        )


def _subject(dsn: str) -> DemoSubject | None:
    """Read the demo subject out of *dsn*, or ``None`` when there is not one to read.

    DELIBERATELY ``tuple_row``, AND NOT THE PRODUCTION CONNECTION. This function makes no
    claim about ``gate_run``, ``handle_transition`` or the router: it is the fixture asking
    the database whether there is anything to run four beats ON, so what it must agree with
    is its own two statements, not ``db.py``. Both are read by POSITION and the first of
    them — ``SELECT count(*) FROM information_schema.tables`` — returns a single column
    CockroachDB names ``count``, so ``exists[0]`` is a ``KeyError`` under ``dict_row``:
    character for character the defect this wave exists to close, which is reason enough to
    spell the factory out here instead of inheriting psycopg's default and hoping.
    """
    with psycopg.connect(dsn, autocommit=True, row_factory=tuple_row) as probe:
        exists = probe.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'mainline' AND table_name = 'permit'"
        ).fetchone()
        if not (exists and exists[0]):
            return None
        row = probe.execute(_DEMO_SUBJECT_SQL, (_DEMO_EXTERNAL_REF,)).fetchone()
    if row is None:
        return None
    return DemoSubject(
        permit_id=row[0],
        site_id=row[1],
        state=str(row[2]),
        open_blocking=int(row[3]),
        check_id=row[4],
        live_receipt_id=row[5],
        receipt_horizon=row[6],
        observed_at=row[7],
    )


#: The most recent receipt that displayed this obligation, live or not. It is the row the
#: replacement is CLONED from, so nothing about the exposure is invented here.
_SOURCE_RECEIPT_SQL = """
SELECT r.receipt_id
  FROM mainline.exposure_receipt r
  JOIN mainline.exposure_line l ON l.receipt_id = r.receipt_id
 WHERE r.permit_id = %s AND l.check_id = %s
 ORDER BY r.issued_at DESC
 LIMIT 1
"""

#: ``INSERT … SELECT`` rather than a Python round-trip: every column except the identifier,
#: the digest and the two timestamps is COPIED from the receipt that actually displayed the
#: obligation, so the clone cannot drift from it. ``issued_at`` is ten minutes in the past
#: because ``fn_disposition_project`` prices ``reading_floor_met`` as
#: ``now() - issued_at >= tau0 + tokens/rho`` (0102 step 10); a receipt issued *now* would
#: record a floor that was not met. Both intervals are ``seed_history``'s own.
_CLONE_RECEIPT_SQL = """
INSERT INTO mainline.exposure_receipt
       (receipt_id, subject_kind, permit_id, actor_sub, issued_at, issued_hlc, expires_at,
        corpus_root, silence_receipt_id, policy_version, total_tokens, receipt_digest)
SELECT %s, r.subject_kind, r.permit_id, r.actor_sub,
       now() - INTERVAL '10 minutes', r.issued_hlc, now() + INTERVAL '2 hours',
       r.corpus_root, r.silence_receipt_id, r.policy_version, r.total_tokens, %s
  FROM mainline.exposure_receipt r
 WHERE r.receipt_id = %s
"""

_CLONE_LINES_SQL = """
INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, tokens)
SELECT %s, l.check_id, l.payload_digest, l.tokens
  FROM mainline.exposure_line l
 WHERE l.receipt_id = %s
"""


def reissue_exposure_receipt(
    conn: psycopg.Connection[Any], permit_id: uuid.UUID, check_id: uuid.UUID
) -> uuid.UUID | None:
    """Issue a fresh exposure receipt over the same obligation. Returns its id, or ``None``.

    THE REPAIR IS AN INSERT, AND IT HAS TO BE. ``0128d_trg_refuse_mutation_exposure_receipt``
    welds ``append_only`` onto ``mainline.exposure_receipt`` for every UPDATE and every
    DELETE, so an expired receipt cannot be extended and cannot be removed — which is the
    correct schema and the reason this function exists in the shape it does. Re-materialising
    the exposure is also what ``fn_disposition_project`` tells the caller to do in the
    message it raises: *"exposure receipt absent or expired — re-materialise before signing"*.

    ``None`` means no receipt has ever displayed this obligation, which is not a stale
    fixture but an unseeded one: the caller rebuilds.

    *conn* must carry ``tuple_row``: ``source[0]`` below is read by position. Both call
    sites supply one explicitly — :func:`_reissue` and the append-only test — because this
    is fixture repair, not a path any Lambda takes.
    """
    source = conn.execute(_SOURCE_RECEIPT_SQL, (permit_id, check_id)).fetchone()
    if source is None:
        return None
    receipt_id = uuid.uuid4()
    digest = hashlib.sha256(b"receipt" + str(receipt_id).encode("utf-8")).digest()
    conn.execute(_CLONE_RECEIPT_SQL, (receipt_id, digest, source[0]))
    conn.execute(_CLONE_LINES_SQL, (receipt_id, source[0]))
    return receipt_id


def _reissue(dsn: str, subject: DemoSubject) -> uuid.UUID | None:
    """``reissue_exposure_receipt`` in one committed transaction, retried by the ONE loop.

    The receipt and its lines are ONE transaction: a receipt committed without the line
    that binds it to the obligation would satisfy nothing — ``scenario._RECEIPT_SQL`` joins
    through ``exposure_line`` — and the next run would re-issue again, forever. It reads a
    source receipt and writes two rows derived from it, so it is a read-modify-write and the
    loser of a race is ``40001``.

    **THE HAND-ROLLED LOOP THAT USED TO BE HERE IS GONE, AND ITS DELETION IS THE POINT.**
    Three attempts, a bare ``except psycopg.errors.SerializationFailure``, and no ceiling on
    anything else: it retried the right code, but it was a SECOND retry taxonomy in a
    repository whose first one — ``trappoint_core.retry.run_gate`` — is specified by
    ``spec/errors.md`` §2.1/§4 and watched by ``tests/concurrency/test_retry_taxonomy_spy.py``.
    Two loops means two things to keep correct, and on the day they disagreed the one nobody
    was spying on would have won. It also discriminated on the psycopg EXCEPTION CLASS
    rather than on the SQLSTATE, and ``40001`` arrives in more than one costume
    (``RETRY_SERIALIZABLE``, ``WriteTooOldError``); only the code is the contract.

    ``tuple_row``, deliberately: this repairs the FIXTURE and asserts nothing about the
    production path. It is spelled out rather than inherited because
    :func:`reissue_exposure_receipt` reads its source receipt by position.
    """
    assert subject.check_id is not None
    check_id = subject.check_id
    return run_txn(
        from_dsn(dsn, row_factory=tuple_row),
        lambda conn: reissue_exposure_receipt(conn, subject.permit_id, check_id),
        subject_kind="permit",
        subject_id=str(subject.permit_id),
    )


@pytest.fixture(scope="session")
def w4_database() -> Iterator[str]:
    """A migrated database holding one seeded demo history. Reused when it is still usable.

    Reused rather than rebuilt because applying 271 migrations costs ~50 s on this node and
    a suite that pays that on every invocation is a suite nobody runs twice. Rebuilt
    automatically when the demo subject is missing or consumed, and unconditionally with
    ``MAINLINE_W4_REBUILD=1``, so a stale scratch database is self-healing rather than a
    confusing red.

    USABLE MEANS USABLE, NOT MERELY PRESENT. Until 2026-08-12 the adoption test asked only
    whether the permit was still ``dispositioned`` with an open obligation. Both of those
    outlive the two-hour exposure receipt ``seed_history`` issues, so a database seeded
    yesterday was adopted today with a dead receipt, ``gate_run`` skipped beat 4, and five
    tests below reported a product failure that was really a fixture failure. The predicate
    now covers every input the four beats consume, and a dead receipt is REPAIRED — by
    issuing a new one, because ``mainline.exposure_receipt`` is append-only — rather than by
    paying 50 s to rebuild a database whose only stale row is that one.

    EVERY CONNECTION THIS FIXTURE OPENS IS DELIBERATELY OFF THE PRODUCTION PATH. It builds
    the world the four beats run in; it does not run them. It talks to the ADMIN database
    rather than the demo one, it issues DDL no handler may issue, and it hands the
    repository's own seeder a connection whose contract is with ``scripts/proof/gate_refusal.py``
    and not with ``db.py``. ``tuple_row`` is therefore the right factory here and is spelled
    out at each place a row is actually read by position.
    """
    admin = _admin_dsn()
    try:
        # Reachability only: opened, proven, closed, no row ever read — so this one connect
        # is the single place in the fixture where the row factory could not matter.
        psycopg.connect(admin, autocommit=True).close()
    except psycopg.OperationalError as exc:  # pragma: no cover - depends on the host
        pytest.skip(f"no CockroachDB at {admin.split('@')[-1].split('?')[0]}: {exc}")

    dsn = _scratch_dsn()
    rebuild = os.environ.get("MAINLINE_W4_REBUILD", "").strip() not in ("", "0", "false")

    # tuple_row, deliberately: `SELECT count(*)` returns one column CockroachDB names
    # `count`, so `present_row[0]` below is a KeyError under dict_row. This asserts nothing
    # about the API — it asks the cluster whether the scratch database exists at all.
    with psycopg.connect(admin, autocommit=True, row_factory=tuple_row) as probe:
        present_row = probe.execute(
            "SELECT count(*) FROM [SHOW DATABASES] WHERE database_name = %s", (SCRATCH_DB,)
        ).fetchone()
    present = bool(present_row and present_row[0])

    subject = _subject(dsn) if present and not rebuild else None
    # The one repair worth attempting before falling back to a rebuild: the subject is
    # intact and only its exposure has aged out.
    if subject is not None and subject.gate_ready and not subject.beat_four_ready:
        _reissue(dsn, subject)
        subject = _subject(dsn)

    usable = subject is not None and subject.beat_four_ready
    if not usable:
        # DDL only — no row is read, and no handler may issue any of these three statements.
        with psycopg.connect(admin, autocommit=True) as probe:
            probe.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" CASCADE')
            probe.execute(f'CREATE DATABASE "{SCRATCH_DB}"')
            # 4500 is what CockroachDB Cloud Basic enforces. Pinning it locally keeps the
            # laptop from being more permissive than the cluster the demo will run on.
            probe.execute(
                f'ALTER DATABASE "{SCRATCH_DB}" CONFIGURE ZONE USING gc.ttlseconds = 4500'
            )

        proof = _gate_refusal_module()
        # The migration chain and the seed both belong to `scripts/proof/gate_refusal.py`,
        # which reads its own rows by position. Its connection is its contract, not db.py's:
        # handing it dict_row would be asserting something about the proof script that this
        # file has no business asserting, and would break it.
        with psycopg.connect(dsn, autocommit=True, row_factory=tuple_row) as work:
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
        # The DSN, not a connection: `seed_history_into` hands the whole transaction to
        # `run_txn`, which opens a fresh connection per attempt. A connection opened here
        # and passed in would put the retry INSIDE the transaction that had just failed.
        seed_history_into(dsn)
        subject = _subject(dsn)

    assert subject is not None, (
        f"{SCRATCH_DB} was rebuilt and no permit with external_ref {_DEMO_EXTERNAL_REF} is "
        "in it — seed_history did not run, or it ran against another database"
    )
    assert subject.beat_four_ready, (
        f"{SCRATCH_DB} was rebuilt and its demo subject still cannot drive four beats: "
        f"{subject.why_not()}"
    )
    permit_id, site_id = subject.permit_id, subject.site_id
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


@contextlib.contextmanager
def _demo_gate_run_connection(dsn: str) -> Iterator[psycopg.Connection[Any]]:
    """The connection the Function URL actually takes, prepared the way the Lambda does.

    :func:`mainline_demo_api.db.connection` is the REAL factory and the only thing that
    carries ``db.py``'s own ``row_factory=dict_row``. A hand-rolled
    ``psycopg.connect(dsn, row_factory=dict_row)`` would look identical and prove something
    weaker: that this file agrees with itself. The contract that has to hold — and that
    nothing asserted until 2026-08-13 — is between ``db.py``'s choice and the statements in
    ``gate_run.py``, ``scenario.py`` and ``refusal.py``.

    ``db.connection()`` returns an AUTOCOMMIT connection and ``gate_run`` refuses one,
    because the four beats sharing ONE transaction is the property being demonstrated.
    ``transitions._demo_gate_run`` clears the flag before calling; this mirrors that rather
    than opening a differently-configured connection, so nothing about the connection under
    test differs from the one a judge's POST arrives on.

    The flag is restored and the module-scope connection dropped on the way out, so a test
    cannot inherit an open transaction — or a cleared autocommit flag — from the one before
    it. That matters concretely: ``test_gate_run_refuses_an_autocommit_connection`` asserts
    the refusal on a connection whose ``autocommit`` is still ``True``.
    """
    conn = demo_db.connection(dsn=dsn)
    restore = conn.autocommit
    if conn.autocommit:
        conn.autocommit = False
    try:
        yield conn
    finally:
        with contextlib.suppress(psycopg.Error):
            conn.rollback()
        conn.autocommit = restore
        demo_db.close()


@pytest.fixture
def w4_conn(w4_database: str) -> Iterator[psycopg.Connection[Any]]:
    """The production connection, ready for the four beats.

    See :func:`_demo_gate_run_connection` for why it is obtained rather than opened.
    """
    with _demo_gate_run_connection(w4_database) as connection:
        yield connection


@pytest.fixture
def w4_tuple_conn(w4_database: str) -> Iterator[psycopg.Connection[Any]]:
    """A ``tuple_row`` connection for the tests that are about the FIXTURE, not the API.

    Kept separate from :func:`w4_conn` rather than folded into it because the two are
    asserting different things and the whole lesson of the row-factory defect is that a
    suite which cannot tell those apart proves neither. What this one asserts is that
    ``mainline.exposure_receipt`` refuses UPDATE and DELETE and that the fixture's repair
    is therefore an INSERT — a property of the SCHEMA, read by position, on statements no
    handler issues.
    """
    with psycopg.connect(w4_database, autocommit=False, row_factory=tuple_row) as connection:
        yield connection


@pytest.fixture(scope="session")
def run_once(w4_database: str) -> dict[str, Any]:
    """One gate run, shared by the assertions about it. Runs the demo exactly as shipped.

    "Exactly as shipped" is now literal: the connection is ``db.connection()``'s, with the
    autocommit flag cleared the way ``transitions._demo_gate_run`` clears it. Every
    assertion downstream of this fixture — the four beats, the refusal payloads, the
    contract check — is therefore a statement about the payload the deployed Function URL
    returns, and not about a payload that only this file's connection could produce.
    """
    with _demo_gate_run_connection(w4_database) as connection:
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
    """count(*) for every base table in the vertical's schemas, in ONE statement.

    *conn* is the PRODUCTION connection — this helper brackets a real ``gate_run`` — but
    both statements below are read by position, so each asks its CURSOR for tuples instead
    of inheriting whatever the connection carries. That is ``scenario.positional()``'s
    mechanism, and its reason applies here verbatim: the union's per-table ``count(*)``
    columns are what a ``dict`` row collapses, and nothing about *conn* is mutated, so the
    caller still holds ``db.py``'s factory afterwards. Written this way the helper is
    correct under either factory rather than under the one it happens to be handed.
    """
    tables = (
        conn.cursor(row_factory=tuple_row)
        .execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('mainline', 'mainline_meas', 'mainline_ops', 'trappoint') "
            "AND table_type = 'BASE TABLE' ORDER BY table_schema, table_name"
        )
        .fetchall()
    )
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
    rows = (
        conn.cursor(row_factory=tuple_row)
        .execute(f"SELECT t, n FROM ({union}) ORDER BY t")  # noqa: S608
        .fetchall()
    )
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
    """Two runs interleaved on two connections. Neither sees the other's writes.

    TWO CONTAINERS, NOT TWO CALLS TO ``connection()``. ``db.connection()`` is a per-execution-
    environment SINGLETON — that is its whole design, one connection per warm container —
    so calling it twice returns the same object and this test would silently become a test
    of one connection. Two concurrent judges hit two Lambda execution environments, and what
    each of those does on its cold start is ``db._open``. Opening through it rather than
    through ``psycopg.connect(..., row_factory=dict_row)`` means these two connections carry
    ``db.py``'s row factory, its ``connect_timeout`` and its ``application_name`` because
    ``db.py`` says so, and follow it if it ever changes its mind.

    ``_open`` returns autocommit connections, as production's do, so both have the flag
    cleared here exactly as ``transitions._demo_gate_run`` clears it.
    """
    one, two = demo_db._open(w4_database), demo_db._open(w4_database)
    assert one is not two, "db._open must hand out a second connection, not the singleton"
    try:
        one.autocommit = False
        two.autocommit = False
        a = gate_run(one)
        b = gate_run(two)
    finally:
        one.close()
        two.close()
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
    """The four beats share one transaction. A connection that cannot hold one is refused.

    Run against the PRODUCTION connection unmodified, because that connection is autocommit
    — ``db._open`` passes ``autocommit=True`` — and this is therefore not a hypothetical
    misuse but the exact state ``app.handler`` hands ``handle_transition`` on every POST.
    The refusal asserted here is the reason ``transitions._demo_gate_run`` must clear the
    flag, and the reason :func:`_demo_gate_run_connection` mirrors it. Delete that one line
    in ``transitions.py`` and the demo answers 500 instead of running; this is the test that
    says so, on the connection it would happen on.
    """
    connection = demo_db.connection(dsn=w4_database)
    try:
        assert connection.autocommit is True, (
            "db.connection() no longer returns an autocommit connection, so this test is no "
            "longer exercising the state the Function URL hands handle_transition"
        )
        with pytest.raises(ValueError, match="autocommit"):
            gate_run(connection)
    finally:
        demo_db.close()


# ═══════════════════════════════════════════════════════════════════════════════════════
# the fixture's own contract — the expired-receipt defect, pinned
# ═══════════════════════════════════════════════════════════════════════════════════════


def _subject_at(**overrides: Any) -> DemoSubject:
    """A gate-ready ``DemoSubject``, with named fields overridden. Nothing is read."""
    now = _dt.datetime(2026, 8, 12, 12, 27, tzinfo=_dt.UTC)
    fields: dict[str, Any] = {
        "permit_id": uuid.uuid4(),
        "site_id": uuid.uuid4(),
        "state": "dispositioned",
        "open_blocking": 1,
        "check_id": uuid.uuid4(),
        "live_receipt_id": uuid.uuid4(),
        "receipt_horizon": now + _dt.timedelta(hours=2),
        "observed_at": now,
    }
    fields.update(overrides)
    return DemoSubject(**fields)


def test_a_subject_whose_receipt_expired_is_gate_ready_and_not_beat_four_ready() -> None:
    """The exact shape of the 2026-08-12 defect, as a predicate rather than as a symptom.

    ``state`` and ``open_blocking`` are what the old adoption test looked at, and BOTH of
    them survive the receipt — which is why a database seeded yesterday was adopted today
    and then reported ``NOT PROVEN`` about a gate that was working perfectly.
    """
    dead = _subject_at(
        live_receipt_id=None,
        receipt_horizon=_dt.datetime(2026, 8, 11, 7, 50, tzinfo=_dt.UTC),
    )
    assert dead.gate_ready is True, "beats 1-3 have everything they need"
    assert dead.beat_four_ready is False, "beat 4 has no receipt to cite"
    why = dead.why_not()
    assert "LIVE exposure receipt" in why
    assert "2026-08-11T07:50:00+00:00" in why, why
    assert "NOT PROVEN" in why

    never = _subject_at(live_receipt_id=None, receipt_horizon=None)
    assert "never issued" in never.why_not()


def test_a_consumed_subject_is_reported_as_consumed_not_as_an_expiry() -> None:
    """The four unmet conditions are distinguished, because they have different remedies."""
    assert "consumed" in _subject_at(state="merged").why_not()
    assert "nothing to refuse" in _subject_at(open_blocking=0).why_not()
    assert "live disposition" in _subject_at(check_id=None).why_not()
    assert _subject_at().beat_four_ready is True


def test_the_fixture_yields_a_subject_beat_four_can_actually_run_on(w4_database: str) -> None:
    """The postcondition this fixture did not previously carry.

    Before 2026-08-12 this assertion was false on any scratch database more than two hours
    old, and the five tests above failed instead of this one — which is the wrong test
    failing, because none of them is about the fixture.
    """
    subject = _subject(w4_database)
    assert subject is not None, f"no permit with external_ref {_DEMO_EXTERNAL_REF}"
    assert subject.beat_four_ready, subject.why_not()
    assert subject.receipt_horizon is not None
    assert subject.receipt_horizon > subject.observed_at, (
        "the fixture yielded with a receipt that has already expired: horizon "
        f"{subject.receipt_horizon.isoformat()} <= now {subject.observed_at.isoformat()}"
    )


def test_an_expired_receipt_is_repaired_by_issuing_one_not_by_editing_one(
    w4_tuple_conn: psycopg.Connection[Any], w4_database: str
) -> None:
    """Why the repair is an INSERT: the receipt table refuses UPDATE and DELETE.

    ``0128d_trg_refuse_mutation_exposure_receipt`` welds ``append_only`` onto
    ``mainline.exposure_receipt``. That is asserted here against the running database rather
    than read off the migration, because the reason ``reissue_exposure_receipt`` clones a
    row instead of extending one is a property of the schema and not of this worker's taste.

    ``w4_tuple_conn`` and not ``w4_conn``: nothing here goes near ``gate_run``, the four
    statements below are the fixture's own repair read by position, and the UPDATE and
    DELETE being probed are ones no handler is permitted to issue. A production connection
    would be a costume, not a claim.

    Everything this test writes is rolled back.
    """
    subject = _subject(w4_database)
    assert subject is not None and subject.check_id is not None
    live_before = subject.live_receipt_id
    assert live_before is not None

    for statement in (
        (
            "UPDATE mainline.exposure_receipt SET expires_at = now() + INTERVAL '2 hours' "
            "WHERE receipt_id = %s"
        ),
        "DELETE FROM mainline.exposure_receipt WHERE receipt_id = %s",
    ):
        w4_tuple_conn.execute("SAVEPOINT append_only_probe")
        with pytest.raises(psycopg.Error) as raised:
            w4_tuple_conn.execute(statement, (live_before,))
        assert raised.value.sqlstate == "P0001", statement
        w4_tuple_conn.execute("ROLLBACK TO SAVEPOINT append_only_probe")
        w4_tuple_conn.execute("RELEASE SAVEPOINT append_only_probe")

    issued = reissue_exposure_receipt(w4_tuple_conn, subject.permit_id, subject.check_id)
    assert issued is not None and issued != live_before
    row = w4_tuple_conn.execute(_DEMO_SUBJECT_SQL, (_DEMO_EXTERNAL_REF,)).fetchone()
    assert row is not None
    assert row[5] == issued, "the re-issued receipt is the one scenario._RECEIPT_SQL picks"
    lines = w4_tuple_conn.execute(
        "SELECT check_id FROM mainline.exposure_line WHERE receipt_id = %s", (issued,)
    ).fetchall()
    assert [line[0] for line in lines] == [subject.check_id], (
        "the clone carries the exposure line that binds it to the obligation; without it "
        "the disposition's fk_exposure has nothing to land on"
    )
    w4_tuple_conn.rollback()
    assert _subject(w4_database).live_receipt_id == live_before, "the probe left nothing behind"


# ═══════════════════════════════════════════════════════════════════════════════════════
# THE SECOND WORLD — four beats, through the real handler, on the seed the cloud carries
# ═══════════════════════════════════════════════════════════════════════════════════════
#
# See the module docstring for the measurement that made this section necessary. In one
# line: every assertion above runs on `scripts/proof/gate_refusal.py`'s history, which
# enrols `_sha("cred", "signer")` at line 844 — the same value `gate_run` used to derive —
# so the seeder and the code agreed with each other and neither had ever met
# `verticals/mainline/db/seeds/demo/demo_world.sql`, which is what is DEPLOYED.
#
# Nothing here re-seeds anything. `conftest.demo_database` already builds a database by
# applying the two seed FILES through `scripts/deploy/seed_demo.apply_seeds` — the
# deployment's own applier, file list and 40001 retry loop — and hands back the identifiers
# it then read out of that database. This section consumes `demo_dsn` and `seed` so there
# is exactly one such fixture in this directory rather than a second one that could drift
# from it. `w4_database` stays where it is: the two worlds are both wanted, and the point
# of this section is that they are DIFFERENT.


#: What ``gate_run`` used to bind: ``sha256(b"cred" + b"signer")`` and its countersigner
#: twin. Spelled out rather than imported from ``gate_run._sha``, and the asymmetry IS the
#: design — importing the helper is exactly what let four files agree with each other and
#: with nothing that ships. Here the two values are pinned as results a correct run must
#: never produce, and as the payload of the negative control below.
_DERIVED_SIGNER_CREDENTIAL: Final = hashlib.sha256(b"credsigner").digest()
_DERIVED_COUNTERSIGNER_CREDENTIAL: Final = hashlib.sha256(b"credcosigner").digest()

#: The foreign key beat 4 died on, named once so every assertion below names the same thing
#: ``mainline.disposition`` does (migration ``0066_disposition.sql``:117-118).
_CREDENTIAL_FKEY: Final = "disposition_signer_credential_id_fkey"

#: The four beats as the DEPLOYED seed must produce them:
#: ``(ordinal, name, outcome, sqlstate, constraint, constraint_source)``.
#:
#: Restated here rather than read off ``beat["expected"]`` on purpose. ``gate_run`` computes
#: ``matched_expectation`` by comparing what happened against expectations ``gate_run``
#: itself declares, so a suite that asserted only that boolean would be asserting that the
#: module under test agrees with the module under test — the shape of defect this whole
#: section exists to close, one level up. This tuple is the second opinion, and if
#: ``gate_run``'s own expectations are ever loosened these assertions go red anyway.
_DEPLOYED_BEATS: Final[tuple[tuple[int, str, str, str, str | None, str | None], ...]] = (
    (1, "read", "read", ADMISSION_SQLSTATE, None, None),
    (2, "merge", "refused", CF01_SQLSTATE, CF01_EXHIBIT, "reported"),
    (3, "projection_drift_attack", "refused", CF03_SQLSTATE, CF03_EXHIBIT, "parsed"),
    (4, "admit", "admitted", ADMISSION_SQLSTATE, None, None),
)


def _gate_run_event(run_id: str) -> dict[str, Any]:
    """A Lambda Function URL invocation of ``POST /v1/demo/gate-run``, payload format 2.0.

    Built to the shape ``app._method``, ``app._path``, ``app._body`` and ``ratelimit.check``
    actually read, so what is exercised below is the router's own parsing rather than a
    convenient dict. ``sourceIp`` is present because the rate bound keys a bucket on it and
    an event without one would exercise a different branch of ``ratelimit`` than a judge's
    browser does.
    """
    return {
        "version": "2.0",
        "rawPath": "/v1/demo/gate-run",
        "rawQueryString": "",
        "headers": {"content-type": "application/json", "accept": "application/json"},
        "requestContext": {
            "http": {
                "method": "POST",
                "path": "/v1/demo/gate-run",
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.7",
                "userAgent": "mainline-tests/w6",
            },
            "stage": "$default",
        },
        "body": json.dumps({"run_id": run_id}),
        "isBase64Encoded": False,
    }


@contextlib.contextmanager
def _published_environment(dsn: str, seed: dict[str, str]) -> Iterator[None]:
    """The environment ``infra/modules/demo-api`` publishes, and nothing it does not.

    ``MAINLINE_DEMO_PERMIT_ID`` is set because the module sets it: the seed's permit is
    ``dec0de00-0006-…``, while ``scenario.from_env``'s fallback is the uuid5 derivation
    ``077a6fdd-…``, so without it the run resolves nothing and 422s.

    **``MAINLINE_DEMO_SIGNER_SUB`` and ``MAINLINE_DEMO_COUNTERSIGNER_SUB`` are deliberately
    REMOVED here, and that is a measurement rather than an oversight.** At ``HEAD`` (2dc5c86)
    the module publishes neither — ``git show HEAD:infra/modules/demo-api/main.tf`` names
    only ``MAINLINE_DEMO_DATABASE`` and ``MAINLINE_DEMO_PERMIT_ID`` — so the deployed Lambda
    reaches beat 4 on ``scenario.py``'s committed defaults, and those two subjects are
    load-bearing for the credential lookup. Running with them absent is running the weaker
    of the two configurations, which is the one worth asserting.
    ``test_the_signer_subjects_beat_four_falls_back_to_are_the_ones_the_seed_enrols`` pins
    the coupling that silence depends on. ``MAINLINE_DEMO_SITE_ID`` is removed for the same
    reason and a different finding: the module publishes none and none is needed, because
    ``fn_disposition_project`` projects the column away.

    The previous values are restored on the way out. This fixture shares a process with
    ``w4_database``, which sets three of these names to the PROOF world's identifiers for
    the whole session; leaving them clobbered would silently point the twenty tests above at
    a subject they were not written against.
    """
    absent = (
        f"{scenario_mod.ENV_PREFIX}SIGNER_SUB",
        f"{scenario_mod.ENV_PREFIX}COUNTERSIGNER_SUB",
        f"{scenario_mod.ENV_PREFIX}SITE_ID",
    )
    present = {
        demo_db.DSN_ENV: dsn,
        f"{scenario_mod.ENV_PREFIX}PERMIT_ID": seed["permit_id"],
    }
    previous = {name: os.environ.get(name) for name in (*present, *absent)}
    try:
        for name in absent:
            os.environ.pop(name, None)
        os.environ.update(present)
        # `db` caches the resolved DSN and the connection for the life of an execution
        # environment, and this process IS one execution environment shared with every
        # other test in the session. Without this the handler would answer against
        # whichever database the previous test opened.
        demo_db.reset_dsn_cache()
        yield
    finally:
        demo_db.reset_dsn_cache()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _invoke_gate_run(dsn: str, seed: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """One ``POST /v1/demo/gate-run`` through :func:`app.handler`. Returns (response, payload).

    ``ratelimit.reset()`` first, and it is not decoration: ``ratelimit``'s buckets are
    module-scope state belonging to one execution environment, and a pytest process is one
    execution environment shared with ``test_ratelimit.py``. A neighbour that drained the
    global bucket would turn this into a ``429`` and the failure would name the wrong
    module. Resetting refills; it does not reconfigure, and no environment variable can
    disarm the limiter (``ratelimit`` module docstring).
    """
    ratelimit.reset()
    with _published_environment(dsn, seed):
        response = app.handler(_gate_run_event(str(uuid.uuid4())))
    body = json.loads(response["body"])
    return response, body


@pytest.fixture(scope="session")
def deployed_seed_response(demo_dsn: str, seed: dict[str, str]) -> tuple[dict[str, Any], Any]:
    """One gate run on the DEPLOYED seed, through the router, shared by the assertions.

    Session-scoped for the same reason :func:`run_once` is: the run is expensive and every
    assertion below is about one payload. It is a different payload from ``run_once``'s in
    two independent ways — a different database and a different entry point — and both
    differences are the point.
    """
    return _invoke_gate_run(demo_dsn, seed)


@pytest.fixture(scope="session")
def deployed_seed_run(deployed_seed_response: tuple[dict[str, Any], Any]) -> dict[str, Any]:
    """The gate-run payload out of the envelope the handler returned."""
    _, body = deployed_seed_response
    assert isinstance(body, dict) and "data" in body, (
        "POST /v1/demo/gate-run did not return an invoke envelope on the deployed seed: "
        f"{json.dumps(body)[:600]}"
    )
    return dict(body["data"])


def test_the_real_handler_answers_the_deployed_seed_with_a_gate_run_envelope(
    deployed_seed_response: tuple[dict[str, Any], Any],
) -> None:
    """200, ``no-store``, and the contract this payload is governed by — off the router.

    Nothing here calls ``gate_run``. The path is ``app.handler`` → ``app._transition`` →
    ``transitions.handle_transition`` → ``transitions._demo_gate_run`` → ``gate_run``, which
    is the path a judge's POST takes, and each of those four hops is a place a working
    ``gate_run`` has previously been rendered unreachable — ``app._routes()`` returned
    sixteen rows and no ``/v1/demo/gate-run`` while every beat below it worked
    (``tests/test_routes_gate_run.py``).
    """
    response, body = deployed_seed_response
    assert response["statusCode"] == 200, json.dumps(body)[:600]
    assert response["headers"]["cache-control"] == "no-store"
    assert body["resource"] == "demo_gate_run"
    assert body["schema_id"] == GATE_RUN_SCHEMA_ID


def test_all_four_beats_run_through_the_real_handler_on_the_deployed_seed(
    deployed_seed_run: dict[str, Any],
) -> None:
    """The four beats, on the database built from ``demo_world.sql`` + ``demo_permit.sql``.

    This is the assertion the twenty above could not make: the world it runs in is the world
    ``scripts/deploy/seed_demo.py`` puts into CockroachDB Cloud, byte for byte, so the
    agreement between the seed and the code is now something a test can DISAGREE with.
    """
    observed = tuple(
        (
            beat["ordinal"],
            beat["name"],
            beat["outcome"],
            beat["sqlstate"],
            beat["constraint"],
            beat["constraint_source"],
        )
        for beat in deployed_seed_run["beats"]
    )
    assert observed == _DEPLOYED_BEATS, (
        "the four beats the DEPLOYED seed produced are not the four beats this demo "
        f"claims. Observed {observed!r}"
    )
    assert all(beat["matched_expectation"] for beat in deployed_seed_run["beats"])


def test_beat_four_admits_on_the_deployed_seed_rather_than_23503(
    deployed_seed_run: dict[str, Any],
) -> None:
    """Blocker 1, as a test: the admission beat, on the deployed seed, through the handler.

    ``23503`` is called out by name because it is what this beat actually did on 2026-08-13
    and because the taxonomy in ``refusal.classify`` treats it as a REFUSAL — so the run
    still answered ``200``, still filled a ``refusal`` payload, and reported a foreign-key
    violation in a position a reader takes for an exhibit the gate produced. It had not.
    """
    admit = deployed_seed_run["beats"][3]
    assert admit["name"] == "admit"
    assert admit["sqlstate"] != "23503" or admit["constraint"] != _CREDENTIAL_FKEY, (
        "beat 4 failed the credential foreign key against the database the deployment "
        "actually builds. mainline.disposition.signer_credential_id is a FK onto "
        "mainline.signing_credential and demo_world.sql enrols "
        "digest('mainline-demo/credential/demo.signer','sha256'); anything gate_run "
        "DERIVES instead of reading is a different 32 bytes. Resolve it, do not re-derive "
        "it, and do not edit the seed to match the code."
    )
    assert admit["outcome"] == "admitted"
    assert admit["sqlstate"] == ADMISSION_SQLSTATE
    assert admit["observed"]["merge_record"] is not None, (
        "beat 4 reported ADMITTED with no merge_record row, so nothing was written and "
        "the clearance digest the payload carries came from nowhere"
    )
    assert _HEX64.match(admit["observed"]["merge_record"]["clearance_digest"])


def test_the_verdict_on_the_deployed_seed_is_proven(deployed_seed_run: dict[str, Any]) -> None:
    """The demo's own verdict, on the demo's own database, off the demo's own URL.

    ``failures`` is asserted before ``verdict`` because it carries the sentence; asserting
    the verdict first would report ``'NOT PROVEN' != 'PROVEN'`` and make a reader go
    looking for the reason that was already in the payload.
    """
    assert deployed_seed_run["failures"] == [], deployed_seed_run["failures"]
    assert deployed_seed_run["verdict"] == "PROVEN"
    assert deployed_seed_run["outcome"] == "completed"
    assert deployed_seed_run["persisted"] is False
    assert deployed_seed_run["persistence_check"]["identical"] is True
    assert deployed_seed_run["transaction"]["single_transaction"] is True


def test_the_admission_is_a_green_this_database_could_have_refused(
    demo_dsn: str, seed: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control, run every time, so the green above is never taken on trust.

    A test that has never been seen to fail is a claim, not a measurement. This one plants
    the defect that shipped — ``gate_run`` binding ``sha256(b"cred" + b"signer")`` instead
    of the value ``mainline.signing_credential`` holds — by substituting the resolver, and
    requires the database to come back with ``23503`` on
    ``disposition_signer_credential_id_fkey``. The substitution is on the NAME ``gate_run``
    imported, which is where the value it binds actually comes from; patching
    ``credentials.resolve_credential_id`` would leave ``gate_run``'s own binding untouched
    and the control would pass while proving nothing.

    It also pins the premise the control depends on: the seed does not happen to enrol the
    derived value. If it ever did, the whole class would be invisible again and this test
    says so before it says anything else.

    THE PAYLOAD IS ROLLED BACK EXACTLY AS THE REAL RUN IS — the plant changes 32 bytes that
    a savepoint discards, not the transaction discipline — so this leaves the shared
    database as it found it, which the persistence check below re-measures.
    """
    assert bytes.fromhex(seed["signer_credential_id"]) != _DERIVED_SIGNER_CREDENTIAL, (
        "the deployed seed enrols the value gate_run used to DERIVE, so the divergence "
        "this control exists to exhibit does not exist in this database and every "
        "assertion above is vacuous. Check demo_world.sql's signing_credential rows."
    )

    derived = {
        seed["signer_sub"]: _DERIVED_SIGNER_CREDENTIAL,
        seed["countersigner_sub"]: _DERIVED_COUNTERSIGNER_CREDENTIAL,
    }

    def _derive_instead(conn: psycopg.Connection[Any], signer_sub: str) -> bytes:  # noqa: ARG001
        return derived[signer_sub]

    monkeypatch.setattr(gate_run_mod, "resolve_credential_id", _derive_instead)
    response, body = _invoke_gate_run(demo_dsn, seed)

    assert response["statusCode"] == 200, (
        "the planted defect changed the STATUS. That is a different finding and a better "
        "one than the demo had: on 2026-08-13 it answered 200 and carried the failure in "
        "its own verdict, which is why nobody noticed."
    )
    payload = body["data"]
    admit = payload["beats"][3]
    assert admit["outcome"] == "refused"
    assert admit["sqlstate"] == "23503", admit
    assert admit["constraint"] == _CREDENTIAL_FKEY, admit
    assert admit["constraint_source"] == "reported"
    assert payload["verdict"] == "NOT PROVEN"
    assert any("beat 4 (admit)" in failure for failure in payload["failures"]), payload["failures"]
    assert payload["persistence_check"]["identical"] is True, (
        "the refused beat left rows behind, so this control has damaged the database the "
        "other tests in this section share"
    )


def test_the_signer_subjects_beat_four_falls_back_to_are_the_ones_the_seed_enrols(
    seed: dict[str, str],
) -> None:
    """The environment gap, pinned rather than papered over.

    ``infra/modules/demo-api`` at ``HEAD`` publishes ``MAINLINE_DEMO_PERMIT_ID`` and does
    NOT publish ``MAINLINE_DEMO_SIGNER_SUB`` or ``MAINLINE_DEMO_COUNTERSIGNER_SUB``, so on
    the deployed Lambda those two names come from ``scenario.py``'s committed defaults —
    and they are load-bearing, because ``credentials.resolve_credential_id`` looks the
    credential up BY SUBJECT. The demo works today only because the defaults and the seed
    happen to agree.

    "Happen to agree" is not a property. It is asserted here, against the subjects read out
    of the seeded database, so that changing either side is a red test naming both. That is
    a report of the gap, not a repair of it: the repair is publishing the two variables, it
    belongs to the deployment domain, and it is recorded as a cross-domain note.
    """
    fallback = scenario_mod.from_env({})
    assert fallback.signer_sub == seed["signer_sub"], (
        f"scenario.py falls back to signer_sub {fallback.signer_sub!r} while the deployed "
        f"seed enrols {seed['signer_sub']!r}. Terraform publishes no "
        f"{scenario_mod.ENV_PREFIX}SIGNER_SUB, so the deployed Lambda would resolve no "
        "credential and beat 4 would 422 rather than admit."
    )
    assert fallback.countersigner_sub == seed["countersigner_sub"], (
        f"scenario.py falls back to countersigner_sub {fallback.countersigner_sub!r} while "
        f"the deployed seed enrols {seed['countersigner_sub']!r}, and Terraform publishes "
        f"no {scenario_mod.ENV_PREFIX}COUNTERSIGNER_SUB."
    )


def test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds(
    demo_dsn: str, seed: dict[str, str], w4_database: str
) -> None:
    """Why twenty green tests could not see Blocker 1 — measured, not asserted in prose.

    ``scripts/proof/gate_refusal.py:844`` enrols ``_sha("cred", "signer")``: the SAME
    expression ``gate_run`` used to bind. Test and code read one constant, so they agreed,
    and neither had met ``demo_world.sql``. This test reads both databases and requires them
    to disagree — which is what makes the section above additional coverage rather than the
    same coverage twice.

    ``tuple_row`` on both connections: two probes read by position, asserting nothing about
    ``db.py``.
    """
    assert demo_dsn != w4_database, "the two worlds collapsed into one database"

    with psycopg.connect(demo_dsn, autocommit=True, row_factory=tuple_row) as deployed:
        deployed_row = deployed.execute(
            "SELECT count(*) FROM mainline.signing_credential WHERE credential_id = %s",
            (_DERIVED_SIGNER_CREDENTIAL,),
        ).fetchone()
    with psycopg.connect(w4_database, autocommit=True, row_factory=tuple_row) as proof:
        proof_row = proof.execute(
            "SELECT count(*) FROM mainline.signing_credential WHERE credential_id = %s",
            (_DERIVED_SIGNER_CREDENTIAL,),
        ).fetchone()

    assert deployed_row is not None and deployed_row[0] == 0, (
        "the DEPLOYED seed enrols the derived credential id, which would make the "
        "divergence invisible again"
    )
    assert proof_row is not None and proof_row[0] == 1, (
        "scripts/proof/gate_refusal.py no longer enrols _sha('cred','signer'), so the "
        "explanation this file gives for twenty green tests missing a 23503 is out of "
        "date — re-measure it before editing this assertion away"
    )
    assert seed["signer_sub"] != "proof.signer", "the two worlds share a signer"
