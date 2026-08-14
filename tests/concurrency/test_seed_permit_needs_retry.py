# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The negative control: `_seed_permit`'s shape raises a REAL 40001, and the adapter survives it.

**Why this file exists.** A retry loop added to code that has never been shown to need one
is an untested guard dressed as a fix. ``_seed_permit`` —
`verticals/mainline/apps/demo-api/tests/test_transitions.py:224` — commits its whole
statement list as one transaction with no retry of any kind, and the wave's brief called
that a Cloud-only hazard: *"CockroachDB Cloud … returns 40001 RETRY_SERIALIZABLE under
contention that single-node Docker never produces."* **That sentence is false, and this
file is the measurement that says so.** Two callers of that shape, run at once over the
SAME subject against the local single-node CockroachDB v26.2.5, produce ``40001`` on this
workstation in every race measured — 6 of 6, one loser per race.

The exhibit is quoted rather than paraphrased, because ``40001`` arrives in more than one
costume and only the SQLSTATE is the contract. This plant produces
``restart transaction: TransactionRetryWithProtoRefreshError: WriteTooOldError: write for
key … too old``; the rejected variant below produced
``TransactionRetryError: retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)``.
Both are ``40001``, both are retryable, and a client that discriminated on the message
instead of the code would have got one of them wrong.

**Two assertions, two tests, failing independently.**

1. :func:`test_the_unguarded_seed_permit_shape_raises_a_real_40001` — the UNGUARDED shape
   raises ``40001``, and the loser's whole history is missing afterwards. If it ever stops
   raising, this control has stopped controlling for anything, and the honest response is a
   plant that contends, **never** a relaxed assertion. That is the trap
   ``cluster-lane-bites`` exists to catch elsewhere in this repository: a negative control
   that cannot fail proves nothing.
2. :func:`test_the_same_shape_under_the_adapter_completes` — the SAME work, wrapped in
   :func:`trappoint_testkit.txn.run_txn`, commits, the spy shows a ``40001`` was actually
   retried, and both callers' rows are present. A guarded run in which nothing ever
   conflicted would be a green with no content, so that is asserted too rather than hoped
   for.

**The shape is transcribed, not imported.** ``_seed_permit`` is a private helper in a test
module of another distribution, under another licence, which imports the demo API package
and takes fixtures this lane does not have. What is reproduced here is its STATEMENT SHAPE:
read the demo subject, then write ``recall_run``, ``silence_receipt``, ``blocking_check``,
``exposure_receipt``, ``exposure_line``, a ``permit_event`` at the sequence just read, and
the ``UPDATE mainline.permit`` that moves the head — and commit once. **If ``_seed_permit``
changes, this transcription is stale and must be re-read; it is a copy, and a copy can rot.**

**WHERE THE TWO CALLERS MEET, AND WHY IT IS THIS AND NOT THE OTHER THING.** The subject's
``permit`` row is created once, before the race, by the three statements ``_seed_permit``
opens with. It is not raced, because racing it would be two INSERTs of one ``permit_id``,
which is ``23505`` — a *refusal*, which the retry loop must attempt exactly once and must
NOT retry. What the two callers race is the rest of the shape over one subject: both read
that subject's state and head sequence, both write children of it, and both move its head.
That is a read-modify-write on one row from two SERIALIZABLE transactions, so the loser is
``40001`` by construction rather than by luck — and it is the contention the demo actually
has, two judges reaching ``POST /v1/demo/gate-run`` at the same moment.

**A weaker plant was measured and rejected, and it is worth knowing why.** Two callers each
running the WHOLE shape for a *different* new permit — sharing only the read of the demo
subject — produced ``40001`` in 6 of 6 races against a database holding ~70 permits and in
**0 of 6** against a freshly built one, with identical query plans in both. The mechanism
was not isolated. A plant whose firing depends on how used the database is would make this
control's silence uninformative, so it is not the plant here; it is recorded in
``docs/diagnosis/retry-negative-control.md`` because it also says something uncomfortable
about how invisible this defect is in a fresh CI database.

