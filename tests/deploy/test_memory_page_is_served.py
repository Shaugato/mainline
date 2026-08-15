# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``/memory.html`` is a real object on the deployed origin, and it costs the console nothing.

WHY THIS FILE EXISTS
--------------------
``docs/demo/memory-visible-plan.md`` **R-M2** puts the store → retrieve → act panel in
``verticals/mainline/apps/console/public/`` as four framework-free files, and rests that
choice on a structural claim: Vite copies ``public/`` **verbatim**, so those files never
enter the module graph, never enter ``dist/.vite/manifest.json``, and are therefore outside
both ``budgets.json`` roots *by construction* rather than by coincidence.

The claim is right. It is also the kind of claim that is true until somebody adds a
``publicDir`` override or a third ``rollupOptions.input``, and the failure it would cause is
invisible from outside this repository:

    ``static_site.DEFAULT_MAX_RESPONSE_BYTES`` is 139,264 B and it bounds the **wire** bytes
    of one response, static files included. The deployed console's compressed entry chunk is
    138,177 B, so the headroom is **1,087 B**. When that reaches zero
    :func:`mainline_demo_api.static_site.serve` answers **413 for the console's own entry
    JavaScript** — to every client, because the gzip representation is the one every browser
    takes. ``GET /`` still answers 200 with its shell. The shell asks for its only module and
    receives a JSON problem document. A judge is looking at a **blank page** while this
    origin logs a healthy day.

So this file asserts two different things, and neither is a restatement of the other:

* **that the memory page is SERVED** — that a file placed in ``console/public/`` reaches the
  web root ``static_site`` reads, answers 200 with ``text/html``, is itself rather than the
  SPA fallback, and that its ``.gz`` sibling has no URL of its own (interface **I1**);
* **that it COSTS NOTHING** — that every one of the four files is under the wire ceiling on
  *both* representations, and that no configuration in this tree can route one of them into
  a ``budgets.json`` root.

WHAT IS MEASURED HERE AND WHAT IS MEASURED IN TYPESCRIPT
--------------------------------------------------------
The companion gate is ``verticals/mainline/apps/console/scripts/check-memory-bytes.ts``,
which builds the console twice — with ``public/`` moved aside and with it in place — and
asserts the entry closure is byte-identical across the two. It has to run under Node because
only Node can drive the bundler.

**This file owns the authoritative compression figure**, because the bytes a browser pulls
are written by ``scripts/deploy/build_lambda.{sh,ps1}``'s ``gzip_bytes()`` — CPython's
``zlib.compressobj(9, DEFLATED, -MAX_WBITS)`` inside a hand-written RFC 1952 container — and
Node's zlib does not agree with CPython's to the byte. Measured 2026-08-15:
``memory.html`` is 7,990 B under CPython and 7,943 B under Node. Both are ~131 KB under the
ceiling, so nothing here turns on the difference; it is named because rounding a disagreement
away is how a measurement becomes a slogan. :func:`_packer_gzip` below is the packer's
function, copied deliberately rather than imported, and
:func:`test_the_sibling_this_file_writes_is_the_one_build_lambda_writes` holds the copy to
its original.

NOTHING HERE MODIFIES ``static_site.py``. It is imported and exercised, and its ceiling is
read from the module rather than restated, so this file cannot pass against a number that has
drifted from the one the origin enforces.

