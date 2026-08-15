# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The file server that makes one Lambda Function URL the whole demo.

`docs/leads/ship-final.md` DECISION **D1**: the account cannot create a CloudFront
distribution, so the demo URL is a public Lambda Function URL and this handler serves the
console SPA, the evidence bundle and ``/v1/*`` from one origin. Every test here is about
one of the three things that makes that safe rather than merely convenient:

**It cannot be talked out of its root.** Four traversal vectors — a literal ``..``, a
percent-encoded one, a Windows-absolute segment and a backslash — must be 403 and must be
403 *before* the filesystem is consulted, so the answer does not depend on what happens to
exist on the machine. The tests assert the status AND that no bytes came back.

**It tells the truth about what it served.** A ``.js.map`` is JSON, a ``.woff2`` is a
font that has to be base64 on the payload-format-2.0 wire, and a hashed asset may be
cached forever while ``index.html`` may not be cached at all. Each of those is one
assertion here, because each of them is a distinct way for a deployed console to fail in
front of a judge with an error message about none of it.

**It degrades instead of dying.** With no web root bundled, ``/`` is a 503 that names the
directory it looked for, and ``/v1/*`` is untouched. An API that still answers is more
useful than a handler that will not import.

**It serves the bytes the packer built, once, under one name.** The builder has been
writing a ``<name>.gz`` beside every compressible ``web/**`` entry since the source-map
strip landed, and until 2026-08-13 nothing in this repository could emit one: 289,312 B of
compressed objects shipped in the package with no code path to reach them, and a direct
request for ``/assets/index-BjAGxrVJ.js.gz`` returned them under a second name with the
wrong media type. Sections (d) and (e) below are interface **I1** — negotiate or 404 —
and interface **I2**, which is the rule that the ceiling weighs what leaves the origin and
not the base64 string it travelled in.

**Its ceiling is bound to the tree it governs, and section (f) is what binds it.** Twice
now this constant has sat above every object it was supposed to bound — at 2 MiB, and then
at 512 KiB once the strip removed the only thing 512 KiB refused. A ceiling above
everything it governs cannot fail, so it proves nothing. The assertions in (f) read the
built package, compute the largest response the origin can actually emit, and fail if the
constant is not tight around it. Ruling **R10** (``docs/leads/reconcile-constants-plan.md``
§1) settles which of those assertions is the LAW: interface I3, plus the straddle, plus
exactly-one-identity-object-refused, all measured over the tree that ships. The 8 KiB
derivation that first CHOSE 139,264 is kept beside them as dated provenance over the tree
it chose from, and is not re-asserted against a tree it did not choose from.
"""

from __future__ import annotations

import base64
import gzip
import json
import math
import zipfile
from pathlib import Path
from typing import Any, Final

import pytest
from mainline_demo_api import app, static_site

from conftest import REPO_ROOT

# A one-pixel PNG. Not valid UTF-8 — byte 0x89 opens the signature — which is exactly the
# property under test: the payload-format-2.0 body is a JSON string, so these bytes have
# to arrive base64 with `isBase64Encoded: true` or they cannot arrive at all.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

#: A WOFF2 begins with the ASCII tag `wOF2` and then binary. Two bytes past the tag are
#: invalid UTF-8, so this stands in for a real font without vendoring one.
_WOFF2 = b"wOF2\x00\x01\x00\x00\xff\xfe\x00\x10"

_INDEX = "<!doctype html><html><head><title>MAINLINE</title></head><body>ok</body></html>"
_JS = "export const x=1;\n"
_CSS = ":root{--x:0}\n"


@pytest.fixture
def web_root(tmp_path: Path) -> Path:
    """A bundled site with one of everything the console's ``dist/`` actually emits."""
    root = tmp_path / "web"
    (root / "assets").mkdir(parents=True)
    (root / "bundle").mkdir(parents=True)

    # write_bytes, never write_text: on Windows `write_text` translates "\n" to "\r\n",
    # which would make every byte-for-byte assertion below a test of the platform's
    # newline policy instead of a test of this module.
    (root / "index.html").write_bytes(_INDEX.encode("utf-8"))
    (root / "assets" / "index-BjAGxrVJ.js").write_bytes(_JS.encode("utf-8"))
    (root / "assets" / "index-BjAGxrVJ.js.map").write_bytes(b'{"version":3}')
    (root / "assets" / "index-rP_bYrut.css").write_bytes(_CSS.encode("utf-8"))
    (root / "assets" / "seal-1a2b3c.svg").write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    (root / "assets" / "inter-latin-9f8e7d.woff2").write_bytes(_WOFF2)
    (root / "favicon.png").write_bytes(_PNG)
    (root / "bundle" / "bundle.json").write_bytes(b'{"envelope_version":1}')
    return root


def _serve(root: Path, path: str, method: str = "GET") -> dict[str, Any]:
    return static_site.serve(method, path, root=root)


def _body_bytes(response: dict[str, Any]) -> bytes:
    if response["isBase64Encoded"]:
        return base64.b64decode(response["body"])
    return str(response["body"]).encode("utf-8")


# ── The SPA fallback ────────────────────────────────────────────────────────────────


def test_root_serves_index_html_uncached(web_root: Path) -> None:
    response = _serve(web_root, "/")
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "text/html; charset=utf-8"
    assert response["headers"]["cache-control"] == "no-cache"
    assert response["isBase64Encoded"] is False
    assert response["body"] == _INDEX


@pytest.mark.parametrize(
    "path",
    ["/permits/0f8f6e94", "/gate", "/a/deep/stray/path", "/index.html", "/?ignored"],
    ids=["route-like", "single-segment", "deep", "explicit-index", "queryish"],
)
def test_an_unknown_non_v1_path_falls_back_to_index_html(web_root: Path, path: str) -> None:
    """Hash routing means a deep link never reaches the server; a stray one must not blank."""
    response = _serve(web_root, path)
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "text/html; charset=utf-8"
    assert response["headers"]["cache-control"] == "no-cache"
    assert response["body"] == _INDEX


def test_a_miss_under_assets_is_404_and_not_html(web_root: Path) -> None:
    """HTML where a module was asked for is ``Unexpected token '<'``, which names nothing."""
    response = _serve(web_root, "/assets/index-deleted.js")
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["kind"] == "asset_not_found"
    assert "assets/index-deleted.js" in body["error"]["detail"]


def test_a_miss_under_bundle_is_404_and_not_html(web_root: Path) -> None:
    response = _serve(web_root, "/bundle/absent.json")
    assert response["statusCode"] == 404
    assert json.loads(response["body"])["error"]["kind"] == "asset_not_found"


# ── Caching ─────────────────────────────────────────────────────────────────────────


def test_a_hashed_asset_is_immutable_for_a_year(web_root: Path) -> None:
    response = _serve(web_root, "/assets/index-BjAGxrVJ.js")
    assert response["statusCode"] == 200
    assert response["headers"]["cache-control"] == "public, max-age=31536000, immutable"
    assert response["headers"]["content-type"] == "text/javascript; charset=utf-8"
    assert response["headers"]["x-mainline-static"] == "assets/index-BjAGxrVJ.js"


def test_the_evidence_bundle_is_cached_briefly_and_not_forever(web_root: Path) -> None:
    """The bundle URL carries no content hash, so a redeploy must not be shadowed."""
    response = _serve(web_root, "/bundle/bundle.json")
    assert response["statusCode"] == 200
    assert response["headers"]["cache-control"] == static_site.BUNDLE_CACHE_CONTROL
    assert response["headers"]["cache-control"] != static_site.IMMUTABLE_CACHE_CONTROL
    assert response["headers"]["content-type"] == "application/json; charset=utf-8"


# ── Media types and encoding ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/index.html", "text/html; charset=utf-8"),
        ("/assets/index-BjAGxrVJ.js", "text/javascript; charset=utf-8"),
        ("/assets/index-rP_bYrut.css", "text/css; charset=utf-8"),
        ("/bundle/bundle.json", "application/json; charset=utf-8"),
        ("/assets/seal-1a2b3c.svg", "image/svg+xml"),
        ("/assets/inter-latin-9f8e7d.woff2", "font/woff2"),
        # `.js.map`.suffix is `.map`, not `.js`. A map served as JavaScript is refused by
        # DevTools, silently, and the source maps in dist/ stop working.
        ("/assets/index-BjAGxrVJ.js.map", "application/json; charset=utf-8"),
    ],
    ids=["html", "js", "css", "json", "svg", "woff2", "map"],
)
def test_the_media_type_is_correct_for_every_extension_the_bundle_emits(
    web_root: Path, path: str, content_type: str
) -> None:
    response = _serve(web_root, path)
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == content_type


def test_text_is_served_as_text_and_binary_is_served_base64(web_root: Path) -> None:
    """``isBase64Encoded`` IS the payload-format-2.0 contract; getting it wrong corrupts."""
    text = _serve(web_root, "/assets/index-rP_bYrut.css")
    assert text["isBase64Encoded"] is False
    assert text["body"] == ":root{--x:0}\n"

    font = _serve(web_root, "/assets/inter-latin-9f8e7d.woff2")
    assert font["isBase64Encoded"] is True
    assert _body_bytes(font) == _WOFF2

    png = _serve(web_root, "/favicon.png")
    assert png["isBase64Encoded"] is True
    assert png["headers"]["content-type"] == "image/png"
    assert _body_bytes(png) == _PNG


def test_content_length_reports_the_bytes_not_the_base64(web_root: Path) -> None:
    response = _serve(web_root, "/assets/inter-latin-9f8e7d.woff2")
    assert response["headers"]["content-length"] == str(len(_WOFF2))


def test_head_returns_the_headers_and_no_body(web_root: Path) -> None:
    response = _serve(web_root, "/assets/index-BjAGxrVJ.js", method="HEAD")
    assert response["statusCode"] == 200
    assert response["body"] == ""
    assert response["headers"]["content-length"] == str(len("export const x=1;\n"))


def test_a_write_method_on_the_static_surface_is_405(web_root: Path) -> None:
    response = _serve(web_root, "/", method="POST")
    assert response["statusCode"] == 405
    assert json.loads(response["body"])["error"]["allow"] == ["GET", "HEAD"]


# ── Refusing to leave the root ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "vector"),
    [
        ("/../../etc/passwd", "dot_dot"),
        ("/%2e%2e%2f%2e%2e%2fetc%2fpasswd", "dot_dot"),
        ("/assets/../../../../etc/passwd", "dot_dot"),
        ("/C:/Windows/System32/drivers/etc/hosts", "drive"),
        ("/%43%3a%2fWindows%2fwin.ini", "drive"),
        ("/..\\..\\windows\\win.ini", "backslash"),
        ("/%2e%2e%5c%2e%2e%5cwindows", "backslash"),
    ],
    ids=[
        "dot-dot",
        "percent-encoded-dot-dot",
        "dot-dot-below-a-real-prefix",
        "windows-absolute",
        "percent-encoded-absolute",
        "backslash",
        "percent-encoded-backslash",
    ],
)
def test_a_traversal_is_403_and_returns_no_file(web_root: Path, path: str, vector: str) -> None:
    response = _serve(web_root, path)
    assert response["statusCode"] == 403, response
    body = json.loads(response["body"])
    assert body["error"]["kind"] == "path_refused"
    assert body["error"]["vector"] == vector
    assert response["isBase64Encoded"] is False


def test_a_traversal_is_refused_even_when_the_web_root_is_absent(tmp_path: Path) -> None:
    """Refusal is decided from the request alone, so a broken deploy answers identically."""
    response = _serve(tmp_path / "never-bundled", "/../../etc/passwd")
    assert response["statusCode"] == 403


def test_the_resolver_refuses_a_target_outside_the_root(tmp_path: Path) -> None:
    """The containment check, exercised directly.

    This is the assertion that covers a symlink pointing out of the bundle: ``resolve()``
    follows links, so a link's target is what gets compared with the root. It is written
    against the resolver rather than against a created symlink because creating one on
    Windows needs a privilege CI does not grant, and a test that skips on the
    developer's own machine protects nothing.
    """
    root = tmp_path / "web"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("no", encoding="utf-8")

    inside, relative = static_site.resolve("/index.html", root)
    assert inside == (root / "index.html").resolve()
    assert relative == "index.html"

    with pytest.raises(static_site.Refused) as caught:
        static_site.resolve("/../secret.txt", root)
    assert caught.value.vector == "dot_dot"


def test_a_nul_byte_is_refused(web_root: Path) -> None:
    response = _serve(web_root, "/index%00.html")
    assert response["statusCode"] == 403
    assert json.loads(response["body"])["error"]["vector"] == "nul"


def test_a_double_encoded_dot_dot_is_a_filename_and_not_a_traversal(web_root: Path) -> None:
    """Decoding exactly once is the rule: decoding twice invents an attack from a name."""
    response = _serve(web_root, "/%252e%252e%252fetc")
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "text/html; charset=utf-8"


# ── No web root ─────────────────────────────────────────────────────────────────────


def test_a_missing_web_root_is_503_that_names_the_directory(tmp_path: Path) -> None:
    absent = tmp_path / "never-bundled"
    response = _serve(absent, "/")
    assert response["statusCode"] == 503
    body = json.loads(response["body"])
    assert body["error"]["kind"] == "web_root_not_bundled"
    assert str(absent) in body["error"]["detail"]
    assert static_site.WEB_ROOT_ENV in body["error"]["detail"]


def test_a_web_root_without_an_index_is_503_rather_than_a_blank_200(tmp_path: Path) -> None:
    root = tmp_path / "web"
    root.mkdir()
    response = _serve(root, "/gate")
    assert response["statusCode"] == 503
    assert json.loads(response["body"])["error"]["kind"] == "web_root_not_bundled"


def test_the_env_override_wins_over_the_bundled_default(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(web_root))
    assert static_site.web_root() == web_root
    assert static_site.serve("GET", "/")["body"] == _INDEX


def test_the_default_root_is_beside_the_module_or_beside_the_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both candidates are named, because the bundler may lay it out either way."""
    monkeypatch.delenv(static_site.WEB_ROOT_ENV, raising=False)
    package = Path(static_site.__file__).resolve().parent
    assert static_site.web_root() in (
        package / static_site.DEFAULT_ROOT_NAME,
        package.parent / static_site.DEFAULT_ROOT_NAME,
    )


# ── The handler fork ────────────────────────────────────────────────────────────────


def _event(method: str, path: str) -> dict[str, Any]:
    return {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"stage": "$default", "http": {"method": method, "path": path}},
    }


def test_the_handler_sends_non_v1_paths_to_the_static_surface(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(web_root))
    response = app.handler(_event("GET", "/"))
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "text/html; charset=utf-8"
    assert response["headers"]["x-mainline-api"] == "demo-static"


def test_the_handler_keeps_v1_paths_on_the_api_surface(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """``/v1/*`` must never be answered with HTML, bundled site or not."""
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(web_root))
    response = app.handler(_event("GET", "/v1/nope"))
    assert response["statusCode"] == 404
    assert response["headers"]["content-type"] == "application/json; charset=utf-8"
    assert json.loads(response["body"])["error"]["kind"] == "no_route"


def test_v1_health_is_unaffected_by_the_static_surface(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """The hourly cron reads this endpoint; the site must not be able to shadow it."""
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(web_root))
    assert static_site.is_api_path("/v1/health") is True

    called: dict[str, bool] = {}

    def _fake_health() -> tuple[int, dict[str, Any]]:
        called["yes"] = True
        return 200, {"ok": True, "database": "mainline_demo"}

    monkeypatch.setattr(app, "health", _fake_health)
    response = app.handler(_event("GET", "/v1/health"))
    assert called == {"yes": True}
    assert response["statusCode"] == 200
    assert response["headers"]["cache-control"] == "no-store"


def test_the_api_prefix_boundary_is_exact() -> None:
    """``/v1abc`` is not the API and ``/v1`` is; a prefix test that used ``in`` would differ."""
    assert static_site.is_api_path("/v1") is True
    assert static_site.is_api_path("/v1/") is True
    assert static_site.is_api_path("/v1/health") is True
    assert static_site.is_api_path("/v1abc") is False
    assert static_site.is_api_path("/") is False
    assert static_site.is_api_path("/assets/index-BjAGxrVJ.js") is False


def test_static_site_imports_nothing_outside_the_standard_library() -> None:
    """It must keep answering when the driver cannot import. Same rule as the read spine."""
    import re
    import sys

    source = Path(static_site.__file__).read_text(encoding="utf-8")
    stdlib = set(sys.stdlib_module_names)
    roots = {
        match.group(1).split(".")[0]
        for match in re.finditer(r"^\s*(?:import|from)\s+([a-zA-Z_][\w.]*)", source, re.M)
    }
    assert roots - stdlib - {"__future__"} == set()


# ── (d) Content negotiation — interface I1 ──────────────────────────────────────────
#
# The packer writes `<name>.gz` beside every compressible `web/**` entry. Until 2026-08-13
# the serving half did not exist, so those bytes shipped and could not be emitted, while a
# direct request for the sibling's own name returned them under a second URL. Both halves
# of that are here: negotiate on `Accept-Encoding`, and 404 the second name.

_BROWSER: Final = "gzip, deflate, br"


def _gz(data: bytes) -> bytes:
    """The packer's coding: level 9, ``mtime=0``, so the sibling is byte-reproducible."""
    return gzip.compress(data, compresslevel=9, mtime=0)


@pytest.fixture
def gz_web_root(web_root: Path) -> Path:
    """The same bundled site, with the pre-compressed siblings the packer actually writes.

    A separate fixture rather than a change to ``web_root``: every test above was written
    against a tree with no siblings and must keep asserting what it asserted, because
    "identity is what you get when you do not ask" is itself a property under test.

    ``favicon.png`` and the ``.woff2`` deliberately get **no** sibling — they are already
    compressed containers, the packer skips them, and the fallback to identity for an
    object with no sibling is the case a build that stopped pre-compressing would land on.
    """
    for relative in (
        "index.html",
        "assets/index-BjAGxrVJ.js",
        "assets/index-rP_bYrut.css",
        "assets/seal-1a2b3c.svg",
        "bundle/bundle.json",
    ):
        target = web_root / relative
        target.with_name(target.name + ".gz").write_bytes(_gz(target.read_bytes()))
    return web_root


@pytest.mark.parametrize(
    ("header", "permitted"),
    [
        (None, False),
        ("", False),
        ("gzip", True),
        ("gzip, deflate, br", True),
        ("deflate, br", False),
        ("identity", False),
        ("GZIP", True),
        ("  gzip  ", True),
        ("x-gzip", True),
        ("gzip;q=0.5", True),
        ("br;q=1.0, gzip;q=0.5", True),
        # A refusal, not a mention. A substring test for "gzip" gets this one wrong and
        # sends compressed bytes to a client that said it cannot read them.
        ("gzip;q=0", False),
        ("gzip;q=0.000", False),
        ("*", True),
        ("*;q=0", False),
        # The specific preference beats the wildcard, in both directions.
        ("gzip;q=0, *", False),
        ("*, gzip;q=0", False),
        ("*;q=0, gzip", True),
        ("gzip;q=nonsense", False),
    ],
    ids=[
        "absent",
        "empty",
        "bare",
        "browser",
        "other-codings",
        "identity",
        "uppercase",
        "padded",
        "legacy-x-gzip",
        "weighted",
        "preferred-other",
        "q-zero",
        "q-zero-spelled-out",
        "wildcard",
        "wildcard-refused",
        "wildcard-then-explicit-refusal",
        "explicit-refusal-then-wildcard",
        "wildcard-refused-explicit-allowed",
        "unparseable-q",
    ],
)
def test_accept_encoding_is_parsed_rather_than_searched_for_a_substring(
    header: str | None, permitted: bool
) -> None:
    assert static_site.accepts_gzip(header) is permitted


def test_a_gzip_capable_request_gets_the_sibling_under_the_identity_name(
    gz_web_root: Path,
) -> None:
    """The whole of I1's serving half, on one response.

    The bytes are the sibling's; everything else — the URL, the media type, the cache
    policy, ``x-mainline-static`` — is the identity object's, because it is the same
    resource. A ``.js.gz`` served as ``application/gzip`` is a module the browser refuses
    to execute, which is the failure this assertion exists to prevent.
    """
    identity = (gz_web_root / "assets" / "index-BjAGxrVJ.js").read_bytes()
    sibling = (gz_web_root / "assets" / "index-BjAGxrVJ.js.gz").read_bytes()

    response = static_site.serve(
        "GET", "/assets/index-BjAGxrVJ.js", root=gz_web_root, accept_encoding=_BROWSER
    )
    assert response["statusCode"] == 200
    assert response["headers"]["content-encoding"] == "gzip"
    assert response["headers"]["content-type"] == "text/javascript; charset=utf-8"
    assert response["headers"]["cache-control"] == static_site.IMMUTABLE_CACHE_CONTROL
    assert response["headers"]["x-mainline-static"] == "assets/index-BjAGxrVJ.js"
    assert response["headers"]["vary"] == "accept-encoding"

    # Not valid UTF-8, so the payload-format-2.0 contract requires base64 and the flag.
    assert response["isBase64Encoded"] is True
    assert _body_bytes(response) == sibling
    assert gzip.decompress(_body_bytes(response)) == identity
    # content-length is the length of the coded body, which is what goes on the wire.
    assert response["headers"]["content-length"] == str(len(sibling))


def test_a_request_that_did_not_ask_for_gzip_gets_the_identity_bytes(
    gz_web_root: Path,
) -> None:
    """Present the sibling and say nothing, and nothing changes. That is the default."""
    response = static_site.serve("GET", "/assets/index-BjAGxrVJ.js", root=gz_web_root)
    assert response["statusCode"] == 200
    assert "content-encoding" not in response["headers"]
    assert response["isBase64Encoded"] is False
    assert response["body"] == _JS
    # Still `vary`: this response WOULD have differed, and a cache that stored it without
    # `vary` would replay identity bytes to a client that asked for and can read gzip.
    assert response["headers"]["vary"] == "accept-encoding"


def test_a_client_that_refuses_gzip_is_not_sent_gzip(gz_web_root: Path) -> None:
    response = static_site.serve(
        "GET", "/assets/index-BjAGxrVJ.js", root=gz_web_root, accept_encoding="gzip;q=0"
    )
    assert response["statusCode"] == 200
    assert "content-encoding" not in response["headers"]
    assert response["body"] == _JS


def test_an_object_with_no_sibling_falls_back_to_identity_rather_than_404(
    gz_web_root: Path,
) -> None:
    """A build that stopped pre-compressing costs money. It must not cost the page."""
    response = static_site.serve(
        "GET", "/assets/inter-latin-9f8e7d.woff2", root=gz_web_root, accept_encoding=_BROWSER
    )
    assert response["statusCode"] == 200
    assert "content-encoding" not in response["headers"]
    assert _body_bytes(response) == _WOFF2


def test_the_spa_fallback_negotiates_like_every_other_object(gz_web_root: Path) -> None:
    """``index.html`` is the first thing every judge fetches; it must not opt out."""
    for path in ("/", "/permits/0f8f6e94"):
        response = static_site.serve("GET", path, root=gz_web_root, accept_encoding=_BROWSER)
        assert response["statusCode"] == 200, path
        assert response["headers"]["content-encoding"] == "gzip"
        assert response["headers"]["content-type"] == "text/html; charset=utf-8"
        assert response["headers"]["cache-control"] == static_site.INDEX_CACHE_CONTROL
        assert gzip.decompress(_body_bytes(response)).decode("utf-8") == _INDEX


def test_head_negotiates_exactly_as_get_does_and_still_carries_no_body(
    gz_web_root: Path,
) -> None:
    """The cheaper method must describe the response the GET would actually send."""
    sibling = (gz_web_root / "assets" / "index-BjAGxrVJ.js.gz").read_bytes()
    response = static_site.serve(
        "HEAD", "/assets/index-BjAGxrVJ.js", root=gz_web_root, accept_encoding=_BROWSER
    )
    assert response["statusCode"] == 200
    assert response["headers"]["content-encoding"] == "gzip"
    assert response["headers"]["content-length"] == str(len(sibling))
    assert response["body"] == ""
    assert response["isBase64Encoded"] is False


@pytest.mark.parametrize(
    "path",
    [
        "/assets/index-BjAGxrVJ.js.gz",
        "/bundle/bundle.json.gz",
        # Outside the asset prefixes, where a miss would otherwise be the SPA fallback and
        # this request would answer 200 with HTML.
        "/index.html.gz",
        # Case-folded, because the developer platform's filesystem is case-insensitive and
        # would happily open the sibling for this name.
        "/assets/index-BjAGxrVJ.js.GZ",
        # A name with no sibling behind it at all: the rule is about the name, not the file.
        "/assets/never-existed.js.gz",
    ],
    ids=["asset", "bundle", "root-level", "case-folded", "absent"],
)
@pytest.mark.parametrize("accept", [None, _BROWSER], ids=["identity", "gzip"])
def test_a_direct_request_for_a_gz_path_is_404_whatever_the_caller_sent(
    gz_web_root: Path, path: str, accept: str | None
) -> None:
    """One set of bytes gets one name — the second half of I1, and the half with teeth.

    Before this, ``/assets/index-BjAGxrVJ.js.gz`` returned the compressed bytes as
    ``application/octet-stream`` with no ``content-encoding``: a second URL for one object,
    a second cache entry, and a browser holding gzip nobody told it to inflate. The refusal
    reuses this module's existing ``asset_not_found`` shape rather than inventing a new
    one, so every consumer of the 404 keeps working.
    """
    response = static_site.serve("GET", path, root=gz_web_root, accept_encoding=accept)
    assert response["statusCode"] == 404
    error = json.loads(response["body"])["error"]
    assert error["kind"] == "asset_not_found"
    assert "accept-encoding" in error["detail"]
    assert response["isBase64Encoded"] is False
    # Whatever else it is, it is not a delivery mechanism for the bytes it refused.
    assert "content-encoding" not in response["headers"]


def test_the_gz_refusal_is_decided_from_the_request_not_from_the_deploy(
    tmp_path: Path,
) -> None:
    """Same answer on a broken deploy as on a good one, like the traversal refusals."""
    response = static_site.serve(
        "GET", "/assets/x.js.gz", root=tmp_path / "never-bundled", accept_encoding=_BROWSER
    )
    assert response["statusCode"] == 404
    assert json.loads(response["body"])["error"]["kind"] == "asset_not_found"


def test_the_refusals_that_do_not_depend_on_the_header_do_not_claim_to(
    gz_web_root: Path,
) -> None:
    """``vary`` belongs on what varies. On what does not, it is a wasted cache entry."""
    for path, status in (
        ("/../../etc/passwd", 403),
        ("/assets/deleted-Xxxx.js", 404),
        ("/assets/index-BjAGxrVJ.js.gz", 404),
    ):
        response = static_site.serve("GET", path, root=gz_web_root, accept_encoding=_BROWSER)
        assert response["statusCode"] == status, path
        assert "vary" not in response["headers"], path

    post = static_site.serve("POST", "/", root=gz_web_root, accept_encoding=_BROWSER)
    assert post["statusCode"] == 405
    assert "vary" not in post["headers"]


# ── (e) The ceiling weighs WIRE bytes — interface I2 ────────────────────────────────


def test_the_ceiling_weighs_the_wire_and_not_the_base64_string(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """**Interface I2**, and it reverses a belief this repository held until 2026-08-13.

    3,300 bytes of non-UTF-8 become a 4,400-character base64 body. Under a 4,096 ceiling
    the old code refused it, on the theory that the encoded string is what the response
    carries. It is not what AWS bills: a Function URL base64-DECODES the body before it
    leaves, so egress is charged on 3,300 and the extra 1,100 exists only between this
    handler and the service. Refusing on the encoded length over-refuses every binary
    object by exactly a third — and the object it would hurt most is the compressed entry
    bundle of the package that ships: at build ``5302005`` that is 137,939 B, which would be
    weighed as 183,920 B, and it is the single path the cost model depends on callers taking.
    It was 138,177 B / 184,236 B on the package before it and 129,400 B / 172,536 B before
    that; the hazard is the ratio, not any of those figures, and the encoded side of it is
    over 139,264 in every case. **The wire side is only 1,325 B under**, which makes this the
    one place worth saying that a 33 % measurement
    error here would not merely over-refuse — at these figures it would take out the console
    entirely, and it would do it for a reason the origin cannot report.

    **This contradicts** ``test_response_contract.py::test_base64_inflation_is_measured_
    and_not_assumed``, deliberately and with the arithmetic above. That test is W2's file
    and is not touched here; it encodes the old belief and is the change W2 has to land.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    (web_root / "assets" / "font-Bbbbbbbb.woff2").write_bytes(b"\xff\xfe" * 1650)  # 3300 B

    response = static_site.serve("GET", "/assets/font-Bbbbbbbb.woff2", root=web_root)
    assert response["statusCode"] == 200
    assert response["isBase64Encoded"] is True
    assert len(_body_bytes(response)) == 3300
    assert len(response["body"]) == 4400, "the encoded string really is 33 % larger"
    assert response["headers"]["content-length"] == "3300"


def test_the_ceiling_still_refuses_when_the_wire_bytes_exceed_it(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """The other side of the same rule: a ceiling that refuses nothing is not a ceiling."""
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    (web_root / "assets" / "font-Ccccccc.woff2").write_bytes(b"\xff\xfe" * 2049)  # 4098 B

    response = static_site.serve("GET", "/assets/font-Ccccccc.woff2", root=web_root)
    assert response["statusCode"] == 413
    error = json.loads(response["body"])["error"]
    assert error["bytes"] == 4098, "the refusal reports the wire, not the base64"
    assert error["ceiling_bytes"] == 4096


def _wide_asset(root: Path, name: str) -> tuple[bytes, bytes]:
    """Write an object big enough to set a ceiling under, plus its sibling. Returns both.

    The two tests below set the ceiling just below a sibling's length, and
    ``_within_ceiling`` weighs the 413 it produces exactly like every other response — so a
    fixture that compressed to 38 bytes would put the refusal itself over the ceiling and
    report its own size instead of the object's. About 24 KB compressed leaves two orders
    of magnitude of room, and the guard below is what says so rather than assuming it.
    """
    identity = "".join(
        f"export const v{index} = {index * 7919 % 100003};\n" for index in range(4000)
    ).encode("utf-8")
    sibling = _gz(identity)
    assert len(sibling) > 4096, "the fixture is too compressible to set a ceiling under"
    (root / name).write_bytes(identity)
    (root / f"{name}.gz").write_bytes(sibling)
    return identity, sibling


def test_a_gzip_body_is_weighed_on_the_compressed_bytes_it_puts_on_the_wire(
    monkeypatch: pytest.MonkeyPatch, gz_web_root: Path
) -> None:
    """The case I2 calls the subtlest hazard in the wave, made concrete.

    A ceiling set exactly at the sibling's own length must SERVE it, even though the base64
    the body travels in is a third longer. If it refuses, the ceiling is being applied to
    the encoding rather than to the egress, and every compressed object in the bundle is
    being over-refused by 33 % — starting with the one the cost model is built on.
    """
    _, sibling = _wide_asset(gz_web_root, "assets/wide-Ffffffff.js")
    encoded = len(base64.b64encode(sibling))
    assert encoded > len(sibling) * 1.3, "the fixture cannot demonstrate the hazard"

    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, str(len(sibling)))
    response = static_site.serve(
        "GET", "/assets/wide-Ffffffff.js", root=gz_web_root, accept_encoding=_BROWSER
    )
    assert response["statusCode"] == 200, "the ceiling was applied to the base64 string"
    assert len(response["body"]) == encoded
    assert len(_body_bytes(response)) == len(sibling)

    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, str(len(sibling) - 1))
    refused = static_site.serve(
        "GET", "/assets/wide-Ffffffff.js", root=gz_web_root, accept_encoding=_BROWSER
    )
    assert refused["statusCode"] == 413
    assert json.loads(refused["body"])["error"]["bytes"] == len(sibling)


def test_a_413_on_the_identity_path_varies_because_a_gzip_request_would_not_get_one(
    monkeypatch: pytest.MonkeyPatch, gz_web_root: Path
) -> None:
    """The refusal is negotiable too, and a cache that stored it unqualified breaks a page.

    This is the exact shape the deployed tree is in at the default ceiling: the entry
    bundle 413s to an identity request and 200s to a browser's. The two answers share a
    URL, so the 413 has to carry ``vary`` or a shared cache will hand the refusal to the
    browser.
    """
    big = b"x" * 4000
    (gz_web_root / "assets" / "big-Ddddddd.js").write_bytes(big)
    (gz_web_root / "assets" / "big-Ddddddd.js.gz").write_bytes(_gz(big))
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "2048")

    identity = static_site.serve("GET", "/assets/big-Ddddddd.js", root=gz_web_root)
    assert identity["statusCode"] == 413
    assert identity["headers"]["vary"] == "accept-encoding"
    error = json.loads(identity["body"])["error"]
    assert error["bytes"] == 4000
    assert error["bytes_on_disk"] == 4000
    assert "accept-encoding" in error["detail"], "the refusal must name the way through"

    negotiated = static_site.serve(
        "GET", "/assets/big-Ddddddd.js", root=gz_web_root, accept_encoding=_BROWSER
    )
    assert negotiated["statusCode"] == 200, "the way through must actually work"


def test_the_refusal_separates_what_was_asked_for_from_what_would_have_gone_out(
    monkeypatch: pytest.MonkeyPatch, gz_web_root: Path
) -> None:
    """``bytes`` is the wire, ``bytes_on_disk`` is the object named. On the negotiated path
    they are different numbers, and reporting only one leaves a caller unable to tell
    whether the fix is a smaller artefact or a different request header."""
    identity, sibling = _wide_asset(gz_web_root, "assets/wide-Eeeeeeee.js")

    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, str(len(sibling) - 1))
    response = static_site.serve(
        "GET", "/assets/wide-Eeeeeeee.js", root=gz_web_root, accept_encoding=_BROWSER
    )
    assert response["statusCode"] == 413
    error = json.loads(response["body"])["error"]
    assert error["bytes"] == len(sibling)
    assert error["bytes_on_disk"] == len(identity)
    assert error["bytes"] < error["bytes_on_disk"]


# ── (f) The ceiling is BOUND to the deployed tree — interface I3 ────────────────────
#
# Twice this constant has sat above every object it governs: at 2 MiB, and then at 512 KiB
# once `build_lambda` began stripping source maps and removed the only object 512 KiB
# refused. Both times the docstring beside it claimed otherwise. A ceiling that cannot fail
# proves nothing, so the number is held against the tree and these assertions are what hold
# it there.
#
# **Ruling R10 (2026-08-15, `docs/leads/reconcile-constants-plan.md` §1) says WHICH of them
# is the law.** The law is `_assert_i3`, plus the straddle
# `0 < largest_served < ceiling < largest_identity`, plus exactly one identity object
# refused — all three measured over the package that ships. The derivation
# `ceil(floor(1.10 x g) / 8192) x 8192` is NOT the law. It has a rounding step, so it is
# many-to-one, and `derive(g) == ceiling` therefore does not say the ceiling is correct: it
# says `g` landed inside one pre-image band, which is a statement about how large the
# console is allowed to be. That is a bundle-size budget wearing a ceiling's clothes, and
# this repository already owns a bundle-size budget
# (`verticals/mainline/apps/console/scripts/check-budgets.ts`). Conflating the two is what
# generates pressure on this constant every time the console legitimately grows.
#
# So the derivation is kept below as dated PROVENANCE, over the frozen tree it chose from
# (`_CEILING_PROVENANCE_G`), and the live law is asserted over today's tree. Note what did
# NOT happen: `DEFAULT_MAX_RESPONSE_BYTES` is byte-identical either way. Nothing that was
# refused is now served, and nothing that cost X now costs more.

#: The deployed artefact. This is the tree the ceiling is measured against, and it is the only
#: tree that HAS the `.gz` siblings: the packer's input tree (`console/dist` +
#: `console/fixtures/bundles/demo-cloud`, which is what `test_response_contract.py` falls
#: back to) is 75 pre-strip files with 18 source maps and zero siblings, so a derivation
#: measured there would be measured over bytes that no longer deploy. That is exactly the
#: mistake the 512 KiB value was made of.
_PACKAGE: Final = REPO_ROOT / "out/lambda/mainline-demo-api-arm64.zip"

#: **FROZEN HISTORY. This is NOT a measurement of the tree that ships.** It is the gzipped
#: figure that 139,264 was CHOSEN from, on 2026-08-14: package
#: `sha256 12fcba7ad69b2ffe8240b1ecbf763744d9441e12309109f7fab88ac62dfbcc27`, object
#: `assets/index-DzVoV1YM.js.gz`, 124,177 B. It is the one number in this section that
#: **MUST NEVER BE RE-MEASURED.** Re-measuring it against a later build would silently
#: RE-CHOOSE the ceiling, and re-choosing a bound is a decision a lead writes down, not
#: something a rebuild does on the way past. It moves only with such a decision.
#: (Ruling **R10** §1.6, `docs/leads/reconcile-constants-plan.md`.)
#:
#: Everything below it is a record of ONE build rather than a bound, and as of 2026-08-16
#: nothing re-measures those records per build either: the live assertions read the archive
#: directly and the records are simply dated. The asymmetry that remains is the one that
#: matters — this number is frozen because re-measuring it would move a BOUND; those are
#: frozen because re-recording them by hand was the treadmill.
_CEILING_PROVENANCE_G: Final = 124_177

# ── DATED PROVENANCE, AND WHY THIS BLOCK STOPPED BEING A RATCHET ───────────────────
#
# **EVERYTHING FROM HERE TO `_PROVENANCE_HEADROOM_BYTES` IS A RECORD OF ONE BUILD. NONE OF
# IT BOUNDS ANYTHING, AND NONE OF IT IS COMPARED FOR EQUALITY AGAINST WHATEVER SITS IN
# `out/lambda/` TODAY.** That is a change of kind, made 2026-08-16, and the reason for it is
# arithmetic rather than taste.
#
# THE CAUSE, NAMED. `verticals/mainline/apps/console/vite.config.ts` inlines
# `__MAINLINE_BUILD_ID__`, so the git short SHA reaches the emitted JavaScript and the entry
# chunk's CONTENT HASH therefore moves on every commit — including a commit that changes
# nothing else. A test that pins `assets/index-<hash>.js` as a literal goes stale on every
# build **by construction**, and this file, `test_response_contract.py` and
# `tests/deploy/test_furl_compression.py` went red together for exactly that, three times in
# two days. Each time the repair was to re-record the numbers by hand. The third repetition
# is the signal to repair the cause rather than the instance, so the assertions below now
# RESOLVE the entry chunk out of the archive by PATTERN (:func:`_resolve_entry_chunk`) and
# assert the PROPERTIES against whatever it resolves to.
#
# THE PROPERTIES — asserted over today's tree, and not one of them relaxed to get here:
#
#     * `static_site.DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024 == 139,264`. It may never
#       move, and no arithmetic makes it available — see `_MINIMUM_HEADROOM_BYTES` below;
#     * the straddle `0 < largest_served_gzipped < ceiling < largest_identity_object`;
#     * EXACTLY ONE identity object at or above the ceiling, on the identity path only;
#     * headroom at or above `_MINIMUM_HEADROOM_BYTES` (`_assert_headroom`);
#     * one `.gz` sibling per identity object, no orphan, no gap, and zero source maps.
#
# THE PROVENANCE — recorded, dated, and never asserted against a later build: the entry
# chunk's FILENAME, its identity and gzipped byte counts, the tree's totals, the
# second-largest object, and every ratio derived from them. Those are the constants below,
# and a reader who wants to know what the site cost on a given day reads them here.
#
# **WHAT RESOLVING THE NAME DOES NOT COST, SAID BEFORE SOMEBODY ASSUMES IT DID.** It does
# not make these assertions agree with the tree by construction, because the properties are
# not statements about a name. *Exactly one object is refused* is false of a tree with two
# giants however the giants are called; the straddle is false of a ceiling above everything
# it governs; the headroom guard is false of a console 302 gzipped bytes larger than this
# one. What the resolution removes is the single claim that was never a property: **the
# chunk is called this**.
#
# ── THE RECORD · BUILD `5302005`, READ FROM THE CENTRAL DIRECTORY ON 2026-08-16 ─────
#
#     artefact      out/lambda/mainline-demo-api-arm64.zip      291 archive entries
#     sha256        e97981a494f432f4db55dd175881d9551610fdd637bbfe63475258041102bf4d
#     packed from   HEAD `5302005`, `--console-transport live`; the manifest beside the
#                   zip records `console.build_ids == ['5302005', 'unknown']`
#
#     web/ entries                    154 files   1,884,886 B
#       identity objects               77 files   1,457,534 B
#       .gz siblings                   77 files     427,352 B   one per object, no orphan
#       source maps                     0 files           0 B   stripped by the builder
#     entry chunk        web/assets/index-HZTFrKeL.js
#       identity                                    490,373 B
#       gzipped                                     137,939 B   `g`, the flood multiplier
#     second-largest identity object                 96,734 B   assets/operator-D24tzVGh.js
#     headroom                                        1,325 B   139,264 - 137,939 = 0.95 %
#
# The surfaces that arrived with this build and are new bytes on the wire:
# `operator-D24tzVGh.js.gz` 29,906 · `operator.html.gz` 2,221 · `memory.html.gz` 7,990 ·
# `memory-loop.js.gz` 16,023 · `memory-verify.js.gz` 8,809.
#
# FOUR BUILDS, SO THE SHAPE OF THE MOVEMENT IS LEGIBLE AND NOT MERELY THE LATEST ROW:
#
#     build         entries/objects   identity B   sibling B   entry identity   g
#     ───────────   ───────────────   ──────────   ─────────   ──────────────   ───────
#     2026-08-13        114 / 57        985,030      289,312       433,396      124,127
#     b822fdc           114 / 57      1,012,812      295,724       457,123      129,400
#     f0ba767           138 / 69      1,177,977      347,013       490,950      138,177
#     5302005           154 / 77      1,457,534      427,352       490,373      137,939
#
# **READ THE LAST ROW AS A WARNING AND NOT AS A RELIEF.** `g` FELL by 238 B while the tree
# gained sixteen objects and 359,896 B. Nobody made the entry chunk smaller; different bytes
# compressed differently, and a margin that improves by accident can worsen by accident on
# the next commit. 1,325 B is 0.95 % of the ceiling. When `g` crosses it this origin answers
# **413 for its own entry JavaScript** to every browser: `GET /` still returns 200 and the
# shell, the shell asks for its one module, receives a JSON problem document, and the reader
# is looking at a BLANK PAGE — a total outage of the demo URL, with the origin reporting a
# healthy day throughout. `_MINIMUM_HEADROOM_BYTES` turns that red in CI at 1,024 B while
# the remedy is still a smaller or split entry chunk. It is never a larger ceiling: that is
# the move that put `DEFAULT_MAX_RESPONSE_BYTES` at 2 MiB and then at 512 KiB, and it has
# been refused three times.
#
# **COUNT THEM IN THE ARCHIVE, NEVER IN `console/dist`.** The zip's own manifest describes
# the tree BEFORE the source-map strip and BEFORE a `.gz` was written beside every
# compressible object. That is a true number about a site no request ever reaches, and
# confusing the two is what the 512 KiB ceiling was made of.

#: The build every figure in this section was read from. Named so the record can be
#: re-derived rather than believed: open the zip, list `web/`, and the numbers are there.
_PROVENANCE_BUILD_ID: Final = "5302005"
_PROVENANCE_SHA256: Final = "e97981a494f432f4db55dd175881d9551610fdd637bbfe63475258041102bf4d"

#: PROVENANCE. The entry chunk's name at build `5302005`. **Recorded, never matched.** This
#: literal is precisely what a build-id-only re-release moves, so nothing asserts against it;
#: `_resolve_entry_chunk` finds today's chunk in the archive instead.
_PROVENANCE_ENTRY_CHUNK: Final = "assets/index-HZTFrKeL.js"

#: PROVENANCE. `g` at build `5302005` — the largest number of bytes this origin can put on
#: the wire for one response, and interface I3's input. **was 129,400 → 138,177 → 137,939.**
#: A measurement of a build; the bound over it is `_assert_i3` plus `_assert_headroom`, and
#: both are additionally applied to whatever today's archive holds.
_LARGEST_SERVED_WIRE_BYTES: Final = 137_939  # web/assets/index-HZTFrKeL.js.gz

#: PROVENANCE. **was 457,123 → 490,950 → 490,373**, the one identity object the ceiling
#: refuses at build `5302005`. A measurement of the entry chunk and not a limit on it: what
#: is authoritative is that EXACTLY ONE object is refused, and this records which one was.
_LARGEST_IDENTITY_BYTES: Final = 490_373  # web/assets/index-HZTFrKeL.js

#: PROVENANCE. **was 51,266 → 67,049 → 96,734**, `assets/operator-D24tzVGh.js` — the
#: operator screens, which are a SECOND HTML ENTRY and therefore not in the console's entry
#: closure at all (`test_the_console_ci_budget_goes_red_before_the_origin_does` asserts the
#: ban that keeps them out of it). It records that the refusal is still isolated: this object
#: sits 42,530 B below the ceiling and 393,639 B below the object above it.
_SECOND_LARGEST_IDENTITY_BYTES: Final = 96_734  # web/assets/operator-D24tzVGh.js

#: PROVENANCE. **was 114 / 57 → 138 / 69 → 154 / 77** at build `5302005`. The PAIRING is the
#: property and it is asserted live: every identity object carries exactly one `.gz` sibling
#: and no sibling is an orphan, which is what keeps `g` the compressed column throughout
#: rather than a mixture of the two columns. The counts themselves are the record.
_WEB_ENTRIES: Final = 154
_IDENTITY_ENTRIES: Final = 77

#: PROVENANCE. The two columns of build `5302005` and their sum, recorded so the table above
#: can be checked by hand: 1,457,534 + 427,352 = 1,884,886. Nothing is served or refused on
#: the strength of a total — the ceiling is applied per response, never per tree.
_IDENTITY_BYTES: Final = 1_457_534
_SIBLING_BYTES: Final = 427_352
_WEB_TREE_BYTES: Final = 1_884_886

#: PROVENANCE. `139,264 - 137,939`. It was 15,087, then 9,864, then 1,087, and it is now
#: 1,325 — the one number in this file a reader should carry out of it. The BOUND under it
#: is `_MINIMUM_HEADROOM_BYTES`, which is asserted; this is where the margin actually stood
#: on 2026-08-16, which is recorded.
_PROVENANCE_HEADROOM_BYTES: Final = 1_325

#: How the entry chunk is FOUND rather than named. Vite emits the console's entry as
#: `assets/index-<content hash>.js` and emits exactly one of them; the operator and memory
#: screens are separate HTML entries under their own stems, and every lazy route is a
#: `surface-`/`worker-` chunk. `_resolve_entry_chunk` requires the match to be unique AND to
#: be the largest identity object in the tree, so this pattern cannot quietly start
#: resolving to something that is not the object the ceiling refuses.
_ENTRY_CHUNK_PREFIX: Final = "assets/index-"
_ENTRY_CHUNK_SUFFIX: Final = ".js"


def _resolve_entry_chunk(identity: dict[str, int]) -> str:
    """The console's entry chunk, resolved from the archive **by pattern**, not by name.

    Two statements, and each is a property this repository would want to hear about:

    * exactly one object matches ``assets/index-*.js``. Two would mean the console emitted a
      second top-level entry under the same stem, which changes what a browser loads first;
    * that object is the LARGEST identity object in the tree. If it ever is not, the biggest
      thing this origin holds is something nobody has reasoned about, and the ceiling's
      exactly-one-refusal property is about a different file than the console's entry.

    Returning the name is the small part. Refusing to return one when either statement fails
    is the reason this is a function rather than a `max()` at each call site.
    """
    matches = sorted(
        name
        for name in identity
        if name.startswith(_ENTRY_CHUNK_PREFIX) and name.endswith(_ENTRY_CHUNK_SUFFIX)
    )
    assert len(matches) == 1, (
        f"{len(matches)} objects match {_ENTRY_CHUNK_PREFIX}*{_ENTRY_CHUNK_SUFFIX} in the "
        f"deployed tree: {matches}. The console emits exactly one entry chunk under that "
        "stem; a second one means a second top-level entry landed, and which of them the "
        "ceiling refuses is then a question nobody has answered."
    )
    largest = max(identity.items(), key=lambda item: item[1])[0]
    assert matches[0] == largest, (
        f"the entry chunk is {matches[0]} but the largest identity object is {largest} at "
        f"{identity[largest]} B. The ceiling's one refusal is supposed to BE the entry "
        "chunk; if something else is now the biggest thing in the tree, that object is what "
        "this origin would 413, and nobody decided to stop serving it."
    )
    return largest

#: The derivation, as three numbers rather than as prose. Ten per cent is the headroom an
#: asset may take between two deploys without the demo going dark; 8 KiB is the rounding
#: that turns the result into a number a human can hold; 1.20 is the ratchet that fails
#: this file when the tree outgrows the constant.
_HEADROOM: Final = 1.10
_ROUNDING: Final = 8 * 1024
_RATCHET: Final = 1.20

#: **A BOUND, NOT A MEASUREMENT — added 2026-08-15, and it is the newest thing in this file.**
#: The fewest bytes of gzipped headroom this repository will let the entry chunk leave under
#: the ceiling before a test goes red.
#:
#: WHY IT EXISTS NOW AND DID NOT BEFORE. `_RATCHET` guards the direction where the ceiling
#: floats so far above the tree that it refuses nothing — a decoration. Nothing guarded the
#: OTHER direction, and that is the direction the packages moved in: headroom fell 15,087 →
#: 9,864 → 1,087 → **1,325 B**, which is **0.95 %** of the ceiling. `_assert_i3`'s lower half
#: does catch the crossing, but it catches it the moment it has already happened, and by then
#: the same build is sitting in `out/lambda/` waiting to be applied.
#:
#: **THE 1,325 IS PROVENANCE AND THE 1,024 IS THIS CONSTANT.** The margin went UP by 238 B
#: at build `5302005` and nobody made it do so — different bytes compress differently — so
#: read that row as an accident that can reverse rather than as room that was won.
#:
#: WHAT CROSSING COSTS, WHICH IS THE WHOLE REASON FOR THE NUMBER. When `g` exceeds the
#: ceiling, `serve` answers **413 to `assets/index-*.js`** — the console's own entry
#: JavaScript — to every client, because the compressed representation is the one every
#: browser takes and it would now be over the bound. `GET /` still answers 200 with a 4,655 B
#: shell, so nothing looks broken from the outside; the shell then fetches its only module,
#: receives a JSON problem document, and the judge is looking at a **blank page**. That is a
#: total outage of the demo URL rather than a degradation, and it is caused by a cost control
#: doing exactly what it was told.
#:
#: WHY 1 KiB. It has to be strictly below the live margin or this assertion is red on arrival
#: and says nothing about the future; it has to be well above zero or it fires only after the
#: cliff. 1,024 B is the round number in that window — 301 B under the 1,325 B measured at
#: build `5302005`, and it was 63 B under the 1,087 B measured at `f0ba767`. So the next
#: console growth that adds more than 301 gzipped bytes to the entry chunk turns this red in
#: CI while the origin is still serving every object it has. That is deliberately a hair
#: trigger: at a 0.95 % margin there is no such thing as a small console change any more.
#: **The trigger tightens on its own as the console grows and this constant does not move**
#: — which is the correct direction, and the reason 1,024 is expressed in bytes rather than
#: as a percentage of a number that keeps moving.
#:
#: **IT IS NOT AVAILABLE TO BE LOWERED, AND NEITHER IS THE CEILING RAISED TO CLEAR IT.**
#: Raising `DEFAULT_MAX_RESPONSE_BYTES` is what put that constant at 2 MiB and then at
#: 512 KiB, and lowering this one would be the same move wearing a different name — both
#: buy a green by widening the thing that is supposed to bite. When this goes red the answer
#: is a smaller entry chunk: code-split the console, or move what grew behind a lazy route.
#: `verticals/mainline/apps/console/scripts/check-budgets.ts` is where a bundle-size budget
#: belongs; this is the last line before the origin refuses its own site.
_MINIMUM_HEADROOM_BYTES: Final = 1024


def _derive_ceiling(largest_served_wire_bytes: int) -> int:
    """The ceiling the rule produces from a tree. The constant must equal this."""
    floor = _HEADROOM * largest_served_wire_bytes
    return -(-int(floor // 1) // _ROUNDING) * _ROUNDING


def _assert_headroom(ceiling: int, largest_served_wire_bytes: int) -> None:
    """Refuse a tree that has crept up under the ceiling. One function, so the falsification
    below runs the real check rather than a copy of it.

    This is the early-warning half of the pair `_assert_i3` completes. I3's lower bound is
    ``largest_served <= ceiling`` and it is the *outage* condition: by the time it fails, the
    console cannot be served. This one fails while there is still a margin, so a console
    change goes red in CI instead of 413ing in production — and it names the remedy, because
    an assertion that says only "too big" invites the reader to move the number that made it
    say so.
    """
    headroom = ceiling - largest_served_wire_bytes
    assert headroom >= _MINIMUM_HEADROOM_BYTES, (
        f"only {headroom} B of gzipped headroom remain: the widest response this origin "
        f"emits is {largest_served_wire_bytes} B against a {ceiling} B ceiling, and this "
        f"repository requires at least {_MINIMUM_HEADROOM_BYTES} B. At zero this origin "
        "answers 413 to its own entry JavaScript for EVERY browser: GET / still returns the "
        "shell, the shell's only module returns a problem document, and a judge sees a blank "
        "page — a total outage of the demo URL, not a slow one. Fix it by making the entry "
        "chunk smaller (code-split the console, move what grew behind a lazy route). Do NOT "
        "raise DEFAULT_MAX_RESPONSE_BYTES and do NOT lower _MINIMUM_HEADROOM_BYTES: both buy "
        "the green by widening the bound that is supposed to bite, which is the move that "
        "put the ceiling at 2 MiB and then at 512 KiB."
    )


def _assert_i3(ceiling: int, largest_served_wire_bytes: int) -> None:
    """Interface **I3**, as one function so the falsification below runs the real check.

    ``largest_served <= ceiling < 1.20 x largest_served``. The lower half says the origin
    can still serve its own site; the upper half says the ceiling is tight around it. A
    check written twice — once for the assertion and once for the falsification — is a
    check that can drift out of step with itself, which is how a control stops controlling.
    """
    assert largest_served_wire_bytes > 0, "an empty tree cannot derive a ceiling"
    assert largest_served_wire_bytes <= ceiling, (
        f"the largest response this origin can emit is {largest_served_wire_bytes} B and "
        f"the ceiling is {ceiling} B: the origin would 413 its own site."
    )
    assert ceiling < _RATCHET * largest_served_wire_bytes, (
        f"the ceiling is {ceiling} B against a largest served response of "
        f"{largest_served_wire_bytes} B — a ratio of "
        f"{ceiling / largest_served_wire_bytes:.4f}, at or above the {_RATCHET} ratchet. A "
        "ceiling that far above everything it governs cannot refuse anything, so it is a "
        "decoration. Re-derive it from the tree; do not raise it to make a test pass."
    )


def test_the_ceiling_still_equals_the_number_its_derivation_chose() -> None:
    """**PROVENANCE.** How 139,264 was CHOSEN, kept checkable so it cannot be re-chosen.

    ``1.10 x 124,177 = 136,594.7``; the next 8 KiB boundary above that is 139,264 = 136 KiB;
    ``139,264 / 124,177 = 1.121``, inside the 1.20 ratchet. Anyone can check those three
    lines by hand, which is the whole point of writing them here rather than asserting the
    constant against itself. What this guarantees is narrow and worth keeping: because the
    input is frozen and nobody may re-measure it, any change to
    ``DEFAULT_MAX_RESPONSE_BYTES`` breaks this equality. The ceiling can be re-chosen, but
    never *silently*.

    **What it deliberately no longer claims** — ruling **R10**,
    ``docs/leads/reconcile-constants-plan.md`` §1. It does not require 139,264 to be
    re-derivable from the tree that ships today, and as of ``sha256 7c97b532…`` it is not:
    ``_derive_ceiling(138_177)`` is 155,648 (it was 147,456 over ``sha256 6802872f…``, and
    the gap is widening with every console release). That is the derivation record going out
    of date, not the bound going wrong, and the difference matters because **a derivation with
    a rounding step is many-to-one.** ``ceil(floor(1.10 x g) / 8192) x 8192`` returns
    139,264 for every ``g`` in ``[119,158, 126,604]``, so ``derive(g) == ceiling`` never
    said *the ceiling is correct*; it said *g fell inside one 7,447 B pre-image band*, which
    is a statement about how large the console is permitted to be. That is **a bundle-size
    budget wearing a ceiling's clothes**, and this repository already owns a bundle-size
    budget in ``console/scripts/check-budgets.ts``. Conflating the two is what puts pressure
    on this constant every time the console legitimately grows — and raising the ceiling to
    147,456 so the arithmetic agreed would have loosened a cost bound to satisfy a formula.

    The live law is **I3 plus the straddle**, over today's tree, asserted immediately below.
    """
    derived = _derive_ceiling(_CEILING_PROVENANCE_G)
    assert derived == 139_264 == 136 * 1024 == static_site.DEFAULT_MAX_RESPONSE_BYTES
    # 139,264 / 124,177 — the tightness the ceiling had on the day it was chosen.
    assert round(139_264 / _CEILING_PROVENANCE_G, 3) == 1.121


def test_the_live_law_holds_over_the_tree_that_ships_today() -> None:
    """**THE LIVE LAW.** I3 and the straddle — over the record, and then over the archive.

    Ruling **R10** §1.2. What the ceiling must actually guarantee is four things: the origin
    can still serve its own site, the ceiling is still tight enough to refuse something, it
    sits between the largest object this origin puts on the wire and the largest one it turns
    away, and there is still a margin between the two. This is the assertion that goes red if
    the console outgrows the origin, and the first one to read when it does — the provenance
    test above cannot tell you that, and is not asked to.

    **TWO SUBJECTS, AND THE SECOND ONE IS NEW ON 2026-08-16.** Until today this test's name
    said *the tree that ships today* and its body read the declarations at the top of this
    file, so what it actually checked was that four hand-recorded numbers were mutually
    consistent. They were, on the day somebody recorded them, and the test then went red on
    the next build for the one reason that is not a property — the entry chunk's content hash
    moved. Now the four properties are asserted **twice**: once over the frozen provenance
    record, which is a historical fact and cannot go stale, and once over whatever
    ``out/lambda/mainline-demo-api-arm64.zip`` holds right now, with the entry chunk resolved
    by pattern rather than named. The second half skips on a clean checkout that has no build
    output; the first half runs everywhere, so the law is never entirely unasserted.

    **The margin is the fourth thing and it is a BOUND, not a measurement:**
    :data:`_MINIMUM_HEADROOM_BYTES`. The other three hold just as contentedly at 1 B of
    headroom, and one byte before an outage is not a state anybody should be able to reach
    without a test having said so first. See :func:`_assert_headroom`.
    """
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES

    # ── OVER THE RECORD. Build `5302005`: 0 < 137,939 < 139,264 < 490,373, and the same
    # shape held at `f0ba767` (0 < 138,177 < 139,264 < 490,950) and at `b822fdc`
    # (0 < 129,400 < 139,264 < 457,123). Above everything this origin puts on the wire,
    # below the one identity object it refuses. A ceiling that failed either half would be a
    # decoration: too low and the demo goes dark, too high and it refuses nothing.
    _assert_i3(ceiling, _LARGEST_SERVED_WIRE_BYTES)
    assert 0 < _LARGEST_SERVED_WIRE_BYTES < ceiling < _LARGEST_IDENTITY_BYTES
    _assert_headroom(ceiling, _LARGEST_SERVED_WIRE_BYTES)
    # The record's own arithmetic, checkable by hand and frozen with the row it belongs to:
    # 139,264 - 137,939 = 1,325. Both sides move only when somebody re-records both, so this
    # equality can never be what fails a build — which is exactly why it is allowed to be an
    # equality at all.
    assert ceiling - _LARGEST_SERVED_WIRE_BYTES == _PROVENANCE_HEADROOM_BYTES
    assert _IDENTITY_BYTES + _SIBLING_BYTES == _WEB_TREE_BYTES
    assert _IDENTITY_ENTRIES * 2 == _WEB_ENTRIES

    # ── OVER THE ARCHIVE. The same four, against whatever is in `out/lambda/` — no name
    # typed here, no byte count typed here. `g` is the widest `.gz` sibling the tree holds
    # and the largest identity object is the one the ceiling refuses; if a build ever
    # separates those two, `_resolve_entry_chunk` says so rather than this test drifting.
    web = _package_web()
    identity, siblings = _split_web_tree(web)
    entry = _resolve_entry_chunk(identity)
    served = max(siblings.values())
    assert siblings[entry + ".gz"] == served, (
        f"the widest sibling in the tree is not the entry chunk's: {entry}.gz is "
        f"{siblings[entry + '.gz']} B against a maximum of {served} B. `g` is supposed to BE "
        "the entry chunk's compressed size; if it is not, the flood multiplier belongs to "
        "some other object and the cost model is quoting the wrong row."
    )
    _assert_i3(ceiling, served)
    assert 0 < served < ceiling < identity[entry]
    _assert_headroom(ceiling, served)

    # The I3 ratio: 1.121 → 1.076 → 1.008 → 1.010, i.e. hovering just above 1.0. For
    # `_RATCHET` that is the safe direction — the bound bites harder relative to the tree
    # rather than floating above it — and `_assert_i3` refuses only the climb toward 1.20.
    # What the ratio ALSO says is how thin the margin is, and nothing in `_assert_i3` can
    # express that; `_assert_headroom` is the sentence that does. The ratio itself is
    # PROVENANCE — it moves with `g` on every release — so it is bounded here, not pinned.
    ratio = ceiling / served
    assert 1.0 <= ratio < _RATCHET, f"the I3 ratio left its window: {ratio}"


def test_the_declared_largest_served_object_binds_the_ceiling() -> None:
    """I3 against the declaration. Runs everywhere, built package or not.

    The tree-reading assertions below are the ones that keep this declaration honest, but
    they need a build output that a clean checkout does not have. This one needs nothing,
    so raising the constant is red on any machine rather than red only where somebody
    happened to have built the console.
    """
    _assert_i3(static_site.DEFAULT_MAX_RESPONSE_BYTES, _LARGEST_SERVED_WIRE_BYTES)


@pytest.mark.parametrize(
    ("ceiling", "why"),
    [
        (2 * 1024 * 1024, "the value an independent verifier called a control in name only"),
        (512 * 1024, "the value that refused 0 of 57 once the source-map strip landed"),
        (1024 * 1024, "halfway between the two, and just as far above everything"),
        # THE EDGE, COMPUTED RATHER THAN TRANSCRIBED — changed 2026-08-16 and this is the
        # reason. The case pins the smallest ceiling `_assert_i3` must still refuse: the
        # first integer at or above `_RATCHET x g`. Written as a literal it was 149,000,
        # then 149,013, then 155,280, then 165,813 — four re-records of one sentence, each
        # of them a hand-copied consequence of a measurement that moves on every console
        # release. Worse, a stale literal here fails SILENTLY IN THE SAFE-LOOKING DIRECTION:
        # when `g` grows past the old pin, the old pin drops BELOW `1.20 x g`, `_assert_i3`
        # starts ACCEPTING it, and this case stops raising. Deriving it from the same `g`
        # the check reads makes the pin exact for every build and removes the transcription
        # step entirely. `math.ceil` and not `int(...) + 1`: at `g = 129,400` the product is
        # exactly 155,280.0, and the edge there is 155,280 itself. **This is not a ceiling
        # anybody may ship** — `DEFAULT_MAX_RESPONSE_BYTES` is untouched at 139,264 — it is
        # a value pinned to show where the edge is. At build `5302005` it evaluates to
        # 165,527 (`1.20 x 137,939 = 165,526.8`).
        (math.ceil(_RATCHET * _LARGEST_SERVED_WIRE_BYTES), "one step past the ratchet"),
        (100_000, "below the largest served object: the origin would 413 its own site"),
    ],
    ids=["two-mib", "five-twelve-kib", "one-mib", "just-over-the-ratchet", "too-tight"],
)
def test_the_i3_rule_rejects_the_ceilings_it_is_meant_to_reject(ceiling: int, why: str) -> None:
    """**The falsification.** The check is only worth what it refuses.

    Each value below is one this repository either shipped or could plausibly reach, and
    every one of them must make :func:`_assert_i3` raise. Without this, an assertion that
    happens to be satisfied by the current constant is indistinguishable from an assertion
    that is satisfied by everything — which is the defect the ceiling itself had, twice.
    """
    with pytest.raises(AssertionError):
        _assert_i3(ceiling, _LARGEST_SERVED_WIRE_BYTES)
    assert why  # the reason travels with the case rather than in a comment above it


@pytest.mark.parametrize(
    ("largest_served", "why"),
    [
        # The one that matters, and it is NOT a measurement: `ceiling - minimum + 1`, the
        # first `g` the guard must refuse. 139,264 - 1,024 + 1 = 138,241 leaves 1,023 B —
        # under the reserve and still 1,023 B clear of an outage, which is exactly the state
        # this guard exists to catch WHILE it is still recoverable. Both terms are bounds, so
        # this value does not move when the console does; at `f0ba767` it was 64 gzipped
        # bytes of growth away and at `5302005` it is 302.
        (139_264 - 1_024 + 1, "one byte past the reserve: red here, still serving"),
        (139_263, "one byte of headroom: the last state before the origin refuses itself"),
        (139_264, "no headroom at all: g == C, and _assert_i3 still passes at this value"),
        (139_265, "over the ceiling: the outage itself, caught by I3 as well as by this"),
        # Any identity entry chunk this repository has shipped, i.e. what the guard says if
        # the packer ever stops writing `.gz` siblings and `g` becomes the identity size.
        # 433,396 → 457,123 → 490,950 → 490,373: every one of them refused, so this case
        # needed no re-recording at any of those builds and needs none at the next.
        (_LARGEST_IDENTITY_BYTES, "the identity entry chunk: the siblings stopped being written"),
    ],
    ids=["one-byte-past-the-reserve", "one-byte-left", "exactly-zero", "over", "no-compression"],
)
def test_the_headroom_guard_refuses_the_margins_it_is_meant_to_refuse(
    largest_served: int, why: str
) -> None:
    """**The falsification of the headroom guard.** It is only worth what it refuses.

    A guard nobody has seen go red is decoration, so the values that must make it raise are
    pinned here rather than trusted. **Re-falsified 2026-08-16** — a threshold above the live
    margin was planted, this file and its two neighbours went red naming the margin, and the
    plant was reverted — because a guard that has not been seen go red *since the code around
    it changed* is decoration again. Two cases are worth reading twice:

    * ``139,264``, where ``g == C`` exactly. :func:`_assert_i3` **passes** at that value, by
      design: its lower bound is ``largest_served <= ceiling`` and the origin can, technically,
      still emit its widest response. So the state one byte from a blank page is a state I3
      calls fine, and this is the only assertion in the file that does not.
    * ``ceiling - minimum + 1`` = 138,241. It leaves 1,023 B, one byte under
      :data:`_MINIMUM_HEADROOM_BYTES`, and the origin is still serving every object it has.
      That is the point of the guard: it fires where the fix is still "make the chunk
      smaller" rather than "the demo is down". **It is built from two bounds and no
      measurement**, so it is the one case here that never needed re-recording when the
      console moved — which is what every case in this file should look like.

    The complement is asserted too — the recorded margin and the live tree must NOT raise —
    because a guard that refuses everything is as useless as one that refuses nothing, and
    would be indistinguishable from one here if only the raising half were checked.
    """
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    with pytest.raises(AssertionError):
        _assert_headroom(ceiling, largest_served)
    assert why  # the reason travels with the case rather than in a comment above it

    # The negative control, in the same test so it cannot be deleted separately: the recorded
    # margin passes, and so does exactly the minimum. The live tree's own margin is the
    # negative control in `test_the_live_law_holds_over_the_tree_that_ships_today`, which
    # reads the archive; keeping this half free of the archive is what lets it run on a
    # clean checkout.
    _assert_headroom(ceiling, _LARGEST_SERVED_WIRE_BYTES)
    _assert_headroom(ceiling, ceiling - _MINIMUM_HEADROOM_BYTES)


#: The console's own budget gate, and the row in it that is welded to the ceiling above.
#: `verticals/mainline/apps/console/scripts/check-budgets.ts` gzips every object reachable
#: from an HTML entry and refuses the build whose widest one exceeds `max_gzip_bytes`.
_CONSOLE_BUDGETS: Final = REPO_ROOT / "verticals/mainline/apps/console/budgets.json"
_ENTRY_CHUNK_WIRE_BUDGET: Final = "entry-chunk-wire"


def test_the_console_ci_budget_goes_red_before_the_origin_does() -> None:
    """**The weld.** The console's CI budget and this origin's ceiling are one bound in two
    files, and this is the assertion that stops them drifting apart.

    :func:`_assert_headroom` is the last line before the origin refuses its own site, but it
    only runs where a built package exists, and by the time it reads one the build it is
    complaining about is already sitting in ``out/lambda/``. The console's own gate runs
    **during** ``pnpm run ci``, on ``dist/``, before anything is packed — so it is where the
    approach should be caught. For that to be true its threshold has to be exactly
    ``DEFAULT_MAX_RESPONSE_BYTES - _MINIMUM_HEADROOM_BYTES``: one byte higher and CI passes a
    build this file would refuse; one byte lower and the two guards disagree about what the
    rule is.

    **Why an equality and not ``<=``.** A ``<=`` would let somebody buy a green by loosening
    ``budgets.json`` while leaving this file untouched, which is the same move as raising the
    ceiling, wearing a filename that no reviewer of this file would think to open. Ruling
    **R3** (``docs/demo/proof-and-polish-plan.md``) freezes both bounds; this makes the freeze
    checkable from the side the pressure actually comes from.

    **And the ban, in the same test, because bytes without a cause are half a guard.** The
    budget catches the entry chunk crossing; the ``forbidden_in_entry`` row catches the edit
    that would make it cross — a static import from the console into ``src/operator/``, which
    would weld a 96,734 B surface into a chunk with four figures of headroom. The screens the
    film is shot on are a SECOND HTML ENTRY for exactly this reason
    (``verticals/mainline/apps/console/operator.html``), and a boundary that is a convention
    rather than a check is a boundary that survives until the first hurry.
    """
    config = json.loads(_CONSOLE_BUDGETS.read_text(encoding="utf-8"))
    wire = config.get("wire_ceiling")
    assert wire is not None and wire.get("id") == _ENTRY_CHUNK_WIRE_BUDGET, (
        f"{_CONSOLE_BUDGETS} no longer carries a `wire_ceiling` gate, so nothing in "
        "`pnpm run ci` measures the one number that can take the demo dark: the widest "
        "SINGLE object the origin has to serve. Every budget in that file's `budgets` array "
        "is a SUM over a closure, and this ceiling is per object — a sum can pass at 63 % of "
        "its threshold while one chunk inside it is a few hundred bytes from a blank page."
    )

    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    assert wire["max_gzip_bytes"] == ceiling - _MINIMUM_HEADROOM_BYTES == 138_240, (
        f"the console's entry-chunk wire budget is {wire['max_gzip_bytes']} B, but this "
        f"origin refuses at {ceiling} B and this repository reserves "
        f"{_MINIMUM_HEADROOM_BYTES} B of it, so the budget must be "
        f"{ceiling - _MINIMUM_HEADROOM_BYTES} B. A budget above that number lets CI pass a "
        "build that is already inside the margin; below it, the two guards disagree. Fix the "
        "budget — do NOT raise DEFAULT_MAX_RESPONSE_BYTES and do NOT lower "
        "_MINIMUM_HEADROOM_BYTES to make this equality hold."
    )
    # A wire budget that summed its closure would be the gate that could not see the cliff:
    # on 2026-08-16 the closure sum sat at 63 % of its threshold in the same build whose
    # entry chunk was 1,332 B from a 413.
    assert wire["measure"] == "largest_object"
    assert wire["required"] is True
    # `all`, not `static`: a lazy chunk over the ceiling is a 413 too. It is a broken
    # feature rather than a blank page, but it is the same refusal.
    assert wire["follow"] == "all"

    banned = {(row["match"], row.get("in", "entry")) for row in config["forbidden_in_entry"]}
    assert ("src/operator/", "index.html") in banned, (
        "nothing stops the operator screens becoming statically reachable from the console "
        "entry chunk. They are a second HTML entry precisely because that chunk has four "
        "figures of headroom under this origin's ceiling; one static import would undo it, "
        "and the first symptom in production is a 413 on the entry JavaScript and a blank "
        "page for every browser."
    )


def _package_web() -> dict[str, int]:
    """``{name inside web/: bytes}`` from the built package, or skip loudly.

    The zip is a build output and is ``.gitignore``'d, so a clean checkout does not have
    one and this cannot silently pass. It says what to run instead.
    """
    if not _PACKAGE.is_file():
        pytest.skip(
            f"the deployed package {_PACKAGE} is not built, so the ceiling's derivation "
            "was NOT checked against a real tree in this session. Run "
            "scripts/deploy/build_lambda.ps1 (or .sh) to arm it. The declaration-only "
            "assertions in this section still ran."
        )
    with zipfile.ZipFile(_PACKAGE) as archive:
        return {
            info.filename[len("web/") :]: info.file_size
            for info in archive.infolist()
            if info.filename.startswith("web/") and not info.is_dir()
        }


def _split_web_tree(web: dict[str, int]) -> tuple[dict[str, int], dict[str, int]]:
    """``(identity, siblings)``: the objects that have URLs, and the codings that do not.

    One function rather than a comprehension at each call site, because the split is the
    thing every assertion in this section depends on: interface I1 gives one set of bytes
    one name, so a ``.gz`` is reachable only by negotiating on its identity object's URL,
    and an enumeration that mixed the two columns would report 77 404s as ceiling refusals.
    """
    identity = {name: size for name, size in web.items() if not name.lower().endswith(".gz")}
    siblings = {name: size for name, size in web.items() if name.lower().endswith(".gz")}
    return identity, siblings


def test_the_deployed_package_is_the_tree_the_ceiling_was_derived_from() -> None:
    """The artefact's SHAPE, checked against what the ceiling's arithmetic assumes about it.

    **Read this test's name in the past tense** (ruling **R10**). The ceiling was derived
    over the 2026-08-14 tree, whose gzipped figure is frozen in ``_CEILING_PROVENANCE_G``.
    What must hold over the tree that ships today is I3, the straddle and the margin, and
    those are asserted by ``test_the_live_law_holds_over_the_tree_that_ships_today``.

    **WHAT THIS TEST STOPPED ASSERTING ON 2026-08-16, AND WHY THAT IS NOT A LOOSENING.**
    It used to compare five hand-recorded totals to the archive for equality — entry count,
    object count, largest sibling, largest object, second-largest object. Four of those five
    are the *size of a console somebody deliberately grew*, and the fifth is a content hash's
    file size; every one of them therefore went red on a legitimate release, three times in
    two days, and each time the repair was to type the new numbers in. **A number that is
    re-recorded whenever it fails never refused anything.** What it did do was hide the
    assertions that matter inside a wall of red.

    What is asserted here now is the tree's SHAPE, which is what the ceiling's arithmetic
    actually rests on and none of which moves when the console does:

    * every identity object carries exactly one ``.gz`` sibling, no orphan and no gap — this
      is what makes ``g`` the compressed column throughout rather than a mixture of the two,
      and the whole I3 derivation is void without it;
    * the entry chunk resolves by pattern, is unique, and IS the largest identity object;
    * the widest sibling is that same object's — so the flood multiplier belongs to the
      object the cost model says it belongs to;
    * EXACTLY ONE identity object sits at or above the ceiling, and it is the entry chunk;
    * the second-largest identity object is under the ceiling, so the refusal is isolated;
    * zero source maps ship. The strip is the builder's default and this is the assertion
      that notices it being turned off — 3,179,550 B of debug artefact billable to this
      account by anyone on the internet.

    The recorded totals still exist, above, as dated provenance. They are read by a human,
    not by an equality.
    """
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    web = _package_web()
    identity, siblings = _split_web_tree(web)

    assert sorted(siblings) == sorted(name + ".gz" for name in identity), (
        "the package no longer pairs one sibling to one object. `g` is read off the "
        "compressed column for every object; an unpaired object is served identity, and its "
        "size — not its sibling's — is then what this origin emits."
    )
    assert len(identity) == len(siblings) > 0
    assert len(web) == 2 * len(identity), (
        f"{len(web)} web/ entries against {len(identity)} identity objects: something in the "
        "tree is neither an addressable object nor exactly one object's sibling."
    )

    entry = _resolve_entry_chunk(identity)
    widest_sibling = max(siblings.items(), key=lambda item: item[1])[0]
    assert widest_sibling == entry + ".gz", (
        f"the widest sibling is {widest_sibling}, not the entry chunk's. The flood "
        "multiplier the cost model quotes is the entry chunk's compressed size; if some "
        "other object now emits more bytes, that row is about the wrong file."
    )

    over = sorted(name for name, size in identity.items() if size >= ceiling)
    assert over == [entry], (
        f"{len(over)} identity objects are at or above the {ceiling} B ceiling: {over}. "
        "Exactly one — the entry chunk — is the declared consequence of this ceiling. A "
        "second one is an asset nobody decided to stop serving; none at all is a ceiling "
        "that has stopped biting, which is the state it was in at 2 MiB and at 512 KiB."
    )
    second = sorted(identity.values())[-2]
    assert second < ceiling, (
        f"the second-largest identity object is {second} B, at or above the {ceiling} B "
        "ceiling. The refusal is supposed to be isolated to the entry chunk; two objects "
        "over the bound is a different trade and has to be argued for separately."
    )

    assert [name for name in web if name.lower().endswith(".map")] == [], (
        "the package carries source maps. build_lambda strips web/**/*.map by default; a "
        "build that shipped them would put the whole of this section's arithmetic back on "
        "the wrong tree, which is the mistake the 512 KiB ceiling was made of."
    )


