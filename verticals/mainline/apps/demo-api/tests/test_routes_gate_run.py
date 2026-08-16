# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``POST /v1/demo/gate-run`` is addressable, and cannot silently stop being.

WHAT THIS FILE EXISTS TO PREVENT COMING BACK
--------------------------------------------
The demo's headline beat was implemented end to end and unreachable over HTTP.
``transitions.TRANSITION_RESOURCES`` declared ``demo_gate_run``,
``transitions.handle_transition`` dispatched it, and ``gate_run.gate_run`` performed all
four beats inside one transaction with a SAVEPOINT per beat — but ``app._routes()``
returned sixteen rows, none of which was this endpoint, so the router answered 404 before
the dispatcher was ever consulted. ``evidence/deploy/acceptance.json`` recorded it as::

    POST /v1/demo/gate-run (run 1) returned 404, expected 200
    POST /v1/demo/gate-run (run 2) returned 404, expected 200

and ``console/src/features/gate/DemoDriver.tsx`` put *"POST /v1/demo/gate-run is not
addressable from this console"* on screen. That panel still exists — it is
``DeclarationGapPanel``, and it is the honest rendering if the declaration is ever removed
— but with the console's own registry it is now unreachable rather than what a judge sees.

A route table and a dispatcher table are two lists that must agree and nothing in the
language makes them. So the tests here are written as an agreement check in three
directions rather than as one happy-path assertion:

1. the ROUTER resolves the path to the key,
2. the DISPATCHER declares that key,
3. and this API's table and the console's declaration are the SAME SET — so a route
   nobody declared, and a declaration nobody routed, are both failures here.

THE SECOND GAP THIS FILE WAS WRITTEN AGAINST, AND THE DAY IT CLOSED
-------------------------------------------------------------------
Until **2026-08-14** ``console/src/data/resources.ts`` carried sixteen ``declare()``
calls and ``contracts.ts`` did not register ``gate-run.schema.json``, so the endpoint was
routable by ``curl`` and unreachable from the artefact a judge actually drives:
``DemoDriver.tsx`` rendered *"POST /v1/demo/gate-run is not addressable from this
console"* and refused — correctly — to reach it with a bare ``fetch``, because that would
skip envelope and contract validation and have no REPLAY counterpart. Direction 3 above
recorded that gap as a *pinned exception*: ``routed - declared == {DEMO_ROUTE}``, an
exact set rather than a subset, so that a SECOND undeclared route was still a failure.

On 2026-08-14 the console declared the seventeenth resource, ``contracts.ts`` registered
the schema, and ``envelope.SCHEMA_IDS`` gained the matching entry. The exception had
nothing left to except, so it was **collapsed rather than raised**: this file now pins

    ``declared == routed``, both **seventeen**

which is strictly stronger than the assertion it replaces. "Differs by exactly one row I
have named" admits one undeclared route; "is the same set" admits none. The count moved
up and the tolerance moved to zero in the same edit — raising ``_CONSOLE_ROUTE_COUNT``
alone would have kept a hole open with a bigger number in it, and that is not what
happened here.

The history is kept rather than deleted because it is the whole value of the file: a gap
that was real, was visible, and is now shut is evidence the process works, and a reader
who does not know which defect an assertion prevents will eventually weaken it. Both
halves of the original defect are still falsifiable from here — delete the route and
direction 1 fails; delete the ``declare()`` and direction 3 fails naming the row.

THE EIGHTEENTH ROUTE, 2026-08-15, AND WHY IT OPENS NO GAP
---------------------------------------------------------
``GET /v1/demo/subjects`` — :mod:`mainline_demo_api.subjects` — was added because the
console had no way to ASK which subjects a database carries, and so shipped identifiers in
its own source (``BLK-07``, a clause and a commit) that the deployed kernel answers 404
for. It landed on **both** sides in the same wave: ``resources.ts`` declares it,
``envelope.SCHEMA_IDS`` names its contract, ``reads.READS`` implements it, and
``app.ROUTES`` routes it.

