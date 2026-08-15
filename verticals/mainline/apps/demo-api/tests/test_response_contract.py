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

# ── THE DEPLOYED WEB TREE · WHAT IS LAW, AND WHAT IS ONLY A RECORD OF ONE BUILD ─────
#
# **THIS SECTION WAS RESHAPED ON 2026-08-16 AND THE RESHAPING IS THE POINT.** Everything it
# used to declare fell into two piles that it did not distinguish, and the undistinguished
# pile is what put these tests red three times in two days.
#
# THE CAUSE, NAMED ONCE AND IN THE RIGHT PLACE.
# `verticals/mainline/apps/console/vite.config.ts` inlines `__MAINLINE_BUILD_ID__`, so the
# git short SHA reaches the emitted JavaScript. A Vite chunk name IS a content hash.
# Therefore the entry chunk's FILENAME changes on every commit — including a commit that
# changes nothing else about the console — and a test that pins `assets/index-<hash>.js` as
# a literal goes stale on every build **by construction**. On 2026-08-16 this file declared
# `index-LoN3Sn_L.js` while `out/lambda/mainline-demo-api-arm64.zip` carried
# `index-HZTFrKeL.js`, and five tests here plus two in `test_static_site.py` plus
# twenty-eight in `tests/deploy/test_furl_compression.py` were red for that one reason.
# **Three times running, the repair was to type the new numbers in.** A number that is
# re-recorded every time it fails has never refused anything; what it does instead is bury
# the assertions that would refuse something under a wall of red that everybody learns to
# read as "the console was rebuilt again".
#
# THE PROPERTIES. These are the cost claims. They are asserted against whatever the archive
# holds, they are not relaxed, and none of them mentions a filename:
#
#     * `static_site.DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024 == 139,264`. **It may never
#       move.** No argument makes it available — loosening a cost bound so that arithmetic
#       agrees is the move that put it at 2 MiB and then at 512 KiB, and it has been refused
#       three times (ruling R10, `docs/leads/reconcile-constants-plan.md` §1);
#     * the straddle: `largest_served_gzipped < ceiling < largest_identity_object`;
#     * EXACTLY ONE identity object at or above the ceiling, on the identity path only;
#     * headroom at or above `_MINIMUM_HEADROOM_BYTES`;
#     * every identity object paired with one `.gz` sibling — no orphan, no gap, zero maps.
#
# THE PROVENANCE. These move whenever the console legitimately changes, and a build must not
# fail because one of them did: the entry chunk's FILENAME, its identity and gzipped byte
# counts, the web-tree totals, the second-largest object, and every ratio derived from them.
# They are recorded below, dated and attributed to a build, so a reader still learns what the
# tree cost on a given day. Nothing compares them to a later archive.
#
# **WHY RESOLVING THE NAME IS NOT THE LOOKUP THIS FILE HAS ALWAYS REFUSED.** The standing
# objection — *"a number read out of the tree at test time agrees with the tree by
# construction and asserts nothing"* — is correct about a MEASUREMENT and wrong about a
# PROPERTY. `sum(sizes) == 1_884_886` read from the tree is indeed vacuous. *Exactly one
# object is at or above the ceiling* is false of a tree with two giants however they are
# named; the straddle is false of a ceiling above everything it governs; the pairing is
# false of a build that stopped writing siblings; and the end-to-end sweeps below serve every
# object through the real `serve` and compare what came back to the archive's own metadata,
# which are two independent measurements. What resolution removes is only the one claim that
# was never a property: **the chunk is called this**.
#
# ── THE RECORD · BUILD `5302005`, READ FROM THE CENTRAL DIRECTORY ON 2026-08-16 ─────
#
# `zipfile` over `out/lambda/mainline-demo-api-arm64.zip`,
# `sha256 e97981a494f432f4db55dd175881d9551610fdd637bbfe63475258041102bf4d`, 291 archive
# entries, packed from HEAD `5302005` `--console-transport live`; the manifest beside the zip
# records `console.build_ids == ['5302005', 'unknown']`. Reproduce the totals with:
#
#     python -c "import zipfile;z=zipfile.ZipFile('out/lambda/mainline-demo-api-arm64.zip');
#                w=[i for i in z.infolist() if i.filename.startswith('web/') and not i.is_dir()];
#                print(len(w), sum(i.file_size for i in w))"
#
#     web/ entries                    154 files   1,884,886 B
#       identity objects               77 files   1,457,534 B
#       .gz siblings                   77 files     427,352 B   one per object, no orphans
#       source maps                     0 files           0 B   stripped by build_lambda
#     entry chunk        assets/index-HZTFrKeL.js
#       identity                                    490,373 B
#       gzipped                                     137,939 B   `g`, the flood multiplier
#     second-largest identity object                 96,734 B   assets/operator-D24tzVGh.js
#     headroom                                        1,325 B   139,264 - 137,939 = 0.95 %
#
# WHAT MOVED AGAINST THE PACKAGE BEFORE IT (`sha256 7c97b532…`, `MAINLINE_BUILD_ID=f0ba767`):
#
#     web/ bytes          1,524,990 → 1,884,886   (+359,896)
#     identity bytes      1,177,977 → 1,457,534   (+279,557)
#     sibling bytes         347,013 →   427,352   (+80,339)
#     largest identity      490,950 →   490,373   (-577)   ← the entry chunk, renamed
#     largest sibling `g`   138,177 →   137,939   (-238)   ← the flood multiplier
#     second identity        67,049 →    96,734   (+29,685)
#     entries / objects   138 / 69  →  154 / 77   (+16 / +8)
#     source maps               0/0 →       0/0   (0)
#
# **THE ENTRY CHUNK GOT SMALLER WHILE THE SITE GOT BIGGER, AND THAT IS NOT GOOD NEWS.** The
# eight new objects are a whole second screen — `operator-D24tzVGh.js` 96,734 B identity /
# 29,906 B gzipped, `operator.html.gz` 2,221 B — plus the memory panel: `memory.html.gz`
# 7,990 B, `memory-loop.js.gz` 16,023 B, `memory-verify.js.gz` 8,809 B. None of it is in the
# console's entry closure, because the operator screens are a SECOND HTML ENTRY and
# `budgets.json`'s `forbidden_in_entry` row is what keeps them there. `g` fell by 238 B for
# no reason anybody chose: different bytes compress differently. A margin that improves by
# accident can worsen by accident on the next commit, which is why the guard is a fixed
# 1,024 B of bytes and not a percentage of a number that keeps moving.
#
# **READ THOSE OUT OF THE ARCHIVE AND NOWHERE ELSE.** The zip's own manifest records the
# tree BEFORE the source-map strip and BEFORE a `.gz` was written beside every compressible
# object. That is a true number about a site no request ever reaches. Confusing it with the
# 154-entry tree that deploys is the mistake the 512 KiB ceiling was made of, and it is
# available to be made again every time somebody counts `console/dist`.
#
# BEWARE THE WORKING TREE — the property, then the day it was seen. **Line endings change a
# bundle's name without changing its length.** 51 files under `apps/console` are stored LF in
# the index and can be checked out CRLF on Windows (Git for Windows ships `core.autocrlf=true`
# at system scope), and CSS-module class names hash the file's bytes, so a CRLF worktree emits
# a bundle of the SAME LENGTH under a DIFFERENT content hash. Seen 2026-08-14:
# `index-BKZMI9SJ.js`, also 433,564 B, four bytes off the `index-DzVoV1YM.js` build of the
# same day. `git ls-files --eol verticals/mainline/apps/console` is how you tell, and the zip
# digest is what settles it. **Since 2026-08-16 that hazard cannot make these tests red** —
# nothing here reads a chunk name — but it can still make an artefact that is not this
# repository's, so the digest above is what a reader checks the record against.
#
# ── RULING R10 · THE CEILING STANDS AT 139,264; THE DERIVATION IS PROVENANCE ────────
#
# R10 in one sentence: **`static_site.DEFAULT_MAX_RESPONSE_BYTES` remains
# `136 * 1024 == 139,264`, unchanged, not raised and not lowered; the live law is the
# straddle plus interface I3; the derivation `ceil(floor(1.10·g)/8192)·8192` is preserved as
# a dated record of how 139,264 was CHOSEN, and is no longer asserted against the current
# tree.** Measured over the artefact named above on 2026-08-16:
#
#     STRADDLE     0 < 137,939 < 139,264 < 490,373                        HOLDS
#     I3           137,939 <= 139,264 < 1.20 x 137,939 = 165,526.8        HOLDS
#     EXACTLY ONE  identity objects at or over the ceiling: 1 of 77       HOLDS
#     HEADROOM     139,264 - 137,939 = 1,325 >= 1,024                     HOLDS
#     DERIVATION   ceil(floor(1.10 x 137,939)/8192) x 8192 = 155,648   != 139,264
#
# Nothing the ceiling is FOR has changed. Raising it to 155,648 so the arithmetic agrees was
# considered and **refused**: it loosens a cost bound to satisfy a formula. Nor is the
# derivation kept as an inequality in the other direction — `derive(g) >= C` holds for every
# `g` above the window and therefore refuses nothing — but `C <= derive(g)` IS kept, below,
# because it is the half with teeth: it fails the moment somebody raises the ceiling past
# what the derivation would have chosen.
#
# WHY A ROUNDED DERIVATION WAS NEVER THE LAW. `ceil(floor(1.10·g)/8192)·8192` is
# **many-to-one**: it returns 139,264 for every `g` in a 7,447 B band. So `derive(g) == C`
# never said *the ceiling is correct*; it said *`g` is inside a particular pre-image band*,
# which is a bundle-size budget wearing a ceiling's clothes — and this repository already
# owns one, `apps/console/scripts/check-budgets.ts`, welded to this ceiling by
# `test_static_site.py::test_the_console_ci_budget_goes_red_before_the_origin_does`.
# Conflating the two is what generates pressure on the ceiling every time the console
# legitimately grows.
#
# **THE NUMBER WITH TEETH: 1,325 gzipped bytes of headroom remain.** It was 15,087, then
# 9,864, then 1,087. Say plainly what crossing it costs, because the failure is silent from
# outside: when `g` passes 139,264 this origin answers **413 for its own entry JavaScript**
# to every client. `GET /` still returns 200 and the shell; the shell then asks for its one
# module and receives a JSON problem document; the judge is looking at a **blank page**. That
# is a TOTAL OUTAGE of the demo URL rather than a slow one, and the demo URL is the whole
# submission. `_MINIMUM_HEADROOM_BYTES` goes red at 1,024 B, i.e. BEFORE the crossing, while
# the fix is still "make the chunk smaller". **The fix is never a larger ceiling.**

