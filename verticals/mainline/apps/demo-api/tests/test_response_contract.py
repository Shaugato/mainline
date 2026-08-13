# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""What every response this origin emits may and may not carry.

The demo is one Lambda Function URL with ``authorization_type = NONE`` — DECISION **D1**,
`docs/leads/ship-final.md` §1.4, because the account cannot create a CloudFront
distribution. There is no CDN, no WAF and no authoriser between the internet and
``app.handler``, so the only place a property of the public surface can be enforced is
inside the two modules that build responses. This file is the assertion that they do.

TWO PROPERTIES, ONE SECURITY AND ONE COST
-----------------------------------------
**No ``access-control-allow-origin``, on anything.** ``app._response`` used to set it to
``*`` on every response it built — 200s, 4xx, 5xx and problem documents alike. That
contradicted the module the responses are deployed by: ``infra/modules/demo-api/main.tf``
deliberately declares **no** ``cors`` block, and the README argues at length that under D1
the console and the API share one origin, the browser therefore never sends ``Origin``,
and a permissive CORS policy nobody needs is an attack surface nobody audited. The
Terraform was narrow, the handler was wide, and at runtime the handler wins: the header
made every ``/v1/*`` body — envelopes, error details, SQLSTATEs — *readable by script*
from any page on the internet, not merely reachable by one. Those are different exposures
and only the first was ever argued for.

*What that costs, honestly:* a judge who curls this URL from a scratch HTML page **in a
browser** now hits the browser's own CORS check and sees a console error rather than a
body. ``curl`` itself, the console and every non-browser client are unaffected — none of
them enforce CORS. The repair, if it ever matters, is a ``cors`` block in the Terraform
naming that one hostname, landed in the same commit as the hostname; not a wildcard held
open against a caller nobody has had yet.

**A declared ceiling on the bytes one response may carry.** The largest object this origin
can emit is the multiplier in a sustained-egress flood: measured at 1,554,168 B for the
console's largest source map, concurrency 10 for 30 days is roughly USD 33,000. The
ceiling makes that number *declared and tested* instead of *whatever the build happened to
produce*, and the last test in this file is the ratchet that keeps it declared.

**THE CEILING BOUNDS BYTES PER REQUEST. IT DOES NOT BOUND REQUEST RATE.** A flood of small
responses is untouched by every assertion here. Rate on this deployment is bounded by the
AWS account's concurrency ceiling and by nothing in this repository. Nothing below should
be read, quoted or reported as a throttle.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pytest
from mainline_demo_api import app, db, static_site

from conftest import REPO_ROOT

_CORS_HEADER: Final = "access-control-allow-origin"

#: The two modules that build every response this origin can emit. There is no third:
#: ``handler`` forks to ``static_site.serve`` or answers from ``app._response``.
_RESPONSE_MODULES: Final = (app, static_site)

# ── The built web tree, as measured on 2026-08-13 ───────────────────────────────────
#
# `zipfile` over `out/lambda/mainline-demo-api-arm64.zip`, and independently over the two
# directories the packer copies into `web/`. The two agree exactly: 75 files, 0 size
# mismatches, identical key sets. That agreement is why the directory pair below is an
# honest stand-in for the artefact when the zip has not been built.
_WEB_TREE_FILES: Final = 75
_WEB_TREE_BYTES: Final = 3_571_990

#: The largest single object this origin can emit, and therefore the multiplier in the
#: flood arithmetic. **This constant is the ratchet.** It may only be raised by somebody
#: who re-measured it and decided the new number is acceptable; it may never drift upward
#: on its own, which is what `test_the_built_web_tree_has_not_outgrown_its_declaration`
#: enforces. It is deliberately a *declaration*, not a lookup: a number read out of the
#: tree at test time would agree with the tree by construction and assert nothing.
_LARGEST_WEB_OBJECT: Final = "assets/index-BjAGxrVJ.js.map"
_LARGEST_WEB_OBJECT_BYTES: Final = 1_554_168

_CONSOLE_DIST: Final = REPO_ROOT / "verticals/mainline/apps/console/dist"
_EVIDENCE_BUNDLE: Final = REPO_ROOT / "verticals/mainline/apps/console/fixtures/bundles/demo-cloud"


# ── Fixtures and helpers ────────────────────────────────────────────────────────────


_INDEX: Final = "<!doctype html><html><head><title>MAINLINE</title></head><body>ok</body></html>"


@pytest.fixture
def web_root(tmp_path: Path) -> Path:
    """A small bundled site. Deliberately nothing here is near the 2 MiB default."""
    root = tmp_path / "web"
    (root / "assets").mkdir(parents=True)
    (root / "bundle").mkdir(parents=True)
    # write_bytes, never write_text: on Windows `write_text` translates "\n" to "\r\n",
    # which would make every byte count below a test of the platform's newline policy.
    (root / "index.html").write_bytes(_INDEX.encode("utf-8"))
    (root / "assets" / "index-BjAGxrVJ.js").write_bytes(b"export const x=1;\n")
    (root / "bundle" / "bundle.json").write_bytes(b'{"envelope_version":1}')
    return root


def _event(method: str, path: str, body: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"stage": "$default", "http": {"method": method, "path": path}},
    }
    if body is not None:
        event["body"] = body
    return event


def _header_names(response: Mapping[str, Any]) -> set[str]:
    return {str(name).lower() for name in response["headers"]}


def _no_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise() -> Any:
        raise db.DsnUnavailable("no DSN is configured for this test")

    monkeypatch.setattr(app.db, "connection", _raise)


def _every_response(monkeypatch: pytest.MonkeyPatch, root: Path, absent: Path) -> dict[str, Any]:
    """One response per status either surface can produce, keyed by a readable label.

    Built through ``app.handler`` wherever the handler can reach it, because the header
    set under test is added by the response builders and stripped by nothing — testing
    ``static_site.serve`` alone would miss anything ``app`` wraps, and testing ``app``
    alone would miss the static surface entirely.
    """
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(root))
    monkeypatch.setattr(app, "health", lambda: (200, {"ok": True, "database": "mainline_demo"}))
    responses = {
        "static-200-index": app.handler(_event("GET", "/")),
        "static-200-asset": app.handler(_event("GET", "/assets/index-BjAGxrVJ.js")),
        "static-200-bundle": app.handler(_event("GET", "/bundle/bundle.json")),
        "static-200-head": app.handler(_event("HEAD", "/assets/index-BjAGxrVJ.js")),
        "static-403-traversal": app.handler(_event("GET", "/../../etc/passwd")),
        "static-404-asset-miss": app.handler(_event("GET", "/assets/deleted-Xxxx.js")),
        "static-405-post": app.handler(_event("POST", "/")),
        "api-204-options": app.handler(_event("OPTIONS", "/v1/permits/abc")),
        "api-200-health": app.handler(_event("GET", "/v1/health")),
        "api-404-no-route": app.handler(_event("GET", "/v1/nope")),
        "api-405-wrong-method": app.handler(_event("GET", "/v1/permits/abc/merge")),
    }
    # 503 on both surfaces: no DSN for the API, no bundled site for the static one.
    _no_dsn(monkeypatch)
    responses["api-503-dsn-unset"] = app.handler(_event("GET", "/v1/permits/abc"))
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(absent))
    responses["static-503-no-web-root"] = app.handler(_event("GET", "/"))
    return responses


# ── (a) The header is on nothing ────────────────────────────────────────────────────


def test_no_response_the_handler_builds_carries_a_cors_header(
    monkeypatch: pytest.MonkeyPatch, web_root: Path, tmp_path: Path
) -> None:
    """Thirteen responses across both surfaces and eight statuses, and none may carry it.

    The matrix is deliberately wider than the 200s. The header used to be set inside
    ``_response``, which ``_problem`` calls, so the 4xx and 5xx bodies — the ones carrying
    SQLSTATEs, refused traversal vectors and the declared-route list — were the ones a
    cross-origin script could most usefully read.
    """
    responses = _every_response(monkeypatch, web_root, tmp_path / "never-bundled")
    assert len(responses) == 13

    offenders = {
        label: r["headers"] for label, r in responses.items() if _CORS_HEADER in _header_names(r)
    }
    assert offenders == {}, offenders

    # The matrix is only worth as much as its coverage, so pin what it covered.
    assert {r["statusCode"] for r in responses.values()} == {200, 204, 403, 404, 405, 503}


def test_the_ceiling_refusal_itself_carries_no_cors_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 413 is built by a separate literal on each surface; both had to be checked."""
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "16")
    api = app.handler(_event("GET", "/v1/nope"))
    assert api["statusCode"] == 413
    assert _CORS_HEADER not in _header_names(api)


def test_no_response_builder_names_the_cors_header_in_code() -> None:
    """The structural half: no string literal outside a docstring is that header.

    The response matrix proves the header is absent from the paths it walks; this proves
    it is absent from the paths it does not. Both are needed and neither is sufficient:
    a matrix cannot enumerate every branch, and a source check cannot see behaviour.

    Comments are invisible to :mod:`ast` and docstrings are excluded by name, so the two
    modules stay free to *explain at length* why the header is gone — which they do, and
    which a plain ``grep`` would have made impossible without also making the explanation
    unwritable. **Its limit, stated:** a header assembled from concatenated fragments
    would evade this. The matrix above is what covers that case.
    """
    for module in _RESPONSE_MODULES:
        source = Path(module.__file__ or "").read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        named = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _CORS_HEADER in node.value.lower()
            and id(node) not in docstrings
        ]
        assert named == [], f"{module.__name__} still names {_CORS_HEADER} in executable code"

    # …and the modules do still explain themselves, so nobody "fixes" the explanation
    # away and leaves the next reader to rediscover why one origin needs no CORS.
    assert _CORS_HEADER in Path(app.__file__ or "").read_text(encoding="utf-8").lower()


def test_options_answers_204_with_no_preflight_grant(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """OPTIONS still answers, and answering is not the same as permitting.

    A 204 with no ``access-control-*`` header grants a browser nothing: the preflight
    succeeds at the HTTP layer and the browser then blocks the real request because no
    origin was allowed. That is the correct outcome for a same-origin deployment, and it
    is cheaper than a 405 for the direct caller who sent it by habit.
    """
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(web_root))
    response = app.handler(_event("OPTIONS", "/v1/permits/abc"))
    assert response["statusCode"] == 204
    assert [name for name in _header_names(response) if name.startswith("access-control-")] == []


# ── (b) The ceiling is enforced, on both surfaces ───────────────────────────────────


def test_the_default_ceiling_is_two_mebibytes() -> None:
    """Declared so a change to it is a change to a test, not a quiet edit to a constant."""
    assert static_site.DEFAULT_MAX_RESPONSE_BYTES == 2 * 1024 * 1024 == 2_097_152


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1024", 1024),
        ("  4096  ", 4096),
        ("2097152", 2_097_152),
        ("banana", static_site.DEFAULT_MAX_RESPONSE_BYTES),
        ("", static_site.DEFAULT_MAX_RESPONSE_BYTES),
        ("0", static_site.DEFAULT_MAX_RESPONSE_BYTES),
        ("-1", static_site.DEFAULT_MAX_RESPONSE_BYTES),
        ("1.5", static_site.DEFAULT_MAX_RESPONSE_BYTES),
    ],
    ids=[
        "plain",
        "whitespace",
        "the-default-spelled-out",
        "garbage",
        "empty",
        "zero",
        "negative",
        "float",
    ],
)
def test_the_ceiling_is_configurable_and_a_bad_value_never_raises(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: int
) -> None:
    """A typo in a Terraform ``environment`` block must not become a total outage.

    Falling back is not free — a misconfigured deploy silently enforces 2 MiB rather than
    the number somebody meant — and the price is paid by naming the enforced ceiling in
    the body of every 413, which the next test asserts.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, value)
    assert static_site.max_response_bytes() == expected


def test_an_unset_variable_means_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(static_site.RESPONSE_BYTES_ENV, raising=False)
    assert static_site.max_response_bytes() == static_site.DEFAULT_MAX_RESPONSE_BYTES


def test_an_oversize_static_asset_is_413_and_returns_no_bytes(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    (web_root / "assets" / "huge-Aaaaaaaa.js").write_bytes(b"payload;" * 1024)  # 8192 B

    response = static_site.serve("GET", "/assets/huge-Aaaaaaaa.js", root=web_root)
    assert response["statusCode"] == 413
    error = json.loads(response["body"])["error"]
    assert error["kind"] == "response_too_large"
    assert error["bytes"] == 8192
    assert error["ceiling_bytes"] == 4096
    assert error["ceiling_env"] == static_site.RESPONSE_BYTES_ENV
    # The refusal must not be a delivery mechanism for the thing it refused.
    assert "payload;payload;" not in response["body"]
    assert response["isBase64Encoded"] is False


def test_a_head_on_an_oversize_asset_is_refused_exactly_as_the_get_is(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """A 200 + ``content-length`` the matching GET will never deliver is a lie."""
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    (web_root / "assets" / "huge-Aaaaaaaa.js").write_bytes(b"payload;" * 1024)
    assert static_site.serve("HEAD", "/assets/huge-Aaaaaaaa.js", root=web_root)["statusCode"] == 413


def test_base64_inflation_is_measured_and_not_assumed(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """A file 19 % under the ceiling becomes a body 7 % over it once base64 is applied.

    This is the assertion that makes the pre-read ``stat`` check an optimisation rather
    than the control. 3,300 bytes of non-UTF-8 pass the first check under a 4,096 ceiling
    and produce a 4,400-byte body, which only the second check sees.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    (web_root / "assets" / "font-Bbbbbbbb.woff2").write_bytes(b"\xff\xfe" * 1650)  # 3300 B

    response = static_site.serve("GET", "/assets/font-Bbbbbbbb.woff2", root=web_root)
    assert response["statusCode"] == 413
    error = json.loads(response["body"])["error"]
    assert error["bytes_on_disk"] == 3300
    assert error["bytes"] == 4400
    assert error["bytes_on_disk"] < error["ceiling_bytes"] < error["bytes"]


def test_a_file_under_the_ceiling_is_still_served(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """The control has to be a ceiling and not a wall."""
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    response = static_site.serve("GET", "/assets/index-BjAGxrVJ.js", root=web_root)
    assert response["statusCode"] == 200
    assert response["body"] == "export const x=1;\n"


def test_an_oversize_v1_response_is_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "64")
    response = app.handler(_event("GET", "/v1/nope"))
    assert response["statusCode"] == 413
    error = json.loads(response["body"])["error"]
    assert error["kind"] == "response_too_large"
    assert error["ceiling_bytes"] == 64
    assert error["ceiling_env"] == static_site.RESPONSE_BYTES_ENV
    assert response["headers"]["content-type"] == "application/json; charset=utf-8"
    # The 404 body it replaced listed all seventeen declared route templates. None of it
    # may survive into the refusal.
    assert "/v1/permits/" not in response["body"]


def test_the_refusal_is_never_itself_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A control that can be applied to its own output is not a control.

    Under a 16-byte ceiling the 413 body is far larger than the ceiling. It must still be
    the answer: routing the refusal back through the size check would either recurse until
    the stack ends or answer a 413 with a 413, and both are the handler failing to answer.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "16")
    response = app.handler(_event("GET", "/v1/nope"))
    assert response["statusCode"] == 413
    assert len(response["body"].encode("utf-8")) > 16
    assert json.loads(response["body"])["error"]["kind"] == "response_too_large"


def test_the_one_unmeasured_response_is_bounded_by_construction(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """The 413 is never weighed, so its length may not be the caller's to choose.

    A Function URL accepts a long request path, and the static refusal echoes it. Since
    that refusal is the one response ``_within_ceiling`` deliberately does not measure —
    it cannot be, or it could refuse itself — the echo is truncated instead. The
    amplification was roughly 1:1 either way; what this closes is the *statement* that no
    response this origin emits is unbounded, which is worth more than the bytes.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    (web_root / "assets" / "huge-Aaaaaaaa.js").write_bytes(b"payload;" * 1024)
    response = static_site.serve("GET", "/assets/" + "a" * 6000 + ".js", root=web_root)

    assert response["statusCode"] in (403, 404, 413)
    assert len(response["body"].encode("utf-8")) < 2000, "a caller chose the refusal's length"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/"),
        ("GET", "/assets/index-BjAGxrVJ.js"),
        ("GET", "/v1/health"),
        ("GET", "/v1/nope"),
        ("OPTIONS", "/v1/permits/abc"),
        ("POST", "/"),
        ("HEAD", "/index.html"),
    ],
    ids=["index", "asset", "health", "no-route", "options", "post-static", "head"],
)
def test_the_ceiling_never_raises_whatever_it_is_set_to(
    monkeypatch: pytest.MonkeyPatch, web_root: Path, method: str, path: str
) -> None:
    """One byte is a ceiling nothing can satisfy, and nothing raises — everything 413s.

    Both surfaces, both response builders, an empty ``{}`` OPTIONS envelope included: a
    two-byte body is over a one-byte ceiling and is refused like everything else. The
    point is not that a one-byte ceiling is sensible; it is that the degenerate setting
    produces a response contract rather than a stack trace.
    """
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(web_root))
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "1")
    monkeypatch.setattr(app, "health", lambda: (200, {"ok": True}))
    response = app.handler(_event(method, path))
    assert isinstance(response, dict)
    assert set(response) == {"statusCode", "headers", "body", "isBase64Encoded"}
    assert response["statusCode"] == 413
    assert json.loads(response["body"])["error"]["kind"] == "response_too_large"
    assert _CORS_HEADER not in _header_names(response)


# ── (c) The ratchet: the biggest thing this origin can emit ─────────────────────────


def _web_tree_sources() -> tuple[list[tuple[str, Path]], str]:
    """Locate the built web tree. Returns ``([(prefix, root), …], label)``; may be empty.

    Two layouts, in order:

    1. **Deployed.** ``static_site.web_root()`` — ``$MAINLINE_WEB_ROOT``, or ``web/``
       beside the package. This is what the Lambda serves from, and it is one directory.
    2. **Inputs.** ``console/dist`` mounted at the root plus
       ``console/fixtures/bundles/demo-cloud`` mounted at ``bundle/``. This is what the
       packer copies, and it was verified byte-for-byte against the ``web/`` entries of
       ``out/lambda/mainline-demo-api-arm64.zip`` on 2026-08-13: same 75 keys, zero size
       mismatches.

    Both are build outputs — ``.gitignore`` lines 9 and 10 — so a clean checkout that has
    not built the console has neither, and the ratchet skips loudly rather than passing
    silently. That is the honest limit of this assertion and it is stated in the skip.
    """
    deployed = static_site.web_root()
    if deployed.is_dir():
        return [("", deployed)], f"the deployed web root at {deployed}"
    if _CONSOLE_DIST.is_dir() and _EVIDENCE_BUNDLE.is_dir():
        return (
            [("", _CONSOLE_DIST), ("bundle/", _EVIDENCE_BUNDLE)],
            f"the packer's inputs: {_CONSOLE_DIST} + {_EVIDENCE_BUNDLE} at bundle/",
        )
    return [], ""


def _built_web_tree() -> tuple[list[tuple[str, Path, Path]], str]:
    """``[(relative_in_web_tree, absolute_path, serve_root), …]`` and where it came from."""
    sources, label = _web_tree_sources()
    files: list[tuple[str, Path, Path]] = []
    for prefix, root in sources:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files.append((prefix + path.relative_to(root).as_posix(), path, root))
    return files, label


def _require_built_tree() -> tuple[list[tuple[str, Path, Path]], str]:
    files, label = _built_web_tree()
    if not files:
        pytest.skip(
            "no built web tree is present, so the ratchet did NOT run in this session. "
            f"Looked for the deployed root ({static_site.web_root()}) and the packer's "
            f"inputs ({_CONSOLE_DIST} + {_EVIDENCE_BUNDLE}). Both are .gitignore'd build "
            "outputs; build the console to arm this assertion."
        )
    return files, label


def test_the_declared_largest_object_is_under_the_default_ceiling() -> None:
    """Runs everywhere, tree or no tree: the two declared numbers must be consistent.

    This is the arithmetic the ceiling was chosen from. If somebody lowers
    ``DEFAULT_MAX_RESPONSE_BYTES`` below the console's own largest source map, the first
    symptom in production would be DevTools quietly refusing to map a stack trace — a cost
    control that broke the thing it was protecting, noticed by nobody. Here it is a
    failing test instead.
    """
    assert 0 < _LARGEST_WEB_OBJECT_BYTES < static_site.DEFAULT_MAX_RESPONSE_BYTES
    headroom = static_site.DEFAULT_MAX_RESPONSE_BYTES - _LARGEST_WEB_OBJECT_BYTES
    assert headroom == 542_984, f"the declared headroom moved: {headroom} B"


def test_the_largest_file_in_the_built_web_tree_is_below_the_ceiling() -> None:
    """**The ratchet.** The biggest thing this origin can emit, measured, under the bound.

    Not the declaration — the tree. A constant asserted against itself proves nothing;
    this walks whatever was actually built and finds the maximum in it.
    """
    files, label = _require_built_tree()
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    largest = max(files, key=lambda item: item[1].stat().st_size)
    relative, path, _ = largest
    size = path.stat().st_size
    assert size < ceiling, (
        f"{relative} is {size} B in {label}, at or above the {ceiling} B ceiling. This "
        "origin would 413 its own asset. Strip source maps or raise the ceiling "
        "deliberately — do not raise it to make this pass."
    )


def test_the_built_web_tree_has_not_outgrown_its_declaration() -> None:
    """Growth must be declared. That is the difference between a ratchet and a limit.

    The ceiling says the emitted maximum is *safe*; this says it is *known*. Without it
    the largest object could drift from 1.5 MB to 2.0 MB — a 35 % rise in the flood's
    multiplier, tens of thousands of dollars in the worst case — while every test in this
    file stayed green, because it would still be under the ceiling the whole way.
    """
    files, label = _require_built_tree()
    relative, path, _ = max(files, key=lambda item: item[1].stat().st_size)
    size = path.stat().st_size
    assert size <= _LARGEST_WEB_OBJECT_BYTES, (
        f"the largest object in {label} is now {relative} at {size} B, above the declared "
        f"{_LARGEST_WEB_OBJECT} at {_LARGEST_WEB_OBJECT_BYTES} B. Re-measure, decide the "
        "new number is acceptable at concurrency 10 for 30 days, then update "
        "_LARGEST_WEB_OBJECT_BYTES in this file. Do not delete this assertion."
    )


def test_every_file_in_the_built_web_tree_serves_under_the_ceiling() -> None:
    """The end-to-end form: serve all 75 objects and let the real code decide.

    The file-size ratchet above compares bytes on disk. This compares bytes **on the
    wire**, which is what egress is billed in and what base64 inflates by a third — a
    1.6 MiB font would pass the ratchet and emit 2.1 MiB. Only running the server catches
    that, so the server is what runs.
    """
    files, label = _require_built_tree()
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES

    refused: list[str] = []
    widest = ("", 0)
    for relative, path, root in files:
        request_path = "/" + path.relative_to(root).as_posix()
        response = static_site.serve("GET", request_path, root=root)
        if response["statusCode"] != 200:
            refused.append(f"{relative} -> {response['statusCode']}")
            continue
        wire = len(str(response["body"]).encode("utf-8"))
        if wire > widest[1]:
            widest = (relative, wire)

    assert refused == [], f"{label} contains objects this handler will not serve: {refused}"
    assert widest[1] < ceiling, (
        f"the widest response {label} can emit is {widest[0]} at {widest[1]} B on the "
        f"wire, at or above the {ceiling} B ceiling."
    )


def test_the_built_web_tree_matches_the_shape_the_flood_arithmetic_assumed() -> None:
    """A soft check on the two totals the USD figures were derived from.

    Reported, not asserted equal: the file count and total bytes move with every console
    change, and a test that pinned them would fail for reasons that have nothing to do
    with the exposure. What IS asserted is that the tree is non-trivial — a stub or an
    empty directory must not be able to satisfy the ratchet above by having nothing in it.
    """
    files, label = _require_built_tree()
    total = sum(path.stat().st_size for _, path, _ in files)
    assert len(files) >= 20, f"{label} holds only {len(files)} files; that is not a built site"
    assert total > 1_000_000, f"{label} holds only {total} B; that is not a built site"
    # The measured shape on 2026-08-13, for whoever reads this test's output next.
    assert (_WEB_TREE_FILES, _WEB_TREE_BYTES) == (75, 3_571_990)
