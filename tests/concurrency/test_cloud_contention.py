# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The contention probe's own conformance, and the committed census checked against itself.

``scripts/deploy/cloud_contention.py`` drives a constructed read-write cycle against
CockroachDB Cloud and against the local single node in one sitting, and writes
``evidence/deploy/cloud-contention.json``. This file is what stops that artefact from being a
number nobody can check.

**THIS FILE SKIPS NOTHING FOR "NO CLUSTER" AND NOTHING FOR "NO CREDENTIAL."** Both reasons are
false on the workstation this was written on — ``docs/leads/cloud-hardening-final.md`` ruling
**R1** measured the Cloud credential present in the repo-root ``.env``, and the local node has
answered every probe in this lane's history. A skip carrying either reason would be read as a
defect in the test rather than a fact about the environment, and it is stated here so that
nobody adds one later believing it to be polite. **Two** tests in this module want a database —
the live race and its negative control — and both carry ``requires_cluster``. Their one shared
skip reason names the four environment variables and the port that were tried, so that the
reason is actionable rather than a shrug.

WHAT IS ACTUALLY BEING GUARDED, in the order it matters
========================================================

**1. The probe once scored its own headline finding as zero, and this file is why it cannot
again.** Under SERIALIZABLE, CockroachDB usually detects an unorderable cycle at **COMMIT**,
not at a statement. The first version of the probe built its per-attempt record inside the
callable, wrapping the SELECT and the UPDATE — so ``work`` returned cleanly, ``run_txn``
committed, the commit raised ``40001``, ``run_gate`` retried it, and the census printed
``rounds_with_40001: 0`` for a round the spy had recorded a retry in. Two observers disagreed
and the derived one was wrong. :func:`test_the_census_counts_a_40001_that_surfaced_at_commit`
is that failure frozen: it feeds the census an arm in exactly that shape and requires the count
to be one. Run against the original recorder it reads zero.

**2. Every refusal in the probe is demonstrated FIRING.** A verifier that has never failed has
never discriminated. :func:`test_every_unmet_condition_fires_when_its_fault_is_injected` walks
all four branches of :func:`~scripts.deploy.cloud_contention.unmet_conditions` with the fault
each one exists to catch.

**3. The committed census is recomputed from its own rounds.** The summary counts in
``cloud-contention.json`` are re-derived here from the per-round records underneath them and
required to agree. An artefact whose summary was edited by hand — or written by a program whose
tally drifted from its data — fails, and it fails naming the field.

**4. The live race has a control that turns it OFF.** An instrument that reports ``40001`` no
matter what it is pointed at reports nothing.
:func:`test_the_same_harness_produces_no_40001_when_the_two_callers_share_nothing` runs the
identical harness over disjoint keys and requires **zero**. Two weaker controls were tried
first and both still produced 6 of 6 — they are named in that test's docstring so nobody
re-derives them believing they discriminate.

**5. No credential is in the artefact.** Asserted by pattern rather than trusted to discipline.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest

