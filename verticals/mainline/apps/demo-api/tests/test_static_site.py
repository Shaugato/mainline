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
    object by exactly a third — and the object it would hurt most is the 138,177 B
    compressed entry bundle of the package that ships (``sha256 7c97b532…``), weighed as
    184,236 B, which is the single path the cost model depends on callers taking. It was
    129,400 B / 172,536 B against ``sha256 6802872f…``; the hazard is the ratio, not either
    figure, and the encoded side of it is over 139,264 either way. **The wire side is now
    only 1,087 B under**, which makes this the one place worth saying that a 33 % measurement
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
#: something a rebuild does on the way past. It moves only with such a decision. Everything
#: below it is re-measured per build; this one is not, and that asymmetry is the point.
#: (Ruling **R10** §1.6, `docs/leads/reconcile-constants-plan.md`.)
_CEILING_PROVENANCE_G: Final = 124_177

# Everything from here to `_IDENTITY_ENTRIES` was **RE-MEASURED 2026-08-15 (SECOND
# RE-RECORD OF THE DAY)**, from the central directory of the package that ships:
# `out/lambda/mainline-demo-api-arm64.zip`,
# `sha256 7c97b532ea9016fadc2be8ddd2c9e95b28820758e38d0439916940cd41022d22`, built from HEAD
# `f0ba767` `--console-transport live` with `MAINLINE_BUILD_ID=f0ba767` and
# `VITE_MAINLINE_API_BASE=/`. The figures immediately before these were read from
# `sha256 6802872f…` (`MAINLINE_BUILD_ID=b822fdc`), which no longer deploys.
#
# WHAT MOVED THE CONSOLE THIS TIME, so a reader can tell growth from drift: the console
# gained seven working screens, a plain-language on-ramp on every screen, and a new
# `GET /v1/demo/subjects` endpoint (commit `9c902e0`). That is a deliberate change to what
# ships, so the entry chunk grew and — because a Vite chunk name is a content hash — renamed
# itself. Declared rather than looked up so the two can be compared: a number read out of the
# tree at test time agrees with the tree by construction and asserts nothing.
#
# **Why re-recording them is not moving a floor** — R1, and R5's derived/authoritative
# split. Each is a description of what one build emitted. None of them bounds anything:
# nothing is refused because one of them holds a particular value, and nothing gets cheaper
# if one of them shrinks. They are the INPUTS the bounds are checked against. The bounds are
# `static_site.DEFAULT_MAX_RESPONSE_BYTES`, `_HEADROOM`, `_ROUNDING`, `_RATCHET`,
# `_MINIMUM_HEADROOM_BYTES` and `_CEILING_PROVENANCE_G` — not one of those moves in this
# wave, and the ceiling is byte-identical before and after. Freezing a measurement would
# protect nothing; it would only make this file describe a tree that stopped existing, which
# is how the 512 KiB ceiling survived as long as it did.
#
# **WHICH OF THESE MOVE ON A RE-RELEASE AND WHICH DO NOT — the distinction worth stating
# once instead of re-editing forever.** `vite.config.ts` inlines `__MAINLINE_BUILD_ID__`, so
# the git short SHA reaches the emitted bytes. Across a build-id-only re-release every
# FILENAME below moves, every gzipped figure moves by a handful of bytes, and every IDENTITY
# size stays put. So: if an identity size moved, the console really changed and the straddle
# needs re-checking; if only names and gzip totals moved, it was a re-release and nothing
# that bounds anything was touched. Both happened today, and it was the first kind.

