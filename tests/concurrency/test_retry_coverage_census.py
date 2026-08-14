# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Every transaction in ``gate_run.py`` and ``transitions.py``, and what guards it.

WHY A CENSUS AND NOT A LIST OF TESTS
------------------------------------
``spec/errors.md`` §2.1 requires the retried unit to be the WHOLE transaction, from
``BEGIN``. Whether that holds is a property of a **set** — of every transaction in these two
modules — and a suite of individually-green tests cannot say anything about a set. The
sixth transaction, added next month, is green by omission.

So this file does three things and the third is the only one that is really a test:

1. **Enumerates the transactions mechanically**, out of the source, by walking the AST for
   the two things that make a function a transaction site: a call to ``.commit()``, and the
   literal ``SET TRANSACTION ISOLATION LEVEL`` that opens one explicitly. A site the census
   below does not declare is a hard failure, so a new committing function cannot arrive
   unguarded and unnoticed.
2. **Requires a stated disposition for each**, either ``wrapped`` naming the loop it is
   wrapped by, or ``unwrapped`` carrying a written reason. A blank reason is refused.
3. **Proves the loop is REACHED, by spying rather than by reading the source.** An AST check
   that ``run_transaction`` appears in ``handle_transition`` proves the token is present; it
   does not prove any request goes through it. The controls at the bottom drive all five
   POSTs and watch.

NO NEW PRIMITIVE IS WRITTEN HERE, and the census asserts that none is written there either.
The loops are :func:`mainline_demo_api.retry.run_transaction` (the deployment package's, one
of two deliberate copies — the Lambda pins ``psycopg`` only and may not import
``trappoint_core``) and :func:`trappoint_core.retry.run_gate` (the reference). The spy is
:class:`mainline_demo_api.retry.RecordingObserver`, which already exists for this purpose.

NO DATABASE IS REQUIRED, deliberately. Every assertion here is about *control flow* — which
unit the loop is wrapped around and whether it is entered — and none is about what a
database answered. The lanes that need a cluster already have one; making this one need a
node too would mean the census stopped running exactly when the cluster was unavailable,
which is when a coverage claim is least worth taking on trust.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest


def _repo_root() -> Path:
    for candidate in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    raise RuntimeError("no workspace root above this file")


_APP_SRC = _repo_root() / "verticals" / "mainline" / "apps" / "demo-api" / "src"
if str(_APP_SRC) not in sys.path:  # the app is not installed as a distribution
    sys.path.insert(0, str(_APP_SRC))

_MODULES = {
    "gate_run.py": _APP_SRC / "mainline_demo_api" / "gate_run.py",
    "transitions.py": _APP_SRC / "mainline_demo_api" / "transitions.py",
}