So the counts below moved from 17 to 18 and the tolerance did **not** move: direction 3 is
still plain set equality with no permitted exception. Raising a count and loosening the
comparison in the same edit is how a gap gets a bigger number in front of it; only the
count moved here, and the two counts are still written twice so that they have to agree.

THE NINETEENTH AND TWENTIETH ROUTES, 2026-08-16 — THE SECOND GATED SUBJECT
--------------------------------------------------------------------------
Until this wave the API served exactly ONE change-request route,
``GET /v1/change-requests/{cr_id}``. Measured against the live origin this session, it
answered ``200`` with ``state: checks_materialised`` and ``open_blocking: 1`` — a counter
saying one obligation was open — while ``/v1/change-requests/{cr_id}/blocking-checks``
answered ``404`` and ``POST /v1/change-requests/{cr_id}/merge`` did not exist. So the
kernel's second gate had **no HTTP path at all**: nothing could list what the counter was
counting, and nothing could attempt the merge and be refused. That is the first defect in
this file's history, one subject over, and it is why the two rows below landed together:

* ``GET /v1/change-requests/{cr_id}/blocking-checks`` → ``cr_blocking_checks``, an
  ordinary read in every table that names a read, under the EXISTING
  ``blocking-check.schema.json`` — that contract's ``data`` requires ``subject_kind`` and
  ``subject_id`` and carries no ``permit_id``, so it was authored for both subjects;
* ``POST /v1/demo/cr-gate-run`` → ``cr_gate_run``, the change request's gate run, with
  **no path parameter**, dispatched through the ``param_name is None`` branch.

**WHY THAT SECOND ROW MAY NEVER GROW A ``{cr_id}``**, asserted below in
:func:`test_no_mutating_route_carries_a_change_request_path_parameter`:
``transitions._demo_guard`` decides on ``subject_id == scenario.permit_id``. A
change-request identifier never equals the permit's, so a mutating CR route would fall
past the ``demo_subject_write_protected`` branch, find the permit **is** seeded, and be
let through — an unguarded, irreversible, unauthenticated write on the seeded demo change
request, on an origin whose ``authorization_type`` is ``NONE``. The guard would not catch
it. That is not a hypothesis about the future; it is the shape of the defect
``evidence/deploy/demo-guard-armed.json`` already recorded, and the route table is where
it is cheapest to make impossible.

The counts moved 18 → **20** and the tolerance did not move, for the third time.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from mainline_demo_api import app
from mainline_demo_api import db as demo_db

from conftest import RESOURCES_TS

#: The demo driver's endpoint. Declared by the console since 2026-08-14; before that it
#: was the one route this API served that the console's resource registry did not.
DEMO_ROUTE: tuple[str, str] = ("POST", "/v1/demo/gate-run")

#: The dispatcher key ``transitions.handle_transition`` branches on.
DEMO_KEY = "demo_gate_run"

#: The demo's read-only subject index, added 2026-08-15 on both sides at once. Named here
#: rather than counted, for the same reason ``DEMO_ROUTE`` is: an equality between two
#: eighteen-member sets says nothing about WHICH eighteen.
SUBJECTS_ROUTE: tuple[str, str] = ("GET", "/v1/demo/subjects")
SUBJECTS_KEY = "demo_subjects"

#: The change request's obligations, added 2026-08-16 — the read that lists what the CR's
#: ``open_blocking`` counter counts. Named for the same reason the two above are.
CR_CHECKS_ROUTE: tuple[str, str] = ("GET", "/v1/change-requests/{cr_id}/blocking-checks")
CR_CHECKS_KEY = "cr_blocking_checks"

#: The change request's gate run. **No path parameter, and that is a safety property** —
#: see this module's docstring and
#: :func:`test_no_mutating_route_carries_a_change_request_path_parameter`.
CR_DEMO_ROUTE: tuple[str, str] = ("POST", "/v1/demo/cr-gate-run")
CR_DEMO_KEY = "cr_gate_run"

