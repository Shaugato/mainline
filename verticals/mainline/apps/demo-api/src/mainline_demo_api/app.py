# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The whole server: a router, a dispatcher, and one function AWS calls.

THERE IS NO WEB FRAMEWORK HERE AND THERE IS NOT GOING TO BE ONE.
A Lambda invocation already *is* a function call with a dict argument. Bolting Mangum in
front of FastAPI would translate that dict into an HTTP request so a framework could
parse it back into a dict — three dependencies and a cold-start penalty to arrive where
we started. ``handler(event, context)`` is the server, and the routing table below is
sixteen regexes compiled once at import.

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

from . import db, reads
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
    """Build the sixteen declared routes, transcribed from ``console/src/data/resources.ts``.

    The four POST templates are here even though this distribution implements none of
    them: a POST to a real path must answer 501 with the module that owes it, not 404
    with "no such path". Those are different bugs and they belong to different people.
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
            # The console and the site are served from ONE CloudFront distribution, so
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

    Never raises. A handler that raises produces a Lambda-shaped 502 with a stack trace
    the console cannot read and a judge cannot act on; every failure below arrives as a
    JSON body that names what went wrong.
    """
    started = time.monotonic()
    event = event or {}
    method = _method(event)
    path = _path(event)

    if method == "OPTIONS":
        # Same-origin in the deployed stack, so this is only ever reached by a direct
        # caller. Answering it costs nothing and saves that caller a confusing 405.
        return _response(204, {}, cache=_NO_STORE)

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
            schema_id=SCHEMA_IDS[matched.key],
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
            schema_id=SCHEMA_IDS[matched.key],
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
