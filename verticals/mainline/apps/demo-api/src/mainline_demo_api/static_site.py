# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Serve the console SPA and the evidence bundle out of the same Lambda as ``/v1/*``.

WHY THIS MODULE EXISTS
----------------------
`docs/leads/ship-final.md` §1.4 records that this AWS account cannot create a CloudFront
distribution — ``AccessDenied: Your account must be verified before you can add new
CloudFront resources`` — and DECISION **D1** therefore makes the demo URL a **public
Lambda Function URL** that serves *both* the SPA and the API from one origin. There is no
S3 bucket in the request path and no CDN, so the thing that used to serve
``index.html`` has to be this handler.

Two properties of the console make that cheap, and both were measured rather than
assumed: ``console/vite.config.ts`` sets ``base: './'``, and the app routes on the URL
**hash**. A relative-base, hash-routed SPA is correct from any prefix, so nothing here
has to know the deployed hostname and nothing has to be rebuilt when it changes.

NO DEPENDENCIES, AND NOT EVEN A PACKAGE-INTERNAL ONE
----------------------------------------------------
This module imports the standard library and nothing else — not ``psycopg``, not
``envelope``, not ``db``. That is deliberate: the static surface must keep answering when
the database surface cannot import, and
``tests/test_envelope.py::test_no_web_framework_or_sdk_is_imported`` counts the third
party imports of the read spine. A file server that dragged a driver in would be a new
cold-start cost paid by every judge who loads the page.

WHERE THE FILES ARE
-------------------
``$MAINLINE_WEB_ROOT`` wins if it is set. Otherwise the first of these that is a
directory:

    <this package>/web        the bundler copied the site inside the package
    <this package>/../web     the bundler copied it beside the package, i.e. /var/task/web

If neither exists the nominal root is the first candidate, so the 503 below can name the
path that was expected and a deploy that forgot the site says so out loud instead of
serving a blank page.