#: One number, written twice, because the two tables it counts are maintained by two
#: different people in two different languages. They must be equal; that they are equal
#: is the assertion, and a single shared constant would have made it unfalsifiable.
#: 17 until 2026-08-15, 18 with ``demo_subjects``, 20 since 2026-08-16.
_EXPECTED_ROUTE_COUNT = 20
_CONSOLE_ROUTE_COUNT = 20

#: **ROWS ARE NOT PATHS.** ``/v1/checks/{check_id}/disposition`` is declared twice — ``GET
#: disposition`` reads it, ``POST sign_disposition`` signs it — so twenty rows address
#: nineteen distinct templates, and the 404 body (which is
#: ``sorted({r.template for r in ROUTES})``) lists nineteen. Written down here because a
#: reader who counted the 404 body and found nineteen would "fix" a count that is right.
_EXPECTED_PATH_COUNT = 19

#: The one template two rows share, by name, so the discrepancy above has a witness rather
#: than an explanation.
_TWICE_DECLARED_PATH = "/v1/checks/{check_id}/disposition"


def _event(method: str, path: str, body: str | None = None) -> dict[str, Any]:
    """A Lambda Function URL payload-format-2.0 event, the shape AWS actually sends."""
    event: dict[str, Any] = {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"stage": "$default", "http": {"method": method, "path": path}},
    }
    if body is not None:
        event["body"] = body
    return event


# ── 1 · the router ──────────────────────────────────────────────────────────────────


def test_the_demo_route_resolves_to_the_dispatcher_key() -> None:
    """The whole defect, in one assertion."""
    matched, _params, other = app.route(*DEMO_ROUTE)
    assert matched is not None, (
        "POST /v1/demo/gate-run routed nowhere: app._routes() does not carry it and the "
        "four beats in gate_run.py are unreachable over HTTP"
    )
    assert matched.key == DEMO_KEY
    assert matched.template == DEMO_ROUTE[1]
    assert other is False


def test_the_demo_route_takes_no_path_parameters() -> None:
    """The subject is the seeded demo permit, resolved by ``scenario.from_env()``.

    A judge must not be able to point the demo driver at somebody else's row, so the
    template carries no ``{param}`` and the router must hand the dispatcher an empty map.
    """
    matched, params, _ = app.route("POST", DEMO_ROUTE[1])
    assert matched is not None
    assert params == {}


def test_get_on_the_demo_route_is_405_naming_post_and_not_404() -> None:
    """405-vs-404 is load-bearing: a 404 says "never built", a 405 says "wrong verb"."""
    matched, _, other = app.route("GET", DEMO_ROUTE[1])
    assert matched is None
    assert other is True

    response = app.handler(_event("GET", DEMO_ROUTE[1]))
    assert response["statusCode"] == 405
    body = json.loads(response["body"])
    assert body["error"]["kind"] == "method_not_allowed"
    assert body["error"]["allow"] == ["POST"]


def test_a_trailing_slash_is_not_the_demo_route() -> None:
    """The template is exact. A near miss must be a 404, not a silent second spelling."""
    matched, _, other = app.route("POST", f"{DEMO_ROUTE[1]}/")
    assert matched is None
    assert other is False


def test_the_404_body_now_lists_the_demo_template() -> None:
    """The declared list is how a caller discovers the endpoint from a wrong URL."""
    response = app.handler(_event("GET", "/v1/nope"))
    assert response["statusCode"] == 404
    assert DEMO_ROUTE[1] in json.loads(response["body"])["error"]["declared"]


# ── 1b · the two rows added 2026-08-16, in the same three directions ────────────────


def test_the_cr_blocking_checks_route_resolves_to_its_key_and_takes_the_cr_id() -> None:
    """The read that lists what the change request's ``open_blocking`` counter counts.

    It takes a path parameter and the demo endpoints do not, and the difference is not an
    inconsistency: this is a GET, it mutates nothing, and refusing to let a caller name
    the subject of a READ would make it unaddressable rather than safe.
    """
    matched, params, other = app.route(
        "GET", "/v1/change-requests/dec0de00-000c-4000-8000-000000000001/blocking-checks"
    )
    assert matched is not None, (
        "GET /v1/change-requests/{cr_id}/blocking-checks routed nowhere: the CR's "
        "open_blocking counter says an obligation is open and nothing can list it, which "
        "is the live 404 operator/change/ChangeScreen.ts renders as evidence today"
    )
    assert matched.key == CR_CHECKS_KEY
    assert matched.template == CR_CHECKS_ROUTE[1]
    assert params == {"cr_id": "dec0de00-000c-4000-8000-000000000001"}
    assert other is False


