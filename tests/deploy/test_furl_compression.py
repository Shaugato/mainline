# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The compressed response, proved through a real socket rather than inside a dict.

WHY THIS FILE EXISTS, AND WHY IT IS NOT ANOTHER `serve()` TEST
---------------------------------------------------------------
``tests/test_static_site.py`` asserts what :func:`mainline_demo_api.static_site.serve`
puts in a **dict**. Everything on the compression path happens inside that dict, and the
dict is not where this breaks. A Lambda Function URL response body is a **JSON string**;
gzip bytes start ``1f 8b`` and are not valid UTF-8, so a compressed body has to travel
base64 with ``isBase64Encoded: true``, and the base64 form is **exactly 33 % larger** than
the bytes it stands for. Two failure modes live in that gap and neither is visible from
inside the dict:

* a body handed out as text where it should have been base64 is **corrupt on arrival** —
  the status line still says 200, the ``content-length`` still looks plausible, and the
  browser gets mojibake where it asked for a module;
* a ceiling, a metric or a bill computed on the base64 **string** over-counts the wire by
  exactly a third. AWS decodes the envelope before anything leaves and bills egress on the
  **decoded** bytes, so the string's length is a number that exists only between this
  handler and the service. Interface **I2** of `docs/leads/cost-finish-plan.md` fixes that,
  and its §0.5 compressed row prices thirty days of egress off the sibling's byte count
  alone — a figure that is only true if those bytes reach the socket as themselves rather
  than as their envelope, which is the premise this file exists to prove. (That row was
  modelled at ``g = 124,127`` B, a console two rebuilds back; the package described below
  puts **129,400** B on the wire. Re-pricing the row is the cost pages' work and belongs to
  whoever owns them — what is asserted here is the premise, not the price.)

So this file runs the real emulator (``scripts/deploy/local_furl.py``), over a real TCP
socket, with a plain :mod:`http.client` — no ``requests``, no new dependency — and counts
the bytes that come back off the wire. ``local_furl`` is the translation AWS performs:
request → payload-format-2.0 event → ``app.handler`` → response dict → HTTP response.
Nothing between those arrows is stubbed here.

WHAT IT SERVES: THE DEPLOYED TREE, OUT OF THE BUILT ARTEFACT
-------------------------------------------------------------
The web root is unpacked from ``out/lambda/mainline-demo-api-arm64.zip`` — the package that
deploys — and **not** from ``console/dist``. The two are different trees and confusing them
is how the previous ceiling came to be wrong (`docs/leads/cost-finish-plan.md` §0.3 F2):
``console/dist`` carries eighteen source maps and **zero** ``.gz`` siblings, while the
artefact carries zero maps and 57 siblings. A compression test run against the input tree
would find nothing to negotiate and pass by having nothing to do.

WHICH BUILD THESE NUMBERS DESCRIBE, AND WHY THEY MOVED
-------------------------------------------------------
Every size below was read out of that zip's **central directory** on **2026-08-15** — no
unpacking, so they are the packaged sizes rather than whatever a checkout happens to hold.
The package read is ``out/lambda/mainline-demo-api-arm64.zip``, ``sha256
7e49fd5e1426a4d2aaba12a2cd7aa086c95430f0b5daa3645bc8b55eaaed2738``, packed
``--console-transport live`` with ``MAINLINE_BUILD_ID=3933b97``. Its ``web/`` tree is 114
entries / 1,308,543 B, its entry chunk is ``assets/index-DJX27H0M.js`` (``sha256
e30bd39b395bad68…``), and it carries 57 identity objects / 1,012,812 B, 57 ``.gz`` siblings
/ 295,731 B and zero source maps.

**THAT ZIP IS THE SUBJECT OF EVERY NUMBER BELOW, AND IT IS NOT YET WHAT THE FUNCTION URL
SERVES.** The last reading of the wire — ``evidence/deploy/judge-walk.json``, produced by
opening a socket rather than by anybody typing — records the deployed origin referencing
``assets/index-DzVoV1YM.js`` / ``assets/index-C498vmEA.css`` and resolving its transport to
``REPLAY``. That is the package this file declared until today, and this rebuild has not
been deployed. Nothing here claims otherwise: this file unpacks the zip named above and
serves it through the real emulator, so its assertions are statements about **that
artefact**, and the deployment catches up when the orchestrator deploys it. Naming the
artefact by digest and dating the measurement — instead of welding a content hash into a
sentence about "the origin" — is the wording rule of
`docs/leads/reconcile-constants-plan.md` §3, which was written after exactly this
confusion.

**WHAT MOVED, AND WHY (2026-08-15).** Until this re-record the constants named the console
before this one — ``assets/index-DzVoV1YM.js``, 433,564 B identity / 124,177 B gzipped,
siblings totalling 289,437 B, ``index.html.gz`` at 2,123 B, packed in ``sha256
12fcba7a…dfbcc27``. Then ``demo_gate_run`` and its contract were declared, the console's
``src/data/contracts.ts`` began importing ``gate-run.schema.json?raw`` (+23,559 B in the
entry chunk), and the packer rebuilt the console LIVE. A Vite chunk name **is** a content
hash, so the entry chunk renamed itself and every one of the thirty cases in this file
**errored in fixture setup**, reporting the declared object at ``-1`` — this file's own word
for *not in the package at all*. That is this file behaving correctly — a ratchet whose
subject moved — and the answer is to move the declaration to the new measurement and name
the build, which is what the block below does. It is emphatically **not** to delete the
file, skip it, soften the fixture into a silent skip, or list it as known-red
(`docs/leads/package-and-verify-plan.md` ruling **R9**;
`docs/decisions/response-ceiling-authoritative-tree.md` §9.4).

**WHAT DID NOT MOVE: THE CEILING.** ``static_site.DEFAULT_MAX_RESPONSE_BYTES`` is still
139,264 B (``136 * 1024``), and no worker in this wave opens the module that declares it.
Ruling **R10** (`docs/leads/reconcile-constants-plan.md` §1) keeps it there and demotes the
derivation ``ceil(floor(1.10·g)/8192)·8192`` to a dated record of how 139,264 was *chosen*
in the first place. The live law is interface **I3** plus the straddle plus
exactly-one-refusal, and all three are measured true over the package above:
``0 < 129,400 < 139,264 < 457,123``, with exactly one identity object of the 57 refused.
The straddle assertion in this file is therefore unchanged in **form**; only its two
measured endpoints moved. **9,864 gzipped bytes of headroom remain** (139,264 - 129,400,
down from 15,087) before the origin would 413 its own entry chunk.

The same property holds going forward: these are re-asserted against the staged files before
any request is sent, so the next rebuild that changes the bundle fails here saying which
number moved rather than silently measuring a different object. The previous re-record
predicted today in as many words — *"when its package lands at the path above **this file is
expected to go red again and be re-recorded again**"* — and that is precisely what happened.
The prediction still stands for the rebuild after this one. Read the failure, do not route
around it.

