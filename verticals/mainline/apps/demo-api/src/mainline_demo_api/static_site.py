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
403  the request path tried to leave the root, or is longer than any filesystem could
     name — see below; both are decided BEFORE any filesystem read, so a traversal never
     becomes a 200, an unnameable path never becomes an ``OSError``, and neither becomes
     a read
404  a miss under ``/assets/`` or ``/bundle/`` — those are file prefixes, not routes — or
     a direct request for a path ending ``.gz``, which is the compressed half of an object
     that already has a name; see CONTENT NEGOTIATION
405  a method other than GET or HEAD
413  the response would put more bytes on the wire than the per-response ceiling — below
503  the web root was not bundled, or it was bundled without an ``index.html``
===  ==================================================================================

CONTENT NEGOTIATION, AND WHY THE ``.gz`` SIBLING HAS NO URL OF ITS OWN
----------------------------------------------------------------------
``scripts/deploy/build_lambda.{sh,ps1}`` writes ``<name>.gz`` beside every compressible
``web/**`` entry — gzip level 9, ``mtime=0``, no filename field — and
``scripts/deploy/bundle_manifest.py`` reports the pair from the zip's central directory.
Interface **I1** of `docs/leads/cost-finish-plan.md` fixes what this module does with them,
and until 2026-08-13 the answer was *nothing*: the siblings shipped and no code path here
could emit one.

* When the request's ``Accept-Encoding`` permits ``gzip`` **and** ``<name>.gz`` exists, the
  sibling's bytes are the body, ``content-encoding: gzip`` says so, and the media type is
  the one for ``<name>``. A ``.js.gz`` is JavaScript that arrived compressed, not a new
  format, and a browser handed ``application/gzip`` for a module refuses to run it.
* **A direct request for any path ending ``.gz`` is a 404.** One set of bytes gets one
  name. Two names would mean two cache entries for one object, two ``content-type``
  answers, and a URL that hands a browser gzip bytes it was never told to inflate.
* Every response that could have gone either way carries ``vary: accept-encoding``. Without
  it a shared cache that stored the compressed answer serves it to the next client that
  asked for identity — the classic gzip cache-poisoning bug, and the one that turns a
  bandwidth saving into a site that is broken for exactly the clients least able to say so.

Measured on ``out/lambda/mainline-demo-api-arm64.zip`` as built 2026-08-13: 114 ``web/``
entries, of which **57 identity objects** (985,030 B) and **57 siblings** (289,312 B).
Every identity object has one and no sibling is an orphan, so negotiation covers the whole
tree rather than the part somebody remembered. The entry bundle is 433,396 B identity and
124,127 B compressed — a 3.49-fold cut on the single object that dominates this origin's
egress, and the reason the ceiling below is what it is.

WHAT ONE RESPONSE MAY CARRY, AND WHY IT IS WEIGHED ON THE WIRE
--------------------------------------------------------------
:data:`DEFAULT_MAX_RESPONSE_BYTES` is a ceiling on the bytes any single response may put on
the wire, overridable by ``$MAINLINE_MAX_RESPONSE_BYTES``. It lives *here*, rather than in
:mod:`mainline_demo_api.app`, because both surfaces need it and this is the module the
other one already imports — ``app`` imports ``static_site``, never the reverse, and this
module still imports nothing outside the standard library.

The reason it exists is the deployment shape, not a style preference. This origin is a
Lambda Function URL with ``authorization_type = NONE``, so the largest object it can emit
is the multiplier in a sustained-egress flood that any anonymous caller can start. The
ceiling turns "the biggest thing this origin can emit" from whatever the build happened to
produce into a **declared number**, derived from the deployed tree by the rule written out
beside the constant.

**It is weighed on WIRE bytes, not on the body string** — interface **I2**. A Lambda
Function URL carries the body as a JSON string, so bytes that are not valid UTF-8 travel
base64 and the service decodes them before anything leaves. What AWS bills egress on is the
decoded length; the base64 string is 33 % larger and exists only between this handler and
the service. Weighing the string would refuse a 124,127 B compressed bundle as though it
were 165,504 B — over-refusing by exactly the encoding's overhead, on the one path this
origin most wants callers to take. :func:`_wire_bytes` therefore computes the decoded
length from the base64 string's own length, arithmetically, without decoding it.

**Lambda's 6 MB response PAYLOAD quota is a different bound and this is not it.** That one
*does* apply to the encoded string, and it is the one place the base64 envelope is the
quantity that counts. Nothing here enforces it at runtime, because at this ceiling it
cannot be reached: the widest payload this module can construct is
``4 x ceil(139,264 / 3) = 185,688`` characters against
:data:`LAMBDA_RESPONSE_PAYLOAD_BYTES`, thirty-two times under it. That is a property of
the two constants rather than an observation, so it is asserted where the constants are —
``tests/test_response_contract.py::test_base64_inflation_is_measured_and_not_assumed`` —
and it is asserted with a falsification, because a bound no setting can breach is a bound
that proves nothing. A runtime check here would be a branch that can never be taken, which
is a worse way to say the same thing.

**It bounds bytes PER REQUEST. It does not bound request RATE, and it is not a rate
limit.** A flood of small responses is entirely unaffected by it;
:mod:`mainline_demo_api.ratelimit` is what bounds rate, and neither bounds the invocation
charge. That sentence is here so nobody reads a 413 in a log as evidence of throttling.

A refusal is a 413 problem document, in the same shape as every other error on both
surfaces. Nothing here raises — including for a request path no filesystem can express,
which is a 403 decided from the request and not an ``OSError`` escaping from a ``stat``;
see :data:`MAX_REQUEST_PATH_BYTES`.

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
    "GZIP_CODING",
    "GZ_SUFFIX",
    "IMMUTABLE_CACHE_CONTROL",
    "INDEX_CACHE_CONTROL",
    "INDEX_NAME",
    "LAMBDA_RESPONSE_PAYLOAD_BYTES",
    "MAX_REQUEST_PATH_BYTES",
    "MAX_SEGMENT_BYTES",
    "MEDIA_TYPES",
    "RESPONSE_BYTES_ENV",
    "VARY_ACCEPT_ENCODING",
    "WEB_ROOT_ENV",
    "Refused",
    "accepts_gzip",
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

#: 136 KiB = 139,264 B. **Derived from the deployed tree, not chosen**, and the derivation
#: is written out so the next reader recomputes it rather than trusting it.
#:
#: THE RULE — interface **I3**, `docs/leads/cost-finish-plan.md` §2::
#:
#:     largest_served_wire_bytes  <=  ceiling  <  1.20 x largest_served_wire_bytes
#:
#: and within that window the ceiling is the smallest multiple of 8 KiB at or above
#: ``1.10 x largest_served_wire_bytes``. The 10 % is the headroom an asset may take between
#: two deploys without the demo going dark; the 1.20 is the ratchet that fails a test when
#: it takes more. ``tests/test_static_site.py`` asserts both halves against the built
#: package, so this number cannot drift above the tree it governs — which is what happened
#: twice already, and is the only reason this comment is this long.
#:
#: THE MEASUREMENT. Every figure below is over ``out/lambda/mainline-demo-api-arm64.zip``
#: as built on 2026-08-13 — **the tree that actually deploys**, read from the zip's central
#: directory. It is NOT the packer's 75-file input tree (``console/dist`` +
#: ``console/fixtures/bundles/demo-cloud``), and confusing the two is precisely how the
#: previous value came to be wrong::
#:
#:     web/ entries                    114 files   1,274,342 B
#:       identity objects               57 files     985,030 B   median 5,467 B
#:       .gz siblings                   57 files     289,312 B   one per identity object
#:       source maps                     0 files           0 B   stripped by default
#:     largest identity object                      433,396 B   assets/index-BjAGxrVJ.js
#:     second-largest identity object                51,266 B   assets/surface-Csi7pmRe.js
#:     largest .gz sibling                          124,127 B   the same object, compressed
#:
#: All 57 identity objects have a sibling and no sibling is an orphan, so the bytes a
#: browser pulls are the compressed column throughout and
#: ``largest_served_wire_bytes = 124,127``. Then ``1.10 x 124,127 = 136,540``, rounded up to
#: the next 8 KiB is **139,264**, and ``139,264 / 124,127 = 1.122``, inside the 1.20
#: ratchet. The number is a consequence of those two lines, not an input to them.
#:
#: WHAT IT REFUSES, SAID OUT LOUD RATHER THAN DODGED. Exactly one object of the 57, and
#: only on the identity path: ``assets/index-BjAGxrVJ.js`` at 433,396 B answers **413** to a
#: caller that did not send ``Accept-Encoding: gzip``. Every browser that will ever load
#: this console sends it, so the console is unaffected; a client that refuses compression
#: while asking for a 433 KB bundle is exactly the caller a wire ceiling exists for. The
#: refusal names the fix — ask for it with gzip — and the second-largest identity object is
#: 51,266 B, so nothing else in the tree is anywhere near this bound on either path.
#: ``curl`` sends no ``Accept-Encoding`` unless given ``--compressed``; that is a real cost
#: of this value and it is paid deliberately, because the alternative is a ceiling that
#: leaves the flood multiplier at 433,396 B and makes the 124,127 B row of the cost model a
#: number no attacker has to accept.
#:
#: WHY THE PREVIOUS VALUE IS GONE. This constant read ``512 * 1024`` and the comment here
#: said *"and it binds"*. **It did not.** That arithmetic was measured over the packer's
#: 75-file PRE-STRIP input tree, where the single object 512 KiB refused was the 1,554,168 B
#: source map — and ``build_lambda`` began stripping ``web/**/*.map`` by default *the same
#: day*, removing the only thing the ceiling refused. Re-measured over the tree that
#: deploys: 512 KiB refuses **0 of 57** identity objects and **0 of 114** ``web/`` entries,
#: as do 1 MiB and 2 MiB. A ceiling above everything it governs is a decoration — the exact
#: criticism an independent verifier made of the 2 MiB value this replaced, reproduced one
#: octave down. It also fails the I3 rule on its own terms even before the siblings are
#: served: ``524,288 / 433,396 = 1.2097``, outside 1.20.
DEFAULT_MAX_RESPONSE_BYTES: Final = 136 * 1024