def test_the_cr_demo_route_resolves_to_its_dispatcher_key_and_takes_no_parameters() -> None:
    """``POST /v1/demo/cr-gate-run``, and the empty parameter map is the safety property."""
    matched, params, other = app.route(*CR_DEMO_ROUTE)
    assert matched is not None, (
        "POST /v1/demo/cr-gate-run routed nowhere, so the change request's gate run is "
        "unreachable over HTTP — the same defect this file was opened for, one subject over"
    )
    assert matched.key == CR_DEMO_KEY
    assert matched.template == CR_DEMO_ROUTE[1]
    assert params == {}
    assert other is False


def test_get_on_the_cr_demo_route_is_405_naming_post_and_not_404() -> None:
    """405-vs-404 again: a 404 says "never built", a 405 says "wrong verb"."""
    matched, _, other = app.route("GET", CR_DEMO_ROUTE[1])
    assert matched is None
    assert other is True

    response = app.handler(_event("GET", CR_DEMO_ROUTE[1]))
    assert response["statusCode"] == 405
    body = json.loads(response["body"])
    assert body["error"]["kind"] == "method_not_allowed"
    assert body["error"]["allow"] == ["POST"]


def test_a_trailing_slash_is_not_either_new_route() -> None:
    """The templates are exact. A near miss is a 404, never a silent second spelling.

    ``other`` must be ``False`` as well as ``matched`` being ``None``: a trailing slash
    that produced a 405 would tell a caller the path exists under another verb, which is a
    different and false claim about the surface.
    """
    for method, template in (CR_DEMO_ROUTE, CR_CHECKS_ROUTE):
        path = template.replace("{cr_id}", "dec0de00-000c-4000-8000-000000000001")
        matched, _, other = app.route(method, f"{path}/")
        assert matched is None, f"{method} {path}/ resolved to {matched}"
        assert other is False, f"{method} {path}/ was reported as a wrong-verb hit"


def test_the_404_body_now_lists_both_new_templates() -> None:
    """The declared list is how a caller discovers an endpoint from a wrong URL.

    It is ``sorted({r.template for r in ROUTES})``, so it dedupes the twice-declared
    disposition path and carries NINETEEN entries for twenty rows. Both facts are asserted
    here so that neither is discovered by somebody counting the wrong list.
    """
    response = app.handler(_event("GET", "/v1/nope"))
    assert response["statusCode"] == 404
    declared = json.loads(response["body"])["error"]["declared"]
    assert CR_CHECKS_ROUTE[1] in declared, declared
    assert CR_DEMO_ROUTE[1] in declared, declared
    assert len(declared) == _EXPECTED_PATH_COUNT == len({r.template for r in app.ROUTES})
    assert len(declared) < _EXPECTED_ROUTE_COUNT, (
        "the 404 body dedupes by template, so it must be SHORTER than the row count; if "
        "these are equal then the twice-declared disposition path has lost one of its rows"
    )


# ── 2 · the dispatcher ──────────────────────────────────────────────────────────────


def test_the_route_key_is_a_declared_transition_resource() -> None:
    """The route and the dispatcher cannot drift apart without this failing."""
    from mainline_demo_api import transitions

    assert DEMO_KEY in transitions.TRANSITION_RESOURCES, (
        f"{DEMO_KEY} is routed but handle_transition would answer 404 unknown_resource"
    )
    # (path parameter, procedure name, mutates the subject). The demo driver has no path
    # parameter, names no single server-side procedure — it performs four beats — and
    # does not mutate: the transaction is rolled back.
    assert transitions.TRANSITION_RESOURCES[DEMO_KEY] == (None, None, False)