#: **was 129,400 → is 138,177** (+8,777), read from `sha256 7c97b532…`,
#: `--console-transport live`, `MAINLINE_BUILD_ID=f0ba767`. Interface I3's live input: the
#: largest number of bytes this origin can put on the wire for one response. A measurement of
#: a build, not a floor — it bounds nothing, it is what the bound is checked against.
#: `_derive_ceiling(138_177)` is 155,648 rather than 139,264; see
#: `test_the_ceiling_still_equals_the_number_its_derivation_chose` for why that is a
#: provenance record going out of date and not a ceiling going wrong.
#:
#: **THIS IS THE NUMBER THAT NOW CARRIES THE RISK IN THIS FILE.** Against an unchanged
#: 139,264 B ceiling it leaves **1,087 B of headroom — 0.78 %**, where the previous package
#: left 9,864 B. Read what crossing it costs before touching anything here: when `g` passes
#: the ceiling this origin answers **413 to its own entry JavaScript**, for every browser,
#: so `GET /` returns a shell that then fails to load its only module and a judge gets a
#: BLANK PAGE. That is a total demo outage, not a slow one, and it arrives with no warning
#: from production because the shell itself keeps answering 200. `_MINIMUM_HEADROOM_BYTES`
#: below exists to make the approach go red in CI instead. **The fix when it does is a
#: smaller or split entry chunk — never a larger ceiling.**
#:
#: Do not "fix" the filename churn here by dropping `MAINLINE_BUILD_ID`. A chrome that cannot
#: name the artefact a screenshot came from is the defect that shipped to the founder as
#: `BUILD dev`, and it is a worse defect than re-recording four measurements per release.
_LARGEST_SERVED_WIRE_BYTES: Final = 138_177  # web/assets/index-LoN3Sn_L.js.gz

#: **was 457,123 → is 490,950**, +33,827 B, from `sha256 7c97b532…` (`MAINLINE_BUILD_ID=
#: f0ba767`). The one identity object the ceiling refuses. A measurement of the entry chunk,
#: not a limit on it: what is authoritative is that EXACTLY ONE object is refused, and this
#: records which.
_LARGEST_IDENTITY_BYTES: Final = 490_950  # web/assets/index-LoN3Sn_L.js

#: **was 51,266 → is 67,049**, +15,783 B, from `sha256 7c97b532…`. Both the VALUE and the
#: OBJECT moved this time: the second-largest identity object is now
#: `assets/surface-BD2Wh4U2.js`, where in `sha256 6802872f…` it was `assets/surface-0lG8KzXw
#: .js` at 51,266 B. Still a measurement: it is here so a silent reshuffle of the chunk graph
#: cannot pass unnoticed, not because 67,049 is permitted and 67,050 is not. What it reports
#: is that the refusal is still isolated — this object sits 72,215 B **below** the ceiling
#: and 423,901 B below the object above it, so nothing else in the tree is near either bound.
_SECOND_LARGEST_IDENTITY_BYTES: Final = 67_049  # web/assets/surface-BD2Wh4U2.js