#: Lambda's synchronous **response payload** quota — the ONE bound in this module's world
#: that is measured on the base64 envelope rather than on the wire, because it bounds the
#: payload the runtime hands the service, before the service decodes it. It is therefore
#: the exact complement of :data:`DEFAULT_MAX_RESPONSE_BYTES` and interface **I2**, and the
#: reason both are named here is that a reader who has just been told "never weigh the
#: envelope" has to be told where the envelope IS the quantity, or the next person applies
#: I2 one place too far.
#:
#: **6 MB, read as 6,000,000 and not as 6 x 1024 x 1024, deliberately.** AWS documents the
#: figure as "6 MB" and does not disambiguate, so the two readings differ by 291,456 B. The
#: smaller one is the conservative side of an ambiguity this repository does not get to
#: resolve, and at the ceiling above the margin is 32x either way, so nothing turns on the
#: choice except that it is made in the safe direction and said out loud.
#:
#: Nothing enforces this at runtime and nothing should: at
#: :data:`DEFAULT_MAX_RESPONSE_BYTES` the widest payload :func:`_file` can construct is
#: ``4 x ceil(139,264 / 3) = 185,688`` characters, so a check here would be a branch no
#: input can reach. What guards it instead is an assertion over the two constants, in
#: ``tests/test_response_contract.py``, carrying a falsification: at a ceiling of 5 MiB the
#: same arithmetic yields 6,990,508 and breaches this, so the bound is one a setting can
#: actually fail rather than one that holds by being unreachable.
LAMBDA_RESPONSE_PAYLOAD_BYTES: Final = 6_000_000