This file needs no database and no network: it runs under ``--crdb=none``.
"""

from __future__ import annotations

import re
import shutil
import sys
import zlib
from pathlib import Path
from typing import Any, Final

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: The read spine is not installed into the environment this suite runs in — the deployed
#: artefact carries it — so the source tree is put on `sys.path` the same way
#: `tests/deploy/test_console_repro.py` reaches `scripts/deploy/console_repro.py`. The REAL
#: module is imported; nothing here is a copy of it.
DEMO_API_SRC: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "src"
if str(DEMO_API_SRC) not in sys.path:
    sys.path.insert(0, str(DEMO_API_SRC))

from mainline_demo_api import static_site  # noqa: E402  (path established immediately above)

CONSOLE: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "console"
PUBLIC: Final = CONSOLE / "public"
VITE_CONFIG: Final = CONSOLE / "vite.config.ts"
BUDGETS: Final = CONSOLE / "budgets.json"
MANIFEST: Final = CONSOLE / "dist" / ".vite" / "manifest.json"
BUILD_LAMBDA: Final = REPO_ROOT / "scripts" / "deploy" / "build_lambda.ps1"

#: The four files R-M2 places in `public/`, named rather than globbed. A fifth file arriving
#: without anybody deciding it should is exactly what a wire ceiling with 1,087 B of headroom
#: cannot afford, so this list is the declaration and `test_the_memory_panel_is_these_files`
#: is what holds the directory to it.
MEMORY_FILES: Final[tuple[str, ...]] = (
    "memory-loop.js",
    "memory-verify.js",
    "memory.css",
    "memory.html",
)

#: Suffixes `build_lambda.gzip_siblings()` writes a `<name>.gz` beside — its
#: `COMPRESSIBLE_SUFFIXES`, which all four files above are covered by.
COMPRESSIBLE: Final[frozenset[str]] = frozenset(
    {".css", ".html", ".js", ".json", ".map", ".mjs", ".svg", ".txt", ".wasm", ".webmanifest"}
)

#: What `index.html` says in the web root this file builds. It exists so that a 200 for
#: `/memory.html` can be shown to be the memory page rather than the SPA fallback — which is
#: also a 200, with `text/html`, and would otherwise be indistinguishable from success.
FALLBACK_MARKER: Final = "<!doctype html><title>SPA FALLBACK, NOT THE MEMORY PAGE</title>"


def _packer_gzip(data: bytes) -> bytes:
    """``build_lambda.gzip_bytes()``, reproduced byte-for-byte rather than approximated.

    ``1f 8b`` magic, ``08`` deflate, ``00`` flags — **no FNAME**, because the name is the zip
    entry's job and a filename field would carry a staging path into a tracked artefact —
    four zero bytes of MTIME because there is no clock in that program, ``02`` XFL for
    maximum compression, ``ff`` OS unknown so the artefact is not a statement about the
    machine that built it; then the raw deflate stream, then CRC32 and ISIZE little-endian.

    Copied instead of imported on purpose: ``build_lambda.ps1`` is a PowerShell file with a
    Python program inside it, so there is nothing to import, and
    :func:`test_the_sibling_this_file_writes_is_the_one_build_lambda_writes` reads that
    program's own source and fails if this drifts from it.
    """
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    body = compressor.compress(data) + compressor.flush()
    return (
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"
        + body
        + (zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "little")
        + (len(data) & 0xFFFFFFFF).to_bytes(4, "little")
    )


def _wire_bytes(response: dict[str, Any]) -> int:
    """The bytes a response puts on the wire — interface **I2**, the billed number.

    A Function URL carries the body as a JSON string, so anything that is not valid UTF-8
    travels base64 and the service decodes it before it leaves. What AWS bills, and what
    ``DEFAULT_MAX_RESPONSE_BYTES`` bounds, is the decoded length.
    """
    body = str(response["body"])
    if not response.get("isBase64Encoded"):
        return len(body.encode("utf-8"))
    return len(body) // 4 * 3 - body[-2:].count("=")


@pytest.fixture(autouse=True)
def _ceiling_is_the_declared_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ``$MAINLINE_MAX_RESPONSE_BYTES`` so every case below weighs the real constant.

    :func:`static_site.max_response_bytes` lets the environment override the ceiling. A shell
    that happened to carry that variable would make every assertion in this file a statement
    about that shell rather than about the origin.
    """
    monkeypatch.delenv(static_site.RESPONSE_BYTES_ENV, raising=False)


@pytest.fixture
def web_root(tmp_path: Path) -> Path:
    """The served tree the deploy chain produces, built from the real files it produces it from.

    The chain is two copies and one compression pass, and none of the three is simulated with
    invented content:

        ``console/public/*``  --(Vite's default ``publicDir``, verbatim)-->  ``console/dist/``
        ``console/dist/*``    --(``build_lambda``: ``copytree(dist, stage/web)``)-->  ``web/``
        ``web/**``            --(``gzip_siblings``: level 9, MTIME 0, no FNAME)-->  ``web/*.gz``

    so this fixture copies the **actual bytes** of ``console/public/`` into ``tmp_path`` and
    writes the sibling ``build_lambda`` would write beside each one. It deliberately does NOT
    read ``console/dist``: a built tree is not present in every checkout, and a test that
    quietly passes when the thing it measures is absent has not run.

    ``index.html`` is a marker rather than the console's real shell, because what this file
    needs from it is the ability to tell the memory page apart from the SPA fallback.
    """
    root = tmp_path / "web"
    root.mkdir()
    (root / static_site.INDEX_NAME).write_text(FALLBACK_MARKER, encoding="utf-8")
    for name in MEMORY_FILES:
        source = PUBLIC / name
        assert source.is_file(), f"{source} is missing; R-M2 places the memory panel there"
        shutil.copyfile(source, root / name)
    for entry in sorted(root.iterdir()):
        if entry.suffix.lower() in COMPRESSIBLE:
            entry.with_name(entry.name + static_site.GZ_SUFFIX).write_bytes(
                _packer_gzip(entry.read_bytes())
            )
    return root