#: The build every figure in this section was read from, named by digest because a path is
#: not an identity and "the current build" is a sentence that rots.
_PROVENANCE_BUILD_ID: Final = "5302005"
_PROVENANCE_SHA256: Final = "e97981a494f432f4db55dd175881d9551610fdd637bbfe63475258041102bf4d"

#: PROVENANCE, build `5302005`. Was 138 entries / 69 objects. The PAIRING is asserted live —
#: every identity object carries exactly one `.gz` sibling and no sibling is an orphan — and
#: it is the pairing, not the count, that makes the compressed column the multiplier
#: throughout. **Counted in the ARCHIVE, never in `console/dist`.**
_WEB_TREE_ENTRIES: Final = 154
_IDENTITY_OBJECTS: Final = 77

#: PROVENANCE, build `5302005`. The three totals, recorded so the record's own arithmetic can
#: be checked by hand: 1,457,534 + 427,352 = 1,884,886, and 77 x 2 = 154. Nothing is served
#: or refused on the strength of a total — the ceiling is applied per response, never per
#: tree — so these are measurements of a build and never floors under one.
_WEB_TREE_BYTES: Final = 1_884_886
_IDENTITY_BYTES: Final = 1_457_534
_SIBLING_BYTES: Final = 427_352

#: PROVENANCE, build `5302005`. The largest single object the deployed tree held, and the
#: largest number of bytes any caller could ask this origin for by name. It is **above** the
#: ceiling, which is what makes the ceiling demonstrably binding: a bound is only a bound if
#: something is known to sit over it. That PROPERTY is asserted live against whatever the
#: archive resolves to; this pair is the day's reading of it — was `assets/index-LoN3Sn_L.js`
#: at 490,950 B, is `assets/index-HZTFrKeL.js` at 490,373 B.
#:
#: It is not the largest thing that can be EMITTED: the object has two representations and
#: this is the one nobody with a browser ever receives.
_LARGEST_WEB_OBJECT: Final = "assets/index-HZTFrKeL.js"
_LARGEST_WEB_OBJECT_BYTES: Final = 490_373

