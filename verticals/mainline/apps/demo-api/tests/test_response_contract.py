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
largest object this origin can emit is the multiplier in a sustained-egress flood, so the
ceiling turns that multiplier from whatever the build happened to produce into a declared
number. A ceiling above everything it governs is a decoration: it cannot fail, so it proves
nothing, which is the same defect as a test that cannot disagree with its code. It has been
a decoration twice — at 2 MiB, which an independent verifier measured as refusing 0 of 75,
and then at 512 KiB, which refused 0 of 57 the moment ``build_lambda`` began stripping
source maps and removed the only object it had ever refused. Both times the declarations in
section (c) below said otherwise, and both times they said otherwise for the same reason:
**they had been measured over the packer's INPUT tree rather than over the tree that
deploys.**

That is the question this file got wrong, and section (c) now answers it out loud rather
than by choosing a fallback directory. **The deployed tree is authoritative.** Cost is
incurred by bytes leaving the deployed origin, so an object that never reaches the deployed
package cannot be evidence about a cost control; ``console/dist`` still carries eighteen
source maps that the packer strips, and a ceiling justified by refusing them would be a
ceiling justified by refusing objects that are not there.
`docs/decisions/response-ceiling-authoritative-tree.md` is the ruling and its arithmetic.
The ceiling stands at 136 KiB, it is a **consequence** of interface I3 applied to the
deployed tree rather than an input to it, and it refuses exactly one of the 57 identity
objects — on the identity path only.

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
import functools
import json
import zipfile
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

# ── The DEPLOYED web tree, as measured on 2026-08-14 ────────────────────────────────
#
# `zipfile` over the central directory of `out/lambda/mainline-demo-api-arm64.zip` (built
# 2026-08-13 15:54). **This is the tree that deploys**, and under the ruling it is the only
# tree these declarations may be measured over. Reproduce it with:
#
#     python -c "import zipfile;z=zipfile.ZipFile('out/lambda/mainline-demo-api-arm64.zip');
#                w=[i for i in z.infolist() if i.filename.startswith('web/') and not i.is_dir()];
#                print(len(w), sum(i.file_size for i in w))"
#
#     web/ entries        114 files   1,274,342 B
#       identity objects   57 files     985,030 B
#       .gz siblings       57 files     289,312 B   one per identity object, no orphans
#       source maps         0 files           0 B   stripped by build_lambda's default
#
# WHAT THESE NUMBERS ARE NOT. They are not the packer's input tree — `console/dist` +
# `console/fixtures/bundles/demo-cloud`, 75 files and 3,571,990 B, of which eighteen are
# source maps totalling 2,586,960 B. Until 2026-08-14 the constants below were that tree's,
# and every one of them was therefore a statement about bytes this origin cannot emit. The
# lists are not merely differently-sized: the input tree's refusal set is
# `['assets/index-BjAGxrVJ.js', 3 x *.js.map]` and the deployed tree's is
# `['assets/index-BjAGxrVJ.js']` alone, because the maps are absent **by construction**
# rather than absent by measurement.
_WEB_TREE_ENTRIES: Final = 114
_WEB_TREE_BYTES: Final = 1_274_342
_IDENTITY_OBJECTS: Final = 57
_IDENTITY_BYTES: Final = 985_030
_SIBLING_BYTES: Final = 289_312

#: The largest single object the deployed tree holds, and the largest number of bytes any
#: caller can ask this origin for by name. It is **above** the ceiling, which is what makes
#: the ceiling demonstrably binding: a bound is only a bound if something is known to sit
#: over it. It is not the largest thing that can be EMITTED — see below — because the object
#: has two representations and this is the one nobody with a browser ever receives.
_LARGEST_WEB_OBJECT: Final = "assets/index-BjAGxrVJ.js"
_LARGEST_WEB_OBJECT_BYTES: Final = 433_396

#: The largest number of bytes the origin actually PUTS ON THE WIRE for one response, and
#: therefore the multiplier in force in the flood arithmetic and the input to interface I3.
#:
#: It is **the same object as above**, and that is the whole point rather than a coincidence
#: to be tidied away. Every one of the 57 identity objects ships a `.gz` sibling and every
#: browser sends `Accept-Encoding: gzip`, so the bytes that leave are the compressed column
#: throughout: `assets/index-BjAGxrVJ.js` is 433,396 B to a client that refuses compression
#: and 124,127 B to one that does not. The ceiling sits between those two numbers, so one
#: object is a 413 and a 200 depending only on a request header — asserted end-to-end in
#: `test_the_default_ceiling_refuses_the_declared_object_and_serves_the_declared_asset`.
#:
#: **This constant is the ratchet.** It may only be raised by somebody who re-measured it
#: and decided the new number is acceptable; it may never drift upward on its own. It is
#: deliberately a *declaration*, not a lookup: a number read out of the tree at test time
#: would agree with the tree by construction and assert nothing.
_LARGEST_SERVED_OBJECT: Final = "assets/index-BjAGxrVJ.js"
_LARGEST_SERVED_CODING: Final = "assets/index-BjAGxrVJ.js.gz"
_LARGEST_SERVED_OBJECT_BYTES: Final = 124_127

