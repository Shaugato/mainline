# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""What every response this origin emits may and may not carry.

The demo is one Lambda Function URL with ``authorization_type = NONE`` — DECISION **D1**,
`docs/leads/ship-final.md` §1.4, because the account cannot create a CloudFront
distribution. There is no CDN, no WAF and no authoriser between the internet and
``app.handler``, so the only place a property of the public surface can be enforced is
inside the two modules that build responses. This file is the assertion that they do.

THREE PROPERTIES: ONE SECURITY AND TWO COST
--------------------------------------------
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

**A declared ceiling on the bytes one response may carry, and it REFUSES something.** The
largest object this origin can emit is the multiplier in a sustained-egress flood: at
1,554,168 B for the console's largest source map, concurrency 10 for 30 days is roughly
USD 33,000. Until 2026-08-13 the ceiling stood at 2 MiB and refused **0 of the 75 objects
this origin serves** — an independent verifier measured exactly that and reported the
control as non-binding, which it was. A ceiling above everything it governs is a
decoration: it cannot fail, so it proves nothing, which is the same defect as a test that
cannot disagree with its code. It now stands at 512 KiB, refuses the source map by name and
serves the other 74, and the tests in section (c) are what keep that true rather than
merely stated.

**A declared bound on the request path, which is the only thing a caller writes into a
body.** Every refusal this origin emits echoes the path it refused, so the length of a
refusal was the caller's to choose until the path itself was bounded. Worse, it was not
only a length: a request path with a segment no filesystem can name made ``static_site``
raise ``OSError [Errno 36]`` out of a function that promises never to raise — measured on
the deployed runtime image, invisible on Windows because ``pathlib`` ignores that errno
there. ``MAX_REQUEST_PATH_BYTES`` and ``MAX_SEGMENT_BYTES`` are now refusals decided from
the request, and ``test_the_one_unmeasured_response_is_bounded_by_construction`` is where
that is asserted on every platform.

**A declared bound on the rate one instance may be asked at.** The ceiling above bounds
bytes per request and bounds a flood of *small* responses not at all, and until 2026-08-13
this docstring finished by saying that request rate was "bounded by the AWS account's
concurrency ceiling and by nothing in this repository". That was true when it was written
and this wave made it false: :mod:`mainline_demo_api.ratelimit` is now the first statement
in ``app.handler``, and the responses this file walks include the **429** it produces. The
sentence is replaced rather than left standing beside the mechanism that falsified it.