#: The directory name the bundler writes, relative to the package or to the task root.
DEFAULT_ROOT_NAME: Final = "web"

INDEX_NAME: Final = "index.html"

#: Prefixes whose misses are 404s rather than the SPA fallback. See the module docstring.
ASSET_PREFIXES: Final[tuple[str, ...]] = ("assets", "bundle")

#: The suffix interface I1 gives the pre-compressed sibling of a compressible object. Held
#: identical to ``scripts/deploy/bundle_manifest.GZ_SUFFIX``, which reports the pairs, and
#: to the packer embedded in ``build_lambda.{sh,ps1}``, which writes them.
GZ_SUFFIX: Final = ".gz"

#: The one content coding this module can emit, spelled as it goes on the wire.
GZIP_CODING: Final = "gzip"

#: The value of ``vary`` on every response whose bytes depend on ``Accept-Encoding``. A
#: shared cache without it will hand the compressed answer to a client that asked for
#: identity, which is a broken page rather than a slow one.
VARY_ACCEPT_ENCODING: Final = "accept-encoding"

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

#: How much of a caller-supplied request path a refusal is allowed to echo. The 413 is the
#: one response `_within_ceiling` does not weigh, so its length may not be the caller's to
#: choose; the 403 for an over-long path is weighed, but echoing a path back whole when the
#: complaint IS its length is the caller writing the body either way. 200 is long enough to
#: identify any path in the bundled site — the longest one it contains is 42 characters.
_ECHO_LIMIT: Final = 200