#: PROVENANCE, build `5302005`. The largest number of bytes the origin actually PUT ON THE
#: WIRE for one response — `g`, the multiplier in the flood arithmetic and the input to
#: interface I3. Was `assets/index-LoN3Sn_L.js.gz` at 138,177 B.
#:
#: It is **the same object as above**, and that is the point rather than a coincidence to be
#: tidied away: every identity object ships a `.gz` sibling and every browser sends
#: `Accept-Encoding: gzip`, so the bytes that leave are the compressed column throughout. The
#: entry chunk is 490,373 B to a client that refuses compression and 137,939 B to one that
#: does not, and the ceiling sits between those two numbers — so one object is a 413 and a
#: 200 depending only on a request header. That is asserted end-to-end in
#: `test_the_default_ceiling_refuses_the_declared_object_and_serves_the_declared_asset`.
_LARGEST_SERVED_OBJECT: Final = "assets/index-HZTFrKeL.js"
_LARGEST_SERVED_CODING: Final = "assets/index-HZTFrKeL.js.gz"
_LARGEST_SERVED_OBJECT_BYTES: Final = 137_939

#: PROVENANCE, build `5302005`. The widest response the origin can emit to a client that
#: refuses compression *and is still served*. Was `assets/surface-BD2Wh4U2.js` at 67,049 B;
#: is `assets/operator-D24tzVGh.js` at 96,734 B — the operator screen, which arrived in this
#: build as a SECOND HTML ENTRY and is therefore not in the console's entry closure at all.
#: What it reports is that the refusal is still isolated: this object sits 42,530 B below the
#: ceiling and 393,639 B below the object above it. The PROPERTY — the second-largest
#: identity object is under the ceiling — is asserted live.
_WIDEST_SERVED_IDENTITY: Final = "assets/operator-D24tzVGh.js"
_WIDEST_SERVED_IDENTITY_BYTES: Final = 96_734

#: PROVENANCE, build `5302005`. Every object the default ceiling refused, **by name and on
#: the identity path**. Was `('assets/index-LoN3Sn_L.js',)`.
#:
#: **THE PROPERTY IS THE ARITY — EXACTLY ONE — AND IT IS RESOLVED FROM THE ARCHIVE, NOT READ
#: FROM HERE.** `_refused_by_the_ceiling` walks the identity column of the built tree and
#: collects what is at or above the bound; this tuple is what that walk returned on
#: 2026-08-16. 1 of 77, exactly as 1 of 69 and 1 of 57 before it — twenty objects have joined
#: the tree across three releases and not one has come near the bound.
#:
#: **A `.gz` sibling may never appear here**, and that is a rule rather than an observation.
#: Interface I1 makes a direct request for any path ending `.gz` a **404** — one set of bytes
#: gets one name — so enumerating all 154 `web/` entries and collecting every non-200 would
#: file 77 404s as "refusals" and make a control that refuses one object look like a control
#: that refuses seventy-eight. The enumerations below therefore walk identity objects, and
#: the siblings' 404 is asserted as its own property in
#: `test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal`.
_REFUSED_BY_THE_CEILING: Final = ("assets/index-HZTFrKeL.js",)

#: PROVENANCE, build `5302005`. `139,264 - 137,939`, recorded beside the two numbers it is
#: the difference of. The BOUND under it is `_MINIMUM_HEADROOM_BYTES`.
_PROVENANCE_HEADROOM_BYTES: Final = 1_325

#: **A BOUND, NOT A MEASUREMENT.** The fewest bytes of gzipped headroom this repository will
#: let the entry chunk leave under the ceiling before a test goes red. It is
#: `test_static_site.py::_MINIMUM_HEADROOM_BYTES`, restated here rather than imported —
#: two test modules importing each other is a circularity waiting to happen — and welded to
#: it through a third file that neither of them owns: `console/budgets.json` publishes
#: `wire_ceiling.max_gzip_bytes`, `test_static_site` asserts that it equals
#: `ceiling - 1024`, and the straddle test below asserts the same equality from this side. So
#: the two copies cannot drift apart without one of the two going red.
#:
#: **IT IS NOT AVAILABLE TO BE LOWERED, AND NEITHER IS THE CEILING RAISED TO CLEAR IT.**
#: Both buy a green by widening the thing that is supposed to bite.
_MINIMUM_HEADROOM_BYTES: Final = 1024

#: How the entry chunk is FOUND rather than named. Vite emits the console's entry as
#: `assets/index-<content hash>.js` and emits exactly one of them; the operator and memory
#: screens are separate HTML entries under their own stems, and every lazy route is a
#: `surface-`/`worker-` chunk.
_ENTRY_CHUNK_PREFIX: Final = "assets/index-"
_ENTRY_CHUNK_SUFFIX: Final = ".js"

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
       though they were 4,400: over-refusing by exactly the encoding's overhead. At the
       deployed ceiling that lands on whichever object is the largest served — at build
       ``5302005`` the 137,939 B compressed entry bundle, which would be weighed as 183,920.
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


@pytest.mark.parametrize(
    ("vector", "path", "filler"),
    _UNNAMEABLE_PATHS,
    ids=[
        "one-huge-segment",
        "legal-segments-illegal-whole",
        "one-segment-over-name-max",
    ],
)
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