# ── The files exist, and they are the files that were declared ──────────────────────


def test_the_memory_panel_is_these_files_and_no_others() -> None:
    """``public/`` holds exactly the four files R-M2 named.

    A fifth file is not forbidden — it is **undeclared**, which is a different and fixable
    thing. It matters because everything in this directory is copied to the origin and served
    under the same 139,264 B ceiling as the console's own entry chunk, and because the
    honesty script and the browser spec both address these four by name.
    """
    assert PUBLIC.is_dir(), (
        f"{PUBLIC} does not exist. R-M2 puts the memory panel there because Vite copies that "
        "directory verbatim and never writes it into the build manifest."
    )
    found = tuple(sorted(entry.name for entry in PUBLIC.iterdir()))
    assert found == MEMORY_FILES, (
        f"public/ holds {found}, and this file declares {MEMORY_FILES}. Every file in that "
        "directory is copied to the deployed origin and served under the same wire ceiling as "
        "the console entry chunk, so the contents are a declaration, not a folder."
    )
    for name in MEMORY_FILES:
        assert (PUBLIC / name).stat().st_size > 0, f"public/{name} is empty"


# ── It is served, as itself ─────────────────────────────────────────────────────────


def test_a_file_under_console_public_lands_in_the_served_web_root(web_root: Path) -> None:
    """``GET /memory.html`` answers **200 ``text/html``** with the page's own bytes.

    This is the whole point of R-M2's placement: no bundler entry, no route, no code in
    ``static_site.py``. A file appears in ``console/public/`` and the origin serves it,
    because ``serve`` maps a request path to a file under the web root and the deploy chain
    put it there.

    ``x-mainline-static`` is asserted as well as the status. A 200 with ``text/html`` is also
    what the **SPA fallback** answers for a path that does not exist, so status and media type
    alone cannot tell "the memory page is served" from "the memory page is missing and the
    console's shell was returned instead" — and the second one renders a blank console where a
    judge expects the panel.
    """
    response = static_site.serve("GET", "/memory.html", root=web_root)

    assert response["statusCode"] == 200, response["body"]
    headers = response["headers"]
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert headers["x-mainline-static"] == "memory.html", (
        "the response did not come from memory.html. A miss under a non-asset prefix falls "
        "back to index.html, which is also a 200 and also text/html."
    )
    assert headers["cache-control"] == static_site.DEFAULT_CACHE_CONTROL
    assert headers["vary"] == static_site.VARY_ACCEPT_ENCODING

    on_disk = (PUBLIC / "memory.html").read_bytes()
    assert response["isBase64Encoded"] is False, "an HTML page is text and travels as text"
    assert response["body"].encode("utf-8") == on_disk, (
        "the served bytes are not the bytes in console/public/memory.html"
    )
    assert headers["content-length"] == str(len(on_disk))
    assert FALLBACK_MARKER not in response["body"]


def test_the_memory_page_is_negotiated_to_its_gz_sibling_when_the_client_can_read_one(
    web_root: Path,
) -> None:
    """The compressed half is reachable — by ``Accept-Encoding`` and by nothing else.

    Asserted before its complement below, because "``.gz`` is a 404" is only a *rule about
    naming* if the bytes are reachable some other way. If they were not, the 404 would be an
    outage wearing the costume of a policy.
    """
    response = static_site.serve(
        "GET", "/memory.html", root=web_root, accept_encoding="gzip, deflate, br"
    )

    assert response["statusCode"] == 200, response["body"]
    headers = response["headers"]
    assert headers["content-encoding"] == static_site.GZIP_CODING
    assert headers["content-type"] == "text/html; charset=utf-8", (
        "a .html.gz is HTML that arrived compressed, not a new format; a browser handed "
        "application/gzip for a document will not render it"
    )
    assert headers["vary"] == static_site.VARY_ACCEPT_ENCODING
    assert response["isBase64Encoded"] is True, "a gzip member starts 1f 8b and is not UTF-8"

    sibling = _packer_gzip((PUBLIC / "memory.html").read_bytes())
    assert _wire_bytes(response) == len(sibling)
    assert headers["content-length"] == str(len(sibling))