#: The retried unit, for every transaction site in the two modules.
#:
#: ``wrapped_by`` names the loop and ``unit`` names what that loop is wrapped AROUND, because
#: "it is retried" and "the whole transaction is retried" are different claims and only the
#: second one is what §2.1 asks for. ``reason`` is required on every entry, wrapped or not:
#: a disposition without a reason is a decision nobody can review.
CENSUS: dict[str, dict[str, Any]] = {
    "transitions.py::_merge_permit": {
        "wrapped": True,
        "wrapped_by": "mainline_demo_api.retry.run_transaction",
        "unit": "handle_transition.attempt — rollback, guard, then the whole transition",
        "reason": (
            "One whole transaction: `_prepare` states the isolation level, the work "
            "follows, one `commit()` ends it. `handle_transition` runs that closure under "
            "the loop, so one call is exactly one attempt. THIS ENTRY SAYS THE OPPOSITE OF "
            "WHAT THE MODULE SAID AT 7535670 — 're-sending a merge is how a permit gets "
            "issued twice' — and the correction is `docs/leads/ci-green-final.md` R3: "
            "40001 is a transaction the database ABORTED, so nothing was written and "
            "nothing was decided, and a re-attempt is a first attempt against the same "
            "rows. The code that genuinely means 'the commit may or may not have landed' "
            "is 40003, which `classify_for_retry` calls unmodelled and never retries."
        ),
    },
    "transitions.py::_suspend_permit": {
        "wrapped": True,
        "wrapped_by": "mainline_demo_api.retry.run_transaction",
        "unit": "handle_transition.attempt",
        "reason": (
            "As _merge_permit: one `_prepare` … `commit()` unit, retried whole from BEGIN. "
            "Its only identifier is the permit it was addressed by, which the caller "
            "supplied, so a second attempt collides with nothing it minted itself."
        ),
    },
    "transitions.py::_materialise_checks": {
        "wrapped": True,
        "wrapped_by": "mainline_demo_api.retry.run_transaction",
        "unit": "handle_transition.attempt",
        "reason": (
            "As _merge_permit. Safe to re-attempt because its `receipt_id` is minted "
            "INSIDE the transaction, so a second attempt cannot meet its own first "
            "attempt's key and turn a serialization restart into a 23505 nobody may retry."
        ),
    },
    "transitions.py::_sign_disposition": {
        "wrapped": True,
        "wrapped_by": "mainline_demo_api.retry.run_transaction",
        "unit": "handle_transition.attempt",
        "reason": (
            "As _materialise_checks; its `disposition_id` is likewise minted inside the "
            "transaction."
        ),
    },
    "transitions.py::_demo_gate_run": {
        "wrapped": True,
        "wrapped_by": "mainline_demo_api.retry.run_transaction",
        "unit": "gate_run — the whole function, which is one whole transaction",
        "reason": (
            "`gate_run` reports 40001 in its PAYLOAD rather than raising, because it has to "
            "return the beats that did complete, so the undecided outcome is recognised by "
            "the loop's `undecided=` predicate instead of by an except clause. Re-running "
            "is safe for a second, independent reason: the run persists nothing, which the "
            "payload proves rather than asserts."
        ),
    },
    "transitions.py::_prepare": {
        "wrapped": False,
        "wrapped_by": None,
        "unit": None,
        "reason": (
            "NOT A TRANSACTION SITE AND MUST NOT BE WRAPPED. It is the first two statements "
            "OF one — a rollback and `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE` — and "
            "the transaction it opens is closed by its caller's `commit()`. A "
            "`run_transaction` around `_prepare` would retry two statements inside a "
            "transaction that is still open, which `spec/errors.md` §2.1 says is not a "
            "retry of anything. It is covered because its CALLER is wrapped: a 40001 raised "
            "here propagates and the whole transition is re-attempted from the top, which "
            "re-issues the isolation level — the auditability §2.1 is protecting."
        ),
    },
    "gate_run.py::gate_run": {
        "wrapped": True,
        "wrapped_by": "mainline_demo_api.retry.run_transaction, one level up",
        "unit": "gate_run itself, called from transitions._demo_gate_run",
        "reason": (
            "IT MUST NOT RETRY ITSELF, and that is the point rather than an omission: one "
            "call is exactly one attempt, which is what makes it a legitimate retryable "
            "unit for the caller. A loop inside it would re-send a statement into a "
            "transaction the database had already aborted. It opens two transactions in "
            "sequence — the read-only opening fingerprint, then the beats' SERIALIZABLE "
            "transaction — and BOTH are inside the unit the caller re-runs."
        ),
    },
}


# ── 1 · the enumeration, out of the source ──────────────────────────────────────────


def _transaction_sites(path: Path) -> set[str]:
    """Every function in *path* that commits, or that opens a transaction explicitly.

    Two markers, and each is there because it is what the code actually does rather than
    what it is called: ``.commit()`` ends a transaction, and the literal below opens one.
    Nested functions are reported under their OWN name — ``handle_transition.attempt`` is a
    closure, not a transaction site, and it is the loop's argument rather than its subject.
    """
    module = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()

    def commits_or_opens(node: ast.AST) -> bool:
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "commit"
            ):
                return True
            if (
                isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and "SET TRANSACTION ISOLATION LEVEL" in child.value
            ):
                return True
        return False

    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and commits_or_opens(node):
            found.add(f"{path.name}::{node.name}")
    return found


def test_the_census_names_every_transaction_in_both_modules() -> None:
    """A site the census does not declare fails here, on the day it is written."""
    discovered: set[str] = set()
    for path in _MODULES.values():
        discovered |= _transaction_sites(path)

    undeclared = discovered - set(CENSUS)
    assert not undeclared, (
        f"these transaction sites are not in the census: {sorted(undeclared)}. Every "
        "multi-statement transaction in gate_run.py and transitions.py is either wrapped "
        "WHOLE from BEGIN by a retry loop or is recorded here with a stated reason why it "
        "must not be. Add the entry — with the reason — rather than deleting this "
        "assertion: spec/errors.md §2.1 is what it is enforcing."
    )

    # And the census may not name a function that no longer exists, which is how a census
    # goes on asserting coverage of code somebody deleted.
    for name in CENSUS:
        filename, _, function = name.partition("::")
        source = _MODULES[filename].read_text(encoding="utf-8")
        assert f"def {function}(" in source, (
            f"the census declares {name}, which is not in {filename} any more. A census "
            "that outlives its subject is a coverage claim about nothing."
        )