def _resolve_entry_chunk(identity: Mapping[str, int]) -> str:
    """The console's entry chunk, resolved from the archive **by pattern**, not by name.

    This function is the whole repair of 2026-08-16, and it is three lines of logic carrying
    two assertions that are each worth hearing about:

    * exactly one object matches ``assets/index-*.js``. Two would mean the console emitted a
      second top-level entry under the same stem, and which of them a browser loads first —
      and which of them the ceiling refuses — would be a question nobody had answered;
    * that object is the LARGEST identity object in the tree. If it ever is not, the biggest
      thing this origin holds is something nobody reasoned about, the exactly-one-refusal
      property is about a different file than the console's entry, and the flood multiplier
      in the cost model belongs to some other object.

    Returning the name is the small part. **Refusing to return one when either statement
    fails is why this is a function rather than a `max()` at each call site**, and it is what
    keeps the pattern from quietly resolving to the wrong thing after a bundler change.
    """
    matches = sorted(
        name
        for name in identity
        if name.startswith(_ENTRY_CHUNK_PREFIX) and name.endswith(_ENTRY_CHUNK_SUFFIX)
    )
    assert len(matches) == 1, (
        f"{len(matches)} objects match {_ENTRY_CHUNK_PREFIX}*{_ENTRY_CHUNK_SUFFIX} in the "
        f"deployed tree: {matches}. The console emits exactly one entry chunk under that "
        "stem; a second one means a second top-level entry landed and nobody has decided "
        "which of them this origin's one refusal is about."
    )
    largest = max(identity.items(), key=lambda item: item[1])[0]
    assert matches[0] == largest, (
        f"the entry chunk is {matches[0]} but the largest identity object is {largest} at "
        f"{identity[largest]} B. The ceiling's one refusal is supposed to BE the entry "
        "chunk; if something else is now the biggest thing in the tree, that object is what "
        "this origin would 413 and nobody decided to stop serving it."
    )
    return largest


def _refused_by_the_ceiling(identity: Mapping[str, int]) -> tuple[str, ...]:
    """The identity objects the default ceiling turns away, read out of the built tree.

    Identity objects only, and that restriction is interface **I1** rather than a
    convenience: a ``.gz`` sibling has no URL of its own, so a direct request for one is a
    404 and never a 413. A sweep over all 154 ``web/`` entries would file 77 404s here and
    make a control that refuses ONE object look like a control that refuses seventy-eight.
    """
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    return tuple(sorted(name for name, size in identity.items() if size >= ceiling))