def test_the_cr_route_key_is_a_declared_transition_resource() -> None:
    """``cr_gate_run`` must be declared with the SAME shape as ``demo_gate_run``.

    ``(None, None, False)`` is not cosmetic. ``handle_transition`` branches on
    ``param_name is None``, and that branch is what keeps ``transitions._demo_guard`` out
    of the path entirely — which is correct here because there is nothing to guard: the
    transaction is rolled back. A non-``None`` parameter name on this key would route a
    caller-supplied subject into the guard, and the guard compares to the PERMIT id.
    """
    from mainline_demo_api import transitions

    assert CR_DEMO_KEY in transitions.TRANSITION_RESOURCES, (
        f"{CR_DEMO_KEY} is routed but handle_transition would answer 404 unknown_resource"
    )
    assert transitions.TRANSITION_RESOURCES[CR_DEMO_KEY] == (None, None, False)


def test_no_mutating_route_carries_a_change_request_path_parameter() -> None:
    """THE HAZARD THIS TABLE IS THE CHEAPEST PLACE TO MAKE IMPOSSIBLE.

    ``transitions._demo_guard`` decides on ``subject_id == scenario.permit_id``. A
    change-request identifier never equals the permit's, so a POST route carrying
    ``{cr_id}`` would fall PAST the ``demo_subject_write_protected`` branch, reach
    ``_demo_subject_is_established``, find the permit **is** seeded, and return ``None`` —
    *let it through*. On a Function URL with ``authorization_type = NONE`` that is an
    unguarded, irreversible, unauthenticated write on the seeded demo change request.

    The assertion is written over the WHOLE table rather than against the one row that
    exists today, because the failure it prevents arrives as a NEW row somebody adds
    believing the guard covers it. It is also deliberately not an assertion about
    ``_demo_guard`` itself: widening that guard is a decision for the founder, and a test
    that anticipated the widening would be the argument being skipped rather than had.
    """
    from mainline_demo_api import transitions

    offending = sorted(
        (route.method, route.template, route.key)
        for route in app.ROUTES
        if route.method == "POST"
        and "{cr_id}" in route.template
        and transitions.TRANSITION_RESOURCES.get(route.key, (None, None, False))[2]
    )
    assert offending == [], (
        "a mutating route now carries a {cr_id} path parameter: "
        f"{offending}. transitions._demo_guard compares subject_id to scenario.permit_id, "
        "so it cannot refuse this and the write reaches the seeded demo change request "
        "from any caller on the internet. The demo endpoint takes NO path parameter for "
        "exactly this reason — see docs/demo/cr-gate-route-plan.md R7."
    )
    # Anti-vacuity: the predicate must be able to see a mutating key at all, or the empty
    # result above would be a property of the filter rather than of the table.
    assert any(flags[2] for flags in transitions.TRANSITION_RESOURCES.values()), (
        "no declared transition resource mutates, so the filter above can never fire"
    )


def test_every_routed_post_is_a_declared_transition_resource() -> None:
    """Generalises the check above: no POST may route to a key the dispatcher refuses."""
    from mainline_demo_api import transitions

    routed_posts = {r.key for r in app.ROUTES if r.method == "POST"}
    assert routed_posts <= set(transitions.TRANSITION_RESOURCES), sorted(
        routed_posts - set(transitions.TRANSITION_RESOURCES)
    )


