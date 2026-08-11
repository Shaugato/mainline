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

and ``console/src/features/gate/DemoDriver.tsx:255`` renders *"POST /v1/demo/gate-run is
not addressable from this console"* on screen.

A route table and a dispatcher table are two lists that must agree and nothing in the
language makes them. So the tests here are written as an agreement check in three
directions rather than as one happy-path assertion:

1. the ROUTER resolves the path to the key,
2. the DISPATCHER declares that key,
3. and the difference between this API's table and the console's declaration is pinned to
   exactly this one endpoint, so a *second* undeclared route is a failure too.

WHY THE CONSOLE STILL DOES NOT DECLARE IT
-----------------------------------------
``console/src/data/resources.ts`` has sixteen ``declare()`` calls and ``contracts.ts``
does not register ``gate-run.schema.json``. Both files belong to the console domain, and
until they change the console panel keeps reporting the gap. That is a true
incompleteness and it is left visible on purpose; what is fixed here is the API half,
which is what ``scripts/deploy`` acceptance and any ``curl`` address directly.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from mainline_demo_api import app
from mainline_demo_api import db as demo_db

from conftest import RESOURCES_TS

#: The one route this API serves that the console's resource registry does not declare.
DEMO_ROUTE: tuple[str, str] = ("POST", "/v1/demo/gate-run")

#: The dispatcher key ``transitions.handle_transition`` branches on.
DEMO_KEY = "demo_gate_run"

_EXPECTED_ROUTE_COUNT = 17
_CONSOLE_ROUTE_COUNT = 16


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


def test_the_table_is_seventeen_and_the_extra_is_exactly_the_demo_endpoint() -> None:
    """Sixteen transcribed from ``resources.ts``, plus one, pinned by name.

    Written as an exact set difference and not as a count so that adding a route the
    console does not declare — the failure mode that produced the 404 in the first place,
    inverted — still fails here rather than passing because the arithmetic worked out.
    """
    declared = _console_declared()
    routed = {(r.method, r.template) for r in app.ROUTES}

    assert len(declared) == _CONSOLE_ROUTE_COUNT, sorted(declared)
    assert len(app.ROUTES) == _EXPECTED_ROUTE_COUNT, sorted(r.template for r in app.ROUTES)
    assert declared <= routed, f"declared but not routed: {sorted(declared - routed)}"
    assert routed - declared == {DEMO_ROUTE}


def test_no_two_routes_share_a_method_and_template() -> None:
    """A duplicate row would shadow the earlier one at ``route()`` and never be noticed."""
    pairs = [(r.method, r.template) for r in app.ROUTES]
    assert len(pairs) == len(set(pairs)), sorted({p for p in pairs if pairs.count(p) > 1})