def test_every_census_entry_states_a_reason() -> None:
    """`wrapped: False` with no argument is the shape this file exists to prevent."""
    for name, entry in CENSUS.items():
        assert entry["reason"].strip(), f"{name} carries no reason"
        assert len(entry["reason"]) > 80, (
            f"{name}'s reason is a label, not an argument: {entry['reason']!r}"
        )
        if entry["wrapped"]:
            assert entry["wrapped_by"], f"{name} claims to be wrapped but names no loop"
            assert entry["unit"], (
                f"{name} names a loop but not the UNIT it is wrapped around. 'It is "
                "retried' and 'the whole transaction is retried' are different claims."
            )
        else:
            assert entry["wrapped_by"] is None and entry["unit"] is None


def test_neither_module_grows_a_retry_loop_of_its_own() -> None:
    """One taxonomy, specified and spied on, beats two that can disagree.

    ``mainline_demo_api/retry.py`` is already a deliberate SECOND copy of
    ``trappoint_core.retry`` — the Lambda pins ``psycopg`` and nothing else, so it cannot
    import the workspace package — and two is the number that is argued for. A third, grown
    inside a transition because a backoff was needed in a hurry, is the one nobody spies on
    and the one that wins the day they disagree.
    """
    for filename, path in _MODULES.items():
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr != "sleep", (
                    f"{filename}:{node.lineno} sleeps. A sleep in a transition module is a "
                    "backoff, and a backoff is a retry loop that this repository's two "
                    "declared loops do not know about."
                )


# ── 2 · the controls: the loop is REACHED, and it is entered around the right unit ───


class _FakeConnection:
    """Enough connection for ``handle_transition`` to reach the loop, and no more.

    Deliberately not a psycopg connection and deliberately not a database. What is under
    test is which unit the loop is wrapped around and whether a request enters it; a real
    node would add a second reason for these to fail and would not add a single assertion.
    ``_borrowed`` reads and writes ``autocommit`` and calls ``rollback()``; nothing else is
    touched before ``run_transaction`` is called, and any statement issued past that point
    is a defect this double will report by name rather than by a mystery.
    """

    def __init__(self) -> None:
        self.autocommit = True
        self.rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1

    def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:  # noqa: ARG002
        raise AssertionError(
            "handle_transition issued a statement before entering run_transaction: "
            f"{str(query)[:120]!r}. That statement is OUTSIDE the retried unit, so a 40001 "
            "on it would not be re-attempted — which is the coverage gap this census is for."
        )


@pytest.fixture
def transitions_module() -> Any:
    return pytest.importorskip(
        "mainline_demo_api.transitions",
        reason=(
            "the demo-api deployment package is not importable from "
            f"{_APP_SRC}; the retry-coverage census is about ITS control flow and asserts "
            "nothing without it"
        ),
    )


#: The five POSTs, and the path parameter each is addressed by.
_POSTS: tuple[tuple[str, dict[str, str]], ...] = (
    ("merge_permit", {"permit_id": "6f1b1d02-0000-4000-8000-000000000001"}),
    ("suspend_permit", {"permit_id": "6f1b1d02-0000-4000-8000-000000000002"}),
    ("materialise_checks", {"permit_id": "6f1b1d02-0000-4000-8000-000000000003"}),
    ("sign_disposition", {"check_id": "6f1b1d02-0000-4000-8000-000000000004"}),
    ("demo_gate_run", {}),
)