THE ONE THING THIS DOES NOT EMULATE
------------------------------------
``local_furl`` documents its own gaps and they are unchanged. The one that matters to this
file: **AWS's decode is emulated, not observed.** ``local_furl.translate_response`` decodes
``isBase64Encoded`` bodies and writes the raw bytes, which is what the service does; a
divergence between the emulator and the service would not be caught here. What *is* caught
is every defect on this side of that boundary, which is where all of them have been.
"""

from __future__ import annotations

import base64
import gzip
import http.client
import importlib.util
import os
import socket
import sys
import threading
import zipfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
LOCAL_FURL: Final = REPO_ROOT / "scripts" / "deploy" / "local_furl.py"
ARTEFACT: Final = REPO_ROOT / "out" / "lambda" / "mainline-demo-api-arm64.zip"

#: The entry bundle: the object that dominates this origin's egress and the one the whole
#: cost argument turns on.
#:
#: **WAS** ``/assets/index-DzVoV1YM.js``, 433,564 B identity / 124,177 B gzipped.
#: **IS** ``/assets/index-DJX27H0M.js``, **457,123** B identity / **129,400** B gzipped —
#: +23,559 B and +5,223 B respectively.
#: **WHICH BUILD:** ``out/lambda/mainline-demo-api-arm64.zip``,
#: ``sha256 7e49fd5e1426a4d2aaba12a2cd7aa086c95430f0b5daa3645bc8b55eaaed2738``, packed
#: ``--console-transport live`` with ``MAINLINE_BUILD_ID=3933b97``; both figures read from
#: that zip's central directory on 2026-08-15, entry chunk ``sha256 e30bd39b395bad68…``.
#: **WHY THESE ARE MEASUREMENTS AND NOT FLOORS:** nobody in this repository chose 457,123 or
#: 129,400 — a compiler emitted them, and because a Vite chunk name is a content hash the
#: *name* is a measurement too. Ruling **R1** (restated at
#: `docs/leads/reconcile-constants-plan.md` §1.1) makes a content-hashed filename a
#: legitimate constant only where the build is reproducible, and that gate is satisfied
#: measured: the console build reproduced 3/3 byte-identical at two different sources
#: (`evidence/deploy/console-repro.json`). So re-measuring these when the console source
#: moves is the *correct* response to a rebuild and is not lowering anything. The bound in
#: this file is the **straddle** — ``ENTRY_GZIP_BYTES <= ceiling < ENTRY_IDENTITY_BYTES`` —
#: and it is unchanged in form and still holds. What these two numbers do carry is a COST:
#: they are what this origin puts on the wire, so a rebuild that moves them is a cost change
#: and is read as one, which is why they are declared here and re-checked against the staged
#: tree before a single request is sent.
#:
#: They agree, to the byte, with what
#: `verticals/mainline/apps/demo-api/tests/test_response_contract.py` declares for the same
#: two quantities (`_LARGEST_WEB_OBJECT_BYTES`, `_LARGEST_SERVED_OBJECT_BYTES`) and with
#: `test_static_site.py`'s `_LARGEST_IDENTITY_BYTES` / `_LARGEST_SERVED_WIRE_BYTES`. Three
#: modules, one tree, one set of numbers — the property that broke on 2026-08-14, when this
#: file alone still described the previous console, and again today, when this file was the
#: last of the three to be re-recorded.
ENTRY_PATH: Final = "/assets/index-DJX27H0M.js"
ENTRY_IDENTITY_BYTES: Final = 457_123
ENTRY_GZIP_BYTES: Final = 129_400

#: What the same 129,400 B costs *inside the envelope*. ``base64`` packs 3 bytes into 4
#: characters and pads the remainder, so 129,400 = 3 x 43,133 + **1** becomes
#: 4 x 43,134 = 172,536 characters ending in ``==`` (a remainder of 1 takes two pad
#: characters).
#:
#: **WAS 165,572**, for the previous bundle's 124,177 = 3 x 41,392 + **1** — the same
#: remainder, hence the same two pad characters and the same rounded ratio.
#: **IS 172,536**, measured over ``out/lambda/mainline-demo-api-arm64.zip``
#: ``sha256 7e49fd5e…aaed2738`` (``--console-transport live``, ``MAINLINE_BUILD_ID=3933b97``).
#: **WHY A MEASUREMENT:** it is a pure function of ``ENTRY_GZIP_BYTES`` — ``4·ceil(n/3)``,
#: asserted as that identity below — so it moves when and only when the sibling this build
#: emitted moves. A derived reading of a build, never a limit anybody set. **This is the
#: number that must never reach a meter, a ceiling or a bill**, and the whole point of the
#: socket is that it is not the number that reaches the client.
ENTRY_ENVELOPE_CHARS: Final = 172_536

#: The padding the envelope adds and AWS strips: 172,536 less 129,400.
#:
#: **WAS 41,395** (165,572 - 124,177); **IS 43,136**, over arm64.zip
#: ``sha256 7e49fd5e…aaed2738``, ``--console-transport live``,
#: ``MAINLINE_BUILD_ID=3933b97``. **WHY A MEASUREMENT:** it is the difference of the two
#: numbers above and of nothing else, so it is a reading of this build's envelope rather
#: than a threshold. Declared beside the two numbers it is the difference of, because the
#: test that asserts it is asserting that nobody is billed for it.
ENTRY_ENVELOPE_PADDING: Final = 43_136

#: ``index.html`` is the second object every judge fetches and, unlike the entry bundle,
#: **both** of its representations are under the ceiling. That makes it the only place a
#: refusal of compression can be proved as a 200-with-identity-bytes rather than inferred
#: from a 413, which is why the ``q=0`` and token-matching cases below use it.
#:
#: **The identity size did NOT move: 4,655 B before and after**, which is the one fixed
#: point in this file and is what lets the negotiation cases be read as being about
#: negotiation rather than about a moving object. It is unchanged for a reason worth
#: writing down: ``index.html`` names the chunks it preloads, this rebuild renamed both of
#: them (``index-DzVoV1YM.js`` → ``index-DJX27H0M.js``, ``index-C498vmEA.css`` →
#: ``index-DAuZRgAW.css``), and a Vite content hash is a fixed-width field — so the file's
#: **bytes** changed while its **length** did not.
#:
#: Its sibling therefore moved, and moved *downwards*: **WAS 2,123, IS 2,122** — one byte
#: SMALLER — measured 2026-08-15 from the central directory of
#: ``out/lambda/mainline-demo-api-arm64.zip`` ``sha256 7e49fd5e…aaed2738``
#: (``--console-transport live``, ``MAINLINE_BUILD_ID=3933b97``). **WHY A MEASUREMENT AND
#: NOT A FLOOR:** it is whatever DEFLATE emitted for 4,655 changed bytes; compressing
#: different bytes of the same length can produce a shorter stream, and a number that can
#: fall by one on a rename was never anybody's bound. It is also the smallest real
#: re-record in this file, which is exactly the kind of drift a declared constant exists to
#: make visible — nothing else in this repository would have noticed one byte.
INDEX_PATH: Final = "/index.html"
INDEX_IDENTITY_BYTES: Final = 4_655
INDEX_GZIP_BYTES: Final = 2_122

#: Sent verbatim by :meth:`_Emulator.request` when a case wants the header genuinely
#: absent. ``http.client`` volunteers ``Accept-Encoding: identity`` unless told not to, and
#: "absent" and "identity" are different events at the handler even though this origin
#: answers both the same way — one of the three cases ``app._accept_encoding`` is written
#: for, so it is exercised as itself.
_ABSENT: Final = object()

#: THE WHOLE SIBLING SET, which is the claim the cost model actually rests on.
#:
#: ``docs/deploy/lambda-bundle.md``, ``static_site``'s module docstring and the L3 row of
#: ``docs/deploy/COST-BOUND.md`` all publish these two numbers, and every one of them is a
#: statement about **57** objects rather than about the two this file names by hand. The
#: two named ones were chosen because they are the extremes — the object the ceiling
#: refuses in identity, and the object every judge fetches first — and proving negotiation
#: for the extremes is not proving it for the set. These constants are read out of the
#: built artefact's central directory by the sweep below.
#:
#: **57 is unchanged and 289,437 B is not.** The console emitted the same number of chunks
#: before and after — 57 identity objects, 57 siblings, no orphans — so the count held while
#: the total moved.
#:
#: **WAS 289,437 B; IS 295,731 B**, +6,294. **WHICH BUILD:**
#: ``out/lambda/mainline-demo-api-arm64.zip`` ``sha256 7e49fd5e…aaed2738``,
#: ``--console-transport live``, ``MAINLINE_BUILD_ID=3933b97``, summed 2026-08-15 from that
#: zip's central directory and equal to `test_response_contract._SIBLING_BYTES` for the same
#: tree. **WHY A MEASUREMENT:** it is the sum of 57 compressor outputs. 5,223 B of the +6,294
#: is the entry chunk's own sibling (124,177 → 129,400), measured directly; the remaining
#: 1,071 B is somewhere in the other 56 and **this worker does not attribute it
#: object-by-object, because the previous package is not in the tree to diff against** — the
#: only other zip in ``out/`` is the stale x86_64 one, which carries a console *two* rebuilds
#: back and would answer a different question. Saying which objects moved without that diff
#: would be inventing a cause. What is asserted below is the total, which was summed. Nobody
#: set it and nothing is permitted or refused by it — the object that *is* refused is refused
#: by the ceiling, which did not move.
#:
#: ``SIBLING_COUNT`` is a different kind of constant and is deliberately NOT re-measured: it
#: is asserted at 57 because a count that survives a rebuild while the total does not is the
#: normal shape of this pair, and a count that moved would mean an object stopped shipping or
#: stopped being compressed — a different conversation, and one this test should force rather
#: than absorb.
#:
#: The same sibling total is published outside this file — `docs/deploy/lambda-bundle.md` §4,
#: `static_site`'s module docstring, and the L3 row of `docs/deploy/COST-BOUND.md`. **The
#: artefact is authoritative and the documents are derived**, so the number enforced below is
#: the zip's. As of this measurement `docs/deploy/lambda-bundle.md` still carries
#: ``57 | 289 312`` at line 215, and the same figure inside its 114-entry arithmetic at line
#: 209 — the console *two* rebuilds back. That page is not this worker's file, so it is
#: reported to the lead rather than edited here.
SIBLING_COUNT: Final = 57
SIBLING_TOTAL_BYTES: Final = 295_731


# ── Loading the two things under test ───────────────────────────────────────────────


def _load_local_furl() -> Any:
    """Import ``scripts/deploy/local_furl.py`` by path. It is a script, not a package."""
    spec = importlib.util.spec_from_file_location("mainline_local_furl_under_test", LOCAL_FURL)
    if spec is None or spec.loader is None:  # pragma: no cover - a missing file is the skip
        pytest.skip(f"{LOCAL_FURL} is not importable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def local_furl() -> Any:
    if not LOCAL_FURL.is_file():  # pragma: no cover - defensive
        pytest.skip(f"{LOCAL_FURL} is missing")
    return _load_local_furl()


@pytest.fixture(scope="module")
def web_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Unpack ``web/`` out of the built artefact and check the four sizes this file names.

    Skips loudly when the artefact has not been built. That is the honest limit of this
    file and it is stated rather than worked around: ``out/`` is a build output, a clean
    checkout has none, and inventing a fixture tree here would mean asserting compression
    against bytes this test wrote — which agrees with itself by construction and proves
    nothing about what deploys.
    """
    if not ARTEFACT.is_file():
        pytest.skip(
            f"the deployment artefact {ARTEFACT} has not been built, so this file did NOT "
            "run in this session. Build it with scripts/deploy/build_lambda.{sh,ps1}; it is "
            "the only tree that carries the .gz siblings, and console/dist carries none."
        )
    root = tmp_path_factory.mktemp("furl-web") / "web"
    root.mkdir()
    with zipfile.ZipFile(ARTEFACT) as archive:
        members = [n for n in archive.namelist() if n.startswith("web/") and not n.endswith("/")]
        for name in members:
            target = root / Path(name).relative_to("web")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))

    # Addressed through ENTRY_PATH rather than through a second copy of the chunk name, and
    # sized through a helper that reports an ABSENT object as -1 rather than raising: a
    # hard-coded literal plus a bare `.stat()` is what turned a moved bundle into thirty
    # `FileNotFoundError`s in fixture setup, where one assertion naming the number that moved
    # would have said the same thing in one line. Still a hard failure — -1 can never equal a
    # declared size — but a failure that reads as "this constant is stale", which is what it
    # is. Softening it into a skip would be the shortcut this repository forbids.
    def size(relative: str) -> int:
        target = root / relative
        return target.stat().st_size if target.is_file() else -1

    entry_relative = ENTRY_PATH.lstrip("/")
    measured = {
        ENTRY_PATH: size(entry_relative),
        f"{ENTRY_PATH}.gz": size(f"{entry_relative}.gz"),
        INDEX_PATH: size("index.html"),
        f"{INDEX_PATH}.gz": size("index.html.gz"),
    }
    declared = {
        ENTRY_PATH: ENTRY_IDENTITY_BYTES,
        f"{ENTRY_PATH}.gz": ENTRY_GZIP_BYTES,
        INDEX_PATH: INDEX_IDENTITY_BYTES,
        f"{INDEX_PATH}.gz": INDEX_GZIP_BYTES,
    }
    assert measured == declared, (
        f"the built artefact no longer matches the sizes this file declares: {measured} "
        f"against {declared} (-1 means the declared object is not in the package at all, "
        "which is what a content-hashed chunk name looks like after a console rebuild). "
        "Re-measure the bundle from the zip's central directory and update the constants "
        "deliberately, naming the build — every byte count below is an assertion about what "
        "this origin costs, so a rebuild that moves them is a cost change and has to be read "
        "as one. Do not delete, skip or exempt this file to make the red go away."
    )
    return root