#: **was 114 / 57 → is 138 / 69**, +24 entries / +12 objects, from `sha256 7c97b532…`. This
#: pair DID move this time, where the previous re-record found it unchanged: the seven new
#: console screens are seven new lazily-loaded chunks and their CSS, so the console gained
#: files as well as bytes. Every one of the 69 still carries exactly one `.gz` sibling and no
#: sibling is an orphan, which is what keeps `_LARGEST_SERVED_WIRE_BYTES` the compressed
#: column throughout rather than a mixture of the two columns.
#:
#: **Read these out of the ARCHIVE, never out of `console/dist`.** The zip's own manifest
#: records `web_before` at 96 entries — the tree as the console build left it, before the
#: source-map strip (27 maps, 3,179,550 B) and before the packer wrote a `.gz` beside every
#: compressible object. 96 is a true number about a tree this origin never serves; 138 is the
#: tree that deploys, and only the second one is what a ceiling governs.
_WEB_ENTRIES: Final = 138
_IDENTITY_ENTRIES: Final = 69

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
#: OTHER direction, and that is the direction this package moved in: headroom fell 15,087 →
#: 9,864 → **1,087 B**, which is **0.78 %** of the ceiling. `_assert_i3`'s lower half does
#: catch the crossing, but it catches it the moment it has already happened, and by then the
#: same build is sitting in `out/lambda/` waiting to be applied.
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
#: WHY 1 KiB. It has to be strictly below today's 1,087 B or this assertion is red on arrival
#: and says nothing about the future; it has to be well above zero or it fires only after the
#: cliff. 1,024 B is the round number in that window, 63 B under the live measurement — so
#: the next console growth that adds more than 63 gzipped bytes to the entry chunk turns this
#: red in CI while the origin is still serving every object it has. That is deliberately a
#: hair trigger: at 0.78 % margin there is no such thing as a small console change any more.
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
    """**THE LIVE LAW.** I3 and the straddle, over the package that ships, not over history.

    Ruling **R10** §1.2. What the ceiling must actually guarantee is three things, and all
    three are measured true against ``sha256 7c97b532…``: the origin can still serve its own
    site, the ceiling is still tight enough to refuse something, and it sits between the
    largest object this origin puts on the wire and the largest one it turns away. This is
    the assertion that goes red if the console outgrows the origin, and the first one to
    read when it does — the provenance test above cannot tell you that, and is not asked to.

    **A fourth thing is asserted here as of 2026-08-15 and it is a new bound, not a new
    measurement:** :data:`_MINIMUM_HEADROOM_BYTES`. The three above all still hold at a
    margin of 1,087 B, which is 0.78 % — they would hold just as contentedly at 1 B, and one
    byte before an outage is not a state anybody should be able to reach without a test
    having said so first. See :func:`_assert_headroom`.
    """
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    _assert_i3(ceiling, _LARGEST_SERVED_WIRE_BYTES)

    # The straddle: 0 < 138,177 < 139,264 < 490,950 (it read `0 < 129,400 < 139,264 <
    # 457,123`). Above everything this origin puts on the wire, below the one identity object
    # it refuses. A ceiling that failed either half would be a decoration: too low and the
    # demo goes dark, too high and it refuses nothing. Only the outer two numbers moved.
    assert 0 < _LARGEST_SERVED_WIRE_BYTES < ceiling < _LARGEST_IDENTITY_BYTES

    # HEADROOM, AND THIS IS THE NUMBER WITH TEETH. 15,087 → 9,864 → **1,087 B**, which is
    # 0.78 % of the ceiling. A console growth adding more than 1,087 GZIPPED bytes to the
    # entry chunk puts `g` above the ceiling, and this origin then answers 413 for its own
    # entry JavaScript to every browser: the shell loads, its only module does not, and the
    # reader gets a blank page. That is a total demo outage. Carry THIS number in documents;
    # R10 §1.5 retired R4's `119,158 <= g <= 126,604` window, which was a pre-image band and
    # not a live constraint. The equality is the re-record; the inequality after it is the
    # bound, and it is the one that will go red first next time.
    assert ceiling - _LARGEST_SERVED_WIRE_BYTES == 1_087
    _assert_headroom(ceiling, _LARGEST_SERVED_WIRE_BYTES)

    # 139,264 / 138,177. The ratio fell 1.121 → 1.076 → 1.008, i.e. TOWARD 1.0. For
    # `_RATCHET` that is the safe direction — the bound is biting harder relative to the
    # tree, not floating above it — and `_assert_i3` refuses only the climb toward 1.20. But
    # 1.008 is also how thin the margin now is, and nothing in `_assert_i3` can say so; that
    # is the sentence `_assert_headroom` exists to add.
    assert round(ceiling / _LARGEST_SERVED_WIRE_BYTES, 3) == 1.008


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
        # DERIVED, and it moves whenever _LARGEST_SERVED_WIRE_BYTES does: the smallest
        # integer at or above 1.20 x 138,177 = 165,812.4, which is 165,813. It was 155,280
        # against the 129,400 B measurement (1.20 x gave exactly 155,280.0), 149,013 against
        # 124,177 B, and 149,000 against 124,127 B before that. Leaving it at 155,280 after
        # this rebuild (`sha256 7c97b532…`) moved `g` to 138,177 would not have weakened the
        # ratchet quietly: 155,280 is now BELOW 1.20 x 138,177, so `_assert_i3` would ACCEPT
        # it and THIS case would stop raising — the loud failure the pin exists to produce,
        # and the reason it is a `pytest.raises` rather than a comment. Raising the pin is
        # not raising a ceiling. `DEFAULT_MAX_RESPONSE_BYTES` is untouched at 139,264; this
        # is a value nobody may ship, pinned to show where the edge now is.
        (165_813, "one step past the ratchet, to pin where the edge is"),
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
        # The one that matters: the tree as it is, plus one more byte than the guard allows.
        # 138,241 leaves 1,023 B — under 1,024 and still 1,023 B clear of an outage, which is
        # exactly the state this guard exists to catch WHILE it is still recoverable.
        (138_241, "63 B of console growth from today's tree: red here, still serving"),
        (139_263, "one byte of headroom: the last state before the origin refuses itself"),
        (139_264, "no headroom at all: g == C, and _assert_i3 still passes at this value"),
        (139_265, "over the ceiling: the outage itself, caught by I3 as well as by this"),
        (490_950, "the identity entry chunk, i.e. the .gz siblings stopped being written"),
    ],
    ids=["sixty-three-bytes-on", "one-byte-left", "exactly-zero", "over", "no-compression"],
)
def test_the_headroom_guard_refuses_the_margins_it_is_meant_to_refuse(
    largest_served: int, why: str
) -> None:
    """**The falsification of the headroom guard.** It is only worth what it refuses.

    A guard nobody has seen go red is decoration, and this one is new — so the values that
    must make it raise are pinned here rather than trusted. Two of them are worth reading
    twice:

    * ``139,264``, where ``g == C`` exactly. :func:`_assert_i3` **passes** at that value, by
      design: its lower bound is ``largest_served <= ceiling`` and the origin can, technically,
      still emit its widest response. So the state one byte from a blank page is a state I3
      calls fine, and this is the only assertion in the file that does not.
    * ``138,241`` — today's tree plus 64 gzipped bytes. It leaves 1,023 B, one byte under
      :data:`_MINIMUM_HEADROOM_BYTES`, and the origin is still serving every object it has.
      That is the point of the guard: it fires where the fix is still "make the chunk
      smaller" rather than "the demo is down".

    The complement is asserted too — today's measurement must NOT raise — because a guard
    that refuses everything is as useless as one that refuses nothing, and would be
    indistinguishable from one here if only the raising half were checked.
    """
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    with pytest.raises(AssertionError):
        _assert_headroom(ceiling, largest_served)
    assert why  # the reason travels with the case rather than in a comment above it

    # The negative control, in the same test so it cannot be deleted separately: the tree
    # that ships today passes, and so does one byte above the minimum.
    _assert_headroom(ceiling, _LARGEST_SERVED_WIRE_BYTES)
    _assert_headroom(ceiling, ceiling - _MINIMUM_HEADROOM_BYTES)


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