**A missing web root is a 503, never an exception at import.** Nothing here touches the
filesystem while the module loads, so an API-only artefact still imports, still routes
``/v1/*`` and still answers ``/v1/health`` — an API that answers is more useful than a
handler that will not start.

THE SIX ANSWERS
---------------
===  ==================================================================================
200  the file exists under the root
403  the request path tried to leave the root — see below; this is decided BEFORE any
     filesystem read, so a traversal never becomes a 200 and never becomes a read
404  a miss under ``/assets/`` or ``/bundle/``: those are file prefixes, not routes
405  a method other than GET or HEAD
413  the file is larger than the per-response byte ceiling — see below
503  the web root was not bundled, or it was bundled without an ``index.html``
===  ==================================================================================

WHAT ONE RESPONSE MAY CARRY, AND WHY THIS MODULE OWNS THE NUMBER
----------------------------------------------------------------
:data:`DEFAULT_MAX_RESPONSE_BYTES` is a ceiling on the bytes any single response may
carry, overridable by ``$MAINLINE_MAX_RESPONSE_BYTES``. It lives *here*, rather than in
:mod:`mainline_demo_api.app`, because both surfaces need it and this is the module the
other one already imports — ``app`` imports ``static_site``, never the reverse, and this
module still imports nothing outside the standard library.

The reason it exists is the deployment shape, not a style preference. This origin is a
Lambda Function URL with ``authorization_type = NONE``, and the largest object it can
emit is the multiplier in a sustained-egress flood: at the measured 1,554,168 B for the
console's largest source map, concurrency 10 for 30 days is roughly USD 33,000 of egress.
The ceiling turns "the biggest thing this origin can emit" from whatever the build
happened to produce into a **declared number**, and
``tests/test_response_contract.py`` ratchets it against the tree that is actually built.

**It bounds bytes PER REQUEST. It does not bound request RATE, and it is not a rate
limit.** A flood of small responses is entirely unaffected by it; the only thing bounding
rate on this deployment is the AWS account's concurrency ceiling. That sentence is here so
nobody reads a 413 in a log as evidence of throttling.

A refusal is a 413 problem document, in the same shape as every other error on both
surfaces. Nothing here raises.

Anything else that misses — ``/``, ``/permits/abc``, a stray link — is ``index.html``
with ``Cache-Control: no-cache``. Hash routing means a deep link never reaches the
server, but a stray path must not 404 into a blank page.

``/assets/`` and ``/bundle/`` are excluded from that fallback on purpose. Vite emits
content-hashed asset names, so a miss there means the bundle is internally inconsistent;
answering it with ``index.html`` hands the browser HTML where it asked for a module and
produces ``Uncaught SyntaxError: Unexpected token '<'``, which names nothing. A 404 that
names the missing file is the difference between a five-minute fix and an hour.

CACHING
-------
``/assets/*``   ``public, max-age=31536000, immutable`` — the name carries the content
                hash, so the URL changes when the bytes change and the answer is true
                forever.
``index.html``  ``no-cache`` — it is the map to those hashes. A cached map is how a
                browser asks for an asset the next deploy deleted.
``/bundle/*``   ``public, max-age=60`` — the EvidenceBundle is signed but NOT
                content-addressed in its URL, and a judge refreshing after a redeploy
                must not be shown a stale attestation.

REFUSING TO LEAVE THE ROOT
--------------------------
The path is percent-decoded **exactly once** — ``%2e%2e%2f`` is a traversal attempt and
must be seen as ``../``; ``%252e%252e%252f`` is *not*, and decoding twice would invent an
attack out of a literal filename. Then, before the filesystem is touched:

* any segment equal to ``..`` is refused;
* a backslash anywhere is refused (it is a separator on Windows, where this is developed);
* a segment shaped like a drive letter (``C:``) is refused, because ``Path('web') /
  'C:/Windows'`` is ``C:/Windows`` — a join with an absolute component discards the root;
* a NUL byte is refused.

Then the joined path is ``resolve()``d — which follows symlinks — and asserted to be the
root itself or inside it. That last check is what makes a symlink pointing out of the
bundle a 403 rather than an exfiltration primitive.
"""

from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote

__all__ = [
    "API_PREFIX",
    "ASSET_PREFIXES",
    "BUNDLE_CACHE_CONTROL",
    "DEFAULT_CACHE_CONTROL",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DEFAULT_ROOT_NAME",
    "FALLBACK_MEDIA_TYPE",
    "IMMUTABLE_CACHE_CONTROL",
    "INDEX_CACHE_CONTROL",
    "INDEX_NAME",
    "MEDIA_TYPES",
    "RESPONSE_BYTES_ENV",
    "WEB_ROOT_ENV",
    "Refused",
    "is_api_path",
    "max_response_bytes",
    "media_type",
    "resolve",
    "serve",
    "web_root",
]

#: Everything under this prefix belongs to the API and never reaches this module.
API_PREFIX: Final = "/v1"

#: The environment variable a deploy sets to point at an unpacked site.
WEB_ROOT_ENV: Final = "MAINLINE_WEB_ROOT"

#: The environment variable that overrides the per-response byte ceiling.
RESPONSE_BYTES_ENV: Final = "MAINLINE_MAX_RESPONSE_BYTES"

#: 2 MiB. Chosen so nothing legitimate breaks today and not one byte lower: the largest
#: object in the built web tree measures 1,554,168 B (``assets/index-BjAGxrVJ.js.map``),
#: which is 74.1 % of this. A ceiling under that number would 413 the console's own
#: source map, and the first symptom would be DevTools quietly refusing to map a stack
#: trace — a control that broke the thing it was protecting, discovered by nobody.
#: Lowering it is a real lever — the deploy-safety plan costs 512 KiB at roughly a 3.6-fold
#: reduction in the flood's multiplier — but it is a lever that must be pulled in the same
#: change as a source-map strip, not before one.
DEFAULT_MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024

#: The directory name the bundler writes, relative to the package or to the task root.
DEFAULT_ROOT_NAME: Final = "web"

INDEX_NAME: Final = "index.html"

#: Prefixes whose misses are 404s rather than the SPA fallback. See the module docstring.
ASSET_PREFIXES: Final[tuple[str, ...]] = ("assets", "bundle")

IMMUTABLE_CACHE_CONTROL: Final = "public, max-age=31536000, immutable"
INDEX_CACHE_CONTROL: Final = "no-cache"
BUNDLE_CACHE_CONTROL: Final = "public, max-age=60"
DEFAULT_CACHE_CONTROL: Final = "public, max-age=60"

#: Suffix → media type. Everything the console's ``dist/`` can contain, plus the evidence
#: bundle's ``.json``. A type this table does not name is served as an opaque stream and
#: base64-encoded, which is wrong for nothing and merely unhelpful for text.
MEDIA_TYPES: Final[Mapping[str, str]] = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/vnd.microsoft.icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    # A source map is JSON. Naming it explicitly matters because `Path('.js.map').suffix`
    # is `.map`, not `.js`, and a map served as JavaScript makes DevTools refuse it.
    ".map": "application/json; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".wasm": "application/wasm",
    ".webmanifest": "application/manifest+json",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}

FALLBACK_MEDIA_TYPE: Final = "application/octet-stream"

#: How much of a caller-supplied request path the 413 refusal is allowed to echo. It is
#: the one response `_within_ceiling` does not weigh, so its length may not be the
#: caller's to choose. 200 is long enough to identify any path in the bundled site.
_ECHO_LIMIT: Final = 200

#: A segment shaped like a Windows drive specifier. `Path('web').joinpath('C:', 'x')` is
#: `C:x` on Windows and the root is silently discarded, so this is refused by name rather
#: than left to the containment check.
_DRIVE = re.compile(r"^[A-Za-z]:")


class Refused(ValueError):
    """A request path this module refused to turn into a filesystem path.

    Carries *vector* — a short, stable token naming WHICH rule refused — so a log line
    and a test can both say `dot_dot` rather than matching on prose.
    """

    __slots__ = ("detail", "vector")

    def __init__(self, vector: str, detail: str) -> None:
        super().__init__(detail)
        self.vector = vector
        self.detail = detail


# ── Where the site is ───────────────────────────────────────────────────────────────


def web_root() -> Path:
    """Return the directory this module serves from. Never raises; may not exist."""
    override = os.environ.get(WEB_ROOT_ENV)
    if override:
        return Path(override)
    here = Path(__file__).resolve().parent
    candidates = (here / DEFAULT_ROOT_NAME, here.parent / DEFAULT_ROOT_NAME)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def max_response_bytes() -> int:
    """Return the byte ceiling one response may carry. Never raises.

    ``$MAINLINE_MAX_RESPONSE_BYTES`` wins when it parses as a positive integer;
    otherwise :data:`DEFAULT_MAX_RESPONSE_BYTES` applies.

    **A value that does not parse is ignored rather than fatal, and that is a deliberate
    trade.** The alternative — raising — turns one typo in a Terraform ``environment``
    block into a handler that answers every request, including ``/v1/health``, with a
    runtime-shaped 502 carrying a stack trace, i.e. a total outage caused by a cost
    control. Falling back means a misconfigured deploy silently enforces 2 MiB instead of
    the number somebody meant, so the cost of this choice is real and is paid here: the
    ceiling actually in force is written into the body of every 413 it produces, which
    makes the effective value readable from the refusal itself rather than inferable from
    the environment.

    It is read on each call, not captured at import. A Lambda's environment is fixed for
    the life of a container, so this costs one dict lookup and buys a module that can be
    tested without reloading it.
    """
    raw = os.environ.get(RESPONSE_BYTES_ENV)
    if raw is None:
        return DEFAULT_MAX_RESPONSE_BYTES
    try:
        value = int(raw.strip())
    except ValueError:
        return DEFAULT_MAX_RESPONSE_BYTES
    return value if value > 0 else DEFAULT_MAX_RESPONSE_BYTES


def is_api_path(path: str) -> bool:
    """Report whether *path* belongs to the JSON API and must not be served as a file."""
    return path == API_PREFIX or path.startswith(f"{API_PREFIX}/")


def media_type(name: str) -> str:
    """Media type for a file *name*, by suffix, lower-cased."""
    suffix = Path(name).suffix.lower()
    return MEDIA_TYPES.get(suffix, FALLBACK_MEDIA_TYPE)


# ── Turning a request path into a file ──────────────────────────────────────────────


def _segments(request_path: str) -> list[str]:
    """Decode *request_path* once and split it, refusing anything that could escape.

    Raises:
        Refused: with a ``vector`` of ``nul``, ``backslash``, ``dot_dot`` or ``drive``.
    """
    decoded = unquote(request_path or "/")
    if "\x00" in decoded:
        raise Refused("nul", "the request path contains a NUL byte")
    if "\\" in decoded:
        raise Refused(
            "backslash",
            "the request path contains a backslash, which is a path separator on the "
            "platform this is developed on and is never part of a URL path",
        )
    parts: list[str] = []
    for part in decoded.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise Refused("dot_dot", "the request path contains a '..' segment")
        if _DRIVE.match(part):
            raise Refused("drive", f"the request path contains an absolute segment {part!r}")
        parts.append(part)
    return parts


def resolve(request_path: str, root: Path) -> tuple[Path, str]:
    """Map *request_path* to a real path inside *root*.

    Returns ``(absolute_path, relative_posix_path)``. ``/`` maps to ``index.html``.
    The path is resolved — following symlinks — and asserted to be the root or inside
    it. Nothing is read and nothing is stat'd for existence here; a refusal is decided by
    the request alone, so a traversal cannot become a 200 whatever is on disk.

    Raises:
        Refused: the path is not expressible inside *root*.
    """
    parts = _segments(request_path)
    real_root = Path(root).resolve()
    target = real_root.joinpath(*parts) if parts else real_root / INDEX_NAME
    real_target = target.resolve()
    if real_target != real_root and not real_target.is_relative_to(real_root):
        raise Refused(
            "escapes_root",
            f"the request path resolves to {real_target}, which is outside the web root",
        )
    relative = "" if real_target == real_root else real_target.relative_to(real_root).as_posix()
    return real_target, relative


def _cache_control(relative: str) -> str:
    if relative.startswith("assets/"):
        return IMMUTABLE_CACHE_CONTROL
    if relative.startswith("bundle/"):
        return BUNDLE_CACHE_CONTROL
    if relative == INDEX_NAME:
        return INDEX_CACHE_CONTROL
    return DEFAULT_CACHE_CONTROL


# ── Responses ───────────────────────────────────────────────────────────────────────


def _problem(status: int, kind: str, detail: str, **extra: Any) -> dict[str, Any]:
    """Build the same error shape ``app._problem`` emits, without importing it.

    ``console/src/data/transport.ts`` classifies any non-2xx with no envelope as a
    ``status`` transport failure and shows the body, so one shape for both surfaces means
    a judge reads one kind of error message whatever they hit.
    """
    body = {"error": {"kind": kind, "status": status, "detail": detail, **extra}}
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "x-mainline-api": "demo-static",
        },
        "body": json.dumps(body, sort_keys=True, separators=(",", ":")),
        "isBase64Encoded": False,
    }


def _too_large(
    where: str, wire: int, ceiling: int, *, on_disk: int | None = None
) -> dict[str, Any]:
    """Refuse a response above the ceiling. Built as a literal, and never measured.

    **This does not go through** :func:`_problem`, **and** :func:`_within_ceiling` **never
    measures what it returns.** If either were otherwise, a ceiling smaller than this body
    would send the refusal back into the check that produced it: recursion, or a 413
    answered with a 413. A control that can refuse its own refusal answers nothing.

    Being the one unmeasured response makes its size an obligation rather than an
    observation, which is why *where* is truncated. It is the caller's own request path,
    and a Function URL accepts a long one; echoing it whole would let a caller choose the
    length of the only body this module does not check. Truncated it is fixed prose, three
    integers and at most :data:`_ECHO_LIMIT` characters — a bound by construction, which is
    the only kind available to a response that is never weighed. The amplification was
    about 1:1 either way, so this closes a statement, not a flood.

    *wire* is what would go out; *on_disk* is the file when the refusal came from one.
    They differ whenever the body is base64, and reporting only the first would leave a
    caller unable to tell whether the fix is a smaller file or a different media type.
    """
    if len(where) > _ECHO_LIMIT:
        where = f"{where[:_ECHO_LIMIT]}… ({len(where)} characters, truncated)"
    body = {
        "error": {
            "kind": "response_too_large",
            "status": 413,
            "detail": (
                f"{where} would put {wire} bytes on the wire and the ceiling in force is "
                f"{ceiling}. This bounds the bytes ONE response may carry; it is NOT a "
                "rate limit and bounds nothing about how often this may be asked for. Set "
                f"${RESPONSE_BYTES_ENV} to change it, or ship a smaller artefact — for the "
                "console's source maps the smaller artefact is the intended answer."
            ),
            "path": where,
            "bytes": wire,
            "bytes_on_disk": on_disk,
            "ceiling_bytes": ceiling,
            "ceiling_env": RESPONSE_BYTES_ENV,
        }
    }
    return {
        "statusCode": 413,
        "headers": {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "x-mainline-api": "demo-static",
        },
        "body": json.dumps(body, sort_keys=True, separators=(",", ":")),
        "isBase64Encoded": False,
    }


def _within_ceiling(response: dict[str, Any], request_path: str) -> dict[str, Any]:
    """Measure the finished body and refuse it above the ceiling. The one measurement.

    Putting the measurement at the exit rather than at each construction site is what
    makes the property statable: *no response this module emits exceeds the ceiling*. The
    first version of this control lived inside :func:`_file` alone, which left every problem
    document — 403, 404, 405, 503, each of which echoes the caller's own request path —
    unmeasured. That is exactly the shape of defect this repository refuses elsewhere: a
    control present on the path somebody thought of and absent from the rest.

    The body is measured as UTF-8 bytes. Base64 is ASCII, so for an encoded body that is
    its character count; for a text body it is the file's own bytes. Either way it is what
    AWS bills egress on, which is the number this ceiling exists to bound.
    """
    wire = len(str(response["body"]).encode("utf-8"))
    ceiling = max_response_bytes()
    if wire <= ceiling:
        return response
    return _too_large(request_path, wire, ceiling)


def _file(path: Path, relative: str, *, head: bool) -> dict[str, Any]:
    """Answer 200 with *path*'s bytes, base64-encoded unless they are valid UTF-8 text.

    The Lambda Function URL payload contract (format 2.0) carries the body as a JSON
    string, so a byte that is not valid UTF-8 has to be base64 and ``isBase64Encoded``
    has to say so. Text is sent as text because a judge running ``curl`` on the URL and a
    developer reading the CloudWatch log both benefit, and because base64 costs 33 % on
    every asset otherwise.

    The ceiling is consulted twice here, and neither is the module's exit check:

    * against ``stat().st_size`` **before the file is read** — an optimisation, not the
      control. Base64 only ever grows a payload, so a file already over the ceiling cannot
      produce a body under it, and reading it would be exactly the pointless work this
      ceiling exists to refuse.
    * against the **described** body afterwards, which is the only check that can see a
      ``HEAD``. :func:`_within_ceiling` measures what is emitted, and a ``HEAD`` emits
      nothing — so without this, a ``HEAD`` on a 1.6 MiB font would answer 200 with a
      ``content-length`` the matching ``GET`` refuses to deliver. That is a lie told by
      the cheaper method, and the caller most likely to send ``HEAD`` is the one probing
      for exactly that discrepancy.

    :func:`_within_ceiling` remains the control for everything else this module emits,
    problem documents included.
    """
    ceiling = max_response_bytes()
    on_disk = path.stat().st_size
    if on_disk > ceiling:
        return _too_large(relative, on_disk, ceiling, on_disk=on_disk)

    content_type = media_type(path.name)
    raw = path.read_bytes()
    encoded = False
    body: str
    try:
        body = raw.decode("utf-8")
    except UnicodeDecodeError:
        body = base64.b64encode(raw).decode("ascii")
        encoded = True
    else:
        if "charset=utf-8" not in content_type and content_type != "image/svg+xml":
            # Valid UTF-8 is not evidence of a text format: a small PNG can decode. The
            # media type decides, and only the types this module declares as text are
            # sent as text.
            body = base64.b64encode(raw).decode("ascii")
            encoded = True

    # Base64 is ASCII, so its character count is its byte count. Text was decoded from
    # `raw`, so `len(raw)` is its wire length exactly — no second encode, and no chance of
    # the two numbers disagreeing.
    wire = len(body) if encoded else len(raw)
    if wire > ceiling:
        return _too_large(relative, wire, ceiling, on_disk=len(raw))

    return {
        "statusCode": 200,
        "headers": {
            "content-type": content_type,
            "cache-control": _cache_control(relative),
            "content-length": str(len(raw)),
            "x-mainline-api": "demo-static",
            "x-mainline-static": relative,
        },
        "body": "" if head else body,
        "isBase64Encoded": False if head else encoded,
    }


def serve(method: str, request_path: str, *, root: Path | str | None = None) -> dict[str, Any]:
    """Answer one non-``/v1`` request with a Lambda payload-format-2.0 response dict.

    *root* defaults to :func:`web_root`. Never raises: every failure is a status and a
    JSON body that names it.

    This is a two-line function on purpose. It is the module's only exit, so it is the one
    place where "no response this module emits exceeds the ceiling" can be made true of
    *every* response rather than of the ones somebody remembered — see
    :func:`_within_ceiling`.
    """
    return _within_ceiling(_answer(method, request_path, root=root), request_path)


def _answer(  # noqa: PLR0911 - one return per HTTP status, and the statuses ARE the
    # interface: 403 refused, 404 asset miss, 405 wrong method, 413 too large, 503 no
    # bundle, 200 file, 200 index. Collapsing them would mean composing the status from a
    # variable, which is exactly how a 403 becomes a 200 in a refactor nobody reviewed.
    method: str,
    request_path: str,
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Decide the answer. :func:`serve` is the public entry point and measures the result."""
    upper = (method or "GET").upper()
    if upper not in ("GET", "HEAD"):
        return _problem(
            405,
            "method_not_allowed",
            f"the static surface serves GET and HEAD; {upper} {request_path} is not a route",
            allow=["GET", "HEAD"],
        )

    base = web_root() if root is None else Path(root)

    # Refusal is decided from the request, before the root is even known to exist, so a
    # traversal answers 403 on a broken deploy exactly as it does on a good one.
    try:
        target, relative = resolve(request_path, base)
    except Refused as exc:
        return _problem(
            403,
            "path_refused",
            exc.detail,
            vector=exc.vector,
            path=request_path,
        )

    if not base.is_dir():
        return _problem(
            503,
            "web_root_not_bundled",
            f"the web root was not bundled: {base} is not a directory. The API surface is "
            f"unaffected — {API_PREFIX}/health and the {API_PREFIX} resources answer from "
            f"this same handler — but no site was packaged beside it. Set ${WEB_ROOT_ENV} "
            "or rebuild the deployment artefact with the console's dist/ included.",
            web_root=str(base),
            web_root_env=WEB_ROOT_ENV,
        )

    head = upper == "HEAD"
    if target.is_file():
        return _file(target, relative, head=head)

    first = relative.split("/", 1)[0]
    if first in ASSET_PREFIXES:
        return _problem(
            404,
            "asset_not_found",
            f"{relative} is not in the bundled site. Paths under "
            f"{'/, '.join(ASSET_PREFIXES)}/ are files, not routes, so this is a miss and "
            "not a deep link: the artefact is internally inconsistent.",
            path=request_path,
        )

    index = base / INDEX_NAME
    if not index.is_file():
        return _problem(
            503,
            "web_root_not_bundled",
            f"the web root {base} exists but carries no {INDEX_NAME}, so there is no site "
            f"to serve. The API surface is unaffected: {API_PREFIX}/health answers from "
            "this same handler.",
            web_root=str(base),
            web_root_env=WEB_ROOT_ENV,
        )
    return _file(index, INDEX_NAME, head=head)