def test_every_one_of_the_five_posts_enters_the_retry_loop(
    transitions_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spied, not assumed. The loop is replaced by a recorder and every POST is driven.

    ``docs/leads/ci-green-final.md`` R3 wrapped the four committing transitions after
    measuring that a 40001 raised outside a transition's own ``except psycopg.Error`` was
    answered ``503 database_unreachable``. This is the assertion that the wrapping actually
    covers all five paths rather than the one that was being debugged at the time.
    """
    seen: list[str] = []
    resource_being_driven: list[str] = []

    def recording_loop(operation: Any, **kwargs: Any) -> Any:
        resource = resource_being_driven[-1]
        seen.append(resource)
        assert callable(operation), "the loop was handed something that is not an operation"
        assert "undecided" in kwargs, (
            "run_transaction was called without the `undecided` predicate. A 40001 that a "
            "transition ANSWERS instead of raising — the 503/outcome:retry envelope — is a "
            "RETURNED value, and without the predicate the loop cannot see it: half the "
            "surface would be uncovered while looking covered."
        )
        # The two call sites are wrapped around different units and therefore return
        # different shapes: `handle_transition` retries a whole transition, whose value is
        # the `(status, body)` pair; `_demo_gate_run` retries `gate_run`, whose value is the
        # gate-run payload. Standing in for both with one shape would prove only that the
        # recorder is consistent with itself.
        if resource == "demo_gate_run":
            return {"outcome": "completed", "verdict": "PROVEN", "failures": []}
        return (200, {"data": {"outcome": "spied"}})

    monkeypatch.setattr(transitions_module, "run_transaction", recording_loop)

    for resource, params in _POSTS:
        resource_being_driven.append(resource)
        conn = _FakeConnection()
        status, _payload = transitions_module.handle_transition(resource, params, {}, conn)
        assert status == 200, resource
        assert conn.autocommit is True, f"{resource} did not hand the connection back"

    assert seen == [resource for resource, _ in _POSTS], (
        f"only {seen} entered run_transaction. Every POST that opens a transaction must be "
        "one whole retried unit; a path that skips the loop answers 503 "
        "database_unreachable for a database that answered."
    )


def test_a_request_that_never_opens_a_transaction_does_not_enter_the_loop(
    transitions_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control's control. A spy that fires for everything has discriminated nothing.

    An unknown resource is answered 404 before any transaction is opened, so it must NOT
    reach the loop. Without this, the assertion above would still pass if ``handle_transition``
    had been changed to wrap the entire function including its own argument validation —
    which would report coverage it does not have.
    """
    entered: list[Any] = []

    def recording_loop(operation: Any, **kwargs: Any) -> tuple[int, dict[str, Any]]:  # noqa: ARG001
        entered.append(operation)
        return (200, {})

    monkeypatch.setattr(transitions_module, "run_transaction", recording_loop)
    status, _payload = transitions_module.handle_transition(
        "delete_everything", {}, {}, _FakeConnection()
    )
    assert status == 404
    assert entered == [], "a resource that opens no transaction entered the retry loop"


def test_the_loop_that_is_reached_retries_40001_and_only_40001() -> None:
    """The real primitive, driven with the spy it already ships, over the whole taxonomy.

    ``mainline_demo_api.retry`` is not re-implemented here and no third loop is written:
    this drives the deployment package's own :func:`run_transaction` with its own
    :class:`RecordingObserver`, which is what the once-only property is stated in terms of.
    """
    psycopg = pytest.importorskip("psycopg", reason="psycopg 3 is required to build the errors")
    retry = pytest.importorskip("mainline_demo_api.retry", reason="the deployment package")

    # 40001 twice, then success: the WHOLE operation ran three times.
    attempts = [0]

    def flaky() -> str:
        attempts[0] += 1
        if attempts[0] <= 2:
            raise psycopg.errors.SerializationFailure("planted 40001")
        return "committed"

    spy = retry.RecordingObserver()
    assert retry.run_transaction(flaky, observer=spy, sleep=lambda _s: None) == "committed"
    assert attempts[0] == 3
    assert [state for _a, state, _d in spy.retries] == ["40001", "40001"]
    assert spy.successes == [2]

    # And every decided outcome is attempted exactly once, ever (spec/errors.md §4).
    for sqlstate in sorted(retry.REFUSAL_SQLSTATES | {retry.DENIED_SQLSTATE}):
        ran = [0]

        def refuse(code: str = sqlstate, counter: list[int] = ran) -> None:
            counter[0] += 1
            error = psycopg.Error(f"planted {code}")
            error.sqlstate = code  # type: ignore[attr-defined]
            raise error

        once = retry.RecordingObserver()
        with pytest.raises(psycopg.Error):
            retry.run_transaction(refuse, observer=once, sleep=lambda _s: None)
        assert ran[0] == 1, f"{sqlstate} was attempted {ran[0]} times; §4 says once, ever"
        assert once.attempts_for(sqlstate) == 1
        assert once.retries == [], f"{sqlstate} was RETRIED: {once.retries}"


def test_the_two_loops_agree_and_neither_is_re_implemented_here() -> None:
    """The second copy is deliberate; a third would not be. Assert the two classify alike.

    ``mainline_demo_api/retry.py`` exists because the Lambda pins ``psycopg`` only and may
    not import ``trappoint_core``. That is a cost, and this is where it is paid: the two
    must agree over the whole code space, not over the handful of codes a test happens to
    synthesise an error for.
    """
    demo = pytest.importorskip("mainline_demo_api.retry", reason="the deployment package")
    core = pytest.importorskip(
        "trappoint_core.retry",
        reason="the reference implementation; `uv sync --package trappoint-core` installs it",
    )
    assert demo.RETRYABLE_SQLSTATE == "40001"
    assert callable(core.run_gate), "trappoint_core.retry.run_gate is the reference loop"
    for code in sorted(demo.REFUSAL_SQLSTATES | {demo.DENIED_SQLSTATE, "40001", "40003", "XXXXX"}):
        classification = demo.classify_for_retry(code)
        assert (classification == "retry") == (code == "40001"), (
            f"{code} classifies as {classification!r}; only 40001 is retryable and 40003 — "
            "'the commit may or may not have landed' — must never be"
        )
