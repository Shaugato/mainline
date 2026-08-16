# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""THE CONSOLE DECLARES THE RESOURCES; THE DEMO SEED MUST CARRY THEM.

This file exists because of a gap that sat in the repository unnoticed until a fixture
happened to trip over it. ``apps/console/src/data/resources.ts`` declared **twelve**
navigable GET resources. ``db/seeds/demo/demo_world.sql`` + ``demo_permit.sql`` — the two
files ``scripts/deploy/seed_demo.py`` applies to CockroachDB Cloud — carried **eleven** of
them. ``change_request`` had a table (``0051``), a nine-edge transition alphabet
(``0017b:38-46``), four named CHECK refusals, a reader (``reads.read_change_request``), a
route (``app.py:213``) and a committed JSON Schema, and **no row**. A judge who clicked the
resource got a 404.

**Nothing anywhere asserted the correspondence.** The gap surfaced on 2026-08-13 only
because ``tests/test_reads.py`` asked for ``seed["cr_id"]`` and the fixture refused to
invent it — 63 of the suite's 444 results errored on setup, twelve hours before a demo.
That is the correspondence being discovered by accident. This file makes it a test.

WHAT IS AUTHORITATIVE HERE, AND WHY THE LIST IS NOT WRITTEN DOWN IN PYTHON
--------------------------------------------------------------------------
**The console is the authority for which resources exist.** It is the artefact a judge
drives, ``RESOURCE_KEYS`` is the list its own router iterates, and a resource that is in
that list is a link on a page somebody will click. So the list is *parsed out of the
TypeScript*, never restated here: a second copy of a list is a second thing to drift, and
drift between two copies of this particular list is the exact defect this file is about.
Restating it would reproduce the bug in the test written to prevent it.

The parse is guarded against passing vacuously. ``resources.ts`` asserts at module load
that ``RESOURCES`` and ``RESOURCE_KEYS`` are the same set;
:func:`test_the_console_s_two_declarations_of_its_own_key_set_agree` re-runs that assertion
in Python over two INDEPENDENT regexes — one over the ``declare(...)`` calls, one over the
``RESOURCE_KEYS`` array — so a regex that silently stops matching produces a red here
rather than an empty parametrisation that certifies nothing.

WHY "A PAYLOAD RATHER THAN A NOT-FOUND", AND NOT SOMETHING STRONGER
--------------------------------------------------------------------
``test_reads.py`` already validates all twelve payloads against the contracts the console
loads. This file asserts the one thing that test cannot: that the SUBJECT IS THERE AT ALL.
The distinction matters because ``test_reads.py`` reaches its subjects through a
hand-written map of the twelve keys, so a resource the console adds tomorrow is simply
absent from it and nothing goes red. Here the keys come from the console, so a thirteenth
resource is a thirteenth case the day it is declared, and it is red until the seed carries
it.

HOW EACH READ IS ADDRESSED, WITHOUT A HAND-MAINTAINED PARAMETER TABLE
---------------------------------------------------------------------
Path parameters are taken from the template the console declares — ``{cr_id}`` out of
``/v1/change-requests/{cr_id}`` — and their VALUES come from the ``seed`` fixture, which
read every one of them back out of the seeded database with a query. When the seed carries
no value of that name the request is addressed with :data:`_ABSENT` instead, a syntactically
valid UUID chosen so that no row can carry it, and the assertion is unchanged: the resource
must still answer with a payload.

That single rule is what makes this file free of exclusions:

* a resource whose subject the seed carries is driven at the seeded subject and answers;
* a resource whose subject the seed has LOST is driven at ``_ABSENT``, finds nothing, and
  raises ``NotFound`` — which is the red this file exists to produce;
* ``propagation`` — declared by the console, ``owner: 'datamodel'``, and STAGED IN FULL
  because ``mainline.lesson``, ``mainline.propagation`` and ``mainline.merge_conflict`` are
  produced by no migration in this repository (``reads.py:2015-2073``) — answers a payload
  for any UUID, and stays green without being named in an exemption list. If those tables
  are ever created, ``read_propagation`` raises ``Unrepresentable`` and this file goes red
  demanding the seed, which is the correct behaviour and not a special case.