**What this measurement is NOT.** It is single-node. CockroachDB Cloud is multi-node and
adds *rate and variety* — clock-uncertainty restarts, cross-node latency,
``RETRY_WRITE_TOO_OLD`` — not *existence*. Nothing here is evidence about Cloud, and the
diagnosis document says so in those words. This lane may not be cited for a Cloud claim.

**Cost and cleanliness.** The module builds its own database from the repository's own
migration chain (271 files, ~80 s) and the repository's own seeder, inside the
module-scoped database ``trappoint-testkit`` creates and DROPS. Nothing is written into a
database another suite adopts, and nothing survives the run.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
import pytest
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

# Module level, not conftest level: `tests/concurrency/` also holds the custody and recall
# lanes, and a skip raised while a conftest is imported takes the whole directory with it.
pytest.importorskip(
    "trappoint_core",
    reason=(
        "the guarded half runs the repository's ONE retry loop, `trappoint_core.retry`; "
        "`uv sync --package trappoint-core` installs it. A SKIP IS NOT EVIDENCE."
    ),
)

from trappoint_testkit.txn import ISOLATION_SQL, from_dsn, run_txn

from trappoint_core.retry import RecordingObserver

pytestmark = [pytest.mark.requires_cluster, pytest.mark.slow]

#: Two callers, six races. Two is the demo's real case — two judges at one subject — and
#: six is enough that one flake cannot be the verdict while staying inside a minute.
RACES = 6
CALLERS = 2

#: Wall-clock ceiling on the rendezvous. Generous because the first race pays for a cold
#: range cache; short enough that a genuinely wedged partner ends the run rather than
#: pytest's timeout.
RENDEZVOUS_TIMEOUT_S = 60.0

#: The one code that means "the database did not decide; ask again".
RETRYABLE = "40001"

#: Every SQLSTATE this race may legitimately produce. ``00000`` is a commit; the rest are
#: the modelled refusals of ``spec/errors.md`` §2. **A census entry outside this set is the
#: finding** — a mechanism refusing this shape for a reason nobody modelled — which is why
#: it is asserted rather than logged.
TAXONOMY = frozenset({"00000", "40001", "23514", "23503", "23505", "P0001"})

#: Read at the top of every attempt, exactly as ``_seed_permit`` reads it: the site the demo
#: history was seeded into and everything a second permit reuses.
SITE_SQL = """
SELECT s.site_id, s.site_role::STRING, pc.clause_uuid, pc.commit_id, bc.precursor_event_id,
       (SELECT policy_version FROM mainline_meas.recall_policy ORDER BY policy_version LIMIT 1)
  FROM mainline.permit p
  JOIN mainline.site s ON s.site_id = p.site_id
  JOIN mainline.permit_clause pc ON pc.permit_id = p.permit_id
  JOIN mainline.blocking_check bc ON bc.permit_id = p.permit_id
 WHERE p.permit_id = %s
 LIMIT 1
"""

#: The subject row both callers read and both then move. Reading it and writing it in one
#: transaction is what ``_seed_permit``'s tail does; two of those at once is the conflict.
SUBJECT_SQL = "SELECT state::STRING, head_seq FROM mainline.permit WHERE permit_id = %s"

#: The edge each caller claims, from the state it READ. ``_seed_permit`` walks both;
#: two callers arriving at one draft permit walk one each, and the loser only learns which
#: one is left to it by reading again — which is precisely what a retry does and a replay
#: does not.
NEXT_STATE = {"draft": "checks_materialised", "checks_materialised": "dispositioned"}