class _Emulator:
    """A running ``local_furl`` on a loopback port, plus the one request helper."""

    __slots__ = ("host", "port")

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def request(
        self, method: str, path: str, accept_encoding: Any = _ABSENT
    ) -> tuple[int, Mapping[str, str], bytes]:
        """One request on its own connection. Returns ``(status, headers, body_bytes)``.

        A fresh connection per call, deliberately: keep-alive is what the emulator is
        configured for and what a browser does, but a shared connection would let one
        case's framing error be diagnosed as the next case's wrong body. Each assertion
        below is about one exchange, so each gets one.

        ``skip_accept_encoding=True`` is always passed, because ``http.client`` otherwise
        volunteers ``Accept-Encoding: identity`` of its own accord and this file would then
        have no way to send *no* header at all.
        """
        conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
        try:
            conn.putrequest(method, path, skip_accept_encoding=True)
            conn.putheader("Host", f"{self.host}:{self.port}")
            if accept_encoding is not _ABSENT:
                conn.putheader("Accept-Encoding", str(accept_encoding))
            conn.endheaders()
            response = conn.getresponse()
            body = response.read()
            headers = {k.lower(): v for k, v in response.getheaders()}
            return response.status, headers, body
        finally:
            conn.close()


@pytest.fixture(scope="module")
def emulator(local_furl: Any, web_root: Path) -> Iterator[_Emulator]:
    """Start the real emulator against the real handler and the unpacked artefact tree.

    ``$MAINLINE_WEB_ROOT`` is set before the handler is imported and restored after, and
    ``$MAINLINE_MAX_RESPONSE_BYTES`` is removed so the cases below measure the ceiling a
    deploy that sets nothing enforces — which is the value the cost model quotes.
    """
    previous = {
        key: os.environ.get(key) for key in ("MAINLINE_WEB_ROOT", "MAINLINE_MAX_RESPONSE_BYTES")
    }
    os.environ["MAINLINE_WEB_ROOT"] = str(web_root)
    os.environ.pop("MAINLINE_MAX_RESPONSE_BYTES", None)

    entry, _ = local_furl.import_handler(local_furl.DEFAULT_APP_SRC)
    server = local_furl._Server(("127.0.0.1", 0), local_furl._make_request_handler())
    server.handler_entry = entry
    server.call_lock = threading.Lock()
    server.quiet = True
    host, port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.daemon = True
    thread.start()
    try:
        yield _Emulator(str(host), int(port))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(autouse=True)