A third failure mode turned up the first time this file was run, and it is kept rather than
narrowed away: ``silence`` answers neither a payload nor a ``NotFound`` but
``Unrepresentable``, because ``demo_permit.sql:161-171`` seeds a ``boundary_proof`` carrying
``synthetic`` and ``source`` where ``silence.schema.json`` declares only ``leaf_s`` and
``leaf_s_plus_1``, and ``read_silence`` refuses to render what the contract cannot express.
The subject is there; its CONTENT is what the committed schema refuses. That is still a
console link answering with an error rather than a page, so it is still this file's
business, and the assertion was left exactly where it was rather than narrowed to
``NotFound`` to obtain a green. The measurement and the referral are in
``docs/diagnosis/demo-suite-falsification.md`` §5.

**NO GET KEY IS EXCLUDED FROM THIS FILE.** If a future reader is tempted to exclude one
so that the suite goes green, that exclusion IS the defect: the console is telling a judge
the resource exists. Seed it, or delete it from ``resources.ts``.

THE NON-READS ARE NAMED, NOT FILTERED AWAY
------------------------------------------
:func:`_get_keys` drops the POST keys, because "drive the read and require a payload" is
not a sentence about an invocation. That filter is a mechanism, and a mechanism that
silently drops a key is exactly how ``change_request`` came to ship declared-but-unseeded.
So the keys it drops are also written down, by name, in :data:`_NOT_A_READ`, and
:func:`test_every_declared_key_is_either_driven_here_or_named_as_not_a_read` asserts the
two agree exactly.

**2026-08-16 added one key to each side, and the split is the whole discipline.**
``cr_gate_run`` is a POST and joins :data:`_NOT_A_READ`; ``cr_blocking_checks`` is a GET
and joins nothing — it is picked up by :func:`_get_keys` with no edit to this file and
driven at the seeded ``cr_id`` like every other read. Two keys landing together is exactly
the moment a reader is tempted to excuse both, so the second one's non-exemption is
asserted by name rather than left to the filter.

``demo_gate_run`` is the newest member and was measured before it was admitted. The
console declared it on 2026-08-14 as the seventeenth resource; this file was run against
that tree and **did not go red**, because the ``method`` filter had already dropped it
before any assertion looked at it. A silent pass is not a decision, so the decision is
written here instead: ``demo_gate_run`` is a POST, it takes no path parameter — the
subject is the seeded demo permit resolved server-side, so a stranger holding the public
URL cannot point the driver at somebody else's row — and it mutates nothing, because the
transaction is rolled back. There is no subject for ``_request`` to address and no
payload for ``reads.read_resource`` to return, so the ``_ABSENT`` machinery above does not
apply to it. What the seed owes it is asserted where it can be: the four beats are driven
end to end against the seeded world in ``tests/test_gate_run.py``.

Naming them is what keeps this an exemption rather than a hole. A further key that stopped
being driven would have to be added to :data:`_NOT_A_READ` by somebody who typed its name;
widening the predicate instead would excuse it, and every one after it, in silence.