#: One origin per caller, and the reason is a constraint rather than a preference.
#: ``0058_blocking_check.sql`` gives ``blocking_check`` a SERVER-computed
#: ``dedupe_key = digest(permit_id | cr_id | clause_uuid | commit_id | precursor_event_id |
#: origin)`` under ``UNIQUE (dedupe_key)``, so two callers materialising the same finding
#: against one subject are ONE obligation and the second is refused ``23505`` — measured,
#: on the first guarded run of this control. That refusal is CORRECT: the database is
#: saying the two callers described the same fact, and a retry must attempt it exactly once
#: and never again. What two concurrent recall runs actually produce is two DIFFERENT
#: findings, so each caller carries its own origin and the obligations are distinct by
#: content rather than by a collision the loop was asked to paper over. A caller added here
#: needs an origin added here; ``0058``'s ``bc_origin_known`` lists the eight legal values.
ORIGINS = ("blame_ancestry", "weaken_over_blood")
assert len(ORIGINS) >= CALLERS, "every caller needs an origin of its own; see ORIGINS"


def _sha(*parts: bytes | str) -> bytes:
    """The digest ``_seed_permit`` uses for its payload columns."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8") if isinstance(part, str) else part)
    return digest.digest()


def _repo_root() -> Path:
    """The workspace root, found by what is in it rather than by counting directories."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    raise RuntimeError("no workspace root above this test file")


def _gate_refusal_module() -> ModuleType:
    """Import ``scripts/proof/gate_refusal.py`` by path — the repository's OWN applier and seeder.

    By path and not by copy. The migration chain and the demo history are this repository's
    to define; a private re-implementation here would be a second seed to keep true, and
    this wave's governing rule is that a seed and a test may never be quietly moved towards
    each other.
    """
    path = _repo_root() / "scripts" / "proof" / "gate_refusal.py"
    spec = importlib.util.spec_from_file_location("w4_control_gate_refusal", path)
    if spec is None or spec.loader is None:  # pragma: no cover - a broken checkout
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class _World:
    """The database this module built, and the demo history every caller reads."""

    dsn: str
    demo_permit_id: uuid.UUID
    signer: str


@dataclass(frozen=True)
class _Outcome:
    """What one caller's whole transaction did. ``00000`` is a commit."""

    sqlstate: str
    message: str
    committed: bool
    retries: int = 0


@dataclass(frozen=True)
class _Race:
    """One subject and what the callers who raced over it got."""

    subject: uuid.UUID
    outcomes: list[_Outcome]
    rendezvous_broken: bool


class _Rendezvous:
    """Both callers finish READING before either starts WRITING. Once, on the first attempt.

    An honest interleaving device, not a thumb on the scale: two clients that arrive at the
    same moment read at the same moment, and forcing that makes the race *repeatable*
    rather than a coin toss about thread scheduling. It fires exactly once — a retry must
    not wait on a partner that has already finished, and a :class:`threading.Barrier`
    reused after both parties passed it would deadlock the guarded half.
    """

    def __init__(self, parties: int, timeout_s: float) -> None:
        """Build a rendezvous for *parties* callers with a wall-clock ceiling."""
        self._barrier = threading.Barrier(parties)
        self._timeout_s = timeout_s
        self._passed = False
        self.broken = False

    def wait(self) -> None:
        """Block until every party has read, or record that one never arrived."""
        if self._passed:
            return
        try:
            self._barrier.wait(timeout=self._timeout_s)
        except threading.BrokenBarrierError:
            # A partner failed before it reached the rendezvous. The survivor's outcome is
            # still real, so it is recorded rather than raised — but the fact travels out
            # to the test, which prints it, because a race that half-happened must not be
            # reported as a race that happened.
            self.broken = True
        self._passed = True