def _admitting_limiter() -> Iterator[None]:
    """Both token buckets full around every case in this file.

    ``ratelimit`` holds its buckets at module scope — one execution environment, not one
    request — so without this an earlier case would spend the tokens a later one needs and
    a compression assertion would fail as a 429 for a reason that has nothing to do with
    compression. A refill, **not a bypass**: the limiter still runs on every request below.
    """
    from mainline_demo_api import ratelimit

    ratelimit.reset()
    yield
    ratelimit.reset()


# ── (a) The compressed answer, counted on the wire ──────────────────────────────────


def test_a_gzip_accepting_get_puts_the_sibling_bytes_and_only_those_on_the_wire(
    emulator: _Emulator, web_root: Path
) -> None:
    """**The proof this file exists for.** 129,400 bytes off a socket, not 172,536.

    Four claims in one exchange, and the last is the one no dict test can make:

    1. the sibling is what answers — ``content-encoding: gzip`` and 200, from a URL with no
       ``.gz`` in it;
    2. ``vary: accept-encoding`` is present, without which a shared cache replays the
       compressed answer to the next client that asked for identity — the classic gzip
       cache-poisoning bug, which breaks the page for exactly the clients least able to
       say so;
    3. the body is **exactly** the 129,400 wire bytes, so the base64 envelope was decoded
       and its 33 % never reached the socket; and
    4. those bytes inflate to the byte-for-byte 457,123 B original, so what was saved was
       transport and not content.

    **Both figures were re-measured 2026-08-15** — 124,177 → 129,400 on the wire and
    433,564 → 457,123 inflated — from ``out/lambda/mainline-demo-api-arm64.zip``
    ``sha256 7e49fd5e…aaed2738`` (``--console-transport live``,
    ``MAINLINE_BUILD_ID=3933b97``). They are what the compiler emitted and the compressor
    produced for this build, not thresholds: the claim being proved is the *equality of the
    socket and the sibling*, which is a property of the serving path and is indifferent to
    how large either number is.
    """
    status, headers, body = emulator.request("GET", ENTRY_PATH, accept_encoding="gzip")

    assert status == 200, f"the entry bundle answered {status} to a gzip-accepting GET"
    assert headers["content-encoding"] == "gzip"
    assert "accept-encoding" in headers["vary"].lower()
    assert headers["content-type"] == "text/javascript; charset=utf-8", (
        "the media type is the identity object's. A .js.gz is JavaScript that arrived "
        "compressed, not a new format, and a browser handed application/gzip for a module "
        "refuses to run it."
    )

    assert len(body) == ENTRY_GZIP_BYTES, (
        f"{len(body)} bytes came off the socket and the sibling is {ENTRY_GZIP_BYTES}. If "
        f"this is {ENTRY_ENVELOPE_CHARS}, the base64 envelope reached the client undecoded "
        "and every byte of it is billable egress that nobody meant to send."
    )
    assert int(headers["content-length"]) == ENTRY_GZIP_BYTES
    assert body[:2] == b"\x1f\x8b", "a gzip member starts 1f 8b; this body does not"
    assert gzip.decompress(body) == (web_root / ENTRY_PATH.lstrip("/")).read_bytes()
    assert len(gzip.decompress(body)) == ENTRY_IDENTITY_BYTES


