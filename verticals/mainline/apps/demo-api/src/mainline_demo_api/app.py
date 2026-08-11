# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The whole server: a router, a dispatcher, a file server, and one function AWS calls.

THERE IS NO WEB FRAMEWORK HERE AND THERE IS NOT GOING TO BE ONE.
A Lambda invocation already *is* a function call with a dict argument. Bolting Mangum in
front of FastAPI would translate that dict into an HTTP request so a framework could
parse it back into a dict — three dependencies and a cold-start penalty to arrive where
we started. ``handler(event, context)`` is the server, and the routing table below is
seventeen regexes compiled once at import.

ONE ORIGIN, TWO SURFACES
------------------------
`docs/leads/ship-final.md` DECISION **D1**: the demo URL is a public **Lambda Function
URL**, because this AWS account is under a verification hold that refuses new CloudFront
distributions (§1.4, with the quoted ``AccessDenied``). So there is no CDN and no S3
bucket in front of this function, and the same handler answers both surfaces:

    /v1/*        the JSON API below — envelope, dispatcher, error contract, unchanged
    everything   :mod:`mainline_demo_api.static_site` — the console SPA and the
                 else        evidence bundle, out of a directory bundled beside this file

Same origin for both means no CORS, one hostname in the submission form, and one
resource to be wrong about. ``GET /v1/health`` answers exactly as it always has: it is
matched before the static branch is ever considered.

WHAT THE EVENT LOOKS LIKE
-------------------------
API Gateway **payload format 2.0**, which is also what a Lambda Function URL emits:

    {"version": "2.0", "rawPath": "/v1/permits/…", "rawQueryString": "as_of=…",
     "queryStringParameters": {…}, "headers": {…}, "body": "…", "isBase64Encoded": false,
     "requestContext": {"stage": "$default", "http": {"method": "GET", "path": "/v1/…"}}}

``rawPath`` is authoritative and ``requestContext.http.path`` is the fallback, because a
Function URL sets both and an API Gateway custom domain can differ between them. A stage
prefix is stripped when the stage is a real name — ``$default`` prefixes nothing.

STATUS CODES, AND WHY THE 4xx BODIES ARE NOT ENVELOPES
------------------------------------------------------
``console/src/data/transport.ts`` classifies a non-2xx response with no parseable
envelope as a ``status`` transport failure and shows the body. That is exactly right for
a missing permit, so the error bodies here are a small, honestly-named problem object
rather than a fake envelope:

===  ==================================================================================
200  a read envelope
400  a path or query parameter the resource cannot use
404  the subject does not exist
405  the path exists under a different method
409  the row exists and its contract cannot express it — the field is named
501  a POST whose implementation module is not deployed
503  no DSN, or the database did not answer
500  anything else, with the SQLSTATE when the driver gave one
===  ==================================================================================

**A refused transition is NOT an error.** It arrives from ``transitions`` as an
``invoke`` envelope with ``outcome: "refused"`` and a specification refusal payload, and
the console turns that into a ``RefusalError`` carrying the payload verbatim. This module
passes the transitions module's ``(status, body)`` through untouched, so a refusal keeps
whatever status W4 chose and its envelope reaches the client intact.

THE POST BOUNDARY
-----------------
``mainline_demo_api.transitions`` is W4's, is not in this distribution, and is imported
lazily. Its contract is fixed:

    ``handle_transition(resource_key, path_params, body, conn) -> tuple[int, dict]``

Until it lands, a POST answers ``501`` naming the module and the missing symbol. The read
surface is therefore deployable before the write surface exists, which is the whole
reason the boundary is a lazy import rather than a top-level one.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import traceback
from collections.abc import Mapping
from typing import Any, Final

import psycopg

from . import db, reads, static_site
from .envelope import SCHEMA_IDS, dumps
from .health import HEALTH_PATH, health

__all__ = ["ROUTES", "Route", "handler", "lambda_handler", "route"]

_log = logging.getLogger("mainline_demo_api")

#: Cache-Control for the twelve reads. Ten seconds is long enough for CloudFront to
#: absorb a room full of judges refreshing at once and short enough that the gate
#: surface still looks live after a transition. The three-beat demo drives POSTs, which
#: are never cached, so nothing a judge *does* is ever served stale.
_READ_CACHE_CONTROL: Final = "public, max-age=10"

#: Health and transitions. A cached health check is not a health check.
_NO_STORE: Final = "no-store"

_TRANSITIONS_MODULE: Final = "mainline_demo_api.transitions"


class Route:
    """One row of the routing table: method, compiled path, resource key."""

    __slots__ = ("key", "method", "pattern", "template")

    def __init__(self, method: str, template: str, key: str) -> None:
        self.method = method
        self.template = template
        self.key = key
        # `{param}` becomes a segment that cannot contain a separator, and every literal
        # run around it is escaped. Same rule the console applies before it sends: a path
        # parameter that could contain `/` could address a different resource than the
        # one asked for. The template is split rather than substituted-then-escaped,
        # because `re.escape` turns `{` into `\{` and a substitution over the escaped
        # string silently matches nothing — a router that routes nowhere.
        pattern = "".join(
            f"(?P<{part[1:-1]}>[A-Za-z0-9._~-]{{1,128}})"
            if part.startswith("{") and part.endswith("}")
            else re.escape(part)
            for part in re.split(r"(\{[a-z_]+\})", template)
        )
        self.pattern = re.compile(f"^{pattern}$")

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"Route({self.method} {self.template} -> {self.key})"


def _routes() -> tuple[Route, ...]:
    """Build the seventeen routes: sixteen console resources plus the demo driver's own.

    **Sixteen are transcribed from** ``console/src/data/resources.ts`` — twelve GETs and
    the four kernel POSTs. Those four POST templates are here even though this
    distribution implements none of them: a POST to a real path must answer 501 with the
    module that owes it, not 404 with "no such path". Those are different bugs and they
    belong to different people.

    **The seventeenth is** ``POST /v1/demo/gate-run``, and it is NOT one of the console's
    sixteen. It is the demo driver's own endpoint: it is governed by
    ``demo-api/contracts/gate-run.schema.json`` (``$id``
    ``gate_run.GATE_RUN_SCHEMA_ID``) rather than by ``invoke.schema.json``, and it is
    declared separately from the resource registry — ``transitions.TRANSITION_RESOURCES``
    carries the key ``demo_gate_run`` and ``transitions.handle_transition`` dispatches it
    to ``gate_run.gate_run``, four beats inside one transaction that is rolled back.

    IT WAS MISSING, AND THAT WAS THE DEMO'S HEADLINE DEFECT. Every beat was implemented
    and none of it was reachable, because this table had sixteen rows and the router
    therefore answered 404 before the dispatcher was consulted.
    ``evidence/deploy/acceptance.json`` recorded it as *"POST /v1/demo/gate-run (run 1)
    returned 404, expected 200"* and ``console/src/features/gate/DemoDriver.tsx`` renders
    *"POST /v1/demo/gate-run is not addressable from this console"* on screen.

    The console still does not declare it: ``resources.ts`` has sixteen ``declare()``
    calls and ``contracts.ts`` does not register ``gate-run.schema.json``, so the panel
    keeps telling that truth until the console domain closes its half.
    ``tests/test_routes_gate_run.py`` pins the difference between the two tables to
    exactly this one endpoint, so a *second* undeclared route is still a failure.
    """
    return (
        Route("GET", "/v1/permits/{permit_id}", "permit"),
        Route("GET", "/v1/permits/{permit_id}/blocking-checks", "blocking_checks"),
        Route("GET", "/v1/permits/{permit_id}/silence", "silence"),
        Route("GET", "/v1/change-requests/{cr_id}", "change_request"),
        Route("GET", "/v1/checks/{check_id}/disposition", "disposition"),
        Route("GET", "/v1/receipts/{receipt_id}", "exposure_receipt"),
        Route("GET", "/v1/clauses/{clause_uuid}/versions/{commit_id}", "clause_version"),
        Route("GET", "/v1/clauses/{clause_uuid}/ancestry", "clause_ancestry"),
        Route("GET", "/v1/ledger", "ledger"),
        Route("GET", "/v1/recall-runs/{run_id}", "recall_run"),
        Route("GET", "/v1/lessons/{lesson_id}/propagation", "propagation"),
        Route("GET", "/v1/audit", "audit"),
        Route("POST", "/v1/permits/{permit_id}/checks:materialise", "materialise_checks"),
        Route("POST", "/v1/checks/{check_id}/disposition", "sign_disposition"),
        Route("POST", "/v1/permits/{permit_id}/merge", "merge_permit"),
        Route("POST", "/v1/permits/{permit_id}/suspend", "suspend_permit"),
        # The seventeenth. No path parameters: the subject is the seeded demo permit,
        # resolved by `scenario.from_env()`, because a judge must not be able to point
        # the demo driver at somebody else's row.
        Route("POST", "/v1/demo/gate-run", "demo_gate_run"),
    )


ROUTES: Final[tuple[Route, ...]] = _routes()


def route(method: str, path: str) -> tuple[Route | None, dict[str, str], bool]:
    """Resolve ``(method, path)``.

    Returns ``(route, path_params, path_exists_under_another_method)``. The third value
    is what turns a ``GET /v1/permits/{id}/merge`` into a 405 that names the methods
    rather than a 404 that implies the endpoint was never built.
    """
    other = False
    for candidate in ROUTES:
        match = candidate.pattern.match(path)
        if match is None:
            continue
        if candidate.method == method:
            return candidate, dict(match.groupdict()), False
        other = True
    return None, {}, other


# ── Event decoding ──────────────────────────────────────────────────────────────────


def _method(event: Mapping[str, Any]) -> str:
    context = event.get("requestContext")
    if isinstance(context, Mapping):
        http = context.get("http")
        if isinstance(http, Mapping) and isinstance(http.get("method"), str):
            return str(http["method"]).upper()
    # `httpMethod` is payload format 1.0. Accepted so a misconfigured API Gateway
    # integration produces a route miss rather than a 500 about a missing key.
    return str(event.get("httpMethod") or "GET").upper()


def _path(event: Mapping[str, Any]) -> str:
    raw = event.get("rawPath")
    if not isinstance(raw, str) or not raw:
        context = event.get("requestContext")
        http = context.get("http") if isinstance(context, Mapping) else None
        raw = http.get("path") if isinstance(http, Mapping) else None
    if not isinstance(raw, str) or not raw:
        raw = str(event.get("path") or "/")

    context = event.get("requestContext")
    stage = context.get("stage") if isinstance(context, Mapping) else None
    if isinstance(stage, str) and stage and stage != "$default":
        prefix = f"/{stage}"
        if raw == prefix:
            return "/"
        if raw.startswith(f"{prefix}/"):
            return raw[len(prefix) :]
    return raw


def _query(event: Mapping[str, Any]) -> dict[str, str]:
    params = event.get("queryStringParameters")
    if not isinstance(params, Mapping):
        return {}
    return {str(key): str(value) for key, value in params.items() if value is not None}


def _body(event: Mapping[str, Any]) -> Any:
    raw = event.get("body")
    if raw is None or raw == "":
        return {}
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    if not isinstance(raw, str):
        return raw
    return json.loads(raw)


def _response(status: int, body: Any, *, cache: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json; charset=utf-8",
            "cache-control": cache,
            # Under DECISION D1 the console and this API are ONE Lambda Function URL, so
            # there is no cross-origin request to permit. This header exists for the
            # judge who curls the Function URL directly from a scratch page.
            "access-control-allow-origin": "*",
            "x-mainline-api": "demo-read",
        },
        "body": dumps(body),
        "isBase64Encoded": False,
    }


def _problem(status: int, kind: str, detail: str, **extra: Any) -> dict[str, Any]:
    body = {"error": {"kind": kind, "status": status, "detail": detail, **extra}}
    return _response(status, body, cache=_NO_STORE)


# ── The handler ─────────────────────────────────────────────────────────────────────


def handler(  # noqa: PLR0911 - one return per HTTP status, and the statuses are the
    # interface: collapsing them into a single exit would mean composing the status from
    # a variable, which is how a 404 becomes a 500 in a refactor nobody reviewed.
    event: Mapping[str, Any] | None,
    context: Any = None,  # noqa: ARG001 - AWS passes it; nothing here reads it, and a
    # handler that quietly depended on the runtime context would not be callable from a
    # test, which is how every routing test in this suite runs.
) -> dict[str, Any]:
    """Answer one Lambda invocation with ``{statusCode, headers, body, isBase64Encoded}``.

    ``/v1/*`` is the JSON API: envelope, dispatcher and error contract, exactly as
    before. Everything else is the bundled site, served by :mod:`static_site`. Never
    raises. A handler that raises produces a Lambda-shaped 502 with a stack trace the
    console cannot read and a judge cannot act on; every failure below arrives as a JSON
    body that names what went wrong.
    """
    started = time.monotonic()
    event = event or {}
    method = _method(event)
    path = _path(event)

    if method == "OPTIONS":
        # Same-origin in the deployed stack, so this is only ever reached by a direct
        # caller. Answering it costs nothing and saves that caller a confusing 405.
        return _response(204, {}, cache=_NO_STORE)

    # THE FORK, and it is the first thing after OPTIONS on purpose. `/v1` is the API's
    # prefix and nothing else is, so a stray path can never consume an API route and an
    # API route can never be answered with HTML. `/v1/health` is inside the prefix, so
    # the health check below is reached exactly as it was before the site existed.
    if not static_site.is_api_path(path):
        return static_site.serve(method, path)

    if path in (HEALTH_PATH, f"{HEALTH_PATH}/"):
        if method != "GET":
            return _problem(405, "method_not_allowed", f"{HEALTH_PATH} is GET only", allow=["GET"])
        status, body = health()
        return _response(status, body, cache=_NO_STORE)

    matched, params, other_method = route(method, path)
    if matched is None:
        if other_method:
            allowed = sorted({r.method for r in ROUTES if r.pattern.match(path)})
            return _problem(
                405,
                "method_not_allowed",
                f"{path} exists but not for {method}",
                allow=allowed,
            )
        return _problem(
            404,
            "no_route",
            f"no resource is declared at {method} {path}",
            declared=sorted({r.template for r in ROUTES}),
        )

    try:
        conn = db.connection()
    except db.DsnUnavailable as exc:
        return _problem(503, "dsn_unset", str(exc))
    except psycopg.Error as exc:
        db.close()
        return _problem(
            503,
            "database_unreachable",
            f"[{exc.sqlstate or '-----'}] {str(exc).splitlines()[0][:400]}",
        )

    try:
        if matched.method == "POST":
            return _transition(matched, params, event, conn)
        envelope = reads.read_resource(conn, matched.key, params, _query(event))
    except reads.ReadError as exc:
        return _problem(
            exc.status,
            type(exc).__name__.lower(),
            exc.detail,
            resource=matched.key,
            # `.get` for the same reason as the 501 below: seventeen routes, sixteen
            # contracts in SCHEMA_IDS. A missing entry must degrade to `null` in the
            # body, not to a KeyError inside an except-clause.
            schema_id=SCHEMA_IDS.get(matched.key),
        )
    except psycopg.Error as exc:
        # A broken connection must not be handed to the next invocation of this warm
        # container. Dropping it costs one reconnect; keeping it costs every request
        # until the container is recycled.
        db.close()
        _log.warning("read %s failed: %s", matched.key, exc.sqlstate)
        return _problem(
            500,
            "database_error",
            f"[{exc.sqlstate or '-----'}] {str(exc).splitlines()[0][:400]}",
            resource=matched.key,
        )
    except Exception as exc:  # noqa: BLE001 - the top of a Lambda is where this belongs
        _log.exception("read %s raised", matched.key)
        return _problem(
            500,
            "internal_error",
            f"{type(exc).__name__}: {exc}",
            resource=matched.key,
            traceback=traceback.format_exc(limit=6).splitlines()[-6:]
            if os.environ.get("MAINLINE_DEBUG") == "1"
            else None,
        )

    response = _response(200, envelope, cache=_READ_CACHE_CONTROL)
    response["headers"]["x-mainline-read-ms"] = str(round((time.monotonic() - started) * 1000, 1))
    return response


def _transition(
    matched: Route,
    params: Mapping[str, str],
    event: Mapping[str, Any],
    conn: psycopg.Connection[Any],
) -> dict[str, Any]:
    """Hand a POST to W4's transitions module, or say honestly that it is not deployed.

    The import is lazy and the signature is fixed:
    ``handle_transition(resource_key, path_params, body, conn) -> (status, body)``.
    Whatever comes back is passed through with ``no-store`` — including a refusal, which
    is a normal response carrying an ``invoke`` envelope and must not be reshaped here.
    """
    try:
        body = _body(event)
    except (ValueError, UnicodeDecodeError) as exc:
        return _problem(400, "malformed_body", f"request body is not JSON: {exc}")

    try:
        from . import transitions
    except ImportError as exc:
        return _problem(
            501,
            "not_implemented",
            f"{matched.key} is a transition and {_TRANSITIONS_MODULE} is not deployed in this "
            f"artefact ({exc}). The read surface ships independently of the write surface, by "
            "design: this distribution owns the twelve GETs and the spine, and the four POSTs "
            "are implemented against handle_transition(resource_key, path_params, body, conn).",
            resource=matched.key,
            # `.get`, not `[...]`: `demo_gate_run` is the one route whose contract is NOT
            # in SCHEMA_IDS. SCHEMA_IDS is a transcription of the console's sixteen
            # `declare()` calls — `tests/test_envelope.py` asserts that equality — and the
            # demo driver's contract is `gate_run.GATE_RUN_SCHEMA_ID`, which cannot be
            # imported here because importing `gate_run` is precisely what this branch
            # exists to survive. A subscript would turn "the write surface is absent"
            # into an unhandled KeyError, i.e. a 502 with no body, from the one code path
            # whose entire job is to fail legibly.
            schema_id=SCHEMA_IDS.get(matched.key),
        )

    entry = getattr(transitions, "handle_transition", None)
    if entry is None or not callable(entry):
        return _problem(
            501,
            "not_implemented",
            f"{_TRANSITIONS_MODULE} is present but exposes no callable handle_transition"
            "(resource_key, path_params, body, conn)",
            resource=matched.key,
        )

    try:
        status, payload = entry(matched.key, dict(params), body, conn)
    except psycopg.Error as exc:
        db.close()
        return _problem(
            500,
            "database_error",
            f"[{exc.sqlstate or '-----'}] {str(exc).splitlines()[0][:400]}",
            resource=matched.key,
        )
    return _response(int(status), payload, cache=_NO_STORE)


#: AWS's default handler name is ``<module>.lambda_handler``. Both names are exported so
#: the Terraform ``handler`` attribute can say either and be right.
lambda_handler = handler