def _new_subject(world: _World) -> uuid.UUID:
    """One permit in ``draft``, by the three statements ``_seed_permit`` opens with.

    Committed on its own, before the race, and **not** through the adapter: a control whose
    setup depended on the thing under test would be arguing in a circle. A permit exists
    once — two INSERTs of one ``permit_id`` is ``23505``, a refusal rather than a conflict —
    so this is where the shape is split, and the split is stated in the module docstring.
    """
    conn = psycopg.connect(world.dsn, autocommit=False, row_factory=tuple_row)
    try:
        conn.execute(ISOLATION_SQL)
        row = conn.execute(SITE_SQL, (world.demo_permit_id,)).fetchone()
        assert row is not None, "the demo history is not seeded in this database"
        site_id, site_role, clause_uuid, commit_id, _event_id, _policy = row
        permit_id = uuid.uuid4()
        tag = permit_id.hex[:12]
        conn.execute(
            "INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, "
            "ref_name, horizon_at) VALUES (%s, %s, %s, %s, %s, now() + INTERVAL '30 days')",
            (permit_id, site_id, site_role, f"PTW-W4C-{tag}", f"refs/permits/w4c-{tag}"),
        )
        conn.execute(
            "INSERT INTO mainline.permit_clause (permit_id, clause_uuid, commit_id, relation) "
            "VALUES (%s, %s, %s, 'relies_on')",
            (permit_id, clause_uuid, commit_id),
        )
        conn.execute(
            "INSERT INTO mainline.boundary_certificate (permit_id, cert_gen, "
            "asset_graph_version, tags_declared, tags_resolved, tags_unmodelled, "
            "under_declared) VALUES (%s, 1, 'w4c-asset-graph-1', 1, 1, 0, 0)",
            (permit_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return permit_id


def _seed_permit_shape(
    conn: Any, world: _World, subject: uuid.UUID, rendezvous: _Rendezvous, ordinal: int
) -> uuid.UUID:
    """``_seed_permit``'s statements over *subject*, minus the commit. Returns the receipt id.

    A recall run with its Proof of Exhausted Recall, one blocking check standing for the
    recalled precursor, an exposure receipt that showed it with the line that binds it to
    that obligation, and the event by which the client CLAIMS the obligation is disposed
    of, with the head moved to match.

    **It does not commit and it does not roll back.** The caller owns the transaction: the
    unguarded half commits by hand, the guarded half hands this whole callable to
    :func:`~trappoint_testkit.txn.run_txn`, and the ONLY difference between the two is the
    retry. A commit in here would make them differ in two ways and the control would then
    measure neither.

    Every identifier is minted INSIDE the callable, which is not incidental: a retry runs
    this again from the top, so a value hoisted out of it would be replayed and the second
    attempt would meet its own first attempt's key. *ordinal* is the exception and must
    stay stable across attempts — it selects this caller's :data:`ORIGINS` entry, which is
    a fact about WHICH recall run this is, not a fresh identifier.
    """
    row = conn.execute(SITE_SQL, (world.demo_permit_id,)).fetchone()
    assert row is not None, "the demo history is not seeded in this database"
    site_id, _site_role, clause_uuid, commit_id, event_id, policy_version = row
    subject_row = conn.execute(SUBJECT_SQL, (subject,)).fetchone()
    assert subject_row is not None, f"subject {subject} is not in this database"
    state, head_seq = str(subject_row[0]), int(subject_row[1])

    rendezvous.wait()

    check_id, run_id, silence_id, receipt_id = (uuid.uuid4() for _ in range(4))
    tag = check_id.hex[:12]

    conn.execute(
        "INSERT INTO mainline_meas.recall_run (run_id, permit_id, site_id, corpus_commit, "
        "policy_version, index_plan_digest, index_generation, n_candidates, n_blocking, "
        "n_advisory, n_silenced, n_deduped) VALUES (%s, %s, %s, %s, %s, %s, 'g1', 1, 1, 0, 0, 0)",
        (run_id, subject, site_id, commit_id, policy_version, _sha("plan", tag)),
    )
    conn.execute(
        "INSERT INTO mainline_meas.silence_receipt (silence_receipt_id, run_id, permit_id, "
        "corpus_root, candidate_root, theta, s, n, boundary_proof, policy_version) "
        "VALUES (%s, %s, %s, %s, %s, 0.35, 1, 1, %s, %s)",
        (
            silence_id,
            run_id,
            subject,
            _sha("corpus-root"),
            _sha("candidate-root", tag),
            Jsonb({"leaf_s": [], "leaf_s_plus_1": []}),
            policy_version,
        ),
    )
    conn.execute(
        "INSERT INTO mainline.blocking_check (check_id, subject_kind, permit_id, site_id, "
        "clause_uuid, commit_id, precursor_event_id, origin, severity, virulence, closure_gen, "
        "recall_run_id, evidence_summary) "
        "VALUES (%s, 'permit', %s, %s, %s, %s, %s, %s, 0, 'routine', 0, %s, %s)",
        (
            check_id,
            subject,
            site_id,
            clause_uuid,
            commit_id,
            event_id,
            ORIGINS[ordinal],
            run_id,
            "A recalled precursor reaches the clause this permit relies on.",
        ),
    )
    conn.execute(
        "INSERT INTO mainline.exposure_receipt (receipt_id, subject_kind, permit_id, actor_sub, "
        "issued_at, issued_hlc, expires_at, corpus_root, silence_receipt_id, policy_version, "
        "total_tokens, receipt_digest) "
        "VALUES (%s, 'permit', %s, %s, now() - INTERVAL '10 minutes', cluster_logical_timestamp(), "
        "now() + INTERVAL '2 hours', %s, %s, %s, 200, %s)",
        (
            receipt_id,
            subject,
            world.signer,
            _sha("corpus-root"),
            silence_id,
            policy_version,
            _sha("receipt", tag),
        ),
    )
    conn.execute(
        "INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, tokens) "
        "VALUES (%s, %s, %s, 200)",
        (receipt_id, check_id, _sha("line", tag)),
    )
    seq = head_seq + 1
    to_state = NEXT_STATE[state]
    conn.execute(
        "INSERT INTO mainline.permit_event (permit_id, seq, prev_seq, from_state, to_state, "
        "subject_kind, actor_sub, payload, prev_digest) "
        "VALUES (%s, %s, %s, %s, %s, 'permit', %s, %s, "
        "coalesce((SELECT e.chain_digest FROM mainline.permit_event e "
        "           WHERE e.permit_id = %s AND e.seq = %s), decode(repeat('00', 32), 'hex')))",
        (
            subject,
            seq,
            seq - 1,
            state,
            to_state,
            world.signer,
            Jsonb({"w4c": to_state}),
            subject,
            seq - 1,
        ),
    )
    conn.execute(
        "UPDATE mainline.permit SET state = %s, head_seq = %s WHERE permit_id = %s",
        (to_state, seq, subject),
    )
    return receipt_id


def _unguarded(
    world: _World, subject: uuid.UUID, rendezvous: _Rendezvous, ordinal: int
) -> _Outcome:
    """One caller, no retry of any kind. This is ``_seed_permit`` as it stands today.

    ``tuple_row`` is spelled out because :data:`SITE_SQL`'s row is read by position — the
    same care ``test_gate_run.py`` takes wherever it reads rows itself.
    """
    conn = psycopg.connect(world.dsn, autocommit=False, row_factory=tuple_row)
    try:
        conn.execute(ISOLATION_SQL)
        _seed_permit_shape(conn, world, subject, rendezvous, ordinal)
        conn.commit()
    except psycopg.Error as exc:
        with suppress(psycopg.Error):
            conn.rollback()
        return _Outcome(sqlstate=exc.sqlstate or "", message=str(exc), committed=False)
    else:
        return _Outcome(sqlstate="00000", message="", committed=True)
    finally:
        conn.close()


def _guarded(world: _World, subject: uuid.UUID, rendezvous: _Rendezvous, ordinal: int) -> _Outcome:
    """The same caller through the adapter. The ONLY difference is the retry."""
    spy = RecordingObserver()
    run_txn(
        from_dsn(world.dsn, row_factory=tuple_row),
        lambda conn: _seed_permit_shape(conn, world, subject, rendezvous, ordinal),
        subject_kind="permit",
        subject_id=str(subject),
        observer=spy,
    )
    return _Outcome(
        sqlstate="00000",
        message="",
        committed=True,
        retries=spy.attempts_for(RETRYABLE),
    )


def _race(world: _World, runner: Any) -> _Race:
    """Fire :data:`CALLERS` copies of *runner* at one fresh subject and collect what each got."""
    subject = _new_subject(world)
    rendezvous = _Rendezvous(CALLERS, RENDEZVOUS_TIMEOUT_S)
    with ThreadPoolExecutor(max_workers=CALLERS) as pool:
        futures = [
            pool.submit(runner, world, subject, rendezvous, ordinal) for ordinal in range(CALLERS)
        ]
        outcomes = [future.result() for future in futures]
    return _Race(subject=subject, outcomes=outcomes, rendezvous_broken=rendezvous.broken)


def _count(dsn: str, sql: str, params: tuple[Any, ...]) -> int:
    """One scalar count, on a connection off every production path. ``tuple_row``, by position."""
    with psycopg.connect(dsn, autocommit=True, row_factory=tuple_row) as probe:
        row = probe.execute(sql, params).fetchone()
    assert row is not None
    return int(row[0])


@pytest.fixture(scope="module")
def world(crdb_dsn: str) -> _World:
    """A database of this module's own, carrying the whole vertical and one demo history.

    ``crdb_dsn`` is ``trappoint-testkit``'s module-scoped fixture: it creates the database
    on the session's ONE cluster and DROPS it afterwards, so this control leaves nothing
    behind and cannot write into a database another suite adopts. It also skips — with the
    session's own reason — when there is no cluster, rather than falling back to a
    hard-coded DSN and connecting to whatever happens to be listening.
    """
    proof = _gate_refusal_module()
    migrations = _repo_root() / "verticals" / "mainline" / "db" / "migrations"
    with psycopg.connect(crdb_dsn, autocommit=True, row_factory=tuple_row) as work:
        report = proof.apply_chain(work, crdb_dsn, migrations, _repo_root())
    if report.failures:
        pytest.fail(
            f"{len(report.failures)} of {report.files} migrations did not apply, so the "
            "shape under test could not be built. First failure: "
            f"{report.failures[0].version} [{report.failures[0].sqlstate}] "
            f"{report.failures[0].message[:200]}"
        )
    with psycopg.connect(crdb_dsn, autocommit=False, row_factory=tuple_row) as conn:
        conn.execute(ISOLATION_SQL)
        history = proof.seed_history(conn)
        conn.commit()
    print(
        f"\n[control] {report.files} migrations applied in {report.seconds:.1f}s; "
        f"demo permit {history.permit_id}"
    )
    return _World(dsn=crdb_dsn, demo_permit_id=history.permit_id, signer=history.signer_sub)


@pytest.mark.timeout(900)
def test_the_unguarded_seed_permit_shape_raises_a_real_40001(world: _World) -> None:
    """The plant must fire: two unguarded callers, one subject, a real ``40001``.

    **If this ever goes green with no ``40001`` in the census, the answer is a plant that
    contends — never a relaxed assertion.** A control that cannot fail is not evidence that
    the code is safe; it is the absence of evidence about anything, and this repository has
    already published one "unstable" list corrupted by exactly that mistake.

    The loser's rows are then counted, because *what the defect costs* is the point: the
    unguarded caller does not merely see an exception, it loses the entire history it was
    writing — a recall run, an exposure receipt, the line that displayed the obligation and
    the event that claimed it disposed of.
    """
    census: Counter[str] = Counter()
    exhibits: list[str] = []
    for race in (_race(world, _unguarded) for _ in range(RACES)):
        if race.rendezvous_broken:
            print(f"[control] race {race.subject}: a caller never reached the rendezvous")
        winners = 0
        for outcome in race.outcomes:
            census[outcome.sqlstate] += 1
            winners += int(outcome.committed)
            if outcome.sqlstate == RETRYABLE:
                exhibits.append(outcome.message.splitlines()[0])
        events = _count(
            world.dsn,
            "SELECT count(*) FROM mainline.permit_event WHERE permit_id = %s",
            (race.subject,),
        )
        assert events == winners, (
            f"subject {race.subject} carries {events} events for {winners} committed "
            "caller(s): a caller that raised nevertheless left rows behind, or one that "
            "returned wrote none"
        )

    print(f"[control] unguarded census over {RACES} races: {dict(census)}")
    for exhibit in exhibits[:1]:
        print(f"[control] {exhibit}")

    unmodelled = set(census) - TAXONOMY
    assert not unmodelled, (
        f"the unguarded shape produced {sorted(unmodelled)}, which nothing in "
        "spec/errors.md §2 models. That is the finding: a mechanism is refusing this shape "
        "for a reason this lane never described."
    )
    assert census[RETRYABLE] >= 1, (
        f"{RACES} races of the UNGUARDED _seed_permit shape over one subject produced no "
        f"40001 at all (census {dict(census)}). This control is therefore not controlling "
        "for anything: it cannot distinguish 'the retry is unnecessary' from 'the race "
        "never happened'. Find a plant that contends — do NOT weaken this assertion, and "
        "do NOT conclude that 40001 is unreachable without CockroachDB Cloud, which is "
        "measurably false on this workstation (docs/diagnosis/retry-negative-control.md)."
    )
    assert census["00000"] >= 1, (
        "every caller failed, so the race shows contention but not liveness: with no "
        "winner there was nothing for the loser to have been serialised behind"
    )


@pytest.mark.timeout(900)
def test_the_same_shape_under_the_adapter_completes(world: _World) -> None:
    """The identical work through :func:`trappoint_testkit.txn.run_txn` commits, every time.

    Three claims, and the last two are what stop this being a green with no content:

    * no caller raised — the loser retried the WHOLE transaction on a FRESH connection and
      committed;
    * a ``40001`` was actually met and retried, so the guard was exercised rather than
      merely present; and
    * **both** callers' rows are in the database. ``did not raise`` and ``wrote the whole
      history`` are different sentences: a retry that replayed statements into a poisoned
      transaction — the mistake ``spec/errors.md`` §2.1 names — could end without an
      exception and leave the subject with one caller's event instead of two.

    That last one is also what proves the retry RE-READ. The loser's second attempt writes
    ``seq`` 2 from ``checks_materialised``, because it read the head the winner moved; a
    replay would have written ``seq`` 1 again and met the event chain's unique index.
    """
    retries = 0
    subjects: list[uuid.UUID] = []
    for race in (_race(world, _guarded) for _ in range(RACES)):
        subjects.append(race.subject)
        assert all(outcome.committed for outcome in race.outcomes), (
            f"a guarded caller did not commit against subject {race.subject}"
        )
        retries += sum(outcome.retries for outcome in race.outcomes)

    print(f"[control] guarded: {len(subjects) * CALLERS} commits, {retries} retried 40001(s)")

    assert retries >= 1, (
        f"{RACES} guarded races completed without a single 40001 being retried. The adapter "
        "was never exercised, so this run is not evidence that it survives a conflict — and "
        "the unguarded control above is what says a conflict is available here."
    )
    events = _count(
        world.dsn,
        "SELECT count(*) FROM mainline.permit_event WHERE permit_id = ANY(%s)",
        (subjects,),
    )
    assert events == RACES * CALLERS, (
        f"{events} permit_event rows for {RACES} subjects raced by {CALLERS} callers each; "
        "every caller writes one, so a retry committed a PART of its transaction rather "
        "than the whole of it"
    )
    lines = _count(
        world.dsn,
        "SELECT count(*) FROM mainline.exposure_line l "
        "JOIN mainline.exposure_receipt r ON r.receipt_id = l.receipt_id "
        "WHERE r.permit_id = ANY(%s)",
        (subjects,),
    )
    assert lines == RACES * CALLERS, (
        f"{lines} exposure lines for {RACES * CALLERS} callers: the exposure that displayed "
        "the obligation did not survive the retry"
    )