def test_the_envelope_is_a_third_larger_than_the_wire_and_the_wire_is_what_arrives(
    emulator: _Emulator, local_furl: Any
) -> None:
    """The 33 % gap, measured on both sides of the boundary in one test.

    The handler's dict and the socket are asked for the same object and their answers are
    compared: the dict carries 172,536 base64 characters, the socket carries 129,400 bytes,
    and the ratio is 4/3 to the character. That ratio is the entire hazard interface **I2**
    names — a meter, a ceiling or an invoice computed on the left-hand number over-states
    this origin's egress by a third — and this is the assertion that says which of the two
    numbers is the one AWS bills.

    **THE ROUNDED RATIO DID NOT MOVE, AND IT WAS STILL RE-DERIVED RATHER THAN LEFT STANDING
    (2026-08-15).** It reads 1.3334 after a rebuild that moved every other figure in this
    file, and that is arithmetic rather than luck. Base64 packs three bytes into four
    characters and pads the remainder, so the encoded length is ``4·ceil(n/3)`` and the ratio
    is a function of ``n mod 3`` alone:

        n = 124,177 (previous)  n mod 3 = 1 → 2 pads → 165,572/124,177 = 1.33335481 → 1.3334
        n = 129,400 (this one)  n mod 3 = 1 → 2 pads → 172,536/129,400 = 1.33335394 → 1.3334

    Both sit in ``[4/3, 4/3 + 8/(3n)]``, which is what "a third larger" means exactly, and
    the upper end is *attained* when the remainder is 1 — which is why both of these bundles
    round up. The bound is asserted below **as a bound**, so the claim survives the next
    re-record without anybody having to decide what a decimal should say; the rounded value
    is kept beside it because it is the number a human reads, and it is written here with the
    division that produces it. A figure that happens to land on its old value is still a new
    measurement of a new build: 1.3334 here is ``172,536/129,400`` over
    ``out/lambda/mainline-demo-api-arm64.zip`` ``sha256 7e49fd5e…aaed2738``, not the
    surviving decimal of a bundle that no longer ships.

    **ONE ASSERTION CHANGED SHAPE ON 2026-08-15 AND IT IS NOT A NUMBER (reported to the
    lead).** The bound used to be evaluated in binary floating point. Because the upper end
    is *attained* whenever ``n mod 3 == 1``, and 129,400 is such an ``n``, the comparison
    reduced to whether ``172,536/129,400`` and ``4/3 + 8/(3·129,400)`` round to the same
    double — they do not, and the assertion failed by one unit in the last place against an
    envelope that is exactly ``4·ceil(n/3)`` characters. The previous bundle had the same
    remainder and happened to round the other way. The inequalities are now multiplied out
    and asserted over exact integers (``3·chars >= 4·n`` and ``3·chars <= 4·n + 8``), which
    is the same statement with the approximation removed: strictly no weaker, and no longer
    dependent on which of two thirds a CPU rounds up. This is the one edit in this file that
    is not a re-measurement, and it is recorded here rather than made quietly.
    """
    from mainline_demo_api import app

    event = {
        "version": "2.0",
        "rawPath": ENTRY_PATH,
        "headers": {"accept-encoding": "gzip"},
        "requestContext": {"stage": "$default", "http": {"method": "GET", "path": ENTRY_PATH}},
    }
    dict_response = app.handler(event)

    assert dict_response["statusCode"] == 200
    assert dict_response["isBase64Encoded"] is True, (
        "gzip bytes are not valid UTF-8. A Function URL body is a JSON string, so a "
        "compressed body that did not set isBase64Encoded would be mangled by the service "
        "before it ever reached a client."
    )
    envelope = str(dict_response["body"])
    assert len(envelope) == ENTRY_ENVELOPE_CHARS
    assert len(base64.b64decode(envelope, validate=True)) == ENTRY_GZIP_BYTES

    _, _, wire = emulator.request("GET", ENTRY_PATH, accept_encoding="gzip")
    assert len(wire) == ENTRY_GZIP_BYTES
    assert base64.b64decode(envelope, validate=True) == wire, (
        "the bytes on the socket are not the decoding of the bytes in the envelope"
    )

    inflation = len(envelope) / len(wire)
    # The bound first, because it is the claim: it holds for EVERY n and is what "a third
    # larger" means. `4·ceil(n/3) ≥ 4n/3` gives the left half; `4·ceil(n/3) ≤ (4n+8)/3`
    # gives the right. A rounded decimal cannot say this and a bound cannot drift.
    #
    # WRITTEN IN EXACT INTEGERS SINCE 2026-08-15, AND THAT IS A CORRECTION, NOT A RELAXATION.
    # These two inequalities were previously asserted as
    # `4/3 <= len(envelope)/len(wire) <= 4/3 + 8/(3n)` in binary floating point. At
    # n = 129,400 the right-hand bound is ATTAINED EXACTLY — n mod 3 == 1, so
    # 3 x 172,536 == 4 x 129,400 + 8 — and the comparison then came down to which way two
    # unrepresentable thirds happened to round. It failed by one unit in the last place
    # against a build that satisfies the claim perfectly. The previous bundle had the same
    # remainder and passed; that was luck, and luck is not a control. Multiplying the
    # denominators out asserts the IDENTICAL mathematical statement over exact integers, so
    # nothing that used to be refused is now accepted — the attained boundary is decided by
    # arithmetic instead of by rounding. The float form is what drifted; the bound is not.
    assert 3 * len(envelope) >= 4 * len(wire), (
        f"the envelope is shorter than 4·ceil(n/3) for n = {len(wire)}: {len(envelope)} "
        "characters, so it is not a base64 encoding of those bytes at all"
    )
    assert 3 * len(envelope) <= 4 * len(wire) + 8, (
        f"the envelope is longer than 4·ceil(n/3) for n = {len(wire)}: {len(envelope)} "
        "characters. Anything above this is padding nobody asked for, or a second encoding."
    )
    # Then the value a human reads, re-derived in the docstring above: 172,536/129,400.
    assert round(inflation, 4) == 1.3334, f"the envelope overhead moved: {inflation}"
    assert len(envelope) - len(wire) == ENTRY_ENVELOPE_PADDING, (
        f"{ENTRY_ENVELOPE_PADDING} characters of base64 padding that AWS strips and nobody "
        "is billed for. A ceiling or a metric applied to the envelope would count them."
    )
    # Declared and derived, side by side: the padding is a CONSEQUENCE of the two byte
    # counts, so a re-record that moved one and not the other is caught here rather than
    # becoming a third number nobody can reproduce.
    assert ENTRY_ENVELOPE_CHARS - ENTRY_GZIP_BYTES == ENTRY_ENVELOPE_PADDING
    assert ENTRY_ENVELOPE_CHARS == 4 * ((ENTRY_GZIP_BYTES + 2) // 3)

    # And the emulator's own `content-length` is the raw count, not the envelope's.
    assert local_furl.translate_response(dict_response).body == wire


# ── (b) The identity answer, and which of the two outcomes is true today ────────────


def test_an_identity_get_of_the_entry_bundle_is_refused_because_the_ceiling_binds(
    emulator: _Emulator,
) -> None:
    """**It is a 413, not the identity bytes, and this test says so out loud.**

    The brief this file was written to allows either outcome and requires the true one to
    be asserted and named. The true one is **413**, and it follows from arithmetic rather
    than from preference: the ceiling in force is 139,264 B (``136 KiB``) and the identity
    entry bundle is 457,123 B, so it is 3.28x over (``457,123 / 139,264 = 3.2824``). Every
    browser that will ever load this console sends ``Accept-Encoding: gzip`` and is served;
    a client that refuses compression while asking for a 457 KB bundle is exactly the caller
    a *wire* ceiling exists for, and ``curl`` without ``--compressed`` is the one that will
    meet it.

    **THE MULTIPLE MOVED BECAUSE THE NUMERATOR DID (2026-08-15).** It was 3.1133
    (``433,564 / 139,264``) and is 3.2824 (``457,123 / 139,264``), measured over
    ``out/lambda/mainline-demo-api-arm64.zip`` ``sha256 7e49fd5e…aaed2738``
    (``--console-transport live``, ``MAINLINE_BUILD_ID=3933b97``). **The denominator is
    unchanged and is not a measurement**: ruling **R10**
    (`docs/leads/reconcile-constants-plan.md` §1) keeps
    ``static_site.DEFAULT_MAX_RESPONSE_BYTES`` at 139,264 and demotes the derivation that
    first chose it to provenance, leaving interface **I3** and the straddle as the live law.
    Both still hold: ``129,400 <= 139,264 < 457,123``, and 139,264 < 1.20 x 129,400.

    The straddle is asserted before the status, so this stays a **ratchet**: if somebody
    raises the ceiling above 457,123 the first assertion fails naming the flood multiplier
    that came back, instead of the second one quietly starting to expect a 200.
    """
    from mainline_demo_api import static_site

    ceiling = static_site.max_response_bytes()
    assert ENTRY_GZIP_BYTES <= ceiling < ENTRY_IDENTITY_BYTES, (
        f"the ceiling is {ceiling}: it no longer straddles the entry bundle's two "
        f"representations ({ENTRY_GZIP_BYTES} compressed, {ENTRY_IDENTITY_BYTES} identity). "
        f"Above {ENTRY_IDENTITY_BYTES} the flood multiplier returns to the identity bundle "
        "and the compressed row of the cost model stops being a bound anybody has to "
        f"accept; below {ENTRY_GZIP_BYTES} the console cannot be served at all. Neither is "
        "a change to make here."
    )

    status, headers, body = emulator.request("GET", ENTRY_PATH, accept_encoding=_ABSENT)
    assert status == 413, f"an identity GET of the entry bundle answered {status}"
    assert headers["content-type"] == "application/json; charset=utf-8"
    assert "accept-encoding" in headers["vary"].lower(), (
        "the 413 is an answer a different Accept-Encoding would have changed — the same "
        "object is a 200 to a gzip request — so a cache that stored it without `vary` "
        "would replay the refusal to a browser that would have been served."
    )
    import json

    error = json.loads(body)["error"]
    assert error["kind"] == "response_too_large"
    assert error["bytes"] == ENTRY_IDENTITY_BYTES
    assert error["bytes_on_disk"] == ENTRY_IDENTITY_BYTES
    assert error["ceiling_bytes"] == ceiling
    assert "accept-encoding: gzip" in error["detail"].lower(), (
        "the refusal has to name the request header that turns it into a 200; otherwise it "
        "is a dead end rather than a redirection to the cheap path."
    )
    assert len(body) < 2000, "the refusal must not be a delivery mechanism for what it refused"


def test_an_identity_get_of_the_index_is_served_whole_so_the_ceiling_is_not_a_wall(
    emulator: _Emulator, web_root: Path
) -> None:
    """The other half of the previous test: identity still works for everything that fits.

    Without this, "identity is refused" would be indistinguishable from "identity is
    broken", and the 413 above would be evidence of a bug rather than of a bound.
    """
    status, headers, body = emulator.request("GET", INDEX_PATH, accept_encoding=_ABSENT)
    assert status == 200
    assert "content-encoding" not in headers
    assert len(body) == INDEX_IDENTITY_BYTES
    assert body == (web_root / "index.html").read_bytes()
    assert "accept-encoding" in headers["vary"].lower()


# ── (c) One set of bytes, one name ──────────────────────────────────────────────────


def test_the_sibling_has_no_url_of_its_own(emulator: _Emulator, web_root: Path) -> None:
    """``/assets/index-DJX27H0M.js.gz`` is a 404 **even though the file is right there**.

    That is the whole content of interface **I1**'s naming rule, and it is why this asserts
    the file exists first: a 404 from a path that happens to be missing would prove nothing.
    Two names for one object is two cache entries, two ``content-type`` answers, and a URL
    that hands a browser gzip bytes it was never told to inflate.

    The property is *"a ``.gz`` sibling has no URL of its own"*; the object it is proved
    against is whichever chunk this build emitted, and today that is
    ``assets/index-DJX27H0M.js`` (**was** ``assets/index-DzVoV1YM.js``, renamed by the
    2026-08-15 LIVE rebuild packed in
    ``out/lambda/mainline-demo-api-arm64.zip`` ``sha256 7e49fd5e…aaed2738``). The name is
    read from ``ENTRY_PATH`` rather than typed here, so this sentence is the only place in
    this test the measurement appears, and the assertion below cannot go stale independently
    of the constant.
    """
    assert (web_root / f"{ENTRY_PATH.lstrip('/')}.gz").is_file(), "the sibling is not staged"

    for accept in ("gzip", _ABSENT):
        status, headers, body = emulator.request("GET", f"{ENTRY_PATH}.gz", accept_encoding=accept)
        assert status == 404, f"{ENTRY_PATH}.gz answered {status} for accept-encoding={accept!r}"
        assert headers["content-type"] == "application/json; charset=utf-8"
        assert len(body) < 2000
        assert body[:2] != b"\x1f\x8b", "the .gz path handed out the compressed bytes"


# ── (d) The two ways a token match goes wrong ───────────────────────────────────────


@pytest.mark.parametrize(
    "accept_encoding",
    [
        "gzip;q=0",
        "gzip; q=0",
        "gzip;q=0.0",
        "deflate, gzip;q=0, br",
        "*;q=1.0, gzip;q=0",
    ],
    ids=["bare", "spaced", "decimal", "in-a-list", "against-a-wildcard"],
)
def test_a_q_of_zero_is_a_refusal_and_not_a_mention(
    emulator: _Emulator, web_root: Path, accept_encoding: str
) -> None:
    """``gzip;q=0`` says *I cannot read gzip*. A substring test hears *gzip* and ships it.

    ``index.html`` is used rather than the entry bundle because both of its representations
    are under the ceiling: the identity answer is a **200 carrying 4,655 bytes**, which is a
    positive proof that compression was declined, where the entry bundle could only produce
    a 413 and leave the reason ambiguous.

    The last case is the subtle one. ``*;q=1.0`` means "any coding is acceptable" and would
    permit gzip on its own; a specific ``gzip;q=0`` beside it still refuses, because an
    explicit preference wins over the wildcard.
    """
    status, headers, body = emulator.request("GET", INDEX_PATH, accept_encoding=accept_encoding)
    assert status == 200
    assert "content-encoding" not in headers, (
        f"{accept_encoding!r} refused gzip and this origin sent it anyway"
    )
    assert len(body) == INDEX_IDENTITY_BYTES
    assert body == (web_root / "index.html").read_bytes()
    assert body[:2] != b"\x1f\x8b"


@pytest.mark.parametrize(
    ("accept_encoding", "compressed"),
    [
        ("gzip", True),
        ("x-gzip", True),
        ("gzip, deflate, br", True),
        ("deflate, gzip", True),
        ("br;q=1.0, gzip;q=0.5", True),
        ("*", True),
        ("x-gzip-nope", False),
        ("notgzip", False),
        ("gzipper", False),
        ("deflate, br", False),
        ("identity", False),
        ("", False),
    ],
    ids=[
        "gzip",
        "x-gzip",
        "browser-shaped",
        "not-first",
        "lower-preference",
        "wildcard",
        "gzip-as-a-substring",
        "gzip-as-a-prefix-of-nothing",
        "gzip-as-a-word-stem",
        "no-gzip-offered",
        "identity",
        "empty",
    ],
)
def test_gzip_is_matched_as_a_token_and_never_as_a_substring(
    emulator: _Emulator, accept_encoding: str, compressed: bool
) -> None:
    """``x-gzip-nope`` contains ``gzip`` and is not ``gzip``. Twelve field values say so.

    The negatives are the point. ``"gzip" in header`` is the one-line version of this
    negotiation and it is wrong for three of the values below, each of which would hand
    compressed bytes to a client that never asked for them. The positives keep it from
    being satisfied by a function that always says no.
    """
    _, headers, body = emulator.request("GET", INDEX_PATH, accept_encoding=accept_encoding)
    if compressed:
        assert headers.get("content-encoding") == "gzip", f"{accept_encoding!r} was not served gzip"
        assert len(body) == INDEX_GZIP_BYTES
    else:
        assert "content-encoding" not in headers, f"{accept_encoding!r} was served gzip"
        assert len(body) == INDEX_IDENTITY_BYTES


def test_the_header_may_be_absent_entirely_and_that_is_not_an_error(emulator: _Emulator) -> None:
    """No ``Accept-Encoding`` at all — the third case ``app._accept_encoding`` handles.

    ``http.client`` volunteers ``identity`` unless it is told not to, so "absent" is easy to
    believe you have tested when you have tested "identity" instead. This one really sends
    no header: the event reaches the handler with ``accept-encoding`` missing from
    ``headers``, and the answer is the identity bytes rather than a ``KeyError``-shaped 502.
    """
    status, headers, body = emulator.request("GET", INDEX_PATH, accept_encoding=_ABSENT)
    assert status == 200
    assert "content-encoding" not in headers
    assert len(body) == INDEX_IDENTITY_BYTES


# ── (e) HEAD says what the GET would do, and carries nothing ────────────────────────


def test_head_carries_no_body_and_the_same_headers_as_the_get(emulator: _Emulator) -> None:
    """A ``HEAD`` that disagreed with its ``GET`` would be a lie told by the cheaper method.

    ``content-length`` is the number the matching ``GET`` would deliver — RFC 9110 §9.3.2 —
    so on the negotiated path it is the **sibling's** 129,400 and not the identity object's
    457,123, and the body is empty. The header sets are compared as sets rather than one by
    one so a header that appears on only one of the two methods fails here rather than in a
    browser's cache six months later.

    **Both figures were re-measured 2026-08-15** (124,177 → 129,400, 433,564 → 457,123) from
    ``out/lambda/mainline-demo-api-arm64.zip`` ``sha256 7e49fd5e…aaed2738``,
    ``--console-transport live``, ``MAINLINE_BUILD_ID=3933b97``. They are measurements of
    what this build emits, not limits: the claim under test is that ``HEAD`` and ``GET``
    agree, and it would be the same claim at any pair of sizes. They are quoted at all
    because a ``HEAD`` that announced the *identity* length on a negotiated response would
    be off by exactly this gap, and naming both numbers is what makes that failure legible.
    """
    get_status, get_headers, get_body = emulator.request("GET", ENTRY_PATH, accept_encoding="gzip")
    head_status, head_headers, head_body = emulator.request(
        "HEAD", ENTRY_PATH, accept_encoding="gzip"
    )

    assert get_status == head_status == 200
    assert head_body == b"", f"HEAD carried {len(head_body)} bytes"
    assert len(get_body) == ENTRY_GZIP_BYTES

    assert head_headers["content-length"] == str(ENTRY_GZIP_BYTES) == get_headers["content-length"]
    assert head_headers["content-encoding"] == "gzip"
    assert head_headers["content-type"] == get_headers["content-type"]
    assert "accept-encoding" in head_headers["vary"].lower()

    # `date` moves between the two exchanges; everything else must be identical.
    volatile = {"date"}
    assert set(head_headers) - volatile == set(get_headers) - volatile
    assert {k: v for k, v in head_headers.items() if k not in volatile} == {
        k: v for k, v in get_headers.items() if k not in volatile
    }


def test_head_is_refused_exactly_where_the_get_is(emulator: _Emulator) -> None:
    """The cheaper method must not answer 200 with a length the GET will never deliver.

    An identity ``HEAD`` of the entry bundle is the request a caller probing for that
    discrepancy sends, so it gets the same 413 the ``GET`` gets.
    """
    get_status, _, _ = emulator.request("GET", ENTRY_PATH, accept_encoding=_ABSENT)
    head_status, _, head_body = emulator.request("HEAD", ENTRY_PATH, accept_encoding=_ABSENT)
    assert get_status == head_status == 413
    assert head_body == b""


# ── (f) All 57 siblings, and not just the two this file names ───────────────────────


def _inventory(web_root: Path) -> list[tuple[str, int, int]]:
    """Every identity object in the staged tree, with its size and its sibling's size.

    Returns ``(relative_posix_path, identity_bytes, gz_bytes)`` sorted by path, with the
    ``.gz`` files themselves excluded — they are representations, not objects. Read from
    the tree unpacked out of the shipping artefact, so it is an inventory of what deploys.
    """
    files = [p for p in web_root.rglob("*") if p.is_file()]
    identity = sorted(p for p in files if p.suffix.lower() != ".gz")
    return [
        (
            p.relative_to(web_root).as_posix(),
            p.stat().st_size,
            sibling.stat().st_size if (sibling := p.with_name(p.name + ".gz")).is_file() else -1,
        )
        for p in identity
    ]


def test_the_shipped_set_is_57_siblings_of_295_731_bytes_with_no_orphan_and_no_gap(
    web_root: Path,
) -> None:
    """The published inventory, measured against the artefact that deploys.

    **THIS TEST WAS RENAMED ON 2026-08-15 AND THE RENAME IS PART OF THE RE-RECORD.** It read
    ``…_of_289_437_bytes_…`` immediately before this edit, and ``…_of_289_312_bytes_…`` at
    commit ``3933b97`` — the same number this file's constants have now moved twice, because
    both re-records were uncommitted when this one began. A test name that embeds a
    measurement is a claim like any other, and a name left standing after the measurement
    moved is a lie that ``-q`` output repeats on every run — so the name moves with the
    number rather than being left to rot. Nothing outside this file referenced any of the
    three names (checked by grep across the repository), so no required list, lane
    declaration or document lost a member; if one ever does, the name still moves and the
    reference is corrected with it, never the other way round.

    The sibling inventory is published in three places outside this file:
    ``docs/deploy/lambda-bundle.md`` §4, ``static_site``'s module docstring, and the L3 row
    of ``docs/deploy/COST-BOUND.md``. Until this control existed those were three copies of
    one unverified sentence.

    **WAS 289,437 B; IS 295,731 B**, +6,294, measured 2026-08-15 by summing the ``.gz``
    entries in the central directory of ``out/lambda/mainline-demo-api-arm64.zip``
    ``sha256 7e49fd5e1426a4d2aaba12a2cd7aa086c95430f0b5daa3645bc8b55eaaed2738``, packed
    ``--console-transport live`` with ``MAINLINE_BUILD_ID=3933b97``. **It is a measurement
    and not a floor**: it is the sum of what the compressor produced for the 57 objects this
    build emitted, and no request is permitted or refused by it — the one refusal in this
    package is made by the ceiling, which did NOT move (ruling R10). As of this measurement
    ``docs/deploy/lambda-bundle.md:209,215`` still carries ``57 | 289 312``, the console two
    rebuilds back; that page is not this worker's file and is reported to the lead rather
    than edited here. **The number this test enforces is the artefact's, not any
    document's.** Four properties, each of which breaks a different published claim if it
    moves:

    1. **57 identity objects**, so the count in the docs is the count in the zip — and this
       one is *asserted rather than re-measured*: it survived the rebuild, and a count that
       moved would mean an object stopped shipping or stopped being compressed;
    2. **every one of them has a ``.gz`` beside it** — one identity object without a
       sibling is one object served uncompressed to every browser, and the L3 saving is
       over-claimed by its identity size;
    3. **no orphan ``.gz``** — a sibling whose identity object was dropped is 100 % dead
       weight, since interface I1 gives it no URL of its own and nothing can ever reach it;
    4. **295,731 B of siblings in total**, the number this package actually carries.

    A rebuild that legitimately changes the console moves these numbers. That is a cost
    change and has to be read as one: re-measure, then move the constants here **and** the
    sentence in ``docs/deploy/lambda-bundle.md`` together, in the same commit.
    """
    inventory = _inventory(web_root)
    gz_files = sorted(p for p in web_root.rglob("*") if p.is_file() and p.suffix.lower() == ".gz")

    assert len(inventory) == SIBLING_COUNT, (
        f"{len(inventory)} identity objects ship, and every document that quotes this "
        f"bundle says {SIBLING_COUNT}"
    )
    without = [name for name, _, gz in inventory if gz < 0]
    assert without == [], (
        f"{len(without)} shipped objects have no .gz sibling and are therefore served "
        f"uncompressed to every browser: {without[:8]}"
    )
    identity_names = {name for name, _, _ in inventory}
    orphans = [
        p.relative_to(web_root).as_posix()
        for p in gz_files
        if p.relative_to(web_root).as_posix()[: -len(".gz")] not in identity_names
    ]
    assert orphans == [], (
        f"{orphans} are .gz files with no identity object. Interface I1 gives a .gz no URL "
        "of its own, so an orphan can never be reached by any request and is dead weight in "
        "the package — the one case where 'stop shipping them' would be the right answer."
    )
    assert len(gz_files) == SIBLING_COUNT
    total = sum(gz for _, _, gz in inventory)
    assert total == SIBLING_TOTAL_BYTES, (
        f"the siblings total {total} B and the published figure is {SIBLING_TOTAL_BYTES} B"
    )


def test_every_one_of_the_57_siblings_reaches_the_wire_and_none_of_them_has_a_url(
    emulator: _Emulator, web_root: Path
) -> None:
    """**The control that discharges the claim.** All 57, over the socket, both directions.

    The rest of this file proves negotiation for two objects. The sentence the cost model
    and the bundle page publish is about the whole set — *the siblings are what every real
    browser receives* — and a set proved at its two extremes is a set with 55 untested
    members. Three exchanges per object, 171 in all:

    * ``Accept-Encoding: gzip`` on the **identity** URL answers 200 with
      ``content-encoding: gzip``, ``vary: accept-encoding`` and the sibling's bytes exactly;
      the body is a real gzip member that inflates to the identity object byte for byte, so
      what was saved is transport and not content;
    * the **media type is the identity object's**, asserted against the identity response
      for the same path rather than against this module's own table — a ``.js.gz`` served
      as ``application/gzip`` is a module a browser refuses to run;
    * ``<path>.gz`` is a **404** for all 57, so the sibling never acquires a second name, a
      second cache entry or a way to hand a browser gzip it was never told to inflate.

    The ceiling is consulted rather than assumed: an object whose identity representation
    is over it answers 413 to the identity request, which is a bound and not a defect, and
    the media-type comparison is made against the gzip answer alone in that case. Today
    exactly one object is in that state and the assertion below names how many, so a
    rebuild that pushes a second object over the ceiling fails here rather than passing
    quietly with one fewer comparison.

    The limiter is refilled between exchanges via its documented harness seam, and it still
    runs on every one of the 171: the per-IP bucket is 50 tokens and this file's own
    ``_admitting_limiter`` fixture only refills between *cases*, so without this the sweep
    would fail as a 429 for a reason that has nothing to do with compression. Nothing here
    disables it — ``ratelimit.reset()`` refills, it does not bypass.
    """
    from mainline_demo_api import ratelimit, static_site

    ceiling = static_site.max_response_bytes()
    inventory = _inventory(web_root)
    assert len(inventory) == SIBLING_COUNT

    served: list[str] = []
    refused_identity: list[str] = []
    for relative, identity_bytes, gz_bytes in inventory:
        url = f"/{relative}"
        assert gz_bytes >= 0, f"{relative} has no sibling; see the inventory control"

        ratelimit.reset()
        status, headers, body = emulator.request("GET", url, accept_encoding="gzip")
        assert status == 200, f"a gzip-accepting GET of {url} answered {status}"
        assert headers.get("content-encoding") == "gzip", (
            f"{url} was served without content-encoding: gzip, so its sibling is dead weight"
        )
        assert "accept-encoding" in headers.get("vary", "").lower(), (
            f"{url} answered a negotiated 200 without vary: accept-encoding, which is the "
            "cache-poisoning bug — a shared cache replays these gzip bytes to the next "
            "client that asked for identity"
        )
        assert len(body) == gz_bytes, (
            f"{url} put {len(body)} bytes on the wire and its sibling is {gz_bytes}"
        )
        assert int(headers["content-length"]) == gz_bytes
        assert body[:2] == b"\x1f\x8b", f"{url} claimed gzip and did not send a gzip member"
        assert gzip.decompress(body) == (web_root / relative).read_bytes(), (
            f"{url}'s sibling does not inflate to the object it stands for"
        )
        gzip_media_type = headers["content-type"]
        assert "gzip" not in gzip_media_type, (
            f"{url} was served as {gzip_media_type}. The media type belongs to the identity "
            "object: a compressed representation is not a new format."
        )
        served.append(relative)

        # The identity answer for the same URL, which is where the media type is pinned.
        ratelimit.reset()
        id_status, id_headers, id_body = emulator.request("GET", url, accept_encoding=_ABSENT)
        if identity_bytes > ceiling:
            assert id_status == 413, (
                f"{url} is {identity_bytes} B against a {ceiling} B ceiling and answered "
                f"{id_status} to an identity request"
            )
            refused_identity.append(relative)
        else:
            assert id_status == 200, f"an identity GET of {url} answered {id_status}"
            assert "content-encoding" not in id_headers
            assert len(id_body) == identity_bytes
            assert id_headers["content-type"] == gzip_media_type, (
                f"{url} answers {id_headers['content-type']} to identity and "
                f"{gzip_media_type} to gzip. One object, one media type."
            )

        # And the sibling still has no name of its own — for every one of the 57.
        ratelimit.reset()
        gz_status, gz_headers, gz_body = emulator.request(
            "GET", f"{url}.gz", accept_encoding="gzip"
        )
        assert gz_status == 404, f"{url}.gz answered {gz_status}; the sibling acquired a URL"
        assert gz_headers["content-type"] == "application/json; charset=utf-8"
        assert gz_body[:2] != b"\x1f\x8b", f"{url}.gz handed out the compressed bytes"

    assert len(served) == SIBLING_COUNT
    assert len(refused_identity) == 1 and refused_identity == [ENTRY_PATH.lstrip("/")], (
        f"{len(refused_identity)} objects are over the {ceiling} B ceiling in identity "
        f"({refused_identity}); one is expected, the entry bundle. Every gzip "
        "representation is under it, which is what makes all 57 siblings reachable — if a "
        "sibling ever goes over, that object stops being servable at all and the L3 row of "
        "the cost model is no longer a bound anybody can rely on."
    )


# ── The emulator's own half of the boundary ─────────────────────────────────────────


def test_the_emulator_decodes_the_envelope_rather_than_writing_it_to_the_socket(
    local_furl: Any,
) -> None:
    """``translate_response`` is the AWS-side half, and this is the unit statement of it.

    Asserted directly as well as end-to-end because the socket cases above would also pass
    if the *handler* stopped setting ``isBase64Encoded`` and started sending raw text; this
    one pins which side of the boundary does the decoding. Both are needed and neither is
    sufficient.
    """
    raw = gzip.compress(b"the console entry bundle, in miniature" * 64, mtime=0)
    response = {
        "statusCode": 200,
        "headers": {"content-encoding": "gzip", "content-length": str(len(raw))},
        "body": base64.b64encode(raw).decode("ascii"),
        "isBase64Encoded": True,
    }
    translated = local_furl.translate_response(response)

    assert translated.status == 200
    assert translated.body == raw
    assert len(translated.body) == len(raw) < len(str(response["body"]))
    assert gzip.decompress(translated.body).endswith(b"in miniature")


def test_a_body_that_claims_base64_and_is_not_becomes_a_502_rather_than_a_short_asset(
    local_furl: Any,
) -> None:
    """The failure mode this boundary has: a truncated asset that still says 200.

    Named here because it is the one thing the socket tests cannot show — they only ever
    see well-formed envelopes. A body that lies about its encoding must fail loudly.
    """
    translated = local_furl.translate_response(
        {"statusCode": 200, "body": "not base64 at all!!", "isBase64Encoded": True}
    )
    assert translated.status == 502
    assert translated.warnings
    assert b"emulator_bad_body" in translated.body


def test_the_emulator_binds_a_real_socket_and_this_file_used_one(emulator: _Emulator) -> None:
    """Anti-vacuity: every assertion above went over TCP, and here is the proof.

    A file that quietly fell back to calling ``app.handler`` in-process would pass every
    byte count above and prove none of them, because the envelope would never be
    translated. This connects to the port by hand.
    """
    with socket.create_connection((emulator.host, emulator.port), timeout=5) as probe:
        assert probe.getpeername()[1] == emulator.port
    assert emulator.port != 0
