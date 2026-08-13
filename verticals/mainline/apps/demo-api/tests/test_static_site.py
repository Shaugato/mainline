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

**Its ceiling is derived from the tree it governs, and section (f) is what keeps it
derived.** Twice now this constant has sat above every object it was supposed to bound —
at 2 MiB, and then at 512 KiB once the strip removed the only thing 512 KiB refused. A
ceiling above everything it governs cannot fail, so it proves nothing. The assertions in
(f) read the built package, compute the largest response the origin can actually emit, and
fail if the constant is not tight around it.
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
    object by exactly a third — and the object it would hurt most is the 124,127 B
    compressed entry bundle, weighed as 165,504 B, which is the single path the cost model
    depends on callers taking.

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


# ── (f) The ceiling is DERIVED from the deployed tree — interface I3 ────────────────
#
# Twice this constant has sat above every object it governs: at 2 MiB, and then at 512 KiB
# once `build_lambda` began stripping source maps and removed the only object 512 KiB
# refused. Both times the docstring beside it claimed otherwise. A ceiling that cannot fail
# proves nothing, so the number is now a CONSEQUENCE of the tree and these assertions are
# what keep it one.

#: The deployed artefact. This is the tree the ceiling is derived over, and it is the only
#: tree that HAS the `.gz` siblings: the packer's input tree (`console/dist` +
#: `console/fixtures/bundles/demo-cloud`, which is what `test_response_contract.py` falls
#: back to) is 75 pre-strip files with 18 source maps and zero siblings, so a derivation
#: measured there would be measured over bytes that no longer deploy. That is exactly the
#: mistake the 512 KiB value was made of.
_PACKAGE: Final = REPO_ROOT / "out/lambda/mainline-demo-api-arm64.zip"

#: Measured over that package on 2026-08-13, from the zip's central directory. Declared
#: rather than looked up so the two can be compared: a number read out of the tree at test
#: time agrees with the tree by construction and asserts nothing.
_LARGEST_SERVED_WIRE_BYTES: Final = 124_127  # web/assets/index-BjAGxrVJ.js.gz
_LARGEST_IDENTITY_BYTES: Final = 433_396  # web/assets/index-BjAGxrVJ.js
_SECOND_LARGEST_IDENTITY_BYTES: Final = 51_266  # web/assets/surface-Csi7pmRe.js
_WEB_ENTRIES: Final = 114
_IDENTITY_ENTRIES: Final = 57

#: The derivation, as three numbers rather than as prose. Ten per cent is the headroom an
#: asset may take between two deploys without the demo going dark; 8 KiB is the rounding
#: that turns the result into a number a human can hold; 1.20 is the ratchet that fails
#: this file when the tree outgrows the constant.
_HEADROOM: Final = 1.10
_ROUNDING: Final = 8 * 1024
_RATCHET: Final = 1.20


def _derive_ceiling(largest_served_wire_bytes: int) -> int:
    """The ceiling the rule produces from a tree. The constant must equal this."""
    floor = _HEADROOM * largest_served_wire_bytes
    return -(-int(floor // 1) // _ROUNDING) * _ROUNDING


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


def test_the_ceiling_is_the_derivation_and_not_a_number_somebody_liked() -> None:
    """The constant reproduced from the rule and the measurement, arithmetic in the open.

    ``1.10 x 124,127 = 136,540``; the next 8 KiB boundary above that is 139,264 = 136 KiB;
    ``139,264 / 124,127 = 1.122``, inside the 1.20 ratchet. Anyone can check those three
    lines by hand, which is the whole point of writing them here rather than asserting the
    constant against itself.
    """
    derived = _derive_ceiling(_LARGEST_SERVED_WIRE_BYTES)
    assert derived == 139_264 == 136 * 1024
    assert derived == static_site.DEFAULT_MAX_RESPONSE_BYTES
    ratio = static_site.DEFAULT_MAX_RESPONSE_BYTES / _LARGEST_SERVED_WIRE_BYTES
    assert round(ratio, 3) == 1.122


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
        (149_000, "one step past the ratchet, to pin where the edge is"),
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
    of the 57 answers 413, on the identity path only.** ``assets/index-BjAGxrVJ.js`` at
    433,396 B is a 200 to every browser that will ever load this console and a 413 to a
    client that asked for 433 KB uncompressed — which is the caller a wire ceiling is for.
    ``curl`` without ``--compressed`` is such a client; that cost is real and is the price
    of the 124,127 B multiplier the cost model quotes.
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

    assert refused == {"assets/index-BjAGxrVJ.js [identity]": 413}, (
        f"the deployed package refuses {sorted(refused)}. Exactly one object, on the "
        "identity path, is the declared consequence of the derived ceiling; anything else "
        "is an asset nobody decided to stop serving, or a ceiling that stopped biting."
    )

    # The derivation, from the responses rather than from the declaration.
    assert widest == ("assets/index-BjAGxrVJ.js", _LARGEST_SERVED_WIRE_BYTES)
    _assert_i3(ceiling, widest[1])

    # And the browser — the client every judge will actually be — gets all 57.
    served = [
        name
        for name in identity_names
        if static_site.serve("GET", "/" + name, root=root, accept_encoding=_BROWSER)[
            "statusCode"
        ]
        == 200
    ]
    assert len(served) == _IDENTITY_ENTRIES


def test_every_sibling_in_the_deployed_package_is_reachable_only_by_negotiation() -> None:
    """I1 over the real 57, not over a fixture: no sibling has a URL of its own."""
    web = _package_web()
    root = REPO_ROOT  # never read: the 404 is decided from the request, before any stat
    for name in sorted(name for name in web if name.endswith(".gz")):
        response = static_site.serve("GET", "/" + name, root=root)
        assert response["statusCode"] == 404, name
        assert json.loads(response["body"])["error"]["kind"] == "asset_not_found"