def test_the_handler_dispatches_the_demo_route_instead_of_404ing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through :func:`app.handler`, with the database and W4 both stubbed.

    Stubbing both is what makes this a ROUTING test: it fails if and only if the router
    fails to deliver ``(demo_gate_run, {}, body)`` to ``handle_transition``, whatever the
    cluster is doing.
    """
    from mainline_demo_api import transitions

    seen: dict[str, Any] = {}

    def _fake_handle_transition(
        resource_key: str, path_params: dict[str, str], body: Any, conn: Any
    ) -> tuple[int, dict[str, Any]]:
        seen["key"] = resource_key
        seen["params"] = path_params
        seen["body"] = body
        seen["conn"] = conn
        return 200, {"ok": True}

    sentinel = object()
    monkeypatch.setattr(demo_db, "connection", lambda **_: sentinel)
    monkeypatch.setattr(transitions, "handle_transition", _fake_handle_transition)

    response = app.handler(_event("POST", DEMO_ROUTE[1], body='{"run_id":"probe"}'))

    assert response["statusCode"] == 200, response["body"]
    assert seen["key"] == DEMO_KEY
    assert seen["params"] == {}
    assert seen["body"] == {"run_id": "probe"}
    assert seen["conn"] is sentinel
    assert response["headers"]["cache-control"] == "no-store"


def test_the_demo_route_reaches_the_connection_step_when_no_dsn_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 503 here proves the router passed it on. Before the fix this was a flat 404."""

    def _no_dsn(**_: Any) -> Any:
        raise demo_db.DsnUnavailable("no dsn in this test")

    monkeypatch.setattr(demo_db, "connection", _no_dsn)
    response = app.handler(_event("POST", DEMO_ROUTE[1], body="{}"))
    assert response["statusCode"] == 503
    assert json.loads(response["body"])["error"]["kind"] == "dsn_unset"


# ── 3 · the table, against the console's declaration ────────────────────────────────

_DECLARE = re.compile(
    r"declare\(\s*'(?P<key>[a-z_]+)',\s*'(?P<method>GET|POST)',\s*'(?P<template>[^']+)'"
)


def _console_declared() -> set[tuple[str, str]]:
    if not RESOURCES_TS.is_file():
        pytest.skip(
            f"{RESOURCES_TS} is absent, so the API's table cannot be compared with the "
            "console's own declaration"
        )
    text = RESOURCES_TS.read_text(encoding="utf-8")
    return {(m.group("method"), m.group("template")) for m in _DECLARE.finditer(text)}


def test_the_table_and_the_console_declaration_are_the_same_twenty() -> None:
    """``declared == routed``, both twenty, with NO permitted exception.

    Until 2026-08-14 this pinned ``routed - declared == {DEMO_ROUTE}``: an exact set, so a
    second undeclared route failed, but one named row was still allowed through. The
    console declared that row on 2026-08-14, so the exception was collapsed to empty
    instead of the count being raised around it. On 2026-08-15 ``demo_subjects`` was added
    to both tables in one wave, so the count moved to eighteen and the tolerance stayed at
    zero. On 2026-08-16 the change request's two rows landed the same way and the count
    moved to twenty; **the tolerance has still never moved.** Equality of the two SETS is
    what is asserted — this is not weakened to ``routed <= declared`` or to a count, and a
    reader tempted to do so should note that a subset check is exactly what would have let
    ``POST /v1/demo/gate-run`` sit undeclared for three days in front of the founder.

    The two counts are asserted beside the set equality because a set cannot see a
    duplicate row in ``app.ROUTES`` and a shadowed duplicate is unreachable.

    It fails in both directions, which is the point. A route this API serves and the
    console does not declare is the 404-in-front-of-a-judge defect this file was opened
    for. A resource the console declares and this API does not route is the same defect
    with the arrow reversed — a link on a page that answers ``no_route``.
    """
    declared = _console_declared()
    routed = {(r.method, r.template) for r in app.ROUTES}

    assert len(declared) == _CONSOLE_ROUTE_COUNT, sorted(declared)
    assert len(app.ROUTES) == _EXPECTED_ROUTE_COUNT, sorted(r.template for r in app.ROUTES)
    assert routed - declared == set(), f"routed but not declared: {sorted(routed - declared)}"
    assert declared - routed == set(), f"declared but not routed: {sorted(declared - routed)}"
    assert declared == routed
    # Named, not merely counted: these are the rows the file exists for, and an equality
    # between two empty sets would satisfy every assertion above it.
    assert DEMO_ROUTE in declared, (
        f"{DEMO_ROUTE[0]} {DEMO_ROUTE[1]} is routed by this API and the console no longer "
        "declares it, so the demo driver is back to rendering the not-addressable panel"
    )
    assert DEMO_ROUTE in routed
    assert SUBJECTS_ROUTE in declared and SUBJECTS_ROUTE in routed, (
        "GET /v1/demo/subjects is missing from one of the two tables, so either the console "
        "cannot ask which subjects exist or it asks and gets no_route — and every screen is "
        "back to carrying its subject's identifier in its own source"
    )
    for route in (CR_CHECKS_ROUTE, CR_DEMO_ROUTE):
        assert route in declared and route in routed, (
            f"{route[0]} {route[1]} is missing from one of the two tables. The change "
            "request is the second gated subject and these two rows are the only HTTP path "
            "to its gate; without both, the demo shows that a clause under blame cannot be "
            "USED and says nothing about it being quietly EDITED AWAY."
        )