from scripts.deploy.cloud_contention import (
    FINGERPRINT_TABLES,
    RETRYABLE,
    _WatchedConnection,
    census_constructed,
    restart_reason,
    structural_differences,
    unmet_conditions,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "evidence" / "deploy" / "cloud-contention.json"
SEED_EVIDENCE = REPO_ROOT / "evidence" / "deploy" / "cloud-seed.json"
DOCUMENT = REPO_ROOT / "docs" / "deploy" / "CLOUD-40001.md"

#: The census is only a census at this size. `docs/leads/cloud-hardening-final.md` W1 fixes the
#: floor at twelve constructed races per arm. IT IS A FLOOR: this number goes up when somebody
#: measures more, and never down to make a short run pass.
MINIMUM_ROUNDS = 12

#: Both platforms, in one sitting. A file carrying only one of them is not a comparison.
REQUIRED_TARGETS = ("cloud", "local")


# ═══════════════════════════════════════════════════════════════════════════════════════
# the classifier — three reasons, one code
# ═══════════════════════════════════════════════════════════════════════════════════════

#: Real server text, from this repository's own captures.
#: ``docs/diagnosis/retry-negative-control.md`` §4.1 quotes the first two verbatim from the
#: local node. The third is CockroachDB's documented wording for a restart that **cannot occur
#: on one node** — there is no second clock to disagree with — and it is here as an INPUT TO A
#: CLASSIFIER AND NOTHING ELSE. It is not an observation, it is not in the evidence artefact,
#: and it must never be quoted as though this repository had seen one.
_SERIALIZABLE_MESSAGE = (
    "restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: "
    'retry txn (RETRY_SERIALIZABLE - failed preemptive refresh): "sql txn" meta={id=7bcba616 '
    "iso=Serializable pri=0.00866982 epo=0} lock=true stat=PENDING"
)
_WRITE_TOO_OLD_MESSAGE = (
    "restart transaction: TransactionRetryWithProtoRefreshError: WriteTooOldError: write for "
    "key /Table/31248/1/x/0 at timestamp 1786665610.710035062,0 too old; must write at or "
    "above 1786665610.711517187,1"
)
_UNCERTAINTY_MESSAGE = (
    "restart transaction: TransactionRetryWithProtoRefreshError: "
    "ReadWithinUncertaintyIntervalError: read at time 1786665610.700000000,0 encountered "
    "previous write with future timestamp 1786665610.900000000,0 within uncertainty interval"
)

_OBSERVED_LOCALLY = "observed: docs/diagnosis/retry-negative-control.md 4.1, local node"
_NEVER_OBSERVED = (
    "NOT OBSERVED ANYWHERE IN THIS REPOSITORY. Documented wording, used here only to prove the "
    "classifier would name it if a multi-node cluster ever produced one."
)

MESSAGES: tuple[tuple[str, str, str], ...] = (
    ("RETRY_SERIALIZABLE", _SERIALIZABLE_MESSAGE, _OBSERVED_LOCALLY),
    ("WriteTooOldError", _WRITE_TOO_OLD_MESSAGE, _OBSERVED_LOCALLY),
    ("ReadWithinUncertaintyInterval", _UNCERTAINTY_MESSAGE, _NEVER_OBSERVED),
)


@pytest.mark.parametrize(
    ("expected", "message", "provenance"), MESSAGES, ids=[m[0] for m in MESSAGES]
)
def test_restart_reason_names_each_costume_of_one_sqlstate(
    expected: str, message: str, provenance: str
) -> None:
    """All three carry SQLSTATE ``40001``; the classifier must tell them apart by name.

    This is the property the whole evidence artefact rests on. A client that discriminated on
    the *message* would get one of the three wrong, which is why ``trappoint_core.retry``
    discriminates on the **code** — and why the reason is recorded as evidence beside the
    server's verbatim line rather than used as a control-flow input anywhere.
    """
    assert restart_reason(message) == expected, (
        f"the classifier read {restart_reason(message)!r} out of a message whose provenance is "
        f"{provenance!r}"
    )


def test_a_message_naming_no_reason_is_reported_as_unnamed_rather_than_guessed() -> None:
    """An unrecognised ``40001`` is ``"unnamed"``. Silence is a finding; a guess is not."""
    assert restart_reason("restart transaction: something nobody has modelled") == "unnamed"


def test_the_longest_token_wins_so_a_generic_word_cannot_shadow_a_specific_one() -> None:
    """``RETRY_WRITE_TOO_OLD`` outranks the bare ``WriteTooOldError`` in one message."""
    both = "TransactionRetryError: retry txn (RETRY_WRITE_TOO_OLD) WriteTooOldError: write for key"
    assert restart_reason(both) == "RETRY_WRITE_TOO_OLD"


# ═══════════════════════════════════════════════════════════════════════════════════════
# the watched connection — the defect this file exists to have caught
# ═══════════════════════════════════════════════════════════════════════════════════════


class _Refusal(psycopg.Error):
    """A driver-shaped exception carrying a chosen SQLSTATE.

    A real :class:`psycopg.Error` subclass rather than a duck type, for the reason
    ``test_retry_taxonomy_spy.py`` gives: the code under test catches ``psycopg.Error`` and
    never ``Exception``, and a stand-in with the right attributes would slip past that
    deliberate narrowness. ``_sqlstate`` is assigned before ``super().__init__`` because
    psycopg's constructor reads ``self.sqlstate`` while it runs.
    """

    def __init__(self, sqlstate: str, message: str) -> None:
        """Build a refusal carrying *sqlstate* and *message*."""
        self._sqlstate = sqlstate
        super().__init__(message)

    @property
    def sqlstate(self) -> str:  # type: ignore[override]
        """The code the loop discriminates on."""
        return self._sqlstate


class _FakeConnection:
    """A connection that does what it is told to do, and records what it was asked."""

    def __init__(self, *, commit_raises: BaseException | None = None) -> None:
        """Build a connection that raises *commit_raises* from :meth:`commit`, if given."""
        self.autocommit = False
        self.info = type("Info", (), {"transaction_status": 0})()
        self.executed: list[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0
        self._commit_raises = commit_raises

    def execute(self, query: Any, params: Any = None) -> Any:
        """Record the statement; raise it if the query is itself an exception."""
        if isinstance(query, BaseException):
            raise query
        self.executed.append((query, params))
        return self

    def commit(self) -> None:
        """Count the commit, or raise what this connection was built to raise."""
        self.commits += 1
        if self._commit_raises is not None:
            raise self._commit_raises

    def rollback(self) -> None:
        """Count the rollback."""
        self.rollbacks += 1

    def close(self) -> None:
        """Count the close."""
        self.closed += 1


def test_a_commit_time_refusal_is_recorded_and_re_raised_unchanged() -> None:
    """THE REGRESSION THIS MODULE EXISTS FOR: the ``40001`` that arrives at ``COMMIT``.

    The probe's first recorder wrapped the statements and not the commit, so a cycle detected
    at commit time — which is where CockroachDB usually detects it — was recorded as a clean
    attempt. The watcher must see it, write down the SQLSTATE and the verbatim message, and
    then let the exception out **unchanged**, because ``run_gate`` is what classifies it and a
    swallowed refusal is a silence.
    """
    seen: list[tuple[str, str]] = []
    refusal = _Refusal(RETRYABLE, "retry txn (RETRY_SERIALIZABLE): a cycle detected at commit")
    inner = _FakeConnection(commit_raises=refusal)
    watched = _WatchedConnection(inner, lambda exc, where: seen.append((str(exc), where)))

    with pytest.raises(psycopg.Error) as raised:
        watched.commit()

    assert raised.value is refusal, "the watcher replaced the exception instead of passing it on"
    assert len(seen) == 1, f"the commit refusal was recorded {len(seen)} times, not once"
    assert seen[0][1] == "commit", (
        "the refusal was attributed to a statement. The distinction is the whole finding: a "
        "recorder that only watches statements scores a commit-time 40001 as a clean attempt."
    )
    assert restart_reason(seen[0][0]) == "RETRY_SERIALIZABLE"


def test_a_statement_refusal_is_recorded_as_a_statement() -> None:
    """The other half of the same distinction, so ``raised_at`` is never a constant."""
    seen: list[tuple[str, str]] = []
    refusal = _Refusal("23514", "failed to satisfy CHECK constraint gate_closed_when_issued")
    watched = _WatchedConnection(
        _FakeConnection(), lambda exc, where: seen.append((str(exc), where))
    )

    with pytest.raises(psycopg.Error):
        watched.execute(refusal)

    assert [where for _, where in seen] == ["statement"]


def test_the_watcher_records_nothing_on_a_clean_transaction() -> None:
    """No exception, no record. A watcher that fired on success would inflate every census."""
    seen: list[tuple[str, str]] = []
    inner = _FakeConnection()
    watched = _WatchedConnection(inner, lambda exc, where: seen.append((str(exc), where)))

    watched.execute("SELECT 1", None)
    watched.commit()
    watched.close()

    assert seen == []
    assert (inner.commits, inner.closed, inner.rollbacks) == (1, 1, 0)


def test_the_watcher_delegates_the_two_attributes_the_adapter_guards_on() -> None:
    """``txn._fresh`` reads ``autocommit`` and ``info.transaction_status`` through this proxy.

    If either were shadowed by the wrapper, the adapter's freshness guards would be asking the
    wrapper about itself and would pass on a connection that was never checked.
    """

    def unreachable(exc: BaseException, where: str) -> None:
        """No statement is run here, so nothing may be recorded. Named so a hit is legible."""
        raise AssertionError(f"the watcher recorded {where} {exc!r} on a read of an attribute")

    inner = _FakeConnection()
    inner.autocommit = True
    watched = _WatchedConnection(inner, unreachable)
    assert watched.autocommit is True
    assert watched.info.transaction_status == 0


# ═══════════════════════════════════════════════════════════════════════════════════════
# the census — counted from the rounds, and required to agree with them
# ═══════════════════════════════════════════════════════════════════════════════════════


def _arm(*callers: dict[str, Any]) -> dict[str, Any]:
    """One round of two callers, in the shape :func:`census_constructed` reads."""
    return {"rounds": [{"round": 1, "callers": {"A": callers[0], "B": callers[1]}}]}


def _caller_record(attempts: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """A caller record with the fields the census reads and sane defaults for the rest."""
    return {
        "outcome": "committed",
        "attempts": attempts,
        "spy_retried": any(a.get("sqlstate") == RETRYABLE for a in attempts),
        "record_agrees_with_spy": True,
        **extra,
    }


def test_the_census_counts_a_40001_that_surfaced_at_commit() -> None:
    """A ``40001`` raised by ``COMMIT`` counts. This is the frozen form of the probe's own bug.

    The loser's attempt 0 reads cleanly and is then refused at commit; attempt 1 converges. Run
    against the recorder this probe shipped with first — the one that only wrapped statements —
    attempt 0 would carry ``00000`` and this assertion would read zero.
    """
    loser = _caller_record(
        [
            {
                "attempt": 0,
                "sqlstate": RETRYABLE,
                "restart_reason": "RETRY_SERIALIZABLE",
                "raised_at": "commit",
                "seconds": 0.03,
            },
            {
                "attempt": 1,
                "sqlstate": "00000",
                "restart_reason": None,
                "raised_at": None,
                "seconds": 0.01,
            },
        ]
    )
    winner = _caller_record(
        [
            {
                "attempt": 0,
                "sqlstate": "00000",
                "restart_reason": None,
                "raised_at": None,
                "seconds": 0.01,
            }
        ]
    )

    census = census_constructed(_arm(loser, winner))

    assert census["rounds_with_40001"] == 1
    assert census["sqlstates"] == {"00000": 2, RETRYABLE: 1}
    assert census["restart_reasons_for_40001"] == {"RETRY_SERIALIZABLE": 1}
    assert census["where_the_40001_surfaced"] == {"commit": 1}
    assert census["callers_run_gate_actually_retried"] == 1
    assert census["rounds_where_both_callers_committed"] == 1


def test_the_census_reports_a_disagreement_between_its_two_observers() -> None:
    """When the record and the spy disagree, the census SAYS SO rather than picking one.

    Two independent observers watch the same attempts. If they ever disagree the artefact is
    not trustworthy, and the honest response is to surface the disagreement — which
    :func:`unmet_conditions` then turns into a failure — not to average it away.
    """
    disagreeing = _caller_record(
        [
            {
                "attempt": 0,
                "sqlstate": "00000",
                "restart_reason": None,
                "raised_at": None,
                "seconds": 0.01,
            }
        ],
        record_agrees_with_spy=False,
    )
    clean = _caller_record(
        [
            {
                "attempt": 0,
                "sqlstate": "00000",
                "restart_reason": None,
                "raised_at": None,
                "seconds": 0.01,
            }
        ]
    )
    assert (
        census_constructed(_arm(disagreeing, clean))["callers_where_record_and_spy_disagree"] == 1
    )


def test_an_undecided_transaction_is_counted_as_undecided_and_not_as_a_refusal() -> None:
    """``RetryBudgetExhausted`` is neither a success nor a refusal — ``spec/errors.md`` §5."""
    undecided = _caller_record(
        [
            {
                "attempt": 0,
                "sqlstate": RETRYABLE,
                "restart_reason": "RETRY_SERIALIZABLE",
                "raised_at": "commit",
                "seconds": 0.02,
            }
        ],
        outcome="undecided",
    )
    clean = _caller_record(
        [
            {
                "attempt": 0,
                "sqlstate": "00000",
                "restart_reason": None,
                "raised_at": None,
                "seconds": 0.01,
            }
        ]
    )
    census = census_constructed(_arm(undecided, clean))
    assert census["callers_undecided_retry_budget_exhausted"] == 1
    assert census["rounds_where_both_callers_committed"] == 0


# ═══════════════════════════════════════════════════════════════════════════════════════
# the refusals — every branch demonstrated firing
# ═══════════════════════════════════════════════════════════════════════════════════════

_CLEAN_TARGET: dict[str, Any] = {
    "target": "local",
    "arm_constructed": {"lifecycle": {"scratch_is_gone": True}, "rounds": []},
    "census_constructed": {"callers_where_record_and_spy_disagree": 0},
    "arm_gate_run": {"row_counts_moved": {}, "nothing_persisted": True},
}


def test_unmet_conditions_is_silent_when_every_condition_holds() -> None:
    """The control that keeps the four below from being vacuously true."""
    assert unmet_conditions([_CLEAN_TARGET], "w_w1") == []


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        pytest.param(
            {"arm_constructed": {"lifecycle": {"scratch_is_gone": False}, "rounds": []}},
            "not proven gone",
            id="the scratch database survived the DROP",
        ),
        pytest.param(
            {"census_constructed": {"callers_where_record_and_spy_disagree": 2}},
            "disagree about how many 40001s",
            id="the two observers disagree",
        ),
        pytest.param(
            {"arm_gate_run": {"row_counts_moved": {"mainline.permit_event": [2, 3]}}},
            "MOVED row counts",
            id="the gate-run arm wrote something",
        ),
        pytest.param(
            {"arm_gate_run": {"arm_failed": "a container never became ready"}},
            "did not complete",
            id="the arm died part way through",
        ),
    ],
)
def test_every_unmet_condition_fires_when_its_fault_is_injected(
    fault: dict[str, Any], expected: str
) -> None:
    """A verifier that has never failed has never discriminated — the lead's ruling R8, applied.

    Each branch is driven with the exact fault it exists to catch, and the message is asserted
    so that a refusal cannot quietly start firing for the wrong reason.
    """
    unmet = unmet_conditions([{**_CLEAN_TARGET, **fault}], "w_w1")
    assert len(unmet) == 1, f"expected exactly one unmet condition, got {unmet!r}"
    assert expected in unmet[0], f"the refusal fired with the wrong words: {unmet[0]!r}"


# ═══════════════════════════════════════════════════════════════════════════════════════
# the committed artefact
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def evidence() -> dict[str, Any]:
    """The committed census. Absent is a FAILURE, never a skip — the probe is meant to be run."""
    if not EVIDENCE.is_file():
        pytest.fail(
            f"{EVIDENCE.relative_to(REPO_ROOT).as_posix()} does not exist. Produce it with "
            "`python -m scripts.deploy.cloud_contention --rounds 12`. This is a failure and not "
            "a skip: the artefact is the deliverable, and a suite that shrugged when it was "
            "missing would go green on a repository that had never taken the measurement."
        )
    parsed: dict[str, Any] = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    return parsed


def _targets(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index the census by platform name, so a missing column fails by name rather than by index."""
    return {t["target"]: t for t in evidence["targets"]}


def test_the_census_covers_both_platforms_in_one_sitting(evidence: dict[str, Any]) -> None:
    """Cloud AND local. One file, one run — otherwise it is two anecdotes, not a comparison."""
    present = _targets(evidence)
    missing = [name for name in REQUIRED_TARGETS if name not in present]
    assert not missing, f"the census names no {missing} column; a one-sided census is not one"
    for name in REQUIRED_TARGETS:
        assert "unreachable" not in present[name], (
            f"{name} was not reached: {present[name]['unreachable']!r}. That is a result worth "
            "reporting and it is NOT a census."
        )


@pytest.mark.parametrize("target", REQUIRED_TARGETS)
def test_each_arm_carries_at_least_twelve_constructed_races(
    evidence: dict[str, Any], target: str
) -> None:
    """Twelve is a FLOOR. It rises when somebody measures more; it never falls for a green."""
    record = _targets(evidence)[target]
    for arm in ("arm_constructed", "arm_gate_run"):
        rounds = record[arm]["rounds"]
        assert len(rounds) >= MINIMUM_ROUNDS, (
            f"{target}/{arm} recorded {len(rounds)} rounds against a floor of {MINIMUM_ROUNDS}"
        )


@pytest.mark.parametrize("target", REQUIRED_TARGETS)
def test_every_attempt_carries_a_sqlstate_and_every_40001_carries_its_reason_verbatim(
    evidence: dict[str, Any], target: str
) -> None:
    """The brief's actual requirement, asserted over every attempt rather than sampled.

    A ``40001`` recorded without the server's own words is a classification nobody can check,
    and checking it is the only reason the reason is recorded at all.
    """
    for row in _targets(evidence)[target]["arm_constructed"]["rounds"]:
        for name, caller in row["callers"].items():
            for attempt in caller["attempts"]:
                where = f"{target} round {row['round']} caller {name} attempt {attempt['attempt']}"
                assert attempt.get("sqlstate"), f"{where}: no SQLSTATE recorded"
                if attempt["sqlstate"] != RETRYABLE:
                    continue
                assert attempt.get("restart_reason"), f"{where}: a 40001 with no restart reason"
                assert attempt.get("message_verbatim"), (
                    f"{where}: a 40001 with no verbatim message. The reason is PARSED from that "
                    "message; without it the classification cannot be checked."
                )
                assert attempt["restart_reason"] in attempt["message_verbatim"], (
                    f"{where}: the recorded reason {attempt['restart_reason']!r} does not appear "
                    f"in the message it was supposedly parsed from"
                )
                assert attempt.get("raised_at") in {"statement", "commit"}, (
                    f"{where}: a 40001 that surfaced nowhere in particular"
                )


@pytest.mark.parametrize("target", REQUIRED_TARGETS)
def test_the_summary_is_recomputed_from_the_rounds_underneath_it(
    evidence: dict[str, Any], target: str
) -> None:
    """The published census must equal one derived here from the same rounds.

    This is what makes the artefact checkable rather than merely readable. A summary edited by
    hand, or produced by a tally that has drifted from its own data, fails here and fails naming
    the field that disagrees.
    """
    record = _targets(evidence)[target]
    recomputed = census_constructed(record["arm_constructed"])
    published = record["census_constructed"]
    for field, value in recomputed.items():
        assert published.get(field) == value, (
            f"{target}: the published census says {field}={published.get(field)!r} and the same "
            f"rounds recompute to {value!r}"
        )


@pytest.mark.parametrize("target", REQUIRED_TARGETS)
def test_the_two_observers_agreed_everywhere(evidence: dict[str, Any], target: str) -> None:
    """Zero disagreements, per caller, not merely zero in the summary."""
    for row in _targets(evidence)[target]["arm_constructed"]["rounds"]:
        for name, caller in row["callers"].items():
            assert caller["record_agrees_with_spy"] is True, (
                f"{target} round {row['round']} caller {name}: the per-attempt record counted "
                f"{caller['recorded_40001']} 40001(s) and the run_gate spy counted "
                f"{caller['spy_attempts_for_40001']}"
            )


@pytest.mark.parametrize("target", REQUIRED_TARGETS)
def test_the_scratch_database_was_created_and_proven_gone(
    evidence: dict[str, Any], target: str
) -> None:
    """Ruling R5: the probe builds its own database, and "gone" is asked rather than assumed."""
    lifecycle = _targets(evidence)[target]["arm_constructed"]["lifecycle"]
    assert lifecycle.get("create_refused") is None, (
        f"{target}: CREATE DATABASE was refused with {lifecycle['create_refused']!r}. That "
        "refusal is a RESULT and is reported as one; it is never routed around by writing into "
        "mainline_demo."
    )
    assert lifecycle["scratch_is_gone"] is True, f"{target}: {lifecycle['scratch_database']} lives"
    assert lifecycle["survivors_after_drop"] == 0


@pytest.mark.parametrize("target", REQUIRED_TARGETS)
def test_the_gate_run_arm_moved_no_row_on_either_platform(
    evidence: dict[str, Any], target: str
) -> None:
    """The CONDITION on Arm B's permission to race against a live demo database.

    ``evidence/deploy/cloud-seed.json`` publishes the Cloud row counts as committed evidence. A
    probe that moved one of them would falsify a committed artefact — so the ten tables the four
    beats can write are counted by this probe, over its own connection, before and after.
    """
    arm = _targets(evidence)[target]["arm_gate_run"]
    assert arm["row_counts_moved"] == {}, (
        f"{target}: the gate-run arm moved {arm['row_counts_moved']!r}. The endpoint's whole "
        "claim is that it persists nothing."
    )
    assert arm["nothing_persisted"] is True
    assert set(arm["row_counts_before"]) == set(FINGERPRINT_TABLES)


def test_the_cloud_row_counts_still_match_the_committed_seed(evidence: dict[str, Any]) -> None:
    """Ruling R5's authority, checked directly against the artefact that published it."""
    seeded = json.loads(SEED_EVIDENCE.read_text(encoding="utf-8"))["row_counts"]
    after = _targets(evidence)["cloud"]["arm_gate_run"]["row_counts_after"]
    shared = sorted(set(seeded) & set(after))
    assert shared, "the two artefacts name no table in common; one of them changed shape"
    drifted = {t: (seeded[t], after[t]) for t in shared if seeded[t] != after[t]}
    assert not drifted, (
        f"Cloud row counts have moved away from evidence/deploy/cloud-seed.json: {drifted!r} "
        "(seeded, observed). cloud-seed.json is the committed expected value."
    )


def test_the_database_was_selected_by_name_and_confirmed_by_the_server(
    evidence: dict[str, Any],
) -> None:
    """Ruling R10(1). The DSN's path segment says ``defaultdb`` and is never believed."""
    cloud = _targets(evidence)["cloud"]
    selection = cloud["fingerprint"]["database_selection"]
    assert selection["matches"] is True
    assert selection["confirmed_by_server"] == "mainline_demo"
    assert selection["dsn_path_segment"] == "defaultdb", (
        "the committed DSN's path segment is no longer 'defaultdb'. If that is a real change, "
        "this expectation moves WITH the DSN and the change is stated; if it is not, something "
        "started trusting the segment."
    )


def test_the_restart_messages_themselves_distinguish_the_two_clusters(
    evidence: dict[str, Any],
) -> None:
    """The cluster's shape, read out of the ``40001`` messages and never out of a catalogue.

    This is the pay-off from ruling R3's method, and it is asserted rather than admired: the
    same text that names the restart reason also names the nodes whose clocks the transaction
    observed, the conflicting key, and the width of the clock-uncertainty window. On Cloud all
    three differ from the local node, and the difference is structural rather than statistical.

    **The node id is not a node count and this test does not treat it as one.** It asserts only
    that Cloud's observed id is not ``1`` — which one process cannot produce — and that local's
    is.
    """
    cloud = structural_differences(_targets(evidence)["cloud"]["arm_constructed"])
    local = structural_differences(_targets(evidence)["local"]["arm_constructed"])

    assert cloud["messages_read"] >= MINIMUM_ROUNDS, "too few messages to say anything"
    assert local["messages_read"] >= MINIMUM_ROUNDS

    assert list(local["observed_clock_node_ids"]) == ["1"], (
        f"the local single node observed clocks from {local['observed_clock_node_ids']!r}; one "
        "process is node 1 and nothing else"
    )
    assert "1" not in cloud["observed_clock_node_ids"], (
        f"Cloud observed clocks from {cloud['observed_clock_node_ids']!r}. An id of 1 would mean "
        "the race never left the first node that ever joined, and the structural claim below "
        "would rest on nothing."
    )

    assert list(local["conflicting_key_prefixes"]) == ["/Table"]
    assert list(cloud["conflicting_key_prefixes"]) == ["/Tenant"], (
        f"Cloud's conflicting keys are {cloud['conflicting_key_prefixes']!r}; CockroachDB Cloud "
        "Basic is multi-tenant and its keys carry a /Tenant/<id>/ prefix that a local "
        "start-single-node cannot produce"
    )

    # The clock-uncertainty window, measured. §3 item 2 is about restarts that happen INSIDE
    # this interval; the interval demonstrably exists on Cloud and is NARROWER than the local
    # node's default, which is the opposite of the way the trade-off is usually assumed.
    assert local["max_clock_offset_seconds"] == [0.5]
    assert cloud["max_clock_offset_seconds"] == [0.25], (
        f"Cloud's gul-rts came out {cloud['max_clock_offset_seconds']!r}. If CockroachDB Cloud "
        "has re-configured its maximum clock offset, this expectation moves WITH the cluster "
        "and §9.4's reading of it is restated — the cluster is authoritative, not this number."
    )


def test_no_topology_was_read_because_the_catalogues_are_restricted(
    evidence: dict[str, Any],
) -> None:
    """Ruling R3. Multi-node behaviour is proven by INDUCING contention, never by counting nodes.

    Asserted against the artefact's own text rather than against the source, because the thing
    that must stay true is what the evidence claims to have done.
    """
    blob = json.dumps(evidence)
    for forbidden in ("gossip_nodes", "crdb_internal.", "FROM system."):
        assert forbidden not in blob, (
            f"the census reads {forbidden!r}. Both catalogues are restricted for mainline-sql on "
            "Cloud Basic and answer 42501; a probe written that way reports a privilege refusal "
            "as a topology."
        )


#: A ``postgres://`` or ``postgresql://`` URL carrying userinfo — anything of the form
#: ``scheme://something:something@``. ``cloud_chain.redact`` rewrites the password half to
#: ``***``, so a match here means a message reached the artefact without crossing that boundary.
_DSN_WITH_USERINFO = re.compile(r'postgres(?:ql)?://[^\s/@"]+:[^\s/@"]*@')

#: ``password = 'x'`` and ``password=x``, the two spellings ``redact`` also rewrites.
_PASSWORD_ASSIGNMENT = re.compile(r"(?i)password\s*=\s*(?!\*\*\*)\S")


def test_the_artefact_carries_no_credential(evidence: dict[str, Any]) -> None:
    """Asserted by pattern, because "we were careful" is not a control.

    ``cloud_chain.redact`` is the boundary every message that leaves the probe crosses. This
    checks the *result* rather than the intention, and it checks both the bytes on disk and the
    parsed structure — the second so that a credential hidden by JSON escaping is still caught.
    """
    for what, blob in (
        ("the file on disk", EVIDENCE.read_text(encoding="utf-8")),
        ("the parsed census", json.dumps(evidence)),
    ):
        userinfo = _DSN_WITH_USERINFO.findall(blob)
        assert not userinfo, f"{what} holds a DSN with userinfo ({len(userinfo)} occurrence(s))"
        assert not _PASSWORD_ASSIGNMENT.search(blob), f"{what} holds a password= assignment"


def test_the_document_no_longer_says_the_credential_is_absent() -> None:
    """``docs/deploy/CLOUD-40001.md`` §3's load-bearing sentence, corrected against the world.

    Ruling **R1**: the environment is authoritative and the document is derived. The sentence
    *"Its credential is not on this workstation, and no attempt was made to obtain one"* was
    true when it was written and is false now, and the correction had to be made in the document
    rather than by pretending the environment had not changed.
    """
    text = DOCUMENT.read_text(encoding="utf-8")
    for dead in (
        "Its credential is not on this workstation, and no attempt was made to obtain one.",
        "The Cloud DSN is\n> a GitHub repository secret and is not present on this workstation",
    ):
        assert dead not in text, (
            f"CLOUD-40001.md still asserts {dead!r}. The credential IS on this workstation "
            "(ruling R1) and the document is the derived side of that disagreement."
        )
    assert "evidence/deploy/cloud-contention.json" in text, (
        "CLOUD-40001.md does not cite the Cloud census. A document whose §3 has been corrected "
        "must say what corrected it."
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# the live arm — one test, one database, one named reason if it ever cannot run
# ═══════════════════════════════════════════════════════════════════════════════════════

_NO_CLUSTER = (
    "no CockroachDB answered on $MAINLINE_TEST_DSN, $COCKROACH_URL, $CRDB_URL, $TRAPPOINT_DSN "
    "or 127.0.0.1:26257 within the probe budget. THIS SKIP IS NOT EVIDENCE, and on the "
    "workstation this test was written on it does not fire: `docker compose up crdb` or a local "
    "`cockroach start-single-node` makes it run. It is not a licence to write 'this cannot be "
    "tested without a cluster' — docs/deploy/CLOUD-40001.md §0 retired that sentence."
)


@pytest.mark.requires_cluster
@pytest.mark.slow
@pytest.mark.timeout(300)
def test_the_constructed_cycle_really_does_produce_40001_here_and_now() -> None:
    """Drive the probe's own Arm A against whatever cluster answers, and require a ``40001``.

    Six rounds rather than twelve: this is a *liveness* check on the probe, not the census —
    the census is the artefact, and it is asserted above. Six is chosen because the shape has
    been measured at 6/6 three separate times in this repository
    (``docs/deploy/CLOUD-40001.md`` §2.1, ``docs/diagnosis/retry-negative-control.md`` §4.1, and
    the lead's own reproduction), so a round with no ``40001`` at all would be news.

    The scratch database is this test's own, named for the test, and dropped by the arm itself.
    """
    from trappoint_testkit.cluster import reuse

    from scripts.deploy.cloud_contention import CYCLE, PROBE_POLICY, arm_constructed

    found = reuse()
    if found is None:
        pytest.skip(_NO_CLUSTER)

    scratch = f"w_w1_live_{uuid.uuid4().hex[:8]}"
    arm = arm_constructed(found.dsn, scratch, rounds=6, policy=PROBE_POLICY, keys=CYCLE)
    census = census_constructed(arm)

    assert arm["lifecycle"]["create_refused"] is None, (
        f"CREATE DATABASE was refused: {arm['lifecycle']['create_refused']!r}. That refusal is "
        "the result and is reported as one."
    )
    assert arm["lifecycle"]["scratch_is_gone"] is True, f"{scratch} survived the DROP"
    assert census["rounds_with_40001"] >= 1, (
        f"six constructed read-write cycles against {found.provenance} produced no 40001 at all: "
        f"{census!r}. Either the rendezvous stopped interleaving the two callers or the cycle "
        "stopped being a cycle — both are defects in the probe, and neither is a fact about the "
        "cluster."
    )
    assert census["callers_where_record_and_spy_disagree"] == 0
    assert set(census["restart_reasons_for_40001"]) - {"unnamed"}, (
        f"every 40001 came back with an unnamed restart reason: "
        f"{census['restart_reasons_for_40001']!r}. The server names one; the classifier is not "
        "reading it."
    )
    assert census["callers_run_gate_actually_retried"] >= 1, (
        "a 40001 was observed and run_gate never retried anything. The guard was not reached."
    )


@pytest.mark.requires_cluster
@pytest.mark.slow
@pytest.mark.timeout(300)
def test_the_same_harness_produces_no_40001_when_the_two_callers_share_nothing() -> None:
    """THE NEGATIVE CONTROL. Without it the test above proves only that the probe is noisy.

    Same threads, same rendezvous, same ``run_txn``, same scratch database, same round count —
    and the two transactions touch **disjoint keys**, so there is no cycle and the correct
    answer is **zero** ``40001``. If this ever produces one, the sibling test above is not
    measuring contention and neither is
    ``evidence/deploy/cloud-contention.json``.

    **Two weaker controls were tried first and both FAILED to discriminate**, which is why this
    one is written the way it is and why the others are named rather than quietly discarded:

    * removing the rendezvous entirely still gave 6 of 6 — the statements are sub-millisecond,
      so two threads started together overlap whether or not a barrier says so;
    * pointing both callers at **one** key still gave 6 of 6 — two concurrent read-modify-writes
      of a single row are unorderable for the same reason a two-key cycle is.

    **Only disjointness turns the signal off**, and a control that cannot be turned off is not a
    control.
    """
    from trappoint_testkit.cluster import reuse

    from scripts.deploy.cloud_contention import DISJOINT, PROBE_POLICY, arm_constructed

    found = reuse()
    if found is None:
        pytest.skip(_NO_CLUSTER)

    scratch = f"w_w1_ctrl_{uuid.uuid4().hex[:8]}"
    arm = arm_constructed(found.dsn, scratch, rounds=6, policy=PROBE_POLICY, keys=DISJOINT)
    census = census_constructed(arm)

    assert arm["lifecycle"]["shape"] == "disjoint"
    assert arm["lifecycle"]["scratch_is_gone"] is True, f"{scratch} survived the DROP"
    assert census["rounds_with_40001"] == 0, (
        f"two transactions that share no key produced {census['rounds_with_40001']} round(s) of "
        f"40001: {census['restart_reasons_for_40001']!r}. The harness is manufacturing "
        "conflicts, so the census it produces is not about the cluster."
    )
    assert census["sqlstates"] == {"00000": 12}, (
        f"the disjoint control saw {census['sqlstates']!r}; twelve clean commits is the only "
        "correct answer and anything else is a defect in the probe, not a fact about contention"
    )
    assert census["callers_run_gate_actually_retried"] == 0
    assert census["rounds_where_both_callers_committed"] == 6