@pytest.fixture(scope="session")
def deployed_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The deployed ``web/`` tree, unpacked once, so the real code can serve the real bytes.

    Session-scoped because unpacking the whole tree per test would be paid fourteen times for
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

    This is the ceiling's live law, and the shape of the assertion is the point. It used to
    say *every* declared object is under the ceiling — which is exactly the statement of a
    control that refuses nothing. The declaration straddles: the largest object the deployed
    tree holds is ABOVE the ceiling on the identity path, the largest number of bytes the
    origin actually emits is BELOW it, and the gap between them is the compression every
    browser asks for and this origin had been shipping unused.

    **RULING R10, and it is why this function changed shape on 2026-08-15.** Until that day
    it also asserted ``derive(g) == ceiling`` — interface I3's formula
    ``ceil(floor(1.10·g)/8192)·8192`` re-emitting 139,264 from the measurement. Over the tree
    that ships at build ``5302005`` (``g = 137,939``) that formula emits **155,648**,
    and **the ceiling was NOT raised to match it.** Raising a cost bound so that a formula
    agrees is the move that put this constant at 2 MiB and then at 512 KiB; it is refused
    outright by `docs/leads/reconcile-constants-plan.md` §1, which is the ruling this
    function now implements. What the derivation was — the dated record of how 139,264 was
    CHOSEN, over ``g = 124,177`` on the 2026-08-14 tree — is preserved as **provenance** in
    ``test_static_site.py``, which still asserts it against that fixed input and would still
    catch the ceiling being silently re-chosen. It is not deleted; it is moved to the tense
    it belongs in.

    **What is asserted HERE is the live law: the straddle, and interface I3's two bounds.**
    A rounded derivation is many-to-one — it returns 139,264 for every ``g`` in a 7,447 B
    band — so ``derive(g) == C`` was never the statement *this ceiling is correct*; it was
    the statement *the console is inside a size band*, which is a bundle-size budget wearing
    a ceiling's clothes, and this repository owns one of those elsewhere. The straddle and I3
    are what say the bound still bites: something is still refused, the console still loads,
    and the ceiling is not floating above everything it governs. The decision record is
    `docs/decisions/response-ceiling-authoritative-tree.md` §9.

    **Every number here is still DERIVED, not transcribed** — and as of 2026-08-16 the
    derived ones are BOUNDED rather than PINNED. The ratio, the compression cut and the
    derivation's own output are each recomputed on the line above the assertion that uses
    them, so a reader can follow the arithmetic by hand; what the assertion then says is
    which side of a bound the result has to fall on. Pinning them to four decimal places was
    a fourth copy of the treadmill: ``round(ratio, 3) == 1.008`` is a statement about one
    build's compressor output wearing the clothes of a law, and it went red on a release
    where every actual law still held. The values are recorded in the block above instead.

    The cost is real and is named rather than hidden: a client that will not accept gzip
    cannot fetch the console's entry bundle at all. ``curl`` without ``--compressed`` is such
    a client. The alternative is a ceiling that leaves the flood multiplier at the identity
    size, which makes the compressed row of the cost model a number no attacker has to accept.
    """
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    # THE STRADDLE — unchanged in shape across every build this repository has packed. It
    # read `0 < 129,400 < 139,264 < 457,123`, then `0 < 138,177 < 139,264 < 490,950`, and at
    # build `5302005` it reads `0 < 137,939 < 139,264 < 490,373`. Only the outer two numbers
    # are measurements; the middle one is the bound and R10 keeps it where it is. Asserted
    # here over the RECORD, and over the live archive in
    # `test_the_largest_file_in_the_built_web_tree_is_the_one_the_ceiling_refuses`.
    assert 0 < _LARGEST_SERVED_OBJECT_BYTES < ceiling < _LARGEST_WEB_OBJECT_BYTES

    # The two names are ONE object with two codings. Asserted rather than left to a reader,
    # because it is the fact that makes a 413 and a 200 for the same URL correct.
    assert _LARGEST_SERVED_OBJECT == _LARGEST_WEB_OBJECT
    assert _LARGEST_SERVED_CODING == _LARGEST_WEB_OBJECT + static_site.GZ_SUFFIX
    # …and the record's own arithmetic, so the block above can be checked by hand: the two
    # columns sum to the tree, and every object is one identity plus one sibling. Both sides
    # of each equality are frozen together, so neither can be what fails a build.
    assert _IDENTITY_BYTES + _SIBLING_BYTES == _WEB_TREE_BYTES
    assert _IDENTITY_OBJECTS * 2 == _WEB_TREE_ENTRIES
    assert ceiling - _LARGEST_SERVED_OBJECT_BYTES == _PROVENANCE_HEADROOM_BYTES

    # INTERFACE I3, THE LIVE HALF, recomputed from the measurement rather than quoted from
    # the ruling. Lower bound: the ceiling is at least what this origin emits, or the console
    # does not load at all. Upper bound: it is under 1.20x that, or it floats above the tree
    # and refuses nothing. The bracket was `129,400 <= 139,264 < 155,280`, then
    # `138,177 <= 139,264 < 165,812.4`, and at build `5302005` it is
    # `137,939 <= 139,264 < 165,526.8`. `g` is the measurement; 1.10 and 1.20 are the bound
    # and are not this file's to move.
    assert _LARGEST_SERVED_OBJECT_BYTES <= ceiling < 1.20 * _LARGEST_SERVED_OBJECT_BYTES
    ratio = ceiling / _LARGEST_SERVED_OBJECT_BYTES
    # 1.121 → 1.076 → 1.008 → 1.010. **Read the direction carefully**: the ceiling is now
    # about 1 % above what this origin emits, where it was 7.6 % above, so the bound sits
    # CLOSER to the tree and bites HARDER than it did. For the 1.20 ratchet — which exists to
    # catch a ratio climbing toward a ceiling that floats above everything and refuses
    # nothing — that is the safe direction. The cost of moving this way is not vacuity, it is
    # the headroom asserted next, and that is where all the risk in this file now sits. The
    # ratio is PROVENANCE: it moves with `g` on every release, so it is bounded, not pinned.
    assert 1.0 <= ratio < 1.20, f"the I3 ratio left its window: {ratio}"

    # THE NUMBER WITH TEETH. 15,087 → 9,864 → 1,087 → **1,325 B**, 0.95 % of the ceiling at
    # build `5302005`. A console growth adding more than this to the compressed entry chunk
    # puts `g` over the ceiling and this origin then 413s its own entry JavaScript to every
    # browser — the shell loads, its only module does not, and a judge gets a blank page: a
    # total outage of the demo URL. This figure — not R4's superseded window
    # `119,158 <= g <= 126,604` — is the live constraint every document carries, per
    # `docs/leads/reconcile-constants-plan.md` §1.5. **The BOUND is the inequality**, and it
    # is `_MINIMUM_HEADROOM_BYTES` rather than the measurement: a repository that re-records
    # its margin whenever the margin moves has no margin.
    headroom = ceiling - _LARGEST_SERVED_OBJECT_BYTES
    assert headroom >= _MINIMUM_HEADROOM_BYTES, (
        f"only {headroom} B of gzipped headroom remain against a {ceiling} B ceiling, and "
        f"this repository reserves {_MINIMUM_HEADROOM_BYTES} B. At zero this origin answers "
        "413 to its own entry JavaScript for EVERY browser and a judge sees a blank page. "
        "Fix it by making the entry chunk smaller — do NOT raise DEFAULT_MAX_RESPONSE_BYTES "
        "and do NOT lower the reserve."
    )
    # THE WELD, from this side. `_MINIMUM_HEADROOM_BYTES` is restated in two test modules and
    # in the console's own CI gate, and this is what stops the three drifting: the budget
    # `pnpm run ci` enforces must be exactly `ceiling - reserve`. `test_static_site.py`
    # asserts the same equality from the other side; either going red names the same defect.
    budgets = json.loads(
        (REPO_ROOT / "verticals/mainline/apps/console/budgets.json").read_text(encoding="utf-8")
    )
    assert budgets["wire_ceiling"]["max_gzip_bytes"] == ceiling - _MINIMUM_HEADROOM_BYTES, (
        "the console's entry-chunk wire budget and this file's reserve disagree about the "
        "same bound. A budget above `ceiling - reserve` lets CI pass a build this file would "
        "refuse; below it, the two guards disagree about what the rule is."
    )

    # R10 IN CODE: the derivation is still COMPUTED here, and is no longer required to equal
    # the ceiling. It was `floor = 142,340.0 → 147,456`, then `floor = 151,994.7 → 155,648`,
    # and at build `5302005` it is `floor = 151,732.9 → 155,648`. Each is a measurement of a
    # build, and the gap the derivation opens against the constant widens with every release
    # — which is what it means for a derivation to be provenance rather than law. The BOUND
    # is the assertion after it, and it is the one with consequences: the ceiling may be
    # tighter than the formula would choose and may NEVER be loosened to meet it.
    floor = 1.10 * _LARGEST_SERVED_OBJECT_BYTES
    rounding = 8 * 1024
    derived = -(-int(floor) // rounding) * rounding
    assert ceiling <= derived, (
        f"the ceiling is {ceiling} B and the I3 derivation over "
        f"{_LARGEST_SERVED_OBJECT_BYTES} B emits {derived} B. A ceiling ABOVE what the "
        "derivation would choose has been loosened to fit the tree it governs, which is "
        "exactly the move ruling R10 refuses. Re-measure the tree; never re-choose the bound "
        "to match it."
    )
    assert ceiling == 139_264 == 136 * 1024, (
        "DEFAULT_MAX_RESPONSE_BYTES moved. R10 (docs/leads/reconcile-constants-plan.md §1) "
        "keeps it at 136 KiB over this tree: the derivation is provenance, held against "
        "g = 124,177 in test_static_site.py; the straddle and I3 above are the law; and "
        "155,648 is not available as a ceiling however cleanly the arithmetic would agree — "
        "least of all now, when raising it by one 8 KiB step would buy back 8,192 B against "
        "a margin of 1,325 B and look like housekeeping while doing it."
    )

    # The flood's multiplier, before and after negotiation, as a ratio somebody can check by
    # hand. 433,564/124,177 = 3.4915, then 457,123/129,400 = 3.5326, then
    # 490,950/138,177 = 3.5531, and at build `5302005` 490,373/137,939 = 3.5549. (It once
    # held 3.586, which was 1,554,168/433,396: the source-map strip's cut, a different pair
    # of numbers entirely.) A measurement of how well one build's entry chunk compresses — it
    # bounds nothing, so it is bounded loosely rather than pinned: what would actually matter
    # is compression stopping, and a cut at or below 1 is that event.
    cut = _LARGEST_WEB_OBJECT_BYTES / _LARGEST_SERVED_OBJECT_BYTES
    assert cut > 1.0, f"the entry chunk no longer compresses: {cut}"


def test_the_ceiling_refuses_something_it_governs() -> None:
    """**The anti-vacuity assertion.** A control that refuses nothing is not a control.

    This is the assertion whose absence let the ceiling sit at 2 MiB above a tree whose
    largest object was 1,554,168 B, refusing 0 of 75, while every other test in this file
    stayed green — because "everything is under the ceiling" is satisfied most easily by a
    ceiling nothing can reach.

    It takes **no tree** for its first half, deliberately: making the one assertion that
    proves the control binds depend on a ``.gitignore``'d build output would make it the one
    most likely to skip. The record above says the ceiling refused exactly one object on the
    day it was read, and that much is asserted on any machine.

    **When a tree IS present the refusal set is RESOLVED from it, not compared to the
    record** (2026-08-16). The old form checked that the declared name was in the archive and
    over the ceiling, which is a true statement that a build-id-only re-release makes false
    without anything about the ceiling changing. What is asserted now is the arity — walk the
    identity column, collect what is at or above the bound, and require exactly one — plus
    the identity of that one: it must be the object ``_resolve_entry_chunk`` finds, so the
    refusal cannot silently migrate to some other file.

    The ``.gz`` assertion is interface **I1** applied to the refusal set itself. A sibling
    has no URL, so a direct request for one is a 404 and never a 413; a sibling appearing
    here would mean somebody had enumerated all 154 ``web/`` entries and filed 77 404s as
    ceiling refusals, turning a control that refuses one object into one that appears to
    refuse seventy-eight. That is the exact hazard this section is shaped around, and it is
    refused at the set rather than caught downstream.
    """
    assert _REFUSED_BY_THE_CEILING, "the ceiling refuses nothing, so it bounds nothing"
    siblings_declared = [
        n for n in _REFUSED_BY_THE_CEILING if n.lower().endswith(static_site.GZ_SUFFIX)
    ]
    assert siblings_declared == [], (
        "a .gz sibling is recorded as a ceiling refusal. Interface I1 makes a direct request "
        "for one a 404, not a 413, so this is a 404 mis-filed as a cost control."
    )

    entries, label = _deployed_entries()
    if entries:
        identity, _ = _identity_and_siblings(entries)
        entry = _resolve_entry_chunk(identity)
        refused = _refused_by_the_ceiling(identity)
        assert refused == (entry,), (
            f"{label} has {len(refused)} identity objects at or above the "
            f"{static_site.DEFAULT_MAX_RESPONSE_BYTES} B ceiling: {list(refused)}. Exactly "
            f"one is expected and it must be the entry chunk, {entry}. More than one is an "
            "asset nobody decided to stop serving; none at all is a ceiling that refuses "
            "nothing and therefore bounds nothing — the state it was in at 2 MiB and again "
            "at 512 KiB. Do not raise the ceiling to make this pass."
        )
        for name in refused:
            assert entries[name] > static_site.DEFAULT_MAX_RESPONSE_BYTES, (
                f"{name} is in the refusal set but is {entries[name]} B, under the "
                f"{static_site.DEFAULT_MAX_RESPONSE_BYTES} B ceiling. A refusal that does "
                "not happen is a claim this file cannot back."
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

    Not a declaration — the tree. A constant asserted against itself proves nothing; this
    walks the artefact, finds the maximum in it, and requires that maximum to be the object
    the ceiling refuses **and** the object ``_resolve_entry_chunk`` finds by pattern. An
    unrecognised giant appearing in the tree fails here instead of quietly becoming the new
    multiplier, and so does the entry chunk ceasing to be the biggest thing in the tree.

    **The straddle, over the live archive** (2026-08-16): the widest sibling is under the
    ceiling and the largest identity object is over it, both read from the zip. The same
    inequality is asserted over the frozen record in
    ``test_the_declared_numbers_straddle_the_ceiling_rather_than_sitting_under_it``, which
    needs no build output; this is the half with the artefact in it.

    It walks identity objects. A ``.gz`` sibling is not a candidate for "the largest object
    the ceiling refuses" because it is not addressable at all.
    """
    entries, label = _require_built_tree()
    identity, siblings = _identity_and_siblings(entries)
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    entry = _resolve_entry_chunk(identity)
    name, size = max(identity.items(), key=lambda item: item[1])
    assert name == entry
    assert size >= ceiling, (
        f"the largest object in {label} is {name} at {size} B, UNDER the {ceiling} B "
        "ceiling. Nothing in the tree is then at or above the bound, so the bound refuses "
        "nothing and is a decoration — the state it was in at 2 MiB and again at 512 KiB. "
        "This is the anti-vacuity half of the straddle and it is not satisfiable by raising "
        "or lowering the ceiling to taste."
    )
    served = max(siblings.values())
    assert 0 < served < ceiling < size, (
        f"the straddle is broken in {label}: the widest sibling is {served} B and the "
        f"largest object is {size} B against a {ceiling} B ceiling. Below the sibling the "
        "console cannot be served at all; above the object the flood multiplier returns to "
        "the identity bundle and the compressed row of the cost model stops being a bound "
        "anybody has to accept."
    )