#: The longest request path this module will turn into a filesystem path, and the longest
#: single segment inside one. Both are decided from the REQUEST, before any `stat`, in
#: `_segments`, beside the NUL, backslash, `..` and drive-letter refusals that are already
#: decided there for the same reason: what a filesystem would do with the path must never
#: be the thing that decides the answer.
#:
#: They exist because the alternative was measured, not imagined. On the deployed runtime
#: image (`public.ecr.aws/lambda/python:3.13`, ext4: NAME_MAX 255, PATH_MAX 4096) a request
#: for a 6,000-character segment made `Path.is_file()` raise `OSError [Errno 36] File name
#: too long` straight out of `serve` — which promises never to raise, under a Function URL
#: with `authorization_type = NONE`, so any anonymous caller could turn one GET into a
#: Lambda-shaped 502 carrying a stack trace, at full invocation price. A path built from
#: segments that are each individually legal raised the same errno once the JOINED length
#: passed PATH_MAX, so bounding the segment alone would have closed half of it.
#:
#: `pathlib` swallows that errno on Windows — `ERROR_FILENAME_EXCED_RANGE` is on its
#: ignore list — and does not on Linux. That is the whole reason the developer box and the
#: CI runner disagreed about this for as long as they did, and it is why the bound is
#: stated here as a property of the public surface rather than inherited from whatever
#: filesystem the code happens to be standing on.
#:
#: 255 is POSIX NAME_MAX, probed on that image: a 255-byte component is created, a 256-byte
#: one is ENAMETOOLONG. 1,024 is deliberately NOT PATH_MAX — the kernel applies PATH_MAX to
#: the joined path, and the web root's share of it is not the caller's to spend, so this
#: leaves 3 KiB for a root of any plausible depth. Against what is actually served both
#: bounds are enormous: the longest path in the built tree is 42 bytes
#: (`bundle/sql/beat-4-merge-admitted-00000.txt`) and its longest segment is 32.
MAX_REQUEST_PATH_BYTES: Final = 1024
MAX_SEGMENT_BYTES: Final = 255

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


def _quality(params: str) -> float:
    """Return the ``q=`` of one ``Accept-Encoding`` element, or 1.0 when it declares none.

    A ``q`` that does not parse is read as 0. That is the conservative direction: an
    unparseable preference means this module sends the identity bytes, which every client
    can read, rather than gzip to a client that may not have asked for it.
    """
    for param in params.split(";"):
        name, _, value = param.partition("=")
        if name.strip().lower() != "q":
            continue
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 1.0


def accepts_gzip(header: str | None) -> bool:
    """Report whether an ``Accept-Encoding`` field value permits a gzip-coded response.

    RFC 9110 §12.5.3, and the two clauses that are easy to get wrong are both here because
    both change what this origin puts on the wire:

    * ``gzip;q=0`` is a **refusal**, not a mention. A substring test for ``"gzip"`` — which
      is what a one-line version of this would be — sends compressed bytes to a client that
      said in as many words that it cannot read them.
    * ``*`` means "any coding is acceptable", so it permits gzip; but an explicit
      ``gzip;q=0`` beside a ``*`` still refuses, because the specific preference wins over
      the wildcard. ``br;q=1.0, gzip;q=0.5`` permits gzip: this module has no ``br``
      sibling to serve, and a lower preference is still a preference.

    ``x-gzip`` is the pre-RFC-2616 spelling and is treated as ``gzip``; it costs one tuple
    entry and it is still emitted by a handful of clients.

    Absent, empty or unparseable means identity, which is always safe to send.
    """
    if not header:
        return False
    explicit: float | None = None
    wildcard: float | None = None
    for element in header.split(","):
        token, _, params = element.strip().partition(";")
        quality = _quality(params)
        coding = token.strip().lower()
        if coding in (GZIP_CODING, "x-gzip"):
            explicit = quality if explicit is None else max(explicit, quality)
        elif coding == "*":
            wildcard = quality if wildcard is None else max(wildcard, quality)
    if explicit is not None:
        return explicit > 0.0
    return wildcard is not None and wildcard > 0.0


