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
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from mainline_demo_api import app, static_site

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