def test_the_built_web_tree_has_not_outgrown_its_declaration() -> None:
    """Growth must be bounded. **The bound is the reserve, not last week's measurement.**

    The tree has two columns and only one of them is what leaves: the identity maximum
    bounds what a caller can ASK for, and the sibling maximum bounds what this origin
    actually EMITS — and it is the second that is the multiplier in the flood arithmetic and
    the input to I3. A build that stopped compressing well would move the second without
    moving the first, which is a rise in what this origin costs and would be invisible to a
    check that watched file sizes alone. Both halves are still checked here.

    **WHAT CHANGED ON 2026-08-16, AND WHY IT IS A TIGHTENING RATHER THAN A LOOSENING.** The
    two assertions used to read ``max(...) <= <the number somebody recorded last time>``.
    That is a ratchet in name only: it goes red on every legitimate console release, and the
    only available response is to type in the new maximum — which is what happened at
    124,127, then 124,177, then 129,400, then 138,177. A bound that is rewritten to the
    measurement whenever the measurement passes it has never bounded anything. What replaces
    it is the bound this repository actually committed to and which does NOT move when the
    console does: the widest response the origin emits must leave ``_MINIMUM_HEADROOM_BYTES``
    under the ceiling. At build ``5302005`` that refuses anything above 138,240 B where the
    old form refused anything above 138,177 B, so it is 63 B looser on that one day and
    permanently tighter than a number that is re-recorded on every release. It is also the
    same bound ``console/budgets.json`` makes CI enforce before a package is ever built.
    """
    entries, label = _require_built_tree()
    identity, siblings = _identity_and_siblings(entries)
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    entry = _resolve_entry_chunk(identity)

    # What a caller can ASK for: the biggest object in the tree is the entry chunk, and it
    # is the only one over the bound. Anything else at the top of this column is an object
    # that would be 413'd without anybody deciding to stop serving it.
    assert _refused_by_the_ceiling(identity) == (entry,), (
        f"{label} refuses {list(_refused_by_the_ceiling(identity))} on the identity path; "
        f"exactly one refusal is expected and it must be the entry chunk, {entry}."
    )

    # What this origin EMITS: the widest sibling, against the reserve. This is interface I3's
    # input and the flood arithmetic's multiplier, and the assertion is the one that goes red
    # while the fix is still "make the chunk smaller" rather than "the demo is down".
    coding, wire = max(siblings.items(), key=lambda item: item[1])
    assert coding == entry + static_site.GZ_SUFFIX, (
        f"the widest response {label} can emit is {coding} at {wire} B, which is not the "
        f"entry chunk's sibling. The compressed row of the cost model quotes the entry "
        "chunk; if some other object emits more, that row is about the wrong file."
    )
    assert ceiling - wire >= _MINIMUM_HEADROOM_BYTES, (
        f"the widest response {label} can emit is {coding} at {wire} B, leaving "
        f"{ceiling - wire} B under the {ceiling} B ceiling where this repository reserves "
        f"{_MINIMUM_HEADROOM_BYTES} B. At zero this origin answers 413 for its own entry "
        "JavaScript to every browser and a judge sees a blank page. Make the entry chunk "
        "smaller — code-split the console, or move what grew behind a lazy route. Do NOT "
        "raise DEFAULT_MAX_RESPONSE_BYTES and do NOT lower the reserve: both buy the green "
        "by widening the bound that is supposed to bite."
    )

    # And every sibling is under the ceiling, not merely the widest one — an object whose
    # COMPRESSED form is over the bound is an object no client can fetch by any means.
    over = sorted(name for name, size in siblings.items() if size >= ceiling)
    assert over == [], (
        f"{over} are compressed representations at or above the ceiling in {label}. Those "
        "objects are unfetchable: identity is refused for being too large and gzip is "
        "refused for the same reason, so there is no request that gets them at all."
    )