def test_the_deployed_package_is_the_tree_the_ceiling_was_derived_from() -> None:
    """The declaration above, checked against the artefact it claims to describe.

    This is what stops the constants in this file from becoming folklore. Each is an
    equality rather than a bound, because a bound would let the tree grow toward the
    ceiling without anybody deciding that was acceptable — which is precisely how the
    largest object drifted while every test stayed green last time.

    **Read this test's name in the past tense** (ruling **R10**). The ceiling was derived
    over the 2026-08-14 tree, whose gzipped figure is frozen in ``_CEILING_PROVENANCE_G``.
    The tree read here is the one that ships today, ``sha256 7c97b532…``, and what must hold
    over it is I3 and the straddle, asserted by
    ``test_the_live_law_holds_over_the_tree_that_ships_today``. This test's own job is
    narrower and unchanged: keep the declarations above equal to the artefact, so that when
    the tree moves somebody has to come here and say so in writing.
    """
    web = _package_web()
    identity = {name: size for name, size in web.items() if not name.endswith(".gz")}
    siblings = {name: size for name, size in web.items() if name.endswith(".gz")}

    assert len(web) == _WEB_ENTRIES
    assert len(identity) == _IDENTITY_ENTRIES
    assert len(siblings) == _IDENTITY_ENTRIES

    # Every identity object has a sibling and no sibling is an orphan. This is what makes
    # `largest_served_wire_bytes` the compressed column throughout rather than a mixture.
    assert sorted(siblings) == sorted(name + ".gz" for name in identity)

    assert max(siblings.values()) == _LARGEST_SERVED_WIRE_BYTES
    assert max(identity.values()) == _LARGEST_IDENTITY_BYTES
    assert sorted(identity.values())[-2] == _SECOND_LARGEST_IDENTITY_BYTES
    # No source map ships; the strip is the builder's default and this is the assertion
    # that would notice it being turned off.
    assert [name for name in identity if name.endswith(".map")] == []