def test_twenty_rows_address_nineteen_paths_and_the_repeat_is_named() -> None:
    """ROWS ARE NOT PATHS, and the difference is one template declared under two verbs.

    The live 404 body lists nineteen templates because it dedupes, and a reader who counts
    that list will find one fewer than this table holds. That discrepancy is a correct
    property of two different questions — "which addresses exist" and "which
    (method, address) pairs are routed" — and it is written down here so that nobody
    reconciles it by deleting a row.
    """
    rows = [(r.method, r.template) for r in app.ROUTES]
    templates = {template for _method, template in rows}
    assert len(rows) == _EXPECTED_ROUTE_COUNT
    assert len(templates) == _EXPECTED_PATH_COUNT
    repeated = sorted(
        template
        for template in templates
        if sum(1 for _method, other in rows if other == template) > 1
    )
    assert repeated == [_TWICE_DECLARED_PATH], (
        f"the set of templates declared under more than one method is {repeated}. Exactly "
        f"one is expected: {_TWICE_DECLARED_PATH} is GET disposition and POST "
        "sign_disposition — two resources, two contracts, two owners, one address."
    )
    assert sorted(r.method for r in app.ROUTES if r.template == _TWICE_DECLARED_PATH) == [
        "GET",
        "POST",
    ]


def test_the_subject_index_resolves_to_its_own_key_and_takes_no_parameters() -> None:
    """The eighteenth route, and the two properties that make it an index rather than a query.

    No path parameter and no query parameter: the question is "which subjects does this
    database carry", and a caller who could filter it would be choosing the answer.
    ``reads._DECLARED_PARAMS`` declares the empty pair and ``reads.check_request`` enforces
    it, so ``?site_code=OTHER`` is a 400 that names the declared set rather than a filter
    silently ignored.
    """
    from mainline_demo_api import reads, subjects

    matched, params, other = app.route(*SUBJECTS_ROUTE)
    assert matched is not None, "GET /v1/demo/subjects routed nowhere"
    assert matched.key == SUBJECTS_KEY == subjects.SUBJECTS_RESOURCE
    assert params == {}
    assert other is False
    assert reads._DECLARED_PARAMS[SUBJECTS_KEY] == ((), ())


def test_the_subject_index_is_a_read_in_every_table_that_names_a_read() -> None:
    """Four tables, one key, and nothing in the language makes them agree.

    ``app.ROUTES`` routes it, ``reads._DECLARED_PARAMS`` declares its parameters,
    ``reads.READS`` implements it and ``envelope.SCHEMA_IDS`` names its contract. The
    failure that this catches is the one this whole file was opened for, one table over: a
    key present in three of the four is a route that 404s, a 400 that names no contract, or
    a read nothing can address, depending on which one is missing.
    """
    from mainline_demo_api import envelope, reads, subjects

    assert SUBJECTS_KEY == subjects.SUBJECTS_RESOURCE
    assert SUBJECTS_KEY in {r.key for r in app.ROUTES}
    assert SUBJECTS_KEY in reads._DECLARED_PARAMS
    assert SUBJECTS_KEY in reads.READS
    assert envelope.SCHEMA_IDS[SUBJECTS_KEY] == subjects.SUBJECTS_SCHEMA_ID
    assert f"{envelope.CONTRACT_BASE}subjects.schema.json" == subjects.SUBJECTS_SCHEMA_ID