def test_every_identity_object_in_the_deployed_tree_serves_or_is_a_declared_refusal(
    deployed_root: Path,
) -> None:
    """The end-to-end form: serve every object, both ways round, and let the real code decide.

    The file-size checks above compare bytes on disk. This compares bytes **on the wire**,
    which is what egress is billed in — and for every negotiated response and every binary
    object the two are not the same number, because those bodies travel base64 and the
    envelope is a third larger. So the measurement is :func:`static_site._wire_bytes`, never
    ``len`` of the body string; the previous version of this test took the latter and would
    have reported every ``.gz`` response as 33 % wider than it is.

    **Both ways round, because an anonymous caller picks.** The ceiling exists to bound the
    choice a caller makes, not the choice we would prefer they made, so each object is served
    once with no ``Accept-Encoding`` and once as a browser sends it.

    ``refused`` is an **exact map**, not a bound: what is refused must be exactly one object,
    on the identity path, and it must be the entry chunk this tree resolves to. A new refusal
    fails here, so does the disappearance of the only one, and so does the same object
    starting to be refused on the negotiated path — which would mean the console had stopped
    loading at all. **The expected key is RESOLVED from the archive rather than transcribed**
    (2026-08-16): the object's name is a content hash and typing it here is what made this
    test red on a release where nothing it checks had changed.

    It enumerates **identity objects only.** Every path ending ``.gz`` is a 404 by interface
    I1, so sweeping all 154 entries would file 77 404s in ``refused`` and drown the one real
    refusal in them. Those 404s are asserted next door, as the property they are.

    The two ``widest`` values are read off the RESPONSES and compared to the archive's own
    metadata. Those are two independent measurements of the same quantity — one through
    ``serve``, base64 and the ceiling, one out of the central directory — so the comparison
    is not the tautology a lookup would be: it fails if negotiation ever stops emitting the
    sibling, which is a silent doubling of what this origin costs.
    """
    entries, label = _require_built_tree()
    identity, siblings = _identity_and_siblings(entries)
    ceiling = static_site.DEFAULT_MAX_RESPONSE_BYTES
    entry = _resolve_entry_chunk(identity)
    second_largest = sorted(identity.items(), key=lambda item: item[1])[-2]

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

    assert refused == {f"{entry} [identity]": 413}, (
        f"{label} refuses {sorted(refused)}; exactly one refusal is expected, on the identity "
        f"path, and it must be the entry chunk {entry}. Every difference is either an object "
        "that started being refused without anybody deciding to stop serving it, or a bound "
        "that stopped biting. Both are changes to what this origin costs."
    )
    assert set(refused.values()) == {413}, f"a refusal that is not the ceiling's: {refused}"

    # The multiplier, derived from the responses and checked against the archive.
    assert widest["gzip"] == (entry, siblings[entry + static_site.GZ_SUFFIX]), (
        f"the widest response {label} emitted is {widest['gzip']}; the entry chunk's sibling "
        f"in the archive is {siblings[entry + static_site.GZ_SUFFIX]} B. A disagreement here "
        "means `serve` is not putting the compressed representation on the wire."
    )
    # The widest IDENTITY response is the second-largest object, because the largest is the
    # one refused. That is the sentence that says the refusal is isolated: one object over
    # the bound, and the next one down served whole.
    assert widest["identity"] == second_largest, (
        f"the widest identity response {label} emitted is {widest['identity']} and the "
        f"second-largest object in the tree is {second_largest}. If those differ, more than "
        "one object is being turned away on the identity path."
    )
    assert widest["gzip"][1] < ceiling
    assert widest["identity"][1] < ceiling
    assert ceiling - widest["gzip"][1] >= _MINIMUM_HEADROOM_BYTES, (
        f"the widest response this origin actually emitted leaves "
        f"{ceiling - widest['gzip'][1]} B under the ceiling, below the "
        f"{_MINIMUM_HEADROOM_BYTES} B this repository reserves. Make the entry chunk smaller."
    )