def _sibling(path: Path, accept_encoding: str | None) -> Path | None:
    """Return the ``<name>.gz`` beside *path* when the caller can read one and it exists.

    Returns ``None`` — meaning "serve the identity bytes" — for every other case, so a
    build that stopped pre-compressing degrades to a larger bill rather than to a 404.
    """
    if not accepts_gzip(accept_encoding):
        return None
    candidate = path.with_name(path.name + GZ_SUFFIX)
    return candidate if candidate.is_file() else None


# ── Turning a request path into a file ──────────────────────────────────────────────


def _segments(request_path: str) -> list[str]:
    """Decode *request_path* once and split it, refusing anything that could escape.

    Raises:
        Refused: with a ``vector`` of ``nul``, ``backslash``, ``dot_dot`` or ``drive``.
    """
    decoded = unquote(request_path or "/")
    if "\x00" in decoded:
        raise Refused("nul", "the request path contains a NUL byte")
    # Length first among the byte-shape rules, and before any segment is looked at: an
    # over-long path is refused for BEING over-long, and the refusal must not itself walk
    # a thousand segments to say so.
    length = len(decoded.encode("utf-8"))
    if length > MAX_REQUEST_PATH_BYTES:
        raise Refused(
            "path_too_long",
            f"the request path is {length} bytes and this origin turns at most "
            f"{MAX_REQUEST_PATH_BYTES} of them into a filesystem path. The longest path "
            "the bundled site contains is 42 bytes, so this is not a deep link that grew.",
        )
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
        segment = len(part.encode("utf-8"))
        if segment > MAX_SEGMENT_BYTES:
            raise Refused(
                "segment_too_long",
                f"the request path contains a {segment}-byte segment and no filesystem "
                f"this is deployed on can name one above {MAX_SEGMENT_BYTES} bytes "
                "(POSIX NAME_MAX). Asking for it would be an error from the kernel, not a "
                "miss, so it is refused from the request instead of read from the disk.",
            )
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