def test_a_direct_request_for_a_gz_path_is_a_404(web_root: Path) -> None:
    """``GET /memory.css.gz`` is **404**. One set of bytes gets one name — interface **I1**.

    Two names for one object is two cache entries, two ``content-type`` answers, and a URL
    that hands a browser gzip bytes it was never told to inflate. The sibling exists on disk
    in this web root — the previous case proves the negotiated path reaches it — so this is
    the naming rule refusing, not a file that is missing.
    """
    assert (web_root / f"memory.css{static_site.GZ_SUFFIX}").is_file(), (
        "the sibling must exist for this to be a test of the naming rule rather than of a "
        "missing file"
    )

    response = static_site.serve("GET", "/memory.css.gz", root=web_root)

    assert response["statusCode"] == 404, response["body"]
    assert response["headers"]["content-type"] == "application/json; charset=utf-8"
    import json

    error = json.loads(response["body"])["error"]
    assert error["kind"] == "asset_not_found"
    assert "memory.css" in error["detail"]
    assert static_site.GZIP_CODING in error["detail"], (
        "the 404 has to name the header that reaches the same bytes, or it is a dead end"
    )

    # And it is refused for BEING a .gz, not because it sits outside assets/ or bundle/:
    # a miss on any other non-asset path is the SPA fallback, which is a 200.
    fallback = static_site.serve("GET", "/memory.css.not-a-real-suffix", root=web_root)
    assert fallback["statusCode"] == 200
    assert FALLBACK_MARKER in fallback["body"]


# ── It costs nothing ────────────────────────────────────────────────────────────────


def test_every_file_the_memory_panel_adds_is_under_the_wire_ceiling(web_root: Path) -> None:
    """Each of the four is served, on **both** representations, under 139,264 B.

    Both, and not just the compressed one. A client that does not send
    ``Accept-Encoding: gzip`` is served the identity object — that is ``curl`` without
    ``--compressed``, which is how a judge checks a page by hand — and an identity object over
    the ceiling answers 413 to exactly that caller. The console's own entry chunk is already
    in that position at 490,950 B identity, deliberately and with the cost written down; the
    memory panel must not join it.

    The numbers are asserted as **inequalities against the module's own constant**, never as
    pinned sizes. W2, W3 and W4 own those files and their bytes will move; what may not move
    is which side of the ceiling they are on.
    """
    ceiling = static_site.max_response_bytes()
    assert ceiling == static_site.DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024 == 139_264, (
        "the ceiling in force is not the declared one, so nothing below measures the origin"
    )

    for name in MEMORY_FILES:
        identity = (PUBLIC / name).read_bytes()
        sibling = _packer_gzip(identity)

        assert len(identity) <= ceiling, (
            f"public/{name} is {len(identity):,} B identity, over the {ceiling:,} B ceiling. "
            "A caller that does not send `accept-encoding: gzip` gets a 413 and the memory "
            "panel renders nothing for them. Make the file smaller — the ceiling is not "
            "available to be raised (R10, docs/leads/reconcile-constants-plan.md)."
        )
        assert len(sibling) <= ceiling, (
            f"public/{name} compresses to {len(sibling):,} B, over the {ceiling:,} B ceiling. "
            "That is a 413 for EVERY client, because the compressed representation is the one "
            "every browser takes."
        )

        plain = static_site.serve("GET", f"/{name}", root=web_root)
        assert plain["statusCode"] == 200, plain["body"]
        assert _wire_bytes(plain) == len(identity) <= ceiling

        negotiated = static_site.serve("GET", f"/{name}", root=web_root, accept_encoding="gzip")
        assert negotiated["statusCode"] == 200, negotiated["body"]
        assert _wire_bytes(negotiated) == len(sibling) <= ceiling