def test_serving_the_deployed_package_derives_the_ceiling_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """**The one that matters.** Unpack the real package, serve every object through the
    real code at the real default ceiling, and derive the bound from what came back.

    Not from file sizes: from ``len`` of the bytes each response actually puts on the wire,
    both ways round — once as a browser (``Accept-Encoding: gzip``) and once as a client
    that refuses compression, because an anonymous caller picks which one and the ceiling
    exists to bound the choice they make, not the choice we would prefer.

    What it asserts about the refusal is stated rather than tolerated: **exactly one identity
    object answers 413, on the identity path only, and it is the console's entry chunk.** It
    is a 200 to every browser that will ever load this console and a 413 to a client that
    asked for 490 KB uncompressed — which is the caller a wire ceiling is for. ``curl``
    without ``--compressed`` is such a client; that cost is real and is the price of the
    compressed multiplier the cost model quotes.

    **THE ARITY IS THE CLAIM AND THE NAME IS THE MEASUREMENT — and until 2026-08-16 this
    test asserted the name.** It read ``refused == {"assets/index-<hash>.js [identity]":
    413}`` with the hash typed in, so a build-id-only re-release turned it red while every
    property it exists to check was still true. The dict equality is kept, because a bound
    on the *count* would tolerate the refusal moving to some other object; what changed is
    that the expected key is now RESOLVED — the entry chunk found by pattern in the archive —
    instead of transcribed. One of 57 became one of 69 became one of 77 without the property
    changing, and it is the property this asserts.
    """
    monkeypatch.delenv(static_site.RESPONSE_BYTES_ENV, raising=False)
    web = _package_web()
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES

    root = tmp_path / "web"
    with zipfile.ZipFile(_PACKAGE) as archive:
        for name in web:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read("web/" + name))

    identity_map, siblings = _split_web_tree(web)
    entry = _resolve_entry_chunk(identity_map)
    identity_names = sorted(identity_map)
    widest = ("", 0)
    refused: dict[str, int] = {}
    for name in identity_names:
        for accept in (None, _BROWSER):
            response = static_site.serve("GET", "/" + name, root=root, accept_encoding=accept)
            if response["statusCode"] != 200:
                refused[f"{name} [{'gzip' if accept else 'identity'}]"] = response["statusCode"]
                continue
            wire = len(_body_bytes(response))
            assert wire == int(response["headers"]["content-length"])
            if wire > widest[1]:
                widest = (name, wire)

    # The refusal set. The KEY is resolved from the archive and the SHAPE is the assertion:
    # exactly one object, on the identity path, answering 413. A second key is an asset
    # nobody decided to stop serving; an empty dict is a ceiling that stopped biting.
    assert refused == {f"{entry} [identity]": 413}, (
        f"the deployed package refuses {sorted(refused)}; the entry chunk this tree resolves "
        f"to is {entry}. Exactly one object, on the identity path, is the declared "
        "consequence of this ceiling; anything else is an asset nobody decided to stop "
        "serving, or a ceiling that stopped biting."
    )

    # The live law, from the RESPONSES rather than from the archive's metadata (ruling R10):
    # the widest thing that actually left this origin is what I3 is checked against. Note
    # that the two agree only if `serve` really emitted the sibling — this is the assertion
    # that would catch negotiation silently breaking and the identity bytes going out
    # instead, which no reading of the central directory can see.
    assert widest == (entry, siblings[entry + ".gz"]), (
        f"the widest response the package emitted is {widest}; the entry chunk's sibling in "
        f"the archive is {siblings[entry + '.gz']} B. If those disagree, `serve` is not "
        "putting the compressed representation on the wire and the flood multiplier in the "
        "cost model is the wrong number."
    )
    _assert_i3(ceiling, widest[1])
    # …and the headroom guard against the SERVED number, so it reads what this origin
    # actually emits rather than what any declaration says it emits.
    _assert_headroom(ceiling, widest[1])

    # And the browser — the client every judge will actually be — gets every one of them.
    served = [
        name
        for name in identity_names
        if static_site.serve("GET", "/" + name, root=root, accept_encoding=_BROWSER)["statusCode"]
        == 200
    ]
    assert len(served) == len(identity_names), (
        f"{len(identity_names) - len(served)} of {len(identity_names)} objects are refused to "
        "a browser. Every identity object has a sibling under the ceiling, so a browser is "
        "supposed to get all of them; one that does not is a broken page or a broken feature."
    )


def test_every_sibling_in_the_deployed_package_is_reachable_only_by_negotiation() -> None:
    """I1 over the real 69, not over a fixture: no sibling has a URL of its own."""
    web = _package_web()
    root = REPO_ROOT  # never read: the 404 is decided from the request, before any stat
    for name in sorted(name for name in web if name.endswith(".gz")):
        response = static_site.serve("GET", "/" + name, root=root)
        assert response["statusCode"] == 404, name
        assert json.loads(response["body"])["error"]["kind"] == "asset_not_found"