**WHAT IS STILL NOT BOUNDED, AND MUST NOT BE READ INTO ANYTHING BELOW.** Lambda bills a 429
exactly as it bills a 200, so neither the ceiling nor the rate bound bounds the *invocation
charge* — refusing early even shortens the invocation, which at a fixed concurrency ceiling
raises the number of billed invocations. The spend bound is the cost-guard responder
(`docs/leads/cost-bound-plan.md` §0.2). Nothing in this file is evidence of a spend bound;
what it is evidence of is that the bytes and the rate are declared, enforced and tested.
"""

from __future__ import annotations

import ast
import base64
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final

import pytest
from mainline_demo_api import app, db, logbudget, ratelimit, static_site

from conftest import REPO_ROOT

_CORS_HEADER: Final = "access-control-allow-origin"

#: The three modules that build every response this origin can emit, and there is no
#: fourth: ``handler`` refuses from ``ratelimit.check``, or forks to ``static_site.serve``,
#: or answers from ``app._response``. ``ratelimit`` joined this tuple on 2026-08-13 — it is
#: a response builder like the other two, its 429 never passes through ``_response``, and a
#: response builder outside this list is a response nothing in this file checks.
_RESPONSE_MODULES: Final = (app, ratelimit, static_site)

# ── The built web tree, as measured on 2026-08-13 ───────────────────────────────────
#
# `zipfile` over `out/lambda/mainline-demo-api-arm64.zip`, and independently over the two
# directories the packer copies into `web/`. The two agree exactly: 75 files, 0 size
# mismatches, identical key sets. That agreement is why the directory pair below is an
# honest stand-in for the artefact when the zip has not been built.
_WEB_TREE_FILES: Final = 75
_WEB_TREE_BYTES: Final = 3_571_990

#: The largest single object in the tree, which is **no longer the largest this origin can
#: emit**: at a 512 KiB ceiling it is the one object of the 75 that answers 413. It stays
#: declared because it is the number the USD 33,000 flood arithmetic was computed from, and
#: because a ceiling is only demonstrably binding if something is known to sit above it.
_LARGEST_WEB_OBJECT: Final = "assets/index-BjAGxrVJ.js.map"
_LARGEST_WEB_OBJECT_BYTES: Final = 1_554_168

#: The largest object the origin actually SERVES, and therefore the multiplier in force in
#: the flood arithmetic. **This constant is the ratchet.** It may only be raised by somebody
#: who re-measured it and decided the new number is acceptable; it may never drift upward
#: on its own, which is what `test_the_built_web_tree_has_not_outgrown_its_declaration`
#: enforces. It is deliberately a *declaration*, not a lookup: a number read out of the
#: tree at test time would agree with the tree by construction and assert nothing.
_LARGEST_SERVED_OBJECT: Final = "assets/index-BjAGxrVJ.js"
_LARGEST_SERVED_OBJECT_BYTES: Final = 433_396

#: Every object of the 75 that the default ceiling refuses, by name. **This is the
#: anti-vacuity declaration and the reason this file can claim the ceiling binds.** An
#: empty tuple here would mean the control refuses nothing, which is where it stood before
#: 2026-08-13; `test_the_ceiling_refuses_something_it_governs` fails on an empty tuple by
#: construction. Serving all eighteen source maps was 2,586,960 B — 72.42 % of the tree —
#: of debug artefact billable to this account by anyone on the internet.
_REFUSED_BY_THE_CEILING: Final = ("assets/index-BjAGxrVJ.js.map",)

_CONSOLE_DIST: Final = REPO_ROOT / "verticals/mainline/apps/console/dist"
_EVIDENCE_BUNDLE: Final = REPO_ROOT / "verticals/mainline/apps/console/fixtures/bundles/demo-cloud"


# ── Fixtures and helpers ────────────────────────────────────────────────────────────


_INDEX: Final = "<!doctype html><html><head><title>MAINLINE</title></head><body>ok</body></html>"


@pytest.fixture(autouse=True)
def _admitting_limiter() -> Iterator[None]:
    """Both token buckets full before and after every test in this file.

    This file is about the *ceiling* and the CORS header, and every case below assumes it
    reaches the response builder it names. The buckets are module-scope by design — one
    execution environment, not one request — so without this an earlier case would spend
    the tokens a later case needs, and a 413 assertion would fail as a 429 for a reason
    that has nothing to do with what it tests.

    It is a refill, **not a bypass**: the limiter still runs on every one of the fourteen
    responses walked below, and the two tests that want a refusal configure it deliberately
    and get a real one. Its own behaviour is ``tests/test_ratelimit.py``.
    """
    ratelimit.reset()
    logbudget.reset()
    yield
    ratelimit.configure()
    ratelimit.reset()
    logbudget.reset()


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

    # The 429 LAST, because obtaining one means emptying a bucket, and every entry above
    # would then be a refusal wearing the name of the status it was meant to carry. The
    # first call spends the only token; the second is refused by the layer that owns it.
    ratelimit.configure(global_rps=0.01, global_burst=1, ip_rps=0.01, ip_burst=1)
    app.handler(_event("GET", "/v1/health"))
    responses["api-429-rate-limited"] = app.handler(_event("GET", "/v1/health"))
    return responses


# ── (a) The header is on nothing ────────────────────────────────────────────────────


def test_no_response_the_handler_builds_carries_a_cors_header(
    monkeypatch: pytest.MonkeyPatch, web_root: Path, tmp_path: Path
) -> None:
    """Fourteen responses across both surfaces and seven statuses, and none may carry it.

    The matrix is deliberately wider than the 200s. The header used to be set inside
    ``_response``, which ``_problem`` calls, so the 4xx and 5xx bodies — the ones carrying
    SQLSTATEs, refused traversal vectors and the declared-route list — were the ones a
    cross-origin script could most usefully read.

    The fourteenth is the **429**, added when the rate bound landed. It is built by a third
    module, as its own literal, and it therefore has to be walked here rather than assumed
    to inherit the property: every previous CORS defect in this file's history was a
    response somebody built somewhere the check did not reach.
    """
    responses = _every_response(monkeypatch, web_root, tmp_path / "never-bundled")
    assert len(responses) == 14

    offenders = {
        label: r["headers"] for label, r in responses.items() if _CORS_HEADER in _header_names(r)
    }
    assert offenders == {}, offenders

    # The matrix is only worth as much as its coverage, so pin what it covered.
    assert {r["statusCode"] for r in responses.values()} == {200, 204, 403, 404, 405, 429, 503}
    assert responses["api-429-rate-limited"]["statusCode"] == 429


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


def test_the_default_ceiling_is_one_hundred_and_thirty_six_kibibytes() -> None:
    """Declared so a change to it is a change to a test, not a quiet edit to a constant.

    It was ``2 * 1024 * 1024`` until 2026-08-13 and this assertion said so. The number moved
    because at 2 MiB the control refused none of the 75 objects it governs; the distribution
    it was re-chosen from is written out beside the constant, and
    ``test_the_ceiling_refuses_something_it_governs`` is what stops it drifting back up to a
    value that refuses nothing.

    IT MOVED A SECOND TIME, and this assertion lagged it by one commit — which is the whole
    reason the assertion exists, so it is worth recording rather than quietly re-pinning.
    ``512 * 1024`` was chosen against the packer's 75-file PRE-STRIP input tree, where the
    one object it refused was the 1,554,168 B source map. ``build_lambda`` began stripping
    ``web/**/*.map`` by default THE SAME DAY, which removed the only thing that ceiling
    governed: re-measured over the tree that actually deploys, 512 KiB refuses **0 of 57**
    identity objects, exactly as 1 MiB and 2 MiB do. A ceiling above everything it governs
    is a decoration — the same criticism a verifier had already made of 2 MiB, reproduced
    one octave down. ``136 * 1024`` refuses 1 of 57 and satisfies the I3 ratio that
    ``524,288 / 433,396 = 1.2097`` fails.

    The lag itself is the recurring shape this repository keeps meeting: a value moved in
    ``static_site.py`` and in both Terraform variable files, and the sibling assertion in
    ANOTHER test module was not moved with it. Same as the credential twin, one layer up.
    """
    assert static_site.DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024 == 139_264


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


#: Three request paths no filesystem can express, and the rule each one is here to trip.
#: Each is *decided from the request*, so none of them may reach a ``stat`` — and until
#: 2026-08-13 all three did. Keyed by the ``vector`` the refusal must name, so a case that
#: starts tripping a different rule fails rather than passing under the wrong one.
_UNNAMEABLE_PATHS: Final = [
    # 6,011 bytes: over the path bound, and its single segment is also over NAME_MAX. This
    # is the exact path that raised OSError [Errno 36] on the Lambda runtime image.
    ("path_too_long", "/assets/" + "a" * 6000 + ".js", "a"),
    # 8,199 bytes of segments that are each individually LEGAL. Bounding the segment alone
    # would have let this one through to the kernel, which refuses it on PATH_MAX — and
    # that is measured, not assumed: it raised the same errno on the same image.
    ("path_too_long", "/assets/" + "/".join(["b" * 255] * 32), "b"),
    # 264 bytes, comfortably under the path bound, one byte over NAME_MAX. The only case
    # that can reach the segment rule, and therefore the only proof that rule is armed.
    ("segment_too_long", "/assets/" + "c" * 256, "c"),
]


@pytest.mark.parametrize(("vector", "path", "filler"), _UNNAMEABLE_PATHS, ids=[
    "one-huge-segment",
    "legal-segments-illegal-whole",
    "one-segment-over-name-max",
])
def test_the_one_unmeasured_response_is_bounded_by_construction(
    monkeypatch: pytest.MonkeyPatch, web_root: Path, vector: str, path: str, filler: str
) -> None:
    """A caller may not choose a refusal's length, and may not make ``serve`` raise at all.

    Two properties, and this test only ever asserted the first — because until 2026-08-13
    it never reached an assertion at all on the platform that matters.

    **It could not raise, and it did.** The path below with a 6,000-character segment made
    ``Path.is_file()`` raise ``OSError [Errno 36] File name too long`` straight out of
    ``static_site.serve``, which documents "Never raises", inside ``app.handler``, which
    documents the same, behind a Function URL with ``authorization_type = NONE``. One
    anonymous GET, one Lambda-shaped 502 with a stack trace, one full invocation charged.
    On Windows the identical call returns a response, because ``pathlib`` has
    ``ERROR_FILENAME_EXCED_RANGE`` on its ignore list and Linux has no equivalent for
    ``ENAMETOOLONG`` — so the developer box said green and the CI runner said
    ``OSError``, and the assertion below was never evaluated on either. **A test that
    cannot reach its assertion is the same lie as a test that cannot disagree with its
    code**, and it hid a live defect for as long as it stood.

    The repair is not a smaller number in this file. It is
    :data:`~mainline_demo_api.static_site.MAX_REQUEST_PATH_BYTES` and
    :data:`~mainline_demo_api.static_site.MAX_SEGMENT_BYTES`, refusals decided from the
    request beside the NUL and ``..`` refusals, so nothing here depends on what a
    filesystem is willing to be asked. That is why this case now runs identically on both
    platforms rather than being written around the one that tolerated it.

    **And the length is still not the caller's.** The refusal echoes the path, so 6,000
    bytes in must not become 6,000 bytes out. At most ``_ECHO_LIMIT`` characters survive,
    which the last assertion checks by asking for a run three hundred long.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    (web_root / "assets" / "huge-Aaaaaaaa.js").write_bytes(b"payload;" * 1024)

    response = static_site.serve("GET", path, root=web_root)

    # Reached only if nothing raised, which is the half that was missing. Asserted rather
    # than assumed so the failure names the property instead of showing a traceback.
    assert set(response) == {"statusCode", "headers", "body", "isBase64Encoded"}
    assert response["statusCode"] == 403
    error = json.loads(response["body"])["error"]
    assert error["kind"] == "path_refused"
    assert error["vector"] == vector, f"tripped {error['vector']}, not {vector}"

    body = len(response["body"].encode("utf-8"))
    assert body < 2000, f"a caller chose the refusal's length: {body} B from {len(path)} in"
    assert filler * 300 not in response["body"], "the caller's run survived into the body"