#: The widest response the origin can emit to a client that refuses compression *and is
#: still served*. Declared because it is what says nothing else in the tree is anywhere near
#: this bound: the refusal below is one object and the next one down is 51,266 B, 37 % of
#: the ceiling. A ceiling that refused the second-largest object too would be a different
#: trade and would have to be argued for separately.
_WIDEST_SERVED_IDENTITY: Final = "assets/surface-Csi7pmRe.js"
_WIDEST_SERVED_IDENTITY_BYTES: Final = 51_266

#: Every object of the 57 that the default ceiling refuses, **by name and on the identity
#: path**. This is the anti-vacuity declaration and the reason this file can claim the
#: ceiling binds; `test_the_ceiling_refuses_something_it_governs` fails on an empty tuple by
#: construction.
#:
#: **A `.gz` sibling may never appear in this tuple**, and that is a rule rather than an
#: observation. Interface I1 makes a direct request for any path ending `.gz` a **404** —
#: one set of bytes gets one name — so enumerating all 114 `web/` entries and collecting
#: every non-200 would file 57 404s here as "refusals" and make a control that refuses one
#: object look like a control that refuses fifty-eight. The enumeration below therefore
#: walks identity objects, and the siblings' 404 is asserted as its own property in
#: `test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal`.
_REFUSED_BY_THE_CEILING: Final = ("assets/index-BjAGxrVJ.js",)

#: The deployed artefact these declarations are measured over. `test_static_site.py` reads
#: the same file for interface I3's derivation, and the two must not disagree about what the
#: origin serves — until 2026-08-14 they did, this file declaring 433,396 B and that one
#: 124,127 B for the same quantity.
_PACKAGE: Final = REPO_ROOT / "out/lambda/mainline-demo-api-arm64.zip"

