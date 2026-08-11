#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""A local AWS Lambda **Function URL** in one standard-library process. NOT THE DEMO.

WHAT THIS IS
------------
`docs/leads/ship-final.md` DECISION **D1** makes the demo URL a public Lambda Function
URL that serves the console SPA *and* ``/v1/*`` from one origin. AWS gets there by
translating an HTTP request into a **payload format 2.0** event dict, calling
``mainline_demo_api.app.handler(event, context)``, and translating the returned dict back
into an HTTP response.

This program is exactly that translation, over ``http.server``, in-process:

    HTTP request  ──►  event dict (v2.0)  ──►  app.handler(event, None)  ──►
    response dict ──►  HTTP response

**Nothing between the two arrows is stubbed, wrapped, patched or re-implemented.** The
handler that answers here is imported from ``verticals/mainline/apps/demo-api/src`` and is
byte-for-byte the module the deployment artefact carries; the site it serves comes out of
the same ``$MAINLINE_WEB_ROOT`` the Lambda reads. That is the whole point: what is tested
here is what ships, and the demo becomes testable **before** any ``terraform apply``
exists — which matters, because on this account CloudFront is blocked by an AWS
verification hold and the apply is gated on a founder review that has not happened yet.

THIS IS NOT THE DEMO URL, AND IT SAYS SO IN THREE PLACES
--------------------------------------------------------
1. A banner on start, before the first request, naming itself and refusing the title.
2. ``X-Mainline-Emulator: local_furl`` on **every** response, so a transcript taken
   against this server can never be mistaken for one taken against the deployment.
   ``scripts/deploy/demo_acceptance.py`` reads that header and stamps
   ``target_is_local_emulator: true`` into ``evidence/deploy/acceptance.json``.
3. ``X-Mainline-Not-The-Demo-Url`` carrying this file's path.

Those two headers are the **only** divergence from what the handler itself returned. They
are added after the handler has produced its response and they replace nothing: if the
handler ever emits a header of either name, the handler's value wins and a warning is
printed, because a file server quietly overwriting the thing it is serving is precisely
the class of lie this repository exists to refuse.

WHY IT SERIALISES REQUESTS BY DEFAULT
--------------------------------------
``mainline_demo_api.db`` caches **one** psycopg connection at module scope for the life of
the process — correct for Lambda, where the platform gives each concurrent request its own
container, and unsafe for a single process fielding two at once. So the default is
``--concurrency serialized``: the socket is threaded (a browser opening six connections for
the asset graph must not deadlock) and the handler call is behind one lock. That is a
faithful emulation of ONE warm container. ``--concurrency parallel`` removes the lock and
prints a warning; it is for deliberately provoking the race, not for making a run look
faster.

WHAT IT DOES NOT EMULATE, NAMED SO NOBODY DISCOVERS IT LATER
-------------------------------------------------------------
* **Cold starts, container reuse and concurrency scaling.** One process, one connection.
* **The 6 MB response cap** and the 15-minute timeout. Nothing here truncates.
* **IAM.** A deployed Function URL under ``authorization_type = NONE`` is open, which is
  what D1 asks for; this server is bound to ``127.0.0.1`` and authenticates nothing.
* **TLS.** Plain HTTP. The acceptance prover records ``tls_verified: false`` when it is
  pointed here, and that is a true statement about this hop.
* **The CloudFront hop**, which does not exist under D1 anyway.

EXIT CODES
----------
``0`` clean shutdown (SIGINT) · ``2`` usage · ``3`` the handler could not be imported or
the web root is missing and ``--require-web-root`` was given.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import http.server
import json
import os
import shutil
import socket
import socketserver
import sys
import threading
import time
import urllib.parse
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

EXIT_OK: Final = 0
EXIT_USAGE: Final = 2
EXIT_UNUSABLE: Final = 3

#: This file lives at ``<repo>/scripts/deploy/local_furl.py``.
REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: The distribution whose ``handler`` AWS would call.
DEFAULT_APP_SRC: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "src"

#: The console build. ``vite.config.ts`` sets ``base: './'`` and the app hash-routes, so
#: this directory is correct from any prefix — including a Function URL root.
DEFAULT_WEB_ROOT: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "console" / "dist"

#: The signed EvidenceBundle the console falls back to when the database is unreachable.
#: Served at ``/bundle/`` because ``console/src/app/composition.tsx`` resolves ``./bundle/``
#: against the document.
DEFAULT_BUNDLE_DIR: Final = (
    REPO_ROOT
    / "verticals"
    / "mainline"
    / "apps"
    / "console"
    / "fixtures"
    / "bundles"
    / "demo-cloud"
)

EMULATOR_HEADER: Final = "x-mainline-emulator"
EMULATOR_VALUE: Final = "local_furl"
DISCLAIMER_HEADER: Final = "x-mainline-not-the-demo-url"

#: Invented, fixed, and obviously fake. A real Function URL id is 32 lowercase hex-ish
#: characters; this one spells what it is so that a log line pasted into an issue cannot be
#: mistaken for a deployment identifier.
EMULATED_FURL_ID: Final = "localfurlemulatornotarealfunction"
EMULATED_REGION: Final = "ap-southeast-1"


# ══════════════════════════════════════════════════════════════════════════════════════
# request  ──►  Lambda Function URL payload format 2.0
# ══════════════════════════════════════════════════════════════════════════════════════


def _headers_to_event(raw: Iterable[tuple[str, str]]) -> tuple[dict[str, str], list[str]]:
    """Fold HTTP headers the way a Function URL does.

    Names are lower-cased; repeated names are joined with ``", "``; ``Cookie`` is removed
    from ``headers`` entirely and its crumbs are returned as the event's ``cookies`` list.
    That last part is a real difference between payload 1.0 and 2.0 and it is emulated
    because a handler that read ``headers['cookie']`` would work here and fail in AWS.
    """
    headers: dict[str, str] = {}
    cookies: list[str] = []
    for name, value in raw:
        lower = name.lower()
        if lower == "cookie":
            cookies.extend(part.strip() for part in value.split(";") if part.strip())
            continue
        headers[lower] = f"{headers[lower]}, {value}" if lower in headers else value
    return headers, cookies


def _query_to_event(raw_query: str) -> dict[str, str]:
    """``a=1&b=2&a=3`` → ``{"a": "1,3", "b": "2"}``, which is what a Function URL sends.

    Repeated keys are joined with a comma rather than dropped. ``mainline_demo_api.reads``
    validates its own query parameters and rejects a comma where it wants one value, so a
    doubled parameter produces the same 400 here as in AWS instead of silently taking the
    first.
    """
    if not raw_query:
        return {}
    collected: dict[str, list[str]] = {}
    for key, value in urllib.parse.parse_qsl(raw_query, keep_blank_values=True):
        collected.setdefault(key, []).append(value)
    return {key: ",".join(values) for key, values in collected.items()}


def build_event(
    method: str,
    target: str,
    headers: Iterable[tuple[str, str]],
    body: bytes,
    *,
    source_ip: str = "127.0.0.1",
) -> dict[str, Any]:
    """Build the payload-format-2.0 event AWS would hand the handler.

    ``target`` is the raw request target off the request line — path plus query string,
    undecoded. ``rawPath`` keeps its percent-encoding, exactly as AWS delivers it, because
    ``static_site._segments`` decodes **once** on purpose and pre-decoding here would hide
    the traversal defence this repository wrote a test for.

    Keys AWS omits are omitted: no ``body`` when there is none, no
    ``queryStringParameters`` when the query string is empty, no ``cookies`` when no cookie
    was sent. A handler that used ``event["body"]`` rather than ``event.get("body")`` must
    fail here for the same reason it would fail in production.
    """
    split = urllib.parse.urlsplit(target)
    raw_path = split.path or "/"
    raw_query = split.query
    event_headers, cookies = _headers_to_event(headers)

    now = dt.datetime.now(dt.UTC)
    event: dict[str, Any] = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": raw_path,
        "rawQueryString": raw_query,
        "headers": event_headers,
        "requestContext": {
            "accountId": "anonymous",
            "apiId": EMULATED_FURL_ID,
            "domainName": f"{EMULATED_FURL_ID}.lambda-url.{EMULATED_REGION}.on.aws",
            "domainPrefix": EMULATED_FURL_ID,
            "http": {
                "method": method.upper(),
                "path": raw_path,
                "protocol": "HTTP/1.1",
                "sourceIp": source_ip,
                "userAgent": event_headers.get("user-agent", ""),
            },
            "requestId": str(uuid.uuid4()),
            "routeKey": "$default",
            # `$default` prefixes nothing, and `app._path` strips a stage prefix only when
            # the stage is a real name. Sending the literal AWS value keeps that branch
            # exercised the way it is exercised in production: not at all.
            "stage": "$default",
            "time": now.strftime("%d/%b/%Y:%H:%M:%S +0000"),
            "timeEpoch": int(now.timestamp() * 1000),
        },
        "isBase64Encoded": False,
    }
    if cookies:
        event["cookies"] = cookies
    query_params = _query_to_event(raw_query)
    if query_params:
        event["queryStringParameters"] = query_params
    if body:
        try:
            event["body"] = body.decode("utf-8")
        except UnicodeDecodeError:
            event["body"] = base64.b64encode(body).decode("ascii")
            event["isBase64Encoded"] = True
    return event


# ══════════════════════════════════════════════════════════════════════════════════════
# Lambda response  ──►  HTTP response
# ══════════════════════════════════════════════════════════════════════════════════════


class Translated:
    """A handler return value turned back into ``(status, headers, body)``."""

    __slots__ = ("body", "headers", "status", "warnings")

    def __init__(
        self, status: int, headers: list[tuple[str, str]], body: bytes, warnings: list[str]
    ) -> None:
        self.status = status
        self.headers = headers
        self.body = body
        self.warnings = warnings


def translate_response(result: Any) -> Translated:
    """Turn what the handler returned into what the socket needs.

    ``isBase64Encoded`` is honoured **on the way out**: a true flag means ``body`` is
    base64 and the bytes on the wire are its decoding. ``static_site`` sets it for every
    binary asset — a favicon, a woff2 — so a server that ignored it would serve
    base64 text where the browser expected a font and the console would render without
    its typeface while every status line said 200.

    A non-mapping return is treated the way a Function URL treats it: JSON-encoded with
    status 200. A malformed base64 body is a 502 that names the defect rather than a
    truncated asset.
    """
    warnings: list[str] = []

    if not isinstance(result, Mapping):
        payload = json.dumps(result).encode("utf-8")
        return Translated(200, [("content-type", "application/json")], payload, warnings)

    status = int(result.get("statusCode", 200))
    raw_headers = result.get("headers") or {}
    headers: list[tuple[str, str]] = []
    if isinstance(raw_headers, Mapping):
        headers.extend((str(k), str(v)) for k, v in raw_headers.items())

    for crumb in result.get("cookies") or []:
        headers.append(("set-cookie", str(crumb)))

    raw_body = result.get("body", "")
    if isinstance(raw_body, (bytes, bytearray)):
        # AWS would reject this — the contract says the body is a JSON string — so it is
        # accepted here and reported, rather than silently working locally and 502-ing in
        # production.
        warnings.append("the handler returned bytes for `body`; a Function URL requires a str")
        body = bytes(raw_body)
    elif result.get("isBase64Encoded"):
        try:
            body = base64.b64decode(str(raw_body), validate=True)
        except Exception as exc:  # noqa: BLE001 - any decode failure is one outcome
            detail = f"isBase64Encoded was true and the body did not decode: {exc}"
            payload = json.dumps({"error": {"kind": "emulator_bad_body", "detail": detail}})
            return Translated(
                502,
                [("content-type", "application/json; charset=utf-8")],
                payload.encode("utf-8"),
                [detail],
            )
    else:
        body = str(raw_body).encode("utf-8")

    return Translated(status, headers, body, warnings)


# ══════════════════════════════════════════════════════════════════════════════════════
# the server
# ══════════════════════════════════════════════════════════════════════════════════════


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Threaded so six parallel asset fetches from one browser cannot deadlock."""

    daemon_threads = True

    #: FALSE ON WINDOWS, AND THIS COST AN HOUR. `SO_REUSEADDR` means "reuse a socket in
    #: TIME_WAIT" on POSIX, but on Windows it means "bind even though another process is
    #: LISTENING here" — the second bind succeeds, `netstat` shows two listeners, and
    #: every connection is answered by whichever process got there first. Measured on
    #: 2026-08-11: a restarted emulator served the previous build's code, and the symptom
    #: was `curl: (52) Empty reply from server` from a server whose log said it had
    #: started. With this false, a stale process makes the bind FAIL and say so.
    allow_reuse_address = os.name != "nt"

    handler_entry: Any = None
    call_lock: threading.Lock | None = None
    quiet: bool = False
    served: int = 0


def _make_request_handler() -> type[http.server.BaseHTTPRequestHandler]:
    class FunctionUrlRequestHandler(http.server.BaseHTTPRequestHandler):
        # Keep-alive: the console pulls a dozen assets and a new TCP connection each time
        # would make every measured latency in the evidence file a measurement of the
        # emulator's socket setup.
        protocol_version = "HTTP/1.1"
        server_version = "mainline-local-furl/1.0"
        sys_version = ""

        # ── plumbing ───────────────────────────────────────────────────────────────────

        def log_message(self, fmt: str, *args: Any) -> None:
            if not getattr(self.server, "quiet", False):
                sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

        def _read_body(self) -> bytes:
            length = self.headers.get("content-length")
            if length is not None:
                try:
                    return self.rfile.read(int(length))
                except (ValueError, OSError):
                    return b""
            if (self.headers.get("transfer-encoding") or "").lower() == "chunked":
                # A Function URL de-chunks before it builds the event, so a chunked request
                # must arrive at the handler as a whole body or not at all.
                chunks: list[bytes] = []
                while True:
                    line = self.rfile.readline().strip()
                    if not line:
                        break
                    try:
                        size = int(line.split(b";")[0], 16)
                    except ValueError:
                        break
                    if size == 0:
                        self.rfile.readline()
                        break
                    chunks.append(self.rfile.read(size))
                    self.rfile.readline()
                return b"".join(chunks)
            return b""

        def _dispatch(self) -> None:
            started = time.monotonic()
            body = self._read_body()
            event = build_event(
                self.command,
                self.path,
                self.headers.items(),
                body,
                source_ip=self.client_address[0] if self.client_address else "127.0.0.1",
            )

            entry = self.server.handler_entry  # type: ignore[attr-defined]
            lock = self.server.call_lock  # type: ignore[attr-defined]
            try:
                if lock is None:
                    result = entry(event, None)
                else:
                    with lock:
                        result = entry(event, None)
            except Exception as exc:  # noqa: BLE001 - AWS answers 502 for an unhandled raise
                detail = f"{type(exc).__name__}: {exc}"
                payload = json.dumps(
                    {
                        "error": {
                            "kind": "handler_raised",
                            "status": 502,
                            "detail": detail,
                            "note": (
                                "app.handler is documented never to raise. AWS answers an "
                                "unhandled exception with a 502 and no useful body; this "
                                "emulator answers 502 and names the exception."
                            ),
                        }
                    }
                ).encode("utf-8")
                translated = Translated(
                    502, [("content-type", "application/json; charset=utf-8")], payload, [detail]
                )
            else:
                translated = translate_response(result)

            self._respond(translated, head=self.command == "HEAD", started=started)

        def _respond(self, translated: Translated, *, head: bool, started: float) -> None:
            names = {name.lower() for name, _ in translated.headers}
            for warning in translated.warnings:
                sys.stderr.write(f"local_furl: WARNING {warning}\n")

            # Content-Length from the bytes actually produced. For HEAD the handler already
            # returned an empty body and its own `content-length`, which RFC 9110 requires
            # to be the length a GET would have sent — so it is preserved rather than
            # overwritten with zero.
            declared = next(
                (v for n, v in translated.headers if n.lower() == "content-length"), None
            )
            if head and declared is not None:
                content_length = declared
            else:
                content_length = str(len(translated.body))

            self.send_response(translated.status)
            for name, value in translated.headers:
                if name.lower() in ("content-length", "transfer-encoding", "connection"):
                    continue
                self.send_header(name, value)
            if EMULATOR_HEADER in names:
                sys.stderr.write(
                    f"local_furl: WARNING the handler set {EMULATOR_HEADER} itself; the "
                    "emulator did NOT overwrite it\n"
                )
            else:
                self.send_header(EMULATOR_HEADER, EMULATOR_VALUE)
            if DISCLAIMER_HEADER not in names:
                # ASCII ONLY. `http.server` encodes header lines latin-1 and an em dash
                # here raises UnicodeEncodeError inside send_header, which closes the
                # socket with no status line at all: every request answers "empty reply
                # from server" and nothing in the log says why. Measured, on this file,
                # on 2026-08-11.
                self.send_header(
                    DISCLAIMER_HEADER,
                    "scripts/deploy/local_furl.py - a local emulator of a Lambda Function "
                    "URL. It is not the deployed demo and must not be published as one.",
                )
            self.send_header("Content-Length", content_length)
            self.end_headers()
            if not head and translated.body:
                try:
                    self.wfile.write(translated.body)
                except (BrokenPipeError, ConnectionResetError):
                    # A browser that navigated away mid-asset is not an error worth a
                    # stack trace in the middle of a recording.
                    return
            self.server.served += 1  # type: ignore[attr-defined]
            if not getattr(self.server, "quiet", False):
                elapsed = (time.monotonic() - started) * 1000
                sys.stderr.write(
                    f"  {self.command:6} {self.path[:64]:64} -> {translated.status} "
                    f"{len(translated.body)}b {elapsed:.1f}ms\n"
                )

        # Every method the handler is willing to see. Anything else gets the handler's own
        # 405, which is the point: the router decides, not this file.
        # N815: `do_<METHOD>` is BaseHTTPRequestHandler's dispatch protocol, not a naming
        # choice. Renaming any of them silently stops that method being served.
        do_GET = _dispatch  # noqa: N815
        do_HEAD = _dispatch  # noqa: N815
        do_POST = _dispatch  # noqa: N815
        do_PUT = _dispatch  # noqa: N815
        do_PATCH = _dispatch  # noqa: N815
        do_DELETE = _dispatch  # noqa: N815
        do_OPTIONS = _dispatch  # noqa: N815

    return FunctionUrlRequestHandler


# ══════════════════════════════════════════════════════════════════════════════════════
# configuration
# ══════════════════════════════════════════════════════════════════════════════════════


def read_env_file(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines. No expansion, no ``export``, no shell."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def redact_dsn(dsn: str) -> str:
    """A DSN with the password replaced. Printed; never the original."""
    try:
        split = urllib.parse.urlsplit(dsn)
    except ValueError:
        return "<unparseable DSN>"
    if not split.hostname:
        return "<non-URL DSN, redacted>"
    user = split.username or ""
    auth = f"{user}:***@" if split.password else (f"{user}@" if user else "")
    port = f":{split.port}" if split.port else ""
    return f"{split.scheme}://{auth}{split.hostname}{port}{split.path}?{split.query}"


def with_database(dsn: str, database: str) -> str:
    """Return *dsn* with its path segment replaced by *database*.

    `docs/leads/ship-final.md` §1.1 and §6.2: ``COCKROACH_DSN`` in ``.env`` names
    ``/defaultdb`` while the demo history lives in ``mainline_demo``. A connection on the
    committed DSN answers and then fails ``UndefinedTable: relation "mainline.permit" does
    not exist``, which reads like a broken migration chain and is not one. Every tool in
    this domain selects the database explicitly rather than trusting the path segment.
    """
    split = urllib.parse.urlsplit(dsn)
    return urllib.parse.urlunsplit(
        (split.scheme, split.netloc, f"/{database.lstrip('/')}", split.query, split.fragment)
    )


def stage_web_root(web_root: Path, bundle_dir: Path, stage: Path) -> tuple[Path, int, int]:
    """Compose ``web_root`` + ``bundle_dir`` into one directory and return it.

    The deployed artefact's bundler does this at build time; doing it here lets the
    ``/bundle/*`` surface — the REPLAY source a judge sees when the database is
    unreachable — be exercised before that artefact exists. It is a **copy**, so the
    console's ``dist/`` is never written into.
    """
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(web_root, stage)
    shutil.copytree(bundle_dir, stage / "bundle", dirs_exist_ok=True)
    site_files = sum(1 for p in stage.rglob("*") if p.is_file())
    bundle_files = sum(1 for p in (stage / "bundle").rglob("*") if p.is_file())
    return stage, site_files - bundle_files, bundle_files


def import_handler(app_src: Path) -> tuple[Any, str]:
    """Import ``mainline_demo_api.app.handler`` from *app_src* and report its file."""
    resolved = str(app_src.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)
    # Imported here and not at module scope: the path above is what makes it importable,
    # and a top-level import would make this file unusable as a library on a machine where
    # the distribution is somewhere else.
    from mainline_demo_api import app as app_module

    return app_module.handler, str(Path(app_module.__file__ or "?").resolve())


# ══════════════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local_furl",
        description=(
            "Serve the REAL demo-api Lambda handler over HTTP by emulating a Lambda "
            "Function URL payload-format-2.0 event. A local emulator: never the demo URL."
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8731, help="0 picks a free port")
    parser.add_argument(
        "--app-src", type=Path, default=DEFAULT_APP_SRC, help="the demo-api distribution's src/"
    )
    parser.add_argument(
        "--web-root",
        type=Path,
        default=None,
        help=f"$MAINLINE_WEB_ROOT for this process (default {DEFAULT_WEB_ROOT})",
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=None,
        help=(
            "stage this EvidenceBundle under <web root>/bundle/ in a temporary copy; "
            f"the console's own is {DEFAULT_BUNDLE_DIR}"
        ),
    )
    parser.add_argument(
        "--stage-dir",
        type=Path,
        default=None,
        help="where --bundle-dir composes its copy (default: a sibling .local_furl_site)",
    )
    parser.add_argument(
        "--require-web-root",
        action="store_true",
        help="exit 3 rather than start when the web root is missing",
    )
    parser.add_argument("--dsn", default=None, help="$MAINLINE_DSN for this process")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="read the DSN from a KEY=VALUE file (see --dsn-key)",
    )
    parser.add_argument("--dsn-key", default="COCKROACH_DSN", help="key inside --env-file")
    parser.add_argument(
        "--database",
        default=None,
        help="replace the DSN's database path segment, e.g. mainline_demo",
    )
    parser.add_argument(
        "--permit-id",
        default=None,
        help="$MAINLINE_DEMO_PERMIT_ID — the seeded permit the gate run drives",
    )
    parser.add_argument(
        "--concurrency",
        choices=("serialized", "parallel"),
        default="serialized",
        help="serialized (default) emulates ONE warm container; parallel removes the lock",
    )
    parser.add_argument(
        "--ready-file",
        type=Path,
        default=None,
        help="write the base URL here once the socket is listening (for scripts and CI)",
    )
    parser.add_argument("--quiet", action="store_true", help="no per-request log lines")
    return parser


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911, PLR0912, PLR0915 - a banner
    # tells the operator exactly what is loaded, where it reads from and what it is not,
    # printed once. Splitting it would separate the configuration from its disclosure.
    args = build_parser().parse_args(argv)

    # ── the DSN ──────────────────────────────────────────────────────────────────────
    dsn = args.dsn
    dsn_source = "--dsn"
    if dsn is None and args.env_file is not None:
        try:
            values = read_env_file(args.env_file)
        except OSError as exc:
            print(f"local_furl: cannot read {args.env_file}: {exc}", file=sys.stderr)
            return EXIT_USAGE
        dsn = values.get(args.dsn_key)
        dsn_source = f"{args.env_file}:{args.dsn_key}"
        if dsn is None:
            print(f"local_furl: {args.env_file} has no {args.dsn_key}", file=sys.stderr)
            return EXIT_USAGE
    if dsn is None:
        dsn = os.environ.get("MAINLINE_DSN")
        dsn_source = "$MAINLINE_DSN (inherited)" if dsn else "unset"
    if dsn and args.database:
        dsn = with_database(dsn, args.database)
        dsn_source += f" + --database {args.database}"
    if dsn:
        os.environ["MAINLINE_DSN"] = dsn

    if args.permit_id:
        os.environ["MAINLINE_DEMO_PERMIT_ID"] = args.permit_id

    # ── the site ─────────────────────────────────────────────────────────────────────
    web_root = args.web_root or DEFAULT_WEB_ROOT
    staged_note = ""
    if args.bundle_dir is not None:
        if not web_root.is_dir():
            print(f"local_furl: --bundle-dir needs a web root; {web_root} is not a directory")
            return EXIT_UNUSABLE
        stage = args.stage_dir or (web_root.parent / ".local_furl_site")
        web_root, site_files, bundle_files = stage_web_root(web_root, args.bundle_dir, stage)
        staged_note = f"staged {site_files} site file(s) + {bundle_files} bundle file(s)"
    os.environ["MAINLINE_WEB_ROOT"] = str(web_root.resolve())

    if not web_root.is_dir():
        message = (
            f"local_furl: the web root {web_root} is not a directory. GET / will answer 503 "
            "web_root_not_bundled and /v1/* will answer normally; build the console with "
            "`npm run build` in verticals/mainline/apps/console, or pass --web-root."
        )
        if args.require_web_root:
            print(message, file=sys.stderr)
            return EXIT_UNUSABLE
        print(f"WARNING  {message}", file=sys.stderr)

    # ── the handler ──────────────────────────────────────────────────────────────────
    try:
        entry, handler_file = import_handler(args.app_src)
    except Exception as exc:  # noqa: BLE001 - an import failure is the one fatal case
        print(
            f"local_furl: cannot import mainline_demo_api.app from {args.app_src}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return EXIT_UNUSABLE

    try:
        server = _Server((args.host, args.port), _make_request_handler())
    except OSError as exc:
        print(
            f"local_furl: cannot listen on {args.host}:{args.port}: {exc}. Something else "
            "is already bound there — very often a previous emulator that was not stopped. "
            "Stop it, or pass --port 0 for a free one.",
            file=sys.stderr,
        )
        return EXIT_UNUSABLE
    server.handler_entry = entry
    server.call_lock = None if args.concurrency == "parallel" else threading.Lock()
    server.quiet = args.quiet
    host, port = server.server_address[:2]
    if isinstance(host, bytes):  # pragma: no cover - AF_INET always gives a str here
        host = host.decode()
    base_url = f"http://{host}:{port}"

    # ── the banner. It is the first thing on the screen and it says what this is not. ──
    # ASCII ONLY in everything printed here: this banner is read on a Windows console
    # whose default code page is cp1252, and a stray em dash renders as a question mark in
    # the one paragraph whose entire job is to be unambiguous.
    print("=" * 78)
    print("LOCAL EMULATOR. THIS IS NOT THE DEMO URL AND MUST NOT BE PUBLISHED AS ONE.")
    print("=" * 78)
    print(f"  serving       {base_url}")
    print("  emulating     AWS Lambda Function URL, payload format 2.0, authorization NONE")
    print(f"  handler       {handler_file}")
    print(f"  web root      {os.environ['MAINLINE_WEB_ROOT']}")
    if staged_note:
        print(f"                {staged_note}")
    print(f"  DSN           {redact_dsn(dsn) if dsn else 'UNSET: /v1/* will answer 503'}")
    print(f"  DSN source    {dsn_source}")
    print(f"  permit        {os.environ.get('MAINLINE_DEMO_PERMIT_ID', '(scenario default)')}")
    print(f"  concurrency   {args.concurrency}", end="")
    if args.concurrency == "serialized":
        print("  (one warm container: mainline_demo_api.db caches ONE connection)")
    else:
        print("  WARNING: one psycopg connection shared across threads")
    print("  every response carries  x-mainline-emulator: local_furl")
    print("  the real demo URL is a Lambda Function URL; docs/submission/SUBMISSION.json")
    print("  holds UNRESOLVED until one exists. Do not paste this address into that file.")
    print("=" * 78)
    sys.stdout.flush()

    if args.ready_file is not None:
        args.ready_file.parent.mkdir(parents=True, exist_ok=True)
        args.ready_file.write_text(base_url + "\n", encoding="utf-8")

    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print(f"\nlocal_furl: stopped after {server.served} request(s)")
    finally:
        server.server_close()
        if args.ready_file is not None and args.ready_file.exists():
            args.ready_file.unlink()
    return EXIT_OK


def serve_in_thread(
    argv: list[str] | None = None,
) -> tuple[_Server, threading.Thread, str]:  # pragma: no cover - used by ad-hoc drivers
    """Start the emulator on a background thread and return ``(server, thread, base_url)``.

    For a caller that wants the server and the prover in one process. The CLI is the
    supported entry point; this exists so a test does not have to shell out.
    """
    args = build_parser().parse_args(argv)
    entry, _ = import_handler(args.app_src)
    server = _Server((args.host, args.port), _make_request_handler())
    server.handler_entry = entry
    server.call_lock = threading.Lock()
    server.quiet = True
    host, port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2})
    thread.daemon = True
    thread.start()
    return server, thread, f"http://{host}:{port}"


def free_port() -> int:  # pragma: no cover - convenience for drivers
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


if __name__ == "__main__":
    raise SystemExit(main())