def test_the_cr_obligations_read_is_in_every_table_that_names_a_read() -> None:
    """Four tables, one key, and nothing in the language makes them agree.

    Same four as the subject index, and the same three failure modes for a key present in
    three of them: a route that 404s, a 400 that names no contract, or a read nothing can
    address.

    The last two assertions are the substantive ones. ``cr_blocking_checks`` names the
    SAME ``$id`` as ``blocking_checks`` — ``blocking-check.schema.json`` — because that
    contract's ``data`` requires ``subject_kind`` and ``subject_id`` and carries no
    ``permit_id`` in its required set, and ``common.schema.json#/$defs/subject_kind`` is
    the closed pair ``permit | change_request``. It was authored subject-polymorphic.
    ``transport.ts::finishExchange`` compares the ``$id`` against the one the console
    holds **for the requested key**, so two keys may name one contract; a key may never
    name two.
    """
    from mainline_demo_api import envelope, reads

    assert CR_CHECKS_KEY in {r.key for r in app.ROUTES}
    assert CR_CHECKS_KEY in reads._DECLARED_PARAMS
    assert CR_CHECKS_KEY in reads.READS
    assert CR_CHECKS_KEY in envelope.SCHEMA_IDS
    assert reads._DECLARED_PARAMS[CR_CHECKS_KEY] == (("cr_id",), ()), (
        "the CR's obligations take one path parameter and no query parameter, exactly as "
        "the permit's mirror declares. A silently-ignored query parameter is how a caller "
        "comes to believe a filter was applied."
    )
    assert reads.READS[CR_CHECKS_KEY] is reads.read_cr_blocking_checks
    assert envelope.SCHEMA_IDS[CR_CHECKS_KEY] == envelope.SCHEMA_IDS["blocking_checks"]
    assert (
        envelope.SCHEMA_IDS[CR_CHECKS_KEY] == f"{envelope.CONTRACT_BASE}blocking-check.schema.json"
    )


def test_the_transcribed_contract_id_is_the_one_the_handler_actually_stamps() -> None:
    """``envelope.SCHEMA_IDS[demo_gate_run]`` and ``gate_run.GATE_RUN_SCHEMA_ID`` are one id.

    Two constants, two modules, one wire value — and until 2026-08-14 only one of them
    existed. ``gate_run.py`` stamps its own ``schema_id`` onto the success payload and
    never consults ``SCHEMA_IDS``; ``app.py``'s 501 branch consults ``SCHEMA_IDS`` and
    cannot import ``gate_run`` (surviving that import failing is the branch's whole job).
    So the two are read on paths that never meet, and nothing but this assertion makes
    them agree. If they drift, one HTTP status names one contract and another names a
    different one for the same endpoint, and ``finishExchange`` refuses whichever it did
    not expect — *a payload that names a contract we do not hold is not forward
    compatibility; it is an unverifiable claim*.
    """
    from mainline_demo_api import envelope, gate_run

    assert envelope.SCHEMA_IDS[DEMO_KEY] == gate_run.GATE_RUN_SCHEMA_ID
    assert envelope.SCHEMA_IDS[DEMO_KEY] == f"{envelope.CONTRACT_BASE}gate-run.schema.json"


def test_no_two_routes_share_a_method_and_template() -> None:
    """A duplicate row would shadow the earlier one at ``route()`` and never be noticed.

    ``route()`` returns the FIRST match, so a second row with the same method and template
    is unreachable code that nothing else in this file can see: every other assertion here
    compares SETS, and a set collapses the duplicate into the row it shadows. The keys are
    asserted distinct too — two rows with one key would route consistently and mean the
    resource registry has two names for one thing.
    """
    pairs = [(r.method, r.template) for r in app.ROUTES]
    assert len(pairs) == len(set(pairs)), sorted({p for p in pairs if pairs.count(p) > 1})
    keys = [r.key for r in app.ROUTES]
    assert len(keys) == len(set(keys)), sorted({k for k in keys if keys.count(k) > 1})