def test_serving_the_deployed_package_derives_the_ceiling_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """**The one that matters.** Unpack the real package, serve every object through the
    real code at the real default ceiling, and derive the bound from what came back.

    Not from file sizes: from ``len`` of the bytes each response actually puts on the wire,
    both ways round — once as a browser (``Accept-Encoding: gzip``) and once as a client
    that refuses compression, because an anonymous caller picks which one and the ceiling
    exists to bound the choice they make, not the choice we would prefer.

    What it asserts about the refusal is stated rather than tolerated: **exactly one object
    of the 69 answers 413, on the identity path only.** Today that object is
    ``assets/index-LoN3Sn_L.js`` at 490,950 B, in the package that ships
    (``sha256 7c97b532…``, ``--console-transport live``, ``MAINLINE_BUILD_ID=f0ba767``); it
    was ``index-BH5dfAvF.js`` at 457,123 B in ``sha256 6802872f…``. It is a 200 to every
    browser that will ever load this console and a 413 to a client that asked for 490 KB
    uncompressed — which is the caller a wire ceiling is for. ``curl`` without
    ``--compressed`` is such a client; that cost is real and is the price of the 138,177 B
    multiplier the cost model quotes.

    **The arity is the claim and the name is the measurement.** One of 57 became one of 69
    without the property changing: the console gained twelve objects and none of them is
    anywhere near the ceiling. What would be a change is a second name appearing in
    ``refused``, and that is why this is an equality on a dict rather than a count.
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

    identity_names = sorted(name for name in web if not name.endswith(".gz"))
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

    # The refusal set, re-measured from `sha256 7c97b532…`: was `index-BH5dfAvF.js`, is
    # `index-LoN3Sn_L.js`. The NAME is the measurement; the property — exactly one, identity
    # path only — is what is authoritative and it did not move.
    assert refused == {"assets/index-LoN3Sn_L.js [identity]": 413}, (
        f"the deployed package refuses {sorted(refused)}. Exactly one object, on the "
        "identity path, is the declared consequence of the derived ceiling; anything else "
        "is an asset nobody decided to stop serving, or a ceiling that stopped biting."
    )

    # The live law, from the responses rather than from the declaration (ruling R10): the
    # widest thing that actually left this origin is what I3 is checked against. The name
    # was `index-BH5dfAvF.js` and is `index-LoN3Sn_L.js`; the number was 129,400 and is
    # 138,177. Both are measurements of `sha256 7c97b532…` — what they feed is the bound.
    assert widest == ("assets/index-LoN3Sn_L.js", _LARGEST_SERVED_WIRE_BYTES)
    _assert_i3(ceiling, widest[1])
    # …and the headroom guard against the SERVED number rather than the declared one, so it
    # reads the artefact even if the declaration above ever drifts off it. This is the
    # assertion that would have caught the console growing 64 more gzipped bytes than it did.
    _assert_headroom(ceiling, widest[1])

    # And the browser — the client every judge will actually be — gets all 69.
    served = [
        name
        for name in identity_names
        if static_site.serve("GET", "/" + name, root=root, accept_encoding=_BROWSER)["statusCode"]
        == 200
    ]
    assert len(served) == _IDENTITY_ENTRIES


def test_every_sibling_in_the_deployed_package_is_reachable_only_by_negotiation() -> None:
    """I1 over the real 69, not over a fixture: no sibling has a URL of its own."""
    web = _package_web()
    root = REPO_ROOT  # never read: the 404 is decided from the request, before any stat
    for name in sorted(name for name in web if name.endswith(".gz")):
        response = static_site.serve("GET", "/" + name, root=root)
        assert response["statusCode"] == 404, name
        assert json.loads(response["body"])["error"]["kind"] == "asset_not_found"