def test_the_ceiling_assertion_above_refuses_a_file_that_crosses_it(web_root: Path) -> None:
    """**The falsification.** A bound nothing can breach is a bound that proves nothing.

    The four real files clear the ceiling by more than 123,000 B, so the case above would pass
    against a broken ``serve``, a broken ceiling or a typo in the comparison. This plants a
    file in the same web root that is over the ceiling on both representations and requires
    the same code path to refuse it — 413, ``response_too_large``, and ``vary`` set, because
    the refusal is an answer a different ``Accept-Encoding`` would have changed.

    ``os.urandom`` rather than a repeated byte: 200 KB of ``b"x"`` compresses to a few hundred
    bytes and would clear the ceiling on the negotiated path, testing half of what this claims
    to test.
    """
    import os

    ceiling = static_site.max_response_bytes()
    planted = web_root / "__falsification-oversize.txt"
    payload = os.urandom(ceiling + 1)
    planted.write_bytes(payload)
    planted.with_name(planted.name + static_site.GZ_SUFFIX).write_bytes(_packer_gzip(payload))

    assert planted.stat().st_size > ceiling
    assert len(_packer_gzip(payload)) > ceiling, "random bytes must not compress under the bound"

    for accept in (None, "gzip"):
        refused = static_site.serve(
            "GET", f"/{planted.name}", root=web_root, accept_encoding=accept
        )
        assert refused["statusCode"] == 413, (
            f"a {len(payload):,} B object answered {refused['statusCode']} against a "
            f"{ceiling:,} B ceiling with accept-encoding={accept!r}"
        )
        import json

        error = json.loads(refused["body"])["error"]
        assert error["kind"] == "response_too_large"
        assert error["ceiling_bytes"] == ceiling
        assert refused["headers"]["vary"] == static_site.VARY_ACCEPT_ENCODING

    # And the real files, in the same root, in the same call, still answer 200 — so the
    # refusal above is about size and not about this fixture.
    assert static_site.serve("GET", "/memory.html", root=web_root)["statusCode"] == 200


# ── Nothing here can enter a budget root ────────────────────────────────────────────


def test_no_memory_file_can_enter_a_budgets_json_root() -> None:
    """R-M2's structural claim, asserted against the two files that could break it.

    ``scripts/check-budgets.ts`` measures the transitive closure of a *manifest key*. A root is
    resolved one of three ways and every one of them is a manifest lookup: the keyword
    ``entry`` selects every chunk with ``isEntry``, a ``glob:`` root is matched against manifest
    keys, and anything else must equal a manifest key exactly. **A file that never enters
    ``dist/.vite/manifest.json`` matches none of the three.** Vite writes a manifest key for a
    build *input* and for a module reached from one; it writes nothing for ``publicDir``, which
    it copies.

    (``memory-visible-plan.md`` §1 records ``budgets.json`` as having exactly two roots,
    ``entry`` and the ``render3d`` glob. That was true when the plan was written and is not
    true now: the operator-systems lead split ``entry`` into ``index.html`` and
    ``operator.html``. The ruling is unaffected — all three are still manifest lookups — so
    this asserts the property rather than the list, and the stale line is recorded in
    ``docs/demo/memory-visible-BYTES.md`` rather than silently worked around.)

    So exactly two edits in this tree could put a ``public/`` file inside a budget:
    a ``publicDir`` override in ``vite.config.ts``, or a third ``rollupOptions.input``
    naming one. Both are asserted absent here, and both are forbidden by R-M2.

    The manifest itself is checked when a build is present. That is a reinforcement rather
    than the assertion — ``console/dist`` is not in every checkout, and a case that measures
    nothing when its input is missing has not run. The unconditional half above is what makes
    this test worth having in a tree with no ``dist/``; the reproducing command for the
    measured half is ``node scripts/check-memory-bytes.ts``, recorded with its output in
    ``docs/demo/memory-visible-BYTES.md``.
    """
    config = VITE_CONFIG.read_text(encoding="utf-8")
    assert "publicDir" not in config, (
        "vite.config.ts now mentions publicDir. R-M2 rests on Vite's DEFAULT — `public/` "
        "copied verbatim into dist/ and never written into the manifest. An override can "
        "point the copy at a directory inside the module graph, or disable it and take "
        "/memory.html off the origin entirely."
    )

    # `rollupOptions.input` is optional: without it Vite's default input is `index.html`
    # alone, which is what this file declared at HEAD 4af05e1 before the operator-systems
    # plan added a second document. Both shapes are legitimate, so the assertion is about
    # WHICH documents are inputs and not about whether the map is written out.
    inputs = re.search(r"input:\s*\{(.*?)\}", config, re.DOTALL)
    declared = (
        {"index.html"}
        if inputs is None
        else set(re.findall(r"['\"]([^'\"]+\.html)['\"]", inputs.group(1)))
    )
    assert declared, "vite.config.ts declares an `input` map that names no HTML document"
    assert not declared & set(MEMORY_FILES), (
        f"the build inputs are {sorted(declared)}, which include a file R-M2 places in "
        "public/. An input is a manifest key, and a manifest key with isEntry IS the `entry` "
        "budget root — so naming one here moves the memory panel inside the budget the "
        "console entry chunk is measured by, with 1,087 B of headroom to share."
    )
    for name in MEMORY_FILES:
        assert name not in config, f"vite.config.ts names {name}; R-M2 forbids a bundler entry"

    budgets = BUDGETS.read_text(encoding="utf-8")
    roots = set(re.findall(r'"root":\s*"([^"]+)"', budgets))
    assert roots, "budgets.json declares no root at all, so the budget gate measures nothing"
    for root in sorted(roots):
        if root.startswith("glob:"):
            continue
        assert root == "entry" or root in declared, (
            f'budgets.json budgets a root "{root}", which is neither the `entry` keyword nor '
            f"one of the declared build inputs {sorted(declared)}. `check-budgets.ts` resolves "
            "a plain root by matching a manifest KEY, so a root naming a public/ file would be "
            "a budget that either measures nothing or measures a file that has stopped being "
            "copied verbatim."
        )
    for name in MEMORY_FILES:
        assert name not in budgets, (
            f"budgets.json names {name}. R-M2 places the memory panel outside every budget "
            "root by keeping it out of the manifest; budgeting it by name says the opposite."
        )

    if MANIFEST.is_file():
        manifest = MANIFEST.read_text(encoding="utf-8")
        for name in MEMORY_FILES:
            assert name not in manifest, (
                f"{name} appears in dist/.vite/manifest.json, so it has entered the module "
                "graph and is now inside the `entry` budget root. Rebuild with "
                "`node scripts/check-memory-bytes.ts` to see what it cost the entry chunk."
            )