def test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal(
    deployed_root: Path,
) -> None:
    """**The hazard, asserted as a property instead of routed around.**

    Half the deployed tree's entries answer non-200 to a direct request — 77 of 154 at build
    ``5302005`` — and none of them is a cost control refusing anything: interface I1 gives
    one set of bytes one name, so ``<name>.gz`` is reachable by sending
    ``accept-encoding: gzip`` to ``<name>`` and by nothing else. An enumeration that collected
    every non-200 over all 154 entries would file those 77 404s beside the one 413 and report
    a ceiling that refuses seventy-eight objects.

    The last block is the **negative control** for that mistake: it performs the naive sweep
    on purpose and separates the 404s from the one that is the ceiling. Without it, "the
    enumeration covers identity objects" is a convention somebody can undo in a refactor
    without anything going red. **The count it lands on is derived — ``len(siblings) + 1`` —
    rather than the literal 70 it used to be**, because the literal was one more entry in the
    treadmill: it moved 58 → 70 → 78 across three releases while the property it stands for
    never changed.
    """
    entries, _ = _require_built_tree()
    identity, siblings = _identity_and_siblings(entries)
    assert len(siblings) == len(identity) > 0, "a sibling is missing or an orphan appeared"
    entry = _resolve_entry_chunk(identity)

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
    assert len(non_200) == len(siblings) + 1, (
        f"the naive whole-tree sweep yields {len(non_200)} non-200s where one sibling per "
        f"object plus the single ceiling refusal is {len(siblings) + 1}: "
        f"{sorted(non_200.items())}"
    )
    assert sorted(name for name, status in non_200.items() if status == 404) == sorted(siblings)
    assert [name for name, status in non_200.items() if status == 413] == [entry], (
        "the naive sweep's ONE genuine ceiling refusal is not the entry chunk"
    )


def test_the_built_web_tree_matches_the_shape_the_flood_arithmetic_assumed() -> None:
    """The SHAPE the USD figures are derived from — the pairing, not the totals.

    **THE TOTALS LEFT THIS TEST ON 2026-08-16 AND THE PAIRING STAYED, WHICH IS THE WHOLE
    DISTINCTION.** It used to assert five equalities against the archive: entry count, object
    count, and the three byte sums. Every one of those is the size of a console somebody
    deliberately grew, so every one of them went red on a legitimate release and was typed in
    again — 114/57 then 138/69 then 154/77, three re-records in two days. A number that is
    rewritten whenever it fails has never refused anything. The totals are now recorded above
    as dated provenance, where a reader learns what the tree cost on 2026-08-16 without a
    rebuild turning that into a red build. Their internal arithmetic is still asserted, in
    ``test_the_declared_numbers_straddle_the_ceiling_rather_than_sitting_under_it``: the two
    columns must sum to the tree and every object must be one identity plus one sibling.

    What remains here is what the flood arithmetic actually rests on and what does NOT move
    when the console does:

    * **every identity object has a sibling and no sibling is an orphan.** That is what makes
      ``largest_served_wire_bytes`` the compressed column throughout rather than a mixture of
      the two columns, and the whole I3 derivation rests on it. If one object lost its
      sibling, the bytes this origin emits for it would jump to the identity size and the
      ceiling would be governing a tree that no longer exists — silently, because every total
      would still add up;
    * **the tree is exactly two entries per addressable object**, so nothing is hiding in the
      count that is neither an object nor exactly one object's coding;
    * **zero source maps.**
    """
    entries, label = _require_built_tree()
    identity, siblings = _identity_and_siblings(entries)

    assert len(identity) == len(siblings) > 0, f"{label} holds {len(entries)} entries"
    assert len(entries) == 2 * len(identity), (
        f"{label} holds {len(entries)} entries against {len(identity)} addressable objects. "
        "Something in the tree is neither an object with a URL nor exactly one object's "
        "compressed coding."
    )
    assert sum(identity.values()) + sum(siblings.values()) == sum(entries.values())

    assert sorted(siblings) == sorted(n + static_site.GZ_SUFFIX for n in identity), (
        f"{label} no longer pairs one sibling to one object. The I3 derivation reads the "
        "compressed column for every object; an unpaired object is served identity and its "
        "size, not its sibling's, is what this origin emits."
    )

    # Zero source maps, and this is the assertion that would notice the strip being turned
    # off — 3,179,550 B of debug artefact billable to this account by anyone on the internet.
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
# The object this decides is whichever one the origin serves widest; measured 2026-08-16 on
# build `5302005` that is the compressed entry bundle at 137,939 B on the wire, whose
# envelope is 183,920 characters (it was 138,177 / 184,236 on the package before it, and
# 129,400 / 172,536 before that — a measurement that moves with the console, not a bound,
# which is why nothing in this file compares it to a literal). Weighing the envelope would refuse
# it at any ceiling between those two numbers, and 139,264 is between them — so this is not
# a hypothetical: the single path the whole cost model depends on callers taking is the one
# a 33 % measurement error refuses. `tests/deploy/test_furl_compression.py` proves the same
# property end-to-end, through a real socket, where the decode is actually performed.


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
    would never have billed. Scaled to the object this actually decides — the largest served,
    which at build `5302005` is the 137,939 B compressed entry bundle — that object would
    be weighed as 183,920 B and refused: the single path the cost model
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