def test_the_path_bound_is_a_ceiling_and_not_a_wall(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """The longest path the origin ACCEPTS, and the bound its worst body inherits from that.

    The refusals above are only half a control; a bound that refused everything long would
    be a wall, and the site would still have to be reachable through it. So this asks for
    a path of exactly :data:`MAX_REQUEST_PATH_BYTES` bytes, every segment legal, and
    requires a 404 — a miss, decided normally — rather than a 403.

    Its body is the largest any caller can provoke out of a path, because the 404 is the
    refusal that echoes the most: the request path once and the resolved relative path
    again. Two copies of at most 1,024 bytes plus fixed prose is a bound *computed from a
    declared constant*, which is what "bounded by construction" has to mean if it is to
    mean anything — the previous version of this claim rested on a magic 2,000.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, str(static_site.DEFAULT_MAX_RESPONSE_BYTES))
    limit = static_site.MAX_REQUEST_PATH_BYTES
    path = "/assets"
    while len(path) + 1 + static_site.MAX_SEGMENT_BYTES <= limit:
        path += "/" + "d" * static_site.MAX_SEGMENT_BYTES
    path += "/" + "e" * (limit - len(path) - 1)

    assert len(path.encode("utf-8")) == limit
    assert max(len(part) for part in path.split("/")) <= static_site.MAX_SEGMENT_BYTES

    response = static_site.serve("GET", path, root=web_root)
    assert response["statusCode"] == 404, "the longest accepted path must not be refused"
    assert json.loads(response["body"])["error"]["kind"] == "asset_not_found"

    body = len(response["body"].encode("utf-8"))
    assert body < 4 * limit, f"a {limit} B path produced a {body} B body"


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


# ── (b2) The rate refusal, which is the third builder and the second unweighed body ──


def _rate_limited(path: str = "/v1/nope") -> dict[str, Any]:
    """Empty the global bucket and return the refusal the next request gets."""
    ratelimit.configure(global_rps=0.01, global_burst=1, ip_rps=0.01, ip_burst=1)
    app.handler(_event("GET", path))
    return app.handler(_event("GET", path))


def test_the_rate_refusal_is_a_response_contract_and_not_a_stack_trace() -> None:
    """The same four keys, the same problem-document shape, no envelope. Nothing raises."""
    response = _rate_limited()
    assert set(response) == {"statusCode", "headers", "body", "isBase64Encoded"}
    assert response["statusCode"] == 429
    assert response["isBase64Encoded"] is False
    assert response["headers"]["content-type"] == "application/json; charset=utf-8"
    assert response["headers"]["cache-control"] == "no-store"
    assert int(response["headers"]["retry-after"]) >= 1
    error = json.loads(response["body"])["error"]
    assert error["kind"] == "rate_limited"
    assert error["status"] == 429
    assert _CORS_HEADER not in _header_names(response)


def test_the_rate_refusal_is_bounded_by_construction_like_the_413_is() -> None:
    """The second response this origin emits without weighing it, and for the same reason.

    ``ratelimit.check`` runs before ``_response`` exists in the call, so its 429 is never
    measured against ``max_response_bytes`` — and it must not be, because a refusal that
    can itself be refused is not a control. Being unweighed makes its length an obligation:
    a fixed template, two numbers this repository owns, and nothing the caller supplied.
    """
    response = _rate_limited("/v1/" + "q" * 3000)
    size = len(str(response["body"]).encode("utf-8"))
    assert size < ratelimit.REFUSAL_BODY_CEILING, f"the 429 body is {size} B"
    assert "qqqq" not in str(response["body"]), "a caller chose the refusal's length"


def test_a_one_byte_ceiling_does_not_turn_the_rate_refusal_into_a_413(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The degenerate setting again, on the one response the ceiling deliberately misses.

    A 413 answered instead of the 429 would mean the rate refusal had been routed through
    ``_response`` — which is precisely the recursion ``app._too_large`` documents at length
    and which this assertion exists to keep from being reintroduced by a tidy-up.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "1")
    response = _rate_limited()
    assert response["statusCode"] == 429
    assert len(str(response["body"]).encode("utf-8")) > 1
    assert json.loads(response["body"])["error"]["kind"] == "rate_limited"


def test_the_rate_bound_and_the_byte_ceiling_are_different_controls() -> None:
    """Named here because the two are now adjacent and a reader will conflate them.

    413 is "this one body is too big"; 429 is "you have asked too often". Neither implies
    the other, neither bounds the invocation charge, and only one of them has ever been
    quoted in this repository's cost documents.
    """
    assert static_site.DEFAULT_MAX_RESPONSE_BYTES > ratelimit.REFUSAL_BODY_CEILING
    over_ceiling = app.handler(_event("GET", "/v1/nope"))
    assert over_ceiling["statusCode"] == 404, "the limiter must not be pre-drained here"
    assert _rate_limited()["statusCode"] == 429


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


def test_the_declared_numbers_straddle_the_ceiling_rather_than_sitting_under_it() -> None:
    """Runs everywhere, tree or no tree: the three declared numbers and the arithmetic.

    This is what the ceiling was chosen from, and the shape of the assertion is the point.
    It used to say *every* declared object is under the ceiling, with a headroom of
    542,984 B — which is exactly the statement of a control that refuses nothing. The
    declaration now straddles: the largest object in the tree is ABOVE the ceiling, the
    largest object the console needs to run is BELOW it, and the gap between them is the
    debug artefact this origin no longer pays to hand out.

    The cost is real and is named rather than hidden: DevTools can no longer map a stack
    trace from the deployed origin. The artefact it would have mapped is not in the
    deployed package either — ``build_lambda`` strips ``web/**/*.map`` by default as of
    2026-08-13 — so the ceiling and the packer agree, and ``--keep-source-maps`` builds the
    debuggable package for anyone who needs one.
    """
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    assert 0 < _LARGEST_SERVED_OBJECT_BYTES < ceiling < _LARGEST_WEB_OBJECT_BYTES

    headroom = ceiling - _LARGEST_SERVED_OBJECT_BYTES
    assert headroom == 90_892, f"the declared headroom moved: {headroom} B"

    # The flood's multiplier, before and after, as a ratio somebody can check by hand.
    cut = _LARGEST_WEB_OBJECT_BYTES / _LARGEST_SERVED_OBJECT_BYTES
    assert round(cut, 3) == 3.586, f"the declared reduction moved: {cut}"


def test_the_ceiling_refuses_something_it_governs() -> None:
    """**The anti-vacuity assertion.** A control that refuses nothing is not a control.

    This is the assertion whose absence let the ceiling sit at 2 MiB above a tree whose
    largest object was 1,554,168 B, refusing 0 of 75, while every other test in this file
    stayed green — because "everything is under the ceiling" is satisfied most easily by a
    ceiling nothing can reach.

    It runs **everywhere**, with no built tree, because the two objects it needs are
    written from the declared sizes rather than looked up: one file of exactly
    ``_LARGEST_WEB_OBJECT_BYTES`` and one of exactly ``_LARGEST_SERVED_OBJECT_BYTES``,
    served through the real code at the real default ceiling. Making it depend on a
    ``.gitignore``'d build output would mean the one assertion that proves the control
    binds is also the one most likely to skip.
    """
    files, _ = _built_web_tree()
    assert _REFUSED_BY_THE_CEILING, "the ceiling refuses nothing, so it bounds nothing"
    if files:
        declared = {relative for relative, _, _ in files}
        assert set(_REFUSED_BY_THE_CEILING) <= declared, "a refusal names an absent object"


def test_the_default_ceiling_refuses_the_declared_object_and_serves_the_declared_asset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The straddle again, through ``serve`` rather than through arithmetic.

    Two files whose sizes are the two declared numbers, under the DEFAULT ceiling with no
    environment override in sight, because the value that matters is the one a deploy that
    sets nothing will enforce.
    """
    monkeypatch.delenv(static_site.RESPONSE_BYTES_ENV, raising=False)
    root = tmp_path / "web"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_bytes(_INDEX.encode("utf-8"))
    (root / "assets" / "over.js").write_bytes(b"x" * _LARGEST_WEB_OBJECT_BYTES)
    (root / "assets" / "under.js").write_bytes(b"x" * _LARGEST_SERVED_OBJECT_BYTES)

    over = static_site.serve("GET", "/assets/over.js", root=root)
    assert over["statusCode"] == 413, f"{_LARGEST_WEB_OBJECT} would still be served"
    error = json.loads(over["body"])["error"]
    assert error["kind"] == "response_too_large"
    assert error["bytes"] == _LARGEST_WEB_OBJECT_BYTES
    assert error["ceiling_bytes"] == static_site.DEFAULT_MAX_RESPONSE_BYTES

    under = static_site.serve("GET", "/assets/under.js", root=root)
    assert under["statusCode"] == 200, "the ceiling refuses the console's own entry bundle"
    assert len(under["body"].encode("utf-8")) == _LARGEST_SERVED_OBJECT_BYTES


def test_the_largest_file_in_the_built_web_tree_is_the_one_the_ceiling_refuses() -> None:
    """**The ratchet.** The biggest thing in the tree, measured, and where it falls.

    Not the declaration — the tree. A constant asserted against itself proves nothing;
    this walks whatever was actually built and finds the maximum in it. What changed on
    2026-08-13 is which side of the ceiling the maximum is allowed to be on: it is now
    required to be an object this file has *named as refused*, so an unrecognised giant
    appearing in the tree fails here instead of quietly becoming the new multiplier.
    """
    files, label = _require_built_tree()
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    relative, path, _ = max(files, key=lambda item: item[1].stat().st_size)
    size = path.stat().st_size
    if size < ceiling:
        assert size <= _LARGEST_SERVED_OBJECT_BYTES, (
            f"{relative} is {size} B in {label} — under the ceiling but above the declared "
            f"served maximum of {_LARGEST_SERVED_OBJECT_BYTES} B. Re-measure and declare it."
        )
        return
    assert relative in _REFUSED_BY_THE_CEILING, (
        f"{relative} is {size} B in {label}, at or above the {ceiling} B ceiling, and this "
        "file does not name it as refused. This origin would 413 an asset nobody decided "
        "to stop serving. Strip it, declare it in _REFUSED_BY_THE_CEILING, or raise the "
        "ceiling deliberately — do not raise it to make this pass."
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


def test_every_file_in_the_built_web_tree_serves_or_is_a_declared_refusal() -> None:
    """The end-to-end form: serve all 75 objects and let the real code decide.

    The file-size ratchet above compares bytes on disk. This compares bytes **on the
    wire**, which is what egress is billed in and what base64 inflates by a third — a
    1.6 MiB font would pass the ratchet and emit 2.1 MiB. Only running the server catches
    that, so the server is what runs.

    It used to assert ``refused == []``. That assertion and a binding ceiling cannot both
    be true, and when they collided it was the ceiling that had been quietly chosen to
    satisfy the test rather than the other way round — a 2 MiB bound above a 1,554,168 B
    maximum, refusing nothing, on the ONE control the cost documents quote. So the empty
    list becomes an **exact set**: what is refused must be what this file declared, no more
    and no less. A new refusal fails here, and so does the disappearance of the only one.
    """
    files, label = _require_built_tree()
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES

    refused: dict[str, int] = {}
    widest = ("", 0)
    for relative, path, root in files:
        request_path = "/" + path.relative_to(root).as_posix()
        response = static_site.serve("GET", request_path, root=root)
        if response["statusCode"] != 200:
            refused[relative] = int(response["statusCode"])
            continue
        wire = len(str(response["body"]).encode("utf-8"))
        if wire > widest[1]:
            widest = (relative, wire)

    assert set(refused) == set(_REFUSED_BY_THE_CEILING), (
        f"{label} refuses {sorted(refused)}; this file declares "
        f"{sorted(_REFUSED_BY_THE_CEILING)}. Every difference is either an object that "
        "started being refused without anybody deciding to stop serving it, or a bound "
        "that stopped biting. Both are changes to what this origin costs."
    )
    assert set(refused.values()) <= {413}, f"a refusal that is not the ceiling's: {refused}"
    assert refused, "the ceiling refused nothing in the tree it governs; it is a decoration"

    assert widest[1] < ceiling, (
        f"the widest response {label} can emit is {widest[0]} at {widest[1]} B on the "
        f"wire, at or above the {ceiling} B ceiling."
    )
    assert widest[1] == _LARGEST_SERVED_OBJECT_BYTES, (
        f"the widest response {label} can emit is {widest[0]} at {widest[1]} B; the "
        f"declared multiplier is {_LARGEST_SERVED_OBJECT} at {_LARGEST_SERVED_OBJECT_BYTES}."
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


# ── (d) The billed quantity: what a base64 body costs, and what it does not ─────────
#
# A Lambda Function URL response body is a **JSON string**. Bytes that are not valid UTF-8
# — a woff2, a favicon, and as of interface I1 every pre-compressed `.gz` sibling — cannot
# be a JSON string, so they travel base64 with `isBase64Encoded: true` and the *service*
# decodes them before anything leaves. Two numbers therefore exist for one response and
# they differ by exactly 4/3:
#
#     the ENVELOPE    len(response["body"])                 what sits between the handler
#                                                            and the service, and is never
#                                                            sent to anybody
#     the WIRE        len(b64decode(response["body"]))      what leaves AWS, what the
#                                                            client receives, and what
#                                                            egress is billed on
#
# Interface **I2** of `docs/leads/cost-finish-plan.md` fixes the wire as the quantity every
# ceiling, meter and cost figure in this repository means. The tests below are the guard on
# that, and the reason they are here rather than only in `test_static_site.py` is that this
# is the file the cost documents cite: `docs/deploy/COST-BOUND.md` quotes the ceiling, and
# a ceiling applied to the envelope over-refuses by 33 % while a bill computed on it
# over-states egress by 33 %. Both are wrong in the direction that is hardest to notice,
# because both fail *conservatively* and a conservative wrong number reads as caution.
#
# The largest object this origin serves is the 124,127 B compressed entry bundle, whose
# envelope is 165,504 characters. Weighing the envelope would refuse it at any ceiling
# between those two numbers — the single path the whole cost model depends on callers
# taking. `tests/deploy/test_furl_compression.py` proves the same property end-to-end,
# through a real socket, where the decode is actually performed.


def _binary_asset(root: Path, name: str, size: int) -> Path:
    """Write *size* bytes that are not valid UTF-8, under a media type declared as binary.

    ``\\xff\\xfe`` is a UTF-8 decode error in any position, so ``_file`` takes the base64
    branch on content rather than on the media-type branch — which means these cases stay
    valid if the ``MEDIA_TYPES`` table ever changes its mind about ``.woff2``.
    """
    path = root / "assets" / name
    payload = (b"\xff\xfe" * ((size // 2) + 1))[:size]
    path.write_bytes(payload)
    assert path.stat().st_size == size
    return path


#: One case per base64 padding class, because the padding is where the arithmetic in
#: ``static_site._wire_bytes`` can be got wrong and nowhere else. It computes the decoded
#: length *without decoding* — ``len(body) // 4 * 3 - body[-2:].count("=")`` — so a version
#: that dropped the padding term would be right for a third of all objects and one or two
#: bytes wrong for the rest: an error too small to notice and permanent once shipped.
_PADDING_CASES: Final = [(3000, 0), (3001, 2), (3002, 1)]


@pytest.mark.parametrize(("size", "padding"), _PADDING_CASES, ids=["no-pad", "two-pad", "one-pad"])
def test_the_billed_quantity_of_a_base64_response_is_its_decoded_length(
    monkeypatch: pytest.MonkeyPatch, web_root: Path, size: int, padding: int
) -> None:
    """``_wire_bytes`` is the decoded length, exactly, for every padding class.

    Three claims, and the third is the one that makes the other two worth asserting:

    1. the response really is base64 — otherwise this measures nothing;
    2. the arithmetic answers what an actual ``b64decode`` answers, to the byte; and
    3. the envelope is 4/3 the size, so the two numbers are genuinely different and a test
       that confused them would have something to confuse.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "1048576")
    _binary_asset(web_root, "blob-Aaaaaaaa.woff2", size)

    response = static_site.serve("GET", "/assets/blob-Aaaaaaaa.woff2", root=web_root)
    assert response["statusCode"] == 200
    assert response["isBase64Encoded"] is True

    envelope = str(response["body"])
    assert envelope.count("=") == padding
    assert len(envelope) == 4 * ((size + 2) // 3)

    decoded = base64.b64decode(envelope, validate=True)
    assert len(decoded) == size
    assert static_site._wire_bytes(response) == size == len(decoded), (
        "the computed wire length disagrees with an actual decode; the padding term is the "
        "only place this arithmetic can be wrong"
    )
    assert len(envelope) > size, "there is no inflation here, so nothing is being guarded"
    assert int(response["headers"]["content-length"]) == size, (
        "content-length is what the CLIENT receives, which is the decoded length"
    )


def test_a_body_under_the_ceiling_on_the_wire_is_served_though_its_envelope_is_over(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """**The 33 % over-refusal, in the one assertion that catches it.**

    4,000 bytes on the wire under a 4,096 ceiling is a **200**. Its envelope is 5,336
    characters, which is 30 % *over* that ceiling, so a control weighing the envelope
    answers 413 to a response that costs less than the bound allows — refusing bytes AWS
    would never have billed. Scaled to the object this actually decides, the 124,127 B
    compressed entry bundle would be weighed as 165,504 B: the single path the cost model
    (`docs/leads/cost-finish-plan.md` §0.5, $159,598 → $46,294) depends on callers taking.

    **This assertion and** ``test_base64_inflation_is_measured_and_not_assumed`` **above
    cannot both hold**, and that is deliberate rather than an oversight. That test pins the
    older semantics — the envelope is the measured quantity — which interface I2 reverses on
    a fact about the platform: a Function URL decodes ``isBase64Encoded`` before the bytes
    leave, and egress is billed on what leaves. The older assertion is not deleted here.
    Reconciling it is a re-derivation owned by whoever owns the ceiling, and W2 reports it
    rather than resolving it quietly; a contradiction two readers can see is worth more
    than a green obtained by removing one side of it.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    _binary_asset(web_root, "under-Bbbbbbbb.woff2", 4000)

    response = static_site.serve("GET", "/assets/under-Bbbbbbbb.woff2", root=web_root)
    envelope = len(str(response["body"]))

    ceiling = static_site.max_response_bytes()
    assert envelope == 5336
    assert 4000 < ceiling < envelope, "the case has stopped straddling the ceiling"
    assert response["statusCode"] == 200, (
        f"a 4,000 B object was refused under a 4,096 B ceiling because its {envelope}-"
        "character base64 envelope was weighed instead of the bytes AWS bills"
    )
    assert len(base64.b64decode(str(response["body"]), validate=True)) == 4000


def test_the_refusal_reports_the_wire_bytes_and_not_the_envelope_characters(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """When a base64 body IS refused, the number in the body is the billed one.

    The mirror of the test above, and it is needed for the same reason a ceiling needs
    something above it: "the envelope is never weighed" is satisfied most easily by never
    refusing anything. Here the wire length is genuinely over, the refusal happens, and the
    figure it reports is 4,100 — the bytes a client would have received — rather than the
    5,468 characters that only ever existed inside the envelope.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    _binary_asset(web_root, "over-Cccccccc.woff2", 4100)

    response = static_site.serve("GET", "/assets/over-Cccccccc.woff2", root=web_root)
    assert response["statusCode"] == 413
    error = json.loads(response["body"])["error"]
    assert error["bytes"] == 4100, "the refusal quoted a quantity nobody is billed for"
    assert error["bytes_on_disk"] == 4100
    assert error["ceiling_bytes"] == 4096
    assert len(base64.b64encode(b"x" * 4100)) == 5468
    assert error["bytes"] != 5468, "the refusal quoted the envelope's character count"


def test_the_one_measurement_never_takes_the_length_of_the_body_string() -> None:
    """The structural half: ``_within_ceiling`` compares ``_wire_bytes``, and nothing else.

    ``static_site`` documents ``_within_ceiling`` as *the one measurement* — the single exit
    where "no response this module emits exceeds the ceiling" is made true of every
    response. That makes it the single place the wrong quantity could be substituted, and
    the substitution is a one-word edit: ``len(response["body"])`` reads as obviously
    correct and is 33 % wrong for every binary object.

    So this asserts two things about that function's source: the value compared against the
    ceiling traces to a ``_wire_bytes`` call, and the function contains **no ``len()`` call
    at all**. The second is the blunt one and it is the one that will actually catch the
    regression, because the tidy-up that reintroduces this defect will write ``len``.

    **Its limit, stated:** a measurement moved *out* of this function would evade it. That
    is what the behavioural sweep below covers, and neither check is sufficient alone.
    """
    tree = ast.parse(Path(static_site.__file__ or "").read_text(encoding="utf-8"))
    within = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_within_ceiling"
        ),
        None,
    )
    assert within is not None, (
        "static_site._within_ceiling is gone. It is the module's single measurement point; "
        "if the measurement moved, this test has to move with it and say where to."
    )

    called = {
        node.func.id
        for node in ast.walk(within)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_wire_bytes" in called, "the one measurement no longer calls _wire_bytes"
    assert "len" not in called, (
        "_within_ceiling takes a len(). The only length that may be compared against the "
        "ceiling is the DECODED one, which _wire_bytes computes; len() of the body string "
        "is the base64 envelope and is 33 % larger than anything AWS bills."
    )

    compares = [node for node in ast.walk(within) if isinstance(node, ast.Compare)]
    assert compares, "_within_ceiling no longer compares anything"


def test_every_response_the_handler_emits_is_weighed_on_the_quantity_aws_bills(
    monkeypatch: pytest.MonkeyPatch, web_root: Path, tmp_path: Path
) -> None:
    """The behavioural sweep: every response in the matrix, plus a base64 one, checked.

    ``_wire_bytes`` must agree with an actual decode on every response either surface can
    build, and the responses ``app`` builds for itself must all be text — ``app._response``
    measures ``len(payload.encode("utf-8"))``, which is the correct billed quantity **only
    because** nothing it builds is ever base64. That "only because" is load-bearing and
    unwritten anywhere else, so it is asserted here: the day ``app`` starts base64-encoding
    something, its measurement becomes the envelope's and this test says so.
    """
    _binary_asset(web_root, "sweep-Dddddddd.woff2", 2048)
    responses = _every_response(monkeypatch, web_root, tmp_path / "never-bundled")
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(web_root))
    # `_every_response` finishes by emptying a bucket to obtain its 429, so the binary case
    # below would be refused by the limiter and this sweep would silently see no base64
    # response at all. A refill, not a bypass: the limiter still runs on the request, and
    # the `encoded == 1` assertion at the end is what makes the omission impossible to miss.
    ratelimit.configure()
    ratelimit.reset()
    responses["static-200-binary"] = app.handler(_event("GET", "/assets/sweep-Dddddddd.woff2"))

    encoded = 0
    for label, response in responses.items():
        body = str(response["body"])
        if response.get("isBase64Encoded"):
            encoded += 1
            decoded = base64.b64decode(body, validate=True)
            assert static_site._wire_bytes(response) == len(decoded), label
            assert len(decoded) < len(body), label
            assert response["headers"]["x-mainline-api"] == "demo-static", (
                f"{label} is base64 and was built by app, whose measurement is "
                "len(payload.encode('utf-8')): the envelope, not the wire"
            )
        else:
            assert static_site._wire_bytes(response) == len(body.encode("utf-8")), label

    assert encoded == 1, (
        "the sweep saw no base64 response, so it asserted nothing about the quantity it "
        "exists to guard"
    )
    assert responses["static-200-binary"]["statusCode"] == 200