def test_the_deploy_chain_copies_the_whole_of_dist_into_the_web_root() -> None:
    """The second link: whatever Vite wrote to ``dist/`` is what the origin serves.

    ``build_lambda`` copies the directory rather than an enumerated list of files, which is
    why R-M2 needs no packer change and why no worker on that plan touches a deploy script. If
    this ever became a list, a new ``public/`` file would ship to nobody and ``/memory.html``
    would be a 404 on the origin while every local check stayed green.
    """
    packer = BUILD_LAMBDA.read_text(encoding="utf-8")
    assert 'shutil.copytree(args.dist, os.path.join(stage, "web"))' in packer, (
        "build_lambda no longer copies the whole of console/dist into web/. R-M2 assumes the "
        "packer moves a directory, not a manifest of names."
    )
    assert "verticals/mainline/apps/console/dist" in packer, (
        "build_lambda no longer names console/dist as the site it packs"
    )


def test_the_sibling_this_file_writes_is_the_one_build_lambda_writes() -> None:
    """:func:`_packer_gzip` is held to the packer's own source, not to a memory of it.

    Every ceiling assertion above is a statement about the bytes ``build_lambda`` will write.
    If this copy drifts — a different level, a filename field, a live MTIME — those assertions
    would be about a compressor nothing deploys, and they would keep passing while saying it.
    """
    packer = BUILD_LAMBDA.read_text(encoding="utf-8")
    assert "compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)" in packer
    assert r'b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"' in packer
    assert '(zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "little")' in packer

    for suffix in sorted(COMPRESSIBLE):
        assert f'"{suffix}"' in packer, (
            f"{suffix} is declared compressible here but build_lambda's COMPRESSIBLE_SUFFIXES "
            "does not name it, so this file predicts a sibling the packer will not write"
        )

    # The container is 18 bytes of frame around a raw deflate stream, and the frame is fixed.
    blob = _packer_gzip(b"")
    assert blob[:10] == b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"
    assert len(blob) == 10 + len(zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS).flush()) + 8
    assert zlib.decompress(_packer_gzip(b"round trip"), 16 + zlib.MAX_WBITS) == b"round trip"