Every test here needs a cluster and skips with the reason there is none.
"""

from __future__ import annotations

import re
from typing import Any, Final

import psycopg
import pytest
from mainline_demo_api import reads

from conftest import RESOURCES_TS

pytestmark = pytest.mark.requires_cluster

#: A syntactically valid UUID used to address a resource whose subject the seed does not
#: name. It is deliberately outside the ``dec0de00-…`` family ``demo_world.sql`` uses and is
#: not written in any seed file — ``grep`` for it under ``db/seeds/`` finds nothing — so a
#: read addressed at it can only answer from a row that was never seeded. It is NOT a
#: fixture value: nothing asserts it, and its only job is to make "the seed does not carry
#: this subject" arrive as a ``NotFound`` naming the resource.
_ABSENT: Final = "9f9f9f9f-0000-4000-8000-9f9f9f9f9f9f"

#: The ``declare(...)`` calls, for key, method and path template. Four positional arguments
#: is as far as this goes on purpose: the fifth is a schema id and the sixth is multi-line
#: prose full of commas and apostrophes, and a regex that survived those would be harder to
#: trust than the thing it checks.
_DECLARE: Final = re.compile(
    r"declare\(\s*'(?P<key>[a-z_]+)',\s*'(?P<method>GET|POST)',\s*'(?P<template>[^']+)'",
)

#: ``export const RESOURCE_KEYS = [ … ] as const;`` — the list the console's own router
#: iterates, read as a block and then as names, so a malformed block is a parse failure
#: rather than a short list.
_KEYS_BLOCK: Final = re.compile(
    r"export const RESOURCE_KEYS\s*=\s*\[(?P<body>[^\]]*)\]\s*as const;", re.DOTALL
)
_QUOTED_NAME: Final = re.compile(r"'([a-z_]+)'")

#: ``{param}`` in a path template, in template order — the console's own ``templateParams``.
_TEMPLATE_PARAM: Final = re.compile(r"\{([a-z_]+)\}")

#: The declared keys this file does NOT drive, written out by name with the reason each
#: one is not a read. See the module docstring: the ``method`` filter in :func:`_get_keys`
#: is the mechanism, this set is the DECISION, and
#: :func:`test_every_declared_key_is_either_driven_here_or_named_as_not_a_read` refuses to
#: let the two disagree. A key that leaves this file has to be typed here by somebody.
_NOT_A_READ: Final = {
    # The four kernel transitions. Each invokes a `trappoint.*` procedure against a
    # subject the caller names, governed by `invoke.schema.json`, and is exercised against
    # the seeded world by `tests/test_transitions.py`.
    "materialise_checks",
    "sign_disposition",
    "merge_permit",
    "suspend_permit",
    # The demo driver, declared by the console on 2026-08-14. A POST with NO path
    # parameter — the subject is the seeded demo permit, resolved server-side — governed
    # by `gate-run.schema.json`, performing four beats in one SERIALIZABLE transaction
    # that is rolled back. Nothing here can address it and nothing here can read it back;
    # `tests/test_gate_run.py` drives it against the seeded world instead.
    "demo_gate_run",
    # The CHANGE REQUEST's gate run, declared 2026-08-16, and it is excused on exactly the
    # same terms as the row above rather than on new ones: a POST with NO path parameter,
    # governed by `cr-gate-run.schema.json`, beats inside one SERIALIZABLE transaction
    # that is rolled back. `test_every_declared_key_is_either_driven_here_or_named_as_not_a_read`
    # re-checks the stated reason instead of trusting it — the console must declare it a
    # POST — and its template is asserted parameter-free below for the same reason
    # `demo_gate_run`'s is, with one extra edge that is specific to this subject:
    # `transitions._demo_guard` compares `subject_id` to `scenario.permit_id`, so a
    # `{cr_id}` on a mutating route would be waved through. The parameter-free assertion
    # below is therefore load-bearing here in a way it is not for the permit.
    #
    # NOTE the read that arrived in the same wave is NOT excused and must not be:
    # `cr_blocking_checks` is a GET, the console declares it, `_get_keys()` picks it up
    # with no edit to this file, and it is driven at the seeded `cr_id` like every other
    # read. If it ever appears in this set, the change request has stopped being seeded.
    "cr_gate_run",
}


def _console_source() -> str:
    if not RESOURCES_TS.is_file():
        pytest.skip(
            f"{RESOURCES_TS} is absent, so the console's declaration of which resources "
            "exist cannot be read, and this file has nothing to compare the seed against."
        )
    return RESOURCES_TS.read_text(encoding="utf-8")


def _resource_keys() -> tuple[str, ...]:
    """``RESOURCE_KEYS``, parsed. Never restated — see this module's docstring."""
    text = _console_source()
    block = _KEYS_BLOCK.search(text)
    assert block is not None, (
        f"{RESOURCES_TS} no longer contains a parsable `export const RESOURCE_KEYS = [ … ] "
        "as const;`. That list is what this file asserts the demo seed satisfies, so a "
        "parse failure is a hard red and not a skip: a silently empty list would make every "
        "case below pass without driving anything."
    )
    return tuple(_QUOTED_NAME.findall(block.group("body")))


