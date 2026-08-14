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

#: One number, written twice, because the two tables it counts are maintained by two
#: different people in two different languages. They must be equal; that they are equal
#: is the assertion, and a single shared constant would have made it unfalsifiable.
_EXPECTED_ROUTE_COUNT = 17
_CONSOLE_ROUTE_COUNT = 17


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


def test_the_table_and_the_console_declaration_are_the_same_seventeen() -> None:
    """``declared == routed``, both seventeen, with NO permitted exception.

    Until 2026-08-14 this pinned ``routed - declared == {DEMO_ROUTE}``: an exact set, so a
    second undeclared route failed, but one named row was still allowed through. The
    console declared that row on 2026-08-14, so the exception was collapsed to empty
    instead of the count being raised around it. Equality of the two SETS is what is
    asserted; the two counts are asserted beside it because a set cannot see a duplicate
    row in ``app.ROUTES`` and a shadowed duplicate is unreachable.

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
    # Named, not merely counted: this is the row the file exists for, and an equality
    # between two empty sets would satisfy every assertion above it.
    assert DEMO_ROUTE in declared, (
        f"{DEMO_ROUTE[0]} {DEMO_ROUTE[1]} is routed by this API and the console no longer "
        "declares it, so the demo driver is back to rendering the not-addressable panel"
    )
    assert DEMO_ROUTE in routed


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
    """A duplicate row would shadow the earlier one at ``route()`` and never be noticed."""
    pairs = [(r.method, r.template) for r in app.ROUTES]
    assert len(pairs) == len(set(pairs)), sorted({p for p in pairs if pairs.count(p) > 1})