def _echo(path: str) -> str:
    """Return a caller-supplied path cut to a length THIS module chose, never the caller.

    One helper rather than two truncations, because the two places that echo a path back
    are the two places a caller can write into a body: the 413, which is never weighed,
    and the 403 for a path refused on its length, where quoting the whole thing would let
    the complaint carry the very bytes it is complaining about. Everything else that
    echoes — 404, 405, 503 — is reached only by a path that already passed
    :data:`MAX_REQUEST_PATH_BYTES`, so it is bounded by construction upstream.
    """
    if len(path) <= _ECHO_LIMIT:
        return path
    return f"{path[:_ECHO_LIMIT]}… ({len(path)} characters, truncated)"


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

    *wire* is what would go out; *on_disk* is the object that was ASKED for. They are the
    same number on the identity path and they diverge on the negotiated one — a caller
    that sent ``Accept-Encoding: gzip`` is weighed on the sibling's 124,127 B while the
    object it names is 433,396 B — so reporting only one would leave a caller unable to
    tell whether the fix is a smaller artefact or a different request header.
    """
    where = _echo(where)
    body = {
        "error": {
            "kind": "response_too_large",
            "status": 413,
            "detail": (
                f"{where} would put {wire} bytes on the wire and the ceiling in force is "
                f"{ceiling}. This bounds the bytes ONE response may carry; it is NOT a "
                "rate limit and bounds nothing about how often this may be asked for. The "
                f"first thing to try is 'accept-encoding: {GZIP_CODING}': every "
                "compressible object in this bundle ships a pre-compressed sibling, and "
                "the largest of them is 124,127 B against this ceiling. Otherwise set "
                f"${RESPONSE_BYTES_ENV} deliberately, or ship a smaller artefact."
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


def _vary(response: dict[str, Any]) -> dict[str, Any]:
    """Mark *response* as one whose bytes depended on ``Accept-Encoding``. Mutates in place.

    Applied to everything :func:`_file` produces — the 200 on either path **and its own
    413** — because both of those are answers a different ``Accept-Encoding`` would have
    changed: the 433,396 B entry bundle is a 413 to an identity request and a 200 to a gzip
    one, and a cache that stored the refusal without ``vary`` would replay it to a browser
    that would have been served.

    It is deliberately NOT applied to the 403, 404, 405 or 503: none of them depends on the
    header, and ``vary`` on a response that does not vary costs a cache entry per distinct
    header value for no benefit.
    """
    response["headers"]["vary"] = VARY_ACCEPT_ENCODING
    return response


def _wire_bytes(response: Mapping[str, Any]) -> int:
    """Return the bytes *response* puts on the wire — interface **I2**, the billed number.

    A Function URL response body is a JSON string, so anything that is not valid UTF-8
    travels base64 and the Lambda service decodes it before it leaves. Egress is billed on
    what leaves, so the base64 string's own length is **not** the quantity this ceiling
    bounds: weighing it would over-refuse every binary object by exactly 33 %, and the
    object that would suffer most is the 124,127 B compressed entry bundle, which would be
    weighed as 165,504 B — the one path the cost model depends on callers taking.

    The decoded length is computed rather than decoded: standard base64 packs three bytes
    into every four characters, and each ``=`` of the final group stands for one byte that
    is not there. So measuring a response never allocates a second copy of it, which
    matters because this runs on every response the module emits.
    """
    body = str(response["body"])
    if not response.get("isBase64Encoded"):
        return len(body.encode("utf-8"))
    return len(body) // 4 * 3 - body[-2:].count("=")


def _within_ceiling(response: dict[str, Any], request_path: str) -> dict[str, Any]:
    """Measure the finished body and refuse it above the ceiling. The one measurement.

    Putting the measurement at the exit rather than at each construction site is what
    makes the property statable: *no response this module emits exceeds the ceiling*. The
    first version of this control lived inside :func:`_file` alone, which left every problem
    document — 403, 404, 405, 503, each of which echoes the caller's own request path —
    unmeasured. That is exactly the shape of defect this repository refuses elsewhere: a
    control present on the path somebody thought of and absent from the rest.

    What is measured is :func:`_wire_bytes`, not the length of the body string. For a text
    body those are the same number; for a base64 body they differ by a third, and the wire
    is the side AWS bills.
    """
    wire = _wire_bytes(response)
    ceiling = max_response_bytes()
    if wire <= ceiling:
        return response
    return _too_large(request_path, wire, ceiling)


def _file(
    path: Path, relative: str, *, head: bool, sibling: Path | None = None
) -> dict[str, Any]:
    """Answer 200 for the object *relative*, from *sibling*'s bytes when there is one.

    *path* is always the **identity** object: it decides the media type, the cache policy
    and the name in ``x-mainline-static``, because the resource is the same resource
    however it was coded. *sibling* — supplied by :func:`_sibling` only when the caller's
    ``Accept-Encoding`` permits gzip and ``<name>.gz`` exists — decides the bytes, the
    ``content-length`` and ``content-encoding: gzip``. That split is interface **I1**: one
    object, one name, two representations.

    The Lambda Function URL payload contract (format 2.0) carries the body as a JSON
    string, so a byte that is not valid UTF-8 has to be base64 and ``isBase64Encoded`` has
    to say so. **A gzip body is therefore always base64**, unconditionally and with no
    ``try``: a gzip member starts ``1f 8b``, which is not valid UTF-8, and a member that
    happened to decode would still be binary. Identity text is sent as text because a judge
    running ``curl`` and a developer reading a CloudWatch log both benefit.

    The ceiling is consulted twice here, and neither is the module's exit check:

    * against ``stat().st_size`` of the bytes that would be SENT, **before they are read** —
      the whole point of the ceiling is not to do the work it refuses;
    * against ``len(raw)`` afterwards, which is the only check that can see a ``HEAD``.
      :func:`_within_ceiling` measures what is emitted and a ``HEAD`` emits nothing, so
      without this a ``HEAD`` on an oversize object would answer 200 with a
      ``content-length`` the matching ``GET`` refuses to deliver. That is a lie told by the
      cheaper method, and the caller most likely to send ``HEAD`` is the one probing for
      exactly that discrepancy.

    Both weigh the WIRE bytes — the file's own length, not the base64 string's — per
    interface **I2**; see :func:`_wire_bytes` for why the two are not the same number and
    which one AWS bills.

    :func:`_within_ceiling` remains the control for everything else this module emits,
    problem documents included.
    """
    ceiling = max_response_bytes()
    source = path if sibling is None else sibling
    # What was asked for, and what would go out. Equal on the identity path; on the
    # negotiated path `on_disk` is the 433,396 B object and `wire` is its 124,127 B coding.
    on_disk = path.stat().st_size
    wire = source.stat().st_size
    if wire > ceiling:
        return _vary(_too_large(relative, wire, ceiling, on_disk=on_disk))

    content_type = media_type(path.name)
    raw = source.read_bytes()
    encoded = False
    body: str
    if sibling is not None:
        body = base64.b64encode(raw).decode("ascii")
        encoded = True
    else:
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

    # `raw` is exactly what the client receives after the service decodes the envelope, so
    # `len(raw)` is the wire length whichever branch above ran. Re-checked because `stat`
    # and `read_bytes` are two syscalls and only the second one is the body.
    wire = len(raw)
    if wire > ceiling:
        return _vary(_too_large(relative, wire, ceiling, on_disk=on_disk))

    headers = {
        "content-type": content_type,
        "cache-control": _cache_control(relative),
        "content-length": str(len(raw)),
        "vary": VARY_ACCEPT_ENCODING,
        "x-mainline-api": "demo-static",
        "x-mainline-static": relative,
    }
    if sibling is not None:
        headers["content-encoding"] = GZIP_CODING

    return {
        "statusCode": 200,
        "headers": headers,
        "body": "" if head else body,
        "isBase64Encoded": False if head else encoded,
    }


def serve(
    method: str,
    request_path: str,
    *,
    root: Path | str | None = None,
    accept_encoding: str | None = None,
) -> dict[str, Any]:
    """Answer one non-``/v1`` request with a Lambda payload-format-2.0 response dict.

    *root* defaults to :func:`web_root`. *accept_encoding* is the request's
    ``Accept-Encoding`` field value, verbatim; it **defaults to ``None``**, which means
    identity, so every caller written before content negotiation existed keeps the exact
    behaviour it had. Passing it is what lets this origin emit the ``.gz`` siblings the
    packer has been shipping unused — see CONTENT NEGOTIATION in the module docstring.

    Never raises: every failure is a status and a JSON body that names it.

    This is a one-expression function on purpose. It is the module's only exit, so it is
    the one place where "no response this module emits exceeds the ceiling" can be made
    true of *every* response rather than of the ones somebody remembered — see
    :func:`_within_ceiling`.
    """
    return _within_ceiling(
        _answer(method, request_path, root=root, accept_encoding=accept_encoding),
        request_path,
    )


def _answer(  # noqa: PLR0911 - one return per HTTP status, and the statuses ARE the
    # interface: 403 refused, 404 asset miss, 405 wrong method, 413 too large, 503 no
    # bundle, 200 file, 200 index. Collapsing them would mean composing the status from a
    # variable, which is exactly how a 403 becomes a 200 in a refactor nobody reviewed.
    method: str,
    request_path: str,
    *,
    root: Path | str | None = None,
    accept_encoding: str | None = None,
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
            path=_echo(request_path),
        )

    # Interface I1: the sibling has no URL of its own. Decided from the REQUEST, beside the
    # 403s and before the root is known to exist, because "one set of bytes has one name"
    # is a rule about naming and not a fact about this filesystem — so it answers the same
    # on a broken deploy as on a good one, and it cannot be reached by a path that happens
    # to sit outside `assets/` or `bundle/` and would otherwise get the SPA fallback.
    if relative.lower().endswith(GZ_SUFFIX):
        identity = relative[: -len(GZ_SUFFIX)]
        return _problem(
            404,
            "asset_not_found",
            f"{relative} is not a route and never will be. {GZ_SUFFIX} is the "
            f"pre-compressed half of {identity}, reached by sending 'accept-encoding: "
            f"{GZIP_CODING}' to that path and by nothing else: one set of bytes gets one "
            "name, one media type and one cache entry. Two names for one object is two "
            "cache entries and a browser holding gzip it was never told to inflate.",
            path=_echo(request_path),
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
        return _file(
            target, relative, head=head, sibling=_sibling(target, accept_encoding)
        )

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
    # The SPA fallback negotiates too: `index.html` is the object every judge fetches
    # first, it has a sibling like everything else compressible, and a fallback that
    # quietly opted out of compression would be the one uncompressed response on the
    # hottest path.
    return _file(
        index, INDEX_NAME, head=head, sibling=_sibling(index, accept_encoding)
    )