def _declarations() -> dict[str, dict[str, str]]:
    """key → {method, template}, from the ``declare(...)`` calls."""
    return {match.group("key"): match.groupdict() for match in _DECLARE.finditer(_console_source())}


def _get_keys() -> tuple[str, ...]:
    """The resources a judge can READ, in the console's own declared order.

    ``method`` is the console's, not a judgement made here: four of the six POST entries
    are invocations of ``trappoint.*`` functions and the other two are the permit's and the
    change request's demo drivers, and "drive the read and require a payload" is not a
    sentence about any of them. All six are also written out by name in
    :data:`_NOT_A_READ`, because this filter is silent and a silent filter is how a
    resource disappears — see
    :func:`test_every_declared_key_is_either_driven_here_or_named_as_not_a_read`.
    Filtering on a field the console declares is not an exclusion list — a further GET
    adds a case here with no edit to this file, which is exactly how
    ``cr_blocking_checks`` arrived on 2026-08-16.
    """
    declared = _declarations()
    return tuple(key for key in _resource_keys() if declared[key]["method"] == "GET")


def _request(key: str, seed: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Address *key* at the seeded subject, or at :data:`_ABSENT` when the seed has none."""
    template = _declarations()[key]["template"]
    # ``seed.get`` and not ``seed[name]``: ``_Seed.__missing__`` raises a paragraph-long
    # KeyError by design, and here an absent name is not an error — it is the case this
    # file exists to drive, at :data:`_ABSENT`, so that the READ is what refuses.
    params = {name: seed.get(name, _ABSENT) for name in _TEMPLATE_PARAM.findall(template)}
    return params, {}


# ── The parse, guarded ──────────────────────────────────────────────────────────────


def test_the_console_s_two_declarations_of_its_own_key_set_agree() -> None:
    """``resources.ts``'s own module-load assertion, re-run over two independent parses.

    Everything below is parametrised by :func:`_get_keys`, so a regex that stops matching
    would silently produce zero cases and a green board. Two regexes over two different
    syntaxes — the ``declare(...)`` calls and the ``RESOURCE_KEYS`` array — cannot both fail
    to the same wrong answer, and the console itself throws at module load when they
    disagree. This is that throw, in Python, where pytest can see it.
    """
    keys = _resource_keys()
    declared = _declarations()

    assert keys, f"no keys parsed out of RESOURCE_KEYS in {RESOURCES_TS}"
    assert declared, f"no declare(...) calls parsed out of {RESOURCES_TS}"
    assert sorted(keys) == sorted(declared), (
        f"{RESOURCES_TS} declares one set of resources and lists another. The console "
        "throws on this at module load; this assertion is that throw, reached from the "
        f"suite. RESOURCE_KEYS: {sorted(keys)}. declare(...): {sorted(declared)}."
    )
    assert len(set(keys)) == len(keys), f"RESOURCE_KEYS repeats a key: {keys}"
    assert _get_keys(), "the console declares no GET resource, which cannot be right"


def test_every_declared_key_is_either_driven_here_or_named_as_not_a_read() -> None:
    """No declared key may fall out of this file silently. It is driven, or it is named.

    :func:`_get_keys` filters on the ``method`` the console itself declares, which is not
    an exclusion list — but it IS a mechanism that removes keys without saying so, and
    this file exists because a resource disappearing quietly is the defect. Measured
    2026-08-14: the console's seventeenth ``declare()``, ``demo_gate_run``, was added and
    every assertion in this file stayed green, because the filter had dropped it before
    anything looked at it. That silence is what this test converts into a name.

    Both directions are asserted. A key added to :data:`_NOT_A_READ` that the console no
    longer declares fails here too, so the set cannot quietly accumulate excuses for
    resources that stopped existing.
    """
    declared = _declarations()
    driven = set(_get_keys())
    dropped = set(_resource_keys()) - driven

    assert dropped == _NOT_A_READ, (
        "the set of declared resources this file does not drive has changed. It is written "
        "out by name on purpose: widening the filter would excuse this key and every future "
        f"one in silence. Not driven now: {sorted(dropped)}. Named in _NOT_A_READ: "
        f"{sorted(_NOT_A_READ)}. Add the name and the reason, or seed the resource."
    )
    assert driven & _NOT_A_READ == set(), sorted(driven & _NOT_A_READ)

    # The stated reason, checked rather than trusted: each excused key is excused because
    # the CONSOLE declares it a POST, not because this file finds it inconvenient.
    for key in sorted(_NOT_A_READ):
        assert key in declared, f"{key} is named in _NOT_A_READ and the console does not declare it"
        assert declared[key]["method"] == "POST", (
            f"{key} is excused from this file as 'not a read' and the console declares it "
            f"{declared[key]['method']}. A GET must be driven against the seed."
        )

    # And the two demo drivers' own reason, by name, because theirs are the exemptions
    # that were decided rather than inherited: no path parameter means there is no subject
    # for `_request` to address, seeded or _ABSENT.
    for driver in ("demo_gate_run", "cr_gate_run"):
        assert driver in _NOT_A_READ
        assert _TEMPLATE_PARAM.findall(declared[driver]["template"]) == [], (
            f"{driver} has acquired a path parameter. Its exemption here rests on the "
            "subject being the seeded demo subject resolved server-side; a caller-supplied "
            "subject is a different resource and needs its own decision. For cr_gate_run "
            "that is more than a contract point: transitions._demo_guard compares "
            "subject_id to scenario.permit_id, so a {cr_id} on a mutating route would be "
            "waved through on a Function URL with authorization_type = NONE."
        )

    # The read that landed in the same wave as cr_gate_run is NOT excused, and saying so
    # by name is what stops the pair being excused together by somebody reading quickly.
    assert "cr_blocking_checks" not in _NOT_A_READ, (
        "GET /v1/change-requests/{cr_id}/blocking-checks is a READ the console declares. "
        "It is driven at the seeded change request like every other read; excusing it "
        "would restore exactly the silence that let change_request ship declared-but-"
        "unseeded."
    )
    assert declared["cr_blocking_checks"]["method"] == "GET"


def test_every_console_read_has_an_implementation_in_this_api() -> None:
    """The reader table and the console's GET set are the same set, in both directions.

    A resource the console declares and this API cannot serve is a link to a 404. A reader
    this API ships for a resource the console never declares is dead code that no judge can
    reach — and, worse, a resource somebody deleted from the console without noticing the
    backend still answers it.
    """
    assert sorted(_get_keys()) == sorted(reads.READS), (
        "the console's GET resources and reads.READS have diverged. The console is the "
        f"authority for which resources exist. Console: {sorted(_get_keys())}. "
        f"reads.READS: {sorted(reads.READS)}."
    )


# ── The seed, driven ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def console_reads(
    demo_database: tuple[str, dict[str, str]],
) -> dict[str, tuple[dict[str, Any] | None, BaseException | None]]:
    """Every GET the console declares, performed once against the seeded world.

    Session-scoped for the same reason ``test_reads.py::payloads`` is: these are reads, and
    performing them per test would assert nothing a single run does not. Each read's
    exception is CAUGHT and stored against its key rather than raised here, so a resource
    the seed has lost fails one case naming that resource instead of erroring every case in
    the file on setup — which is precisely how the ``cr_id`` gap presented, and it cost a
    reader an hour to attribute.
    """
    from mainline_demo_api import db as demo_db

    dsn, seed = demo_database
    out: dict[str, tuple[dict[str, Any] | None, BaseException | None]] = {}
    demo_db.reset_dsn_cache()
    conn: psycopg.Connection[Any] = demo_db.connection(dsn=dsn)
    try:
        for key in _get_keys():
            params, query = _request(key, seed)
            try:
                out[key] = (reads.read_resource(conn, key, params, query), None)
            except BaseException as exc:  # noqa: BLE001 - stored, then re-stated per key
                out[key] = (None, exc)
    finally:
        demo_db.reset_dsn_cache()
    return out


@pytest.mark.parametrize("key", _get_keys())
def test_the_demo_seed_carries_every_resource_the_console_declares(
    key: str,
    seed: dict[str, str],
    console_reads: dict[str, tuple[dict[str, Any] | None, BaseException | None]],
) -> None:
    """*key* is navigable in the deployed demo: it answers with a payload, not a not-found.

    THE ASSERTION IS ABOUT THE SEED, NOT ABOUT THE READER. ``reads.py`` is exercised
    against its contracts in ``test_reads.py``; what is being asserted here is that the two
    files ``scripts/deploy/seed_demo.py`` puts into CockroachDB Cloud contain a subject for
    every resource ``resources.ts`` tells a judge exists. A ``NotFound`` here is the demo
    shipping a link to a 404.
    """
    payload, error = console_reads[key]
    params, _query = _request(key, seed)
    addressed = {name: value for name, value in params.items() if value == _ABSENT}
    not_found = isinstance(error, reads.NotFound)
    unrepresentable = isinstance(error, reads.Unrepresentable)

    if not_found:
        raise AssertionError(
            f"the console declares resource {key!r} and the deployed demo seed does not "
            f"carry it: GET {_declarations()[key]['template']} answered NotFound — "
            f"{error}. "
            + (
                f"It was addressed at {sorted(addressed)} = _ABSENT because the seed names "
                "no such identifier, so this is a MISSING SUBJECT rather than a wrong "
                "lookup. "
                if addressed
                else "It was addressed at the seeded identifiers, so the subject the seed "
                "names is not reachable through the reader. "
            )
            + "Seed it in verticals/mainline/db/seeds/demo/demo_world.sql so the DEPLOYED "
            "demo carries it too — the ruling and the precedent are "
            "docs/leads/demo-suite-plan.md §1.1 and docs/decisions/demo-change-request.md — "
            "or delete the resource from apps/console/src/data/resources.ts. Do NOT exclude "
            "the key from this test: the console is what tells a judge the resource exists, "
            "and an exclusion here would restore exactly the silence that let "
            "change_request ship declared-but-unseeded."
        )
    if unrepresentable:
        raise AssertionError(
            f"the console declares resource {key!r} and the deployed demo seed carries a row "
            f"the committed contract cannot express, so the reader REFUSES to render it: "
            f"{error} — GET {_declarations()[key]['template']} is a link in the console that "
            "answers with an error rather than a page. The subject exists; its CONTENT is "
            "what the schema refuses. The authority is the committed schema under "
            "verticals/mainline/apps/console/contracts/, never the reader's convenience and "
            "never this assertion: fix the seeded row in "
            "verticals/mainline/db/seeds/demo/, or change the contract deliberately and say "
            "why. Do NOT widen the reader to drop the undeclared keys — dropping them is how "
            "a payload comes to say something the database did not."
        ) from error
    if error is not None:
        raise AssertionError(
            f"resource {key!r} is declared by the console and did not answer: "
            f"{type(error).__name__}: {error}"
        ) from error

    assert isinstance(payload, dict) and payload, (
        f"resource {key!r} answered {payload!r}. The console renders this resource, so an "
        "empty answer is a blank page with no error on it."
    )