#: The value of `Accept-Encoding` every browser that will ever load this console sends.
_BROWSER: Final = "gzip, deflate, br"


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
    """The inflation is still MEASURED. What moved is which side of it a ceiling reads.

    **This test used to assert a 413 here and it was right to, under the metric it was
    written against.** 3,300 bytes of non-UTF-8 under a 4,096 ceiling produce a 4,400-
    character body, and a control weighing that body refuses it. Interface **I2**
    (`docs/leads/cost-finish-plan.md` §I2) reverses the metric on a fact about the platform:
    a Function URL decodes ``isBase64Encoded`` before anything leaves, AWS bills egress on
    what leaves, so the ceiling reads the **decoded** length and this is a 200.

    The name is not the casualty of that. The obligation the name states — *measured, not
    assumed* — is the whole of what is asserted below, in four parts, none of which is
    ``assert 200``:

    1. **The inflation is measured on a real response.** 3,300 B in, exactly 4,400
       characters out, and ``4 x ceil(n/3)`` reproduces it. That formula is used again in
       part 4, so it is validated here rather than trusted there.
    2. **The ceiling is applied to the DECODED length.** The case still straddles —
       ``3,300 < 4,096 < 4,400`` — so a control that read the envelope would answer 413 and
       this assertion would catch it. The failure mode is refusing 3,300 billable bytes as
       though they were 4,400: over-refusing by exactly the encoding's overhead, which at
       the deployed ceiling is the 124,127 B compressed entry bundle weighed as 165,504 B.
    3. **The decoded length is computed, never decoded.** ``_wire_bytes`` runs on every
       response this module emits, so a version that called ``b64decode`` would allocate a
       second copy of every body. That is a structural claim about the function's source and
       is checked as one; a behavioural test cannot tell the two implementations apart.
    4. **The ENCODED payload stays under Lambda's response-payload quota** — the one bound
       in this module's world that really is measured on the base64 string, and which
       nothing in this repository asserted before 2026-08-14. It is asserted with a
       falsification, because a bound that no setting can breach is not a bound.
    """
    monkeypatch.setenv(static_site.RESPONSE_BYTES_ENV, "4096")
    (web_root / "assets" / "font-Bbbbbbbb.woff2").write_bytes(b"\xff\xfe" * 1650)  # 3300 B

    response = static_site.serve("GET", "/assets/font-Bbbbbbbb.woff2", root=web_root)
    envelope = str(response["body"])
    ceiling = static_site.max_response_bytes()

    # (1) The inflation, measured.
    assert response["isBase64Encoded"] is True, "nothing is being inflated, so nothing is measured"
    assert len(envelope) == 4400
    assert len(envelope) == 4 * ((3300 + 2) // 3), "the 4-per-3 packing formula does not hold"
    assert len(base64.b64decode(envelope, validate=True)) == 3300

    # (2) …and the ceiling reads the decoded side of it. The straddle is asserted first, so
    # a case that stopped straddling fails as "this test stopped testing" rather than as a
    # status mismatch nobody can interpret.
    assert 3300 < ceiling < len(envelope), "the case no longer straddles the ceiling"
    assert response["statusCode"] == 200, (
        f"a 3,300 B object was refused under a {ceiling} B ceiling because its "
        f"{len(envelope)}-character base64 envelope was weighed instead of the bytes AWS "
        "bills. That is interface I2 inverted, and it over-refuses by 33 % on every binary "
        "object this origin serves."
    )
    assert static_site._wire_bytes(response) == 3300
    assert int(response["headers"]["content-length"]) == 3300

    # (3) Arithmetically, without decoding. `_wire_bytes` runs on every response.
    source = ast.parse(Path(static_site.__file__ or "").read_text(encoding="utf-8"))
    wire_fn = next(
        node
        for node in ast.walk(source)
        if isinstance(node, ast.FunctionDef) and node.name == "_wire_bytes"
    )
    decoders = [
        node
        for node in ast.walk(wire_fn)
        if isinstance(node, ast.Attribute) and "decode" in node.attr and node.attr != "decode"
    ]
    assert decoders == [], (
        "_wire_bytes decodes the body to measure it. The decoded length is "
        "len(body) // 4 * 3 minus the padding, computed from the string's own length; "
        "decoding allocates a second copy of every response this module emits."
    )
    assert "base64" not in {node.id for node in ast.walk(wire_fn) if isinstance(node, ast.Name)}, (
        "_wire_bytes reaches for base64; the length is arithmetic, not a decode"
    )

    # (4) The other direction: the ENCODED string against Lambda's response-payload quota.
    # This is where the envelope IS the quantity, and the formula validated in (1) is what
    # bounds it. At the default ceiling the widest payload `_file` can build is 185,688
    # characters — 32x under — so nothing enforces this at runtime and nothing should.
    quota = static_site.LAMBDA_RESPONSE_PAYLOAD_BYTES
    widest_payload = 4 * ((static_site.DEFAULT_MAX_RESPONSE_BYTES + 2) // 3)
    assert widest_payload == 185_688
    assert widest_payload < quota, (
        f"a response at the {static_site.DEFAULT_MAX_RESPONSE_BYTES} B wire ceiling encodes "
        f"to {widest_payload} characters, over Lambda's {quota} B response payload quota. "
        "The ceiling bounds the wire; the quota bounds the envelope; a ceiling above three "
        "quarters of the quota breaches the second while satisfying the first."
    )
    # The falsification. Without it the line above holds for every ceiling anybody would
    # plausibly set, which makes it a comment rather than a check.
    assert quota < 4 * ((5 * 1024 * 1024 + 2) // 3), (
        "the quota assertion cannot fail at any ceiling, so it asserts nothing"
    )


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
#
# WHICH TREE THESE ASSERTIONS READ, AND WHY IT IS NOT THE ONE THEY USED TO READ.
#
# Every assertion below reads the **deployed** tree: the `web/` entries of
# `out/lambda/mainline-demo-api-arm64.zip`. Until 2026-08-14 they read the first of two
# sources that happened to exist, and on a developer box that was `console/dist` +
# `console/fixtures/bundles/demo-cloud` — the packer's INPUT tree. The two are not
# interchangeable and the difference is not a rounding: the input tree carries eighteen
# source maps that `build_lambda` strips by default, so the objects it reported the ceiling
# as refusing are objects the deployed origin cannot emit at all.
#
# The ruling is `docs/decisions/response-ceiling-authoritative-tree.md`: **cost is incurred
# by bytes leaving the deployed origin, so an object that never reaches the deployed package
# cannot be evidence about a cost control.** `test_static_site.py` §(f) already derived
# interface I3 over this same package and already said in writing that this file's fallback
# was the mistake; the two files declared different values — 433,396 B here and 124,127 B
# there — for one quantity, "the largest object the origin serves". This section is that
# contradiction resolved in the direction the deployed artefact settles.
#
# The input-tree fallback is **deleted rather than demoted**. A fallback that answers a cost
# question with the wrong tree is worse than no answer: the skip below says the assertion did
# not run, which is true and actionable, whereas the fallback said it ran and passed. No
# Python lane in `.github/workflows/` builds the console or the package, so these assertions
# already skipped in CI before this change and still do; what changed is that a developer box
# with a stale `console/dist` can no longer report a green that means nothing.


@functools.cache
def _deployed_entries() -> tuple[Mapping[str, int], str]:
    """``({name inside web/: bytes}, label)`` for the tree that deploys; may be empty.

    Read from the zip's **central directory**, so it costs no unpacking and cannot be
    perturbed by a test that monkeypatches ``$MAINLINE_WEB_ROOT``. One source, named, and no
    fallback: the unpacked root a Lambda serves from is this file unpacked, not a second
    measurement of anything.
    """
    if not _PACKAGE.is_file():
        return {}, ""
    with zipfile.ZipFile(_PACKAGE) as archive:
        entries = {
            info.filename[len("web/") :]: info.file_size
            for info in archive.infolist()
            if info.filename.startswith("web/") and not info.is_dir()
        }
    return entries, f"the web/ entries of {_PACKAGE}"


def _require_built_tree() -> tuple[Mapping[str, int], str]:
    """The deployed tree, or a skip that says the ratchet did not run and how to arm it.

    **Not softened into a silent skip and not allowed to become one.** A skip here means the
    tree-reading half of this section did not execute; the declaration-only half
    (:func:`test_the_declared_numbers_straddle_the_ceiling_rather_than_sitting_under_it` and
    :func:`test_the_ceiling_refuses_something_it_governs`) takes no tree and runs anyway, so
    a machine with no build output still fails on a ceiling that refuses nothing.
    """
    entries, label = _deployed_entries()
    if not entries:
        pytest.skip(
            "the deployed package is not built, so the tree-reading half of the ratchet "
            f"did NOT run in this session. Looked for {_PACKAGE}, which is a .gitignore'd "
            "build output; run scripts/deploy/build_lambda.ps1 (or .sh) to arm it. The "
            "declaration-only assertions in this section still ran, and the packer's input "
            "tree is deliberately NOT accepted as a stand-in — see the note above."
        )
    return entries, label


def _identity_and_siblings(
    entries: Mapping[str, int],
) -> tuple[dict[str, int], dict[str, int]]:
    """Split the tree into the objects that have URLs and the codings that do not."""
    identity = {n: b for n, b in entries.items() if not n.lower().endswith(static_site.GZ_SUFFIX)}
    siblings = {n: b for n, b in entries.items() if n.lower().endswith(static_site.GZ_SUFFIX)}
    return identity, siblings


@pytest.fixture(scope="session")
def deployed_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The deployed ``web/`` tree, unpacked once, so the real code can serve the real bytes.

    Session-scoped because unpacking 114 entries per test would be paid fourteen times for
    one answer. Unpacked rather than read from the archive because ``static_site.serve``
    takes a filesystem root — and serving the artefact through the shipped code is the whole
    difference between measuring file sizes and measuring what this origin emits.
    """
    entries, _ = _require_built_tree()
    root = tmp_path_factory.mktemp("deployed-web")
    with zipfile.ZipFile(_PACKAGE) as archive:
        for name in entries:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read("web/" + name))
    return root


def test_the_declared_numbers_straddle_the_ceiling_rather_than_sitting_under_it() -> None:
    """Runs everywhere, tree or no tree: the declared numbers and the arithmetic in the open.

    This is what the ceiling was chosen from, and the shape of the assertion is the point.
    It used to say *every* declared object is under the ceiling — which is exactly the
    statement of a control that refuses nothing. The declaration straddles: the largest
    object the deployed tree holds is ABOVE the ceiling on the identity path, the largest
    number of bytes the origin actually emits is BELOW it, and the gap between them is the
    compression every browser asks for and this origin had been shipping unused.

    **Every number here is DERIVED, not transcribed.** The I3 rule is recomputed from
    ``_LARGEST_SERVED_OBJECT_BYTES`` on the line above the assertion that checks it, so a
    reader can follow ``1.10 x 124,127 = 136,539.7`` → next 8 KiB boundary → 139,264 by hand.
    A constant that merely happens to equal what a run printed is not evidence, and this
    section had exactly that defect twice.

    The cost is real and is named rather than hidden: a client that will not accept gzip
    cannot fetch the console's entry bundle at all. ``curl`` without ``--compressed`` is such
    a client. The alternative is a ceiling that leaves the flood multiplier at 433,396 B,
    which makes the 124,127 B row of the cost model a number no attacker has to accept.
    """
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    assert 0 < _LARGEST_SERVED_OBJECT_BYTES < ceiling < _LARGEST_WEB_OBJECT_BYTES

    # The two names are ONE object with two codings. Asserted rather than left to a reader,
    # because it is the fact that makes a 413 and a 200 for the same URL correct.
    assert _LARGEST_SERVED_OBJECT == _LARGEST_WEB_OBJECT
    assert _LARGEST_SERVED_CODING == _LARGEST_WEB_OBJECT + static_site.GZ_SUFFIX

    # Interface I3, recomputed from the measurement rather than quoted from the ruling.
    floor = 1.10 * _LARGEST_SERVED_OBJECT_BYTES
    assert round(floor, 1) == 136_539.7
    rounding = 8 * 1024
    derived = -(-int(floor) // rounding) * rounding
    assert derived == ceiling == 139_264 == 136 * 1024, (
        f"the I3 rule over {_LARGEST_SERVED_OBJECT_BYTES} B derives {derived}, and the "
        f"constant is {ceiling}. The constant is the CONSEQUENCE; re-derive it, never "
        "re-choose it."
    )
    ratio = ceiling / _LARGEST_SERVED_OBJECT_BYTES
    assert _LARGEST_SERVED_OBJECT_BYTES <= ceiling < 1.20 * _LARGEST_SERVED_OBJECT_BYTES
    assert round(ratio, 3) == 1.122, f"the I3 ratio moved: {ratio}"

    headroom = ceiling - _LARGEST_SERVED_OBJECT_BYTES
    assert headroom == 15_137, f"the declared headroom moved: {headroom} B"

    # The flood's multiplier, before and after negotiation, as a ratio somebody can check by
    # hand. 433,396 / 124,127 = 3.491553…, which is 3.4916 to four places — NOT the 3.4917
    # the ruling's prose carries, and not the 3.586 this assertion used to hold (that was
    # 1,554,168 / 433,396: the source-map strip's cut, a different pair of numbers entirely).
    cut = _LARGEST_WEB_OBJECT_BYTES / _LARGEST_SERVED_OBJECT_BYTES
    assert round(cut, 4) == 3.4916, f"the declared reduction moved: {cut}"


def test_the_ceiling_refuses_something_it_governs() -> None:
    """**The anti-vacuity assertion.** A control that refuses nothing is not a control.

    This is the assertion whose absence let the ceiling sit at 2 MiB above a tree whose
    largest object was 1,554,168 B, refusing 0 of 75, while every other test in this file
    stayed green — because "everything is under the ceiling" is satisfied most easily by a
    ceiling nothing can reach.

    It takes **no tree**, deliberately: making the one assertion that proves the control
    binds depend on a ``.gitignore``'d build output would make it the one most likely to
    skip. When a tree IS present it additionally checks that each declared refusal is a real
    object and really is over the ceiling, so the declaration cannot name a fiction.

    The second assertion is interface **I1** applied to the declaration itself. A ``.gz``
    sibling has no URL, so a direct request for one is a 404 and never a 413; a sibling
    appearing in this tuple would mean somebody had enumerated all 114 ``web/`` entries and
    filed 57 404s as ceiling refusals, turning a control that refuses one object into one
    that appears to refuse fifty-eight. That is the exact hazard this section is shaped
    around, and here it is refused at the declaration rather than caught downstream.
    """
    assert _REFUSED_BY_THE_CEILING, "the ceiling refuses nothing, so it bounds nothing"
    siblings_declared = [
        n for n in _REFUSED_BY_THE_CEILING if n.lower().endswith(static_site.GZ_SUFFIX)
    ]
    assert siblings_declared == [], (
        "a .gz sibling is declared as a ceiling refusal. Interface I1 makes a direct request "
        "for one a 404, not a 413, so this is a 404 mis-filed as a cost control."
    )

    entries, label = _deployed_entries()
    if entries:
        assert set(_REFUSED_BY_THE_CEILING) <= set(entries), (
            f"a declared refusal names an object {label} does not contain"
        )
        for name in _REFUSED_BY_THE_CEILING:
            assert entries[name] > static_site.DEFAULT_MAX_RESPONSE_BYTES, (
                f"{name} is declared as refused but is {entries[name]} B, under the "
                f"{static_site.DEFAULT_MAX_RESPONSE_BYTES} B ceiling. A refusal that does "
                "not happen is a declaration this file cannot back."
            )


def test_the_default_ceiling_refuses_the_declared_object_and_serves_the_declared_asset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The straddle again, through ``serve`` rather than through arithmetic — **one URL**.

    Three files whose sizes are the three declared numbers, under the DEFAULT ceiling with no
    environment override in sight, because the value that matters is the one a deploy that
    sets nothing will enforce.

    What this asserts that no arithmetic can: the 413 and the 200 are **the same object at
    the same path**, separated only by a request header. That is the deployed truth of a
    136 KiB ceiling over a tree where every object ships a ``.gz`` sibling, it is the
    sentence the module docstring makes in prose, and before 2026-08-14 nothing anywhere
    asserted it at the default ceiling — this test wrote two unrelated files called
    ``over.js`` and ``under.js`` and so could not have noticed if negotiation stopped working
    altogether.
    """
    monkeypatch.delenv(static_site.RESPONSE_BYTES_ENV, raising=False)
    root = tmp_path / "web"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_bytes(_INDEX.encode("utf-8"))

    name = _LARGEST_WEB_OBJECT.split("/", 1)[1]
    (root / "assets" / name).write_bytes(b"x" * _LARGEST_WEB_OBJECT_BYTES)
    (root / "assets" / (name + static_site.GZ_SUFFIX)).write_bytes(
        b"y" * _LARGEST_SERVED_OBJECT_BYTES
    )
    second = _WIDEST_SERVED_IDENTITY.split("/", 1)[1]
    (root / "assets" / second).write_bytes(b"z" * _WIDEST_SERVED_IDENTITY_BYTES)

    identity = static_site.serve("GET", "/" + _LARGEST_WEB_OBJECT, root=root)
    assert identity["statusCode"] == 413, f"{_LARGEST_WEB_OBJECT} would still be served whole"
    error = json.loads(identity["body"])["error"]
    assert error["kind"] == "response_too_large"
    assert error["bytes"] == _LARGEST_WEB_OBJECT_BYTES
    assert error["bytes_on_disk"] == _LARGEST_WEB_OBJECT_BYTES
    assert error["ceiling_bytes"] == static_site.DEFAULT_MAX_RESPONSE_BYTES
    # Without `vary`, a shared cache would replay this refusal to a browser that would have
    # been served — the refusal depends on the request header exactly as the 200 does.
    assert identity["headers"]["vary"] == static_site.VARY_ACCEPT_ENCODING

    negotiated = static_site.serve(
        "GET", "/" + _LARGEST_SERVED_OBJECT, root=root, accept_encoding=_BROWSER
    )
    assert negotiated["statusCode"] == 200, "the ceiling refuses the console's own entry bundle"
    assert negotiated["headers"]["content-encoding"] == static_site.GZIP_CODING
    assert negotiated["isBase64Encoded"] is True
    assert static_site._wire_bytes(negotiated) == _LARGEST_SERVED_OBJECT_BYTES
    assert int(negotiated["headers"]["content-length"]) == _LARGEST_SERVED_OBJECT_BYTES

    # And the ceiling is not a wall on the identity path either: the next object down is
    # served whole to a client that refuses compression.
    plain = static_site.serve("GET", "/" + _WIDEST_SERVED_IDENTITY, root=root)
    assert plain["statusCode"] == 200
    assert static_site._wire_bytes(plain) == _WIDEST_SERVED_IDENTITY_BYTES


def test_the_largest_file_in_the_built_web_tree_is_the_one_the_ceiling_refuses() -> None:
    """**The ratchet.** The biggest thing in the deployed tree, measured, and where it falls.

    Not the declaration — the tree. A constant asserted against itself proves nothing; this
    walks the artefact and finds the maximum in it. The maximum is required to be an object
    this file has *named as refused*, so an unrecognised giant appearing in the tree fails
    here instead of quietly becoming the new multiplier.

    It walks identity objects. A ``.gz`` sibling is not a candidate for "the largest object
    the ceiling refuses" because it is not addressable at all.
    """
    entries, label = _require_built_tree()
    identity, _ = _identity_and_siblings(entries)
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    name, size = max(identity.items(), key=lambda item: item[1])
    if size < ceiling:
        assert size <= _LARGEST_SERVED_OBJECT_BYTES, (
            f"{name} is {size} B in {label} — under the ceiling but above the declared "
            f"served maximum of {_LARGEST_SERVED_OBJECT_BYTES} B. Re-measure and declare it."
        )
        return
    assert name in _REFUSED_BY_THE_CEILING, (
        f"{name} is {size} B in {label}, at or above the {ceiling} B ceiling, and this file "
        "does not name it as refused. This origin would 413 an asset nobody decided to stop "
        "serving. Strip it, declare it in _REFUSED_BY_THE_CEILING, or raise the ceiling "
        "deliberately — do not raise it to make this pass."
    )


def test_the_built_web_tree_has_not_outgrown_its_declaration() -> None:
    """Growth must be declared. That is the difference between a ratchet and a limit.

    The ceiling says the emitted maximum is *safe*; this says it is *known*. Both halves are
    checked, because the tree now has two columns and only one of them is what leaves: the
    identity maximum bounds what a caller can ASK for, and the sibling maximum bounds what
    this origin actually EMITS — and it is the second that is the multiplier in the flood
    arithmetic and the input to I3. A build that stopped compressing well would move the
    second without moving the first, which is a rise in what this origin costs and would
    have been invisible to a ratchet that watched file sizes alone.
    """
    entries, label = _require_built_tree()
    identity, siblings = _identity_and_siblings(entries)

    name, size = max(identity.items(), key=lambda item: item[1])
    assert size <= _LARGEST_WEB_OBJECT_BYTES, (
        f"the largest object in {label} is now {name} at {size} B, above the declared "
        f"{_LARGEST_WEB_OBJECT} at {_LARGEST_WEB_OBJECT_BYTES} B. Re-measure, decide the new "
        "number is acceptable at concurrency 10 for 30 days, then update "
        "_LARGEST_WEB_OBJECT_BYTES in this file. Do not delete this assertion."
    )

    coding, wire = max(siblings.items(), key=lambda item: item[1])
    assert wire <= _LARGEST_SERVED_OBJECT_BYTES, (
        f"the widest response {label} can emit is now {coding} at {wire} B, above the "
        f"declared {_LARGEST_SERVED_CODING} at {_LARGEST_SERVED_OBJECT_BYTES} B. That number "
        "is the input to interface I3, so raising it re-derives the ceiling. Re-derive it; "
        "do not re-declare this one to match."
    )


def test_every_identity_object_in_the_deployed_tree_serves_or_is_a_declared_refusal(
    deployed_root: Path,
) -> None:
    """The end-to-end form: serve all 57 objects, both ways round, and let the real code decide.

    The file-size ratchets above compare bytes on disk. This compares bytes **on the wire**,
    which is what egress is billed in — and for the 57 negotiated responses and every binary
    object the two are not the same number, because those bodies travel base64 and the
    envelope is a third larger. So the measurement is :func:`static_site._wire_bytes`, never
    ``len`` of the body string; the previous version of this test took the latter and would
    have reported every ``.gz`` response as 33 % wider than it is.

    **Both ways round, because an anonymous caller picks.** The ceiling exists to bound the
    choice a caller makes, not the choice we would prefer they made, so each object is served
    once with no ``Accept-Encoding`` and once as a browser sends it.

    ``refused`` is an **exact map**, not a bound: what is refused must be what this file
    declared, on the path it declared, no more and no less. A new refusal fails here, so does
    the disappearance of the only one, and so does the same object starting to be refused on
    the negotiated path — which would mean the console had stopped loading at all.

    It enumerates **identity objects only.** Every path ending ``.gz`` is a 404 by interface
    I1, so sweeping all 114 entries would file 57 404s in ``refused`` and drown the one real
    refusal in them. Those 404s are asserted next door, as the property they are.
    """
    entries, label = _require_built_tree()
    identity, _ = _identity_and_siblings(entries)
    assert len(identity) == _IDENTITY_OBJECTS
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES

    refused: dict[str, int] = {}
    widest: dict[str, tuple[str, int]] = {"identity": ("", 0), "gzip": ("", 0)}
    for name in sorted(identity):
        for coding, accept in (("identity", None), ("gzip", _BROWSER)):
            response = static_site.serve(
                "GET", "/" + name, root=deployed_root, accept_encoding=accept
            )
            if response["statusCode"] != 200:
                refused[f"{name} [{coding}]"] = int(response["statusCode"])
                continue
            wire = static_site._wire_bytes(response)
            assert wire == int(response["headers"]["content-length"]), (
                f"{name} [{coding}] reports a content-length the client will not receive"
            )
            if wire > widest[coding][1]:
                widest[coding] = (name, wire)

    assert refused == {f"{n} [identity]": 413 for n in _REFUSED_BY_THE_CEILING}, (
        f"{label} refuses {sorted(refused)}; this file declares "
        f"{sorted(f'{n} [identity]' for n in _REFUSED_BY_THE_CEILING)}. Every difference is "
        "either an object that started being refused without anybody deciding to stop "
        "serving it, or a bound that stopped biting. Both are changes to what this origin "
        "costs."
    )
    assert set(refused.values()) == {413}, f"a refusal that is not the ceiling's: {refused}"

    # The multiplier, derived from the responses rather than from the declaration.
    assert widest["gzip"] == (_LARGEST_SERVED_OBJECT, _LARGEST_SERVED_OBJECT_BYTES), (
        f"the widest response {label} can emit is {widest['gzip']}; the declared multiplier "
        f"is {_LARGEST_SERVED_CODING} at {_LARGEST_SERVED_OBJECT_BYTES} B."
    )
    assert widest["identity"] == (_WIDEST_SERVED_IDENTITY, _WIDEST_SERVED_IDENTITY_BYTES)
    assert widest["gzip"][1] < ceiling
    assert widest["identity"][1] < ceiling


def test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal(
    deployed_root: Path,
) -> None:
    """**The hazard, asserted as a property instead of routed around.**

    57 of the deployed tree's 114 entries answer non-200 to a direct request, and none of
    them is a cost control refusing anything: interface I1 gives one set of bytes one name,
    so ``<name>.gz`` is reachable by sending ``accept-encoding: gzip`` to ``<name>`` and by
    nothing else. An enumeration that collected every non-200 over all 114 entries would file
    those 57 404s beside the one 413 and report a ceiling that refuses fifty-eight objects.

    The last block is the **negative control** for that mistake: it performs the naive sweep
    on purpose, shows it yields 58, and separates the 57 that are 404s from the 1 that is the
    ceiling. Without it, "the enumeration covers identity objects" is a convention somebody
    can undo in a refactor without anything going red.
    """
    entries, _ = _require_built_tree()
    _, siblings = _identity_and_siblings(entries)
    assert len(siblings) == _IDENTITY_OBJECTS, "a sibling is missing or an orphan appeared"

    for name in sorted(siblings):
        response = static_site.serve("GET", "/" + name, root=deployed_root)
        assert response["statusCode"] == 404, f"{name} answered {response['statusCode']}"
        error = json.loads(response["body"])["error"]
        assert error["kind"] == "asset_not_found", name
        # The sibling exists on disk and is under the ceiling, so a 413 here would not even
        # be the ceiling doing its job — it would be a mis-routed refusal.
        assert error["kind"] != "response_too_large", name

    # The negative control: the sweep this section must NOT perform, performed once.
    naive = {
        name: int(static_site.serve("GET", "/" + name, root=deployed_root)["statusCode"])
        for name in sorted(entries)
    }
    non_200 = {name: status for name, status in naive.items() if status != 200}
    assert len(non_200) == len(siblings) + len(_REFUSED_BY_THE_CEILING) == 58, (
        f"the naive whole-tree sweep yields {sorted(non_200.items())}"
    )
    assert sorted(name for name, status in non_200.items() if status == 404) == sorted(siblings)
    assert [name for name, status in non_200.items() if status == 413] == list(
        _REFUSED_BY_THE_CEILING
    ), "the naive sweep's ONE genuine ceiling refusal is not the declared one"


def test_the_built_web_tree_matches_the_shape_the_flood_arithmetic_assumed() -> None:
    """The totals the USD figures are derived from, and the pairing that makes them true.

    Equalities rather than bounds, and that is a change of shape. It used to *report* the
    file count and total bytes and assert only that the tree was non-trivial — while pinning
    ``(75, 3,571,990)`` against itself, which is a tautology that survives any tree at all. A
    bound would let the tree grow toward the ceiling without anybody deciding that was
    acceptable, which is precisely how the largest object drifted while every test stayed
    green last time.

    The pairing is the load-bearing one and nothing here asserted it before: **every identity
    object has a sibling and no sibling is an orphan.** That is what makes
    ``largest_served_wire_bytes`` the compressed column throughout rather than a mixture of
    the two columns, and the whole I3 derivation rests on it. If one object lost its sibling,
    the bytes this origin emits for it would jump to the identity size and the ceiling would
    be derived over a tree that no longer exists — silently, because every other number here
    would still add up.
    """
    entries, label = _require_built_tree()
    identity, siblings = _identity_and_siblings(entries)

    assert len(entries) == _WEB_TREE_ENTRIES, f"{label} holds {len(entries)} entries"
    assert len(identity) == len(siblings) == _IDENTITY_OBJECTS
    assert sum(entries.values()) == _WEB_TREE_BYTES
    assert sum(identity.values()) == _IDENTITY_BYTES
    assert sum(siblings.values()) == _SIBLING_BYTES
    assert _IDENTITY_BYTES + _SIBLING_BYTES == _WEB_TREE_BYTES
    assert _IDENTITY_OBJECTS * 2 == _WEB_TREE_ENTRIES

    assert sorted(siblings) == sorted(n + static_site.GZ_SUFFIX for n in identity), (
        f"{label} no longer pairs one sibling to one object. The I3 derivation reads the "
        "compressed column for every object; an unpaired object is served identity and its "
        "size, not its sibling's, is what this origin emits."
    )

    # Zero source maps, and this is the assertion that would notice the strip being turned
    # off — 2,586,960 B of debug artefact billable to this account by anyone on the internet.
    assert [n for n in entries if n.lower().endswith(".map")] == [], (
        f"{label} carries source maps. build_lambda strips web/**/*.map by default; a build "
        "that shipped them would put the whole of this file's arithmetic back on the wrong "
        "tree."
    )


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
    could not both hold**, and the contradiction was left standing on purpose until somebody
    owned the ceiling: that test pinned the older semantics, in which the envelope is the
    measured quantity. It was **resolved on 2026-08-14 in I2's favour, and the deciding
    evidence was that I2 is ratified outside the module that changed** — a module that moves
    a metric and documents the move in its own docstring is a module marking its own
    homework. `docs/leads/cost-finish-plan.md` fixes the wire as the billed quantity because
    a Function URL decodes ``isBase64Encoded`` before the bytes leave and AWS bills what
    leaves. Had that ratification not existed outside `static_site.py`, the older assertion
    would have been the authoritative side and this one would have moved instead.

    What the older test did **not** lose is its obligation: it still measures the inflation,
    still requires the case to straddle the ceiling, and now also bounds the encoded string
    against Lambda's response-payload quota — the one place the envelope really is the
    number that counts. See its docstring for the four parts.
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
