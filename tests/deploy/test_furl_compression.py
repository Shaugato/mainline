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
  modelled at ``g = 124,127`` B, a console several rebuilds back; the package described below
  puts **137,939** B on the wire. Re-pricing the row is the cost pages' work and belongs to
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
``console/dist`` carries source maps and **zero** ``.gz`` siblings, while the artefact
carries zero maps and one sibling per object. A compression test run against the input tree
would find nothing to negotiate and pass by having nothing to do. The zip's own manifest
names the same split: the tree as the console build left it, the tree once the source maps
are gone, and the tree once every compressible object has its pair. **Every count in this
file is read from the last of those three** — at build ``5302005``, 77 objects and 154
``web/`` entries.

WHICH BUILD THESE NUMBERS DESCRIBE, AND WHY A REBUILD NO LONGER MAKES THEM RED
-------------------------------------------------------------------------------
**Until 2026-08-16 every size below was a literal typed in from one build, and the entry
chunk's NAME was one of them.** ``verticals/mainline/apps/console/vite.config.ts`` inlines
``__MAINLINE_BUILD_ID__``, so the git short SHA reaches the emitted JavaScript — and a Vite
chunk name IS a content hash. The entry chunk therefore renames itself on every commit,
including a commit that changes nothing else about the console. Each time it did,
``ENTRY_PATH`` named an object that was no longer in the package, the ``web_root`` fixture
reported it at ``-1`` — this file's own word for *not in the package at all* — and **every
one of the thirty-odd cases here errored in fixture setup**. That happened three times in
two days, and three times the repair was to type the new hash in. The third repetition is
the signal to repair the cause instead of the instance.

**THE REPAIR.** :func:`_resolve_artefact` reads the zip's central directory and finds the
entry chunk **by pattern** — the unique ``assets/index-*.js``, required also to be the
largest identity object in the tree — and every constant below is derived from what it
resolves. The measurements of build ``5302005`` are recorded as dated PROVENANCE beside
them, so a reader still learns what this origin cost on 2026-08-16 without a rebuild
turning that record into a red suite.

**WHAT STILL GOES RED, WHICH IS EVERYTHING THIS FILE EXISTS FOR.** Resolving a name does
not resolve a property, and nothing here is a comparison of the archive with itself:

* every byte count below is checked against **bytes that came off a TCP socket**, through
  ``local_furl`` and the real handler. The archive says how large the sibling is; the
  socket says what a client received. Those are two measurements, and the whole point of
  the emulator is that they can disagree — that is exactly what a base64 envelope reaching
  the wire undecoded would look like;
* **the straddle** ``ENTRY_GZIP_BYTES <= ceiling < ENTRY_IDENTITY_BYTES`` is a statement
  about a bound and two representations, false for any ceiling that refuses everything or
  nothing;
* **exactly one identity refusal** across the whole sibling sweep;
* **one ``.gz`` per object, no orphan, no gap**, and every one of them reachable only by
  negotiation;
* **the envelope identity** ``4·ceil(n/3)``, asserted against the handler's actual output.

WHAT THE ARTEFACT MEASURED, 2026-08-16 · BUILD ``5302005``
-----------------------------------------------------------
Read from the central directory of ``out/lambda/mainline-demo-api-arm64.zip``,
``sha256 e97981a494f432f4db55dd175881d9551610fdd637bbfe63475258041102bf4d``, 291 archive
entries, packed from HEAD ``5302005`` ``--console-transport live``::

    web/ entries        154        1,884,886 B
      identity           77        1,457,534 B
      .gz siblings       77          427,352 B      one per object, no orphan
      source maps         0                0 B
    entry chunk       assets/index-HZTFrKeL.js
      identity                       490,373 B      413 to a client refusing gzip
      gzipped                        137,939 B      what every browser receives
    index.html                         4,749 B      gzipped 2,152 B
    headroom                           1,325 B      139,264 - 137,939, 0.95 %

**WHAT MOVED AGAINST THE PACKAGE BEFORE IT** (``sha256 7c97b532…``, ``MAINLINE_BUILD_ID=
f0ba767``): the console gained the operator screens and the memory panel —
``operator-D24tzVGh.js.gz`` 29,906 B, ``operator.html.gz`` 2,221 B, ``memory.html.gz``
7,990 B, ``memory-loop.js.gz`` 16,023 B, ``memory-verify.js.gz`` 8,809 B — so the sibling
set went 69 → 77 and 347,013 → 427,352 B. The entry chunk went 490,950 → 490,373 identity
and 138,177 → **137,939** gzipped: it got 238 B SMALLER on the wire while the site got
359,896 B bigger, because the operator screens are a second HTML entry and are not in the
console's entry closure at all. Nobody made that margin; different bytes compressed
differently, and a margin that improves by accident can worsen by accident on the next
commit.

**``index.html`` STOPPED BEING THIS FILE'S FIXED POINT AT THIS BUILD.** It held 4,655 B
across three consecutive packages, which is what let the negotiation cases be read as being
about negotiation rather than about a moving object; at ``5302005`` it is 4,749 B, because
the shell now names a second HTML entry as well as its own two chunks. Its sibling went
2,122 → 2,120 → 2,152. Both are resolved from the artefact now, so neither is a literal
anybody has to notice.

**THAT ZIP IS THE SUBJECT OF EVERY NUMBER BELOW, AND IT IS NOT NECESSARILY WHAT THE FUNCTION
URL SERVES.** The last reading of the wire — ``evidence/deploy/judge-walk.json``, produced
by opening a socket rather than by anybody typing — records the deployed origin referencing
an older console. Nothing here claims otherwise: this file unpacks the zip at the path above
and serves it through the real emulator, so its assertions are statements about **that
artefact**, and the deployment catches up when the orchestrator deploys it. Naming the
artefact by digest and dating the measurement — instead of welding a content hash into a
sentence about "the origin" — is the wording rule of
`docs/leads/reconcile-constants-plan.md` §3, which was written after exactly this confusion.

**WHAT DID NOT MOVE: THE CEILING.** ``static_site.DEFAULT_MAX_RESPONSE_BYTES`` is still
139,264 B (``136 * 1024``); ``git diff`` on that module shows no change to it. Ruling **R10**
(`docs/leads/reconcile-constants-plan.md` §1) keeps it there and demotes the derivation
``ceil(floor(1.10·g)/8192)·8192`` to a dated record of how 139,264 was *chosen* in the first
place. The live law is interface **I3** plus the straddle plus exactly-one-refusal, and all
three are measured true over the package above: ``0 < 137,939 < 139,264 < 490,373``, with
exactly one identity object of the 77 refused.

**WHAT THE MARGIN COSTS, AND IT IS THE ONE PARAGRAPH HERE WORTH READING TWICE: 1,325 gzipped
bytes of headroom remain** (139,264 - 137,939), which is **0.95 %**. It was 15,087, then
9,864, then 1,087. When it reaches zero this origin answers **413 for ``ENTRY_PATH`` to every
browser on earth**: ``GET /`` still returns 200 and the shell, the shell asks for its one
module, receives a JSON problem document, and the judge is looking at a **blank page**. That
is a total outage of the demo URL — not a slow demo, no demo — with the origin reporting
itself healthy throughout, because the only request that fails is the one no human types.
The remedy is a smaller or split entry chunk. Raising the ceiling is refused by R10 and would
be the third time that constant was loosened to fit the tree it is supposed to bound.
``test_static_site._MINIMUM_HEADROOM_BYTES`` goes red at 1,024 B so the warning arrives in CI
instead of on the wire.

**AND THE OLD PREDICTION, WITHDRAWN.** The previous re-record said in as many words that
when the next package landed *"this file is expected to go red again and be re-recorded
again"*. It did, and it was — and that sentence is the defect, not the forecast. It is no
longer true of a build-id-only re-release: :func:`_resolve_artefact` refuses to return an
entry chunk unless the pattern matches exactly one object AND that object is the largest in
the tree, so a rename is invisible here and a genuine change of shape is not. **A rebuild
that moves an identity size, breaks the pairing, or puts a second object over the ceiling
still turns this file red, and that is the state in which it should be read rather than
routed around.**

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
from typing import Any, Final, NamedTuple

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
LOCAL_FURL: Final = REPO_ROOT / "scripts" / "deploy" / "local_furl.py"
ARTEFACT: Final = REPO_ROOT / "out" / "lambda" / "mainline-demo-api-arm64.zip"

# ── The artefact, resolved rather than named ────────────────────────────────────────
#
# **THE ONE RULE THIS BLOCK EXISTS TO KEEP.** A PROPERTY is asserted; a MEASUREMENT is
# recorded. The entry chunk's filename, its two byte counts, `index.html`'s two byte counts
# and the sibling set's count and total are all measurements — they move whenever the console
# legitimately changes, and a build must not fail because one of them did. The straddle, the
# exactly-one refusal, the pairing, the envelope identity and every byte count checked
# against a socket are properties, and they stay asserted.

#: How the entry chunk is FOUND rather than named. Vite emits the console's entry as
#: `assets/index-<content hash>.js` and emits exactly one of them; the operator and memory
#: screens are separate HTML entries under their own stems, and every lazy route is a
#: `surface-`/`worker-` chunk.
_ENTRY_CHUNK_PREFIX: Final = "assets/index-"
_ENTRY_CHUNK_SUFFIX: Final = ".js"
_GZ: Final = ".gz"

#: DATED PROVENANCE · build `5302005`, read 2026-08-16 from the central directory of
#: `out/lambda/mainline-demo-api-arm64.zip`
#: `sha256 e97981a494f432f4db55dd175881d9551610fdd637bbfe63475258041102bf4d`.
#:
#: **These are the fallback this module imports with when `out/lambda/` is empty**, so that a
#: clean checkout still gets a module that imports and a `web_root` fixture that skips with a
#: sentence rather than an `AttributeError`. When the artefact IS present every one of them
#: is replaced by what the archive holds, and nothing compares the two: a rebuild is expected
#: to move them, that is what a rebuild is, and the file docstring records what they were.
#:
#: The history, so the SHAPE of the movement stays legible:
#:
#:     build      entry identity   entry gzip   index    index gz   siblings   sibling B
#:     ────────   ──────────────   ──────────   ──────   ────────   ────────   ─────────
#:     b822fdc         457,123       129,400     4,655      2,122      57       295,724
#:     f0ba767         490,950       138,177     4,655      2,120      69       347,013
#:     5302005         490,373       137,939     4,749      2,152      77       427,352
_PROVENANCE_BUILD_ID: Final = "5302005"
_PROVENANCE_SHA256: Final = "e97981a494f432f4db55dd175881d9551610fdd637bbfe63475258041102bf4d"
_PROVENANCE_ENTRY_PATH: Final = "/assets/index-HZTFrKeL.js"
_PROVENANCE_ENTRY_IDENTITY_BYTES: Final = 490_373
_PROVENANCE_ENTRY_GZIP_BYTES: Final = 137_939
_PROVENANCE_INDEX_IDENTITY_BYTES: Final = 4_749
_PROVENANCE_INDEX_GZIP_BYTES: Final = 2_152
_PROVENANCE_SIBLING_COUNT: Final = 77
_PROVENANCE_SIBLING_TOTAL_BYTES: Final = 427_352


class _Artefact(NamedTuple):
    """What one reading of the package's ``web/`` central directory says about it."""

    entry_path: str
    entry_identity_bytes: int
    entry_gzip_bytes: int
    index_identity_bytes: int
    index_gzip_bytes: int
    sibling_count: int
    sibling_total_bytes: int
    resolved: bool


def _resolve_artefact() -> _Artefact:
    """Read the built package and resolve the objects this file addresses **by pattern**.

    Central directory only — no unpacking — so this costs microseconds at import and cannot
    be perturbed by anything a test does to the filesystem later.

    Two assertions guard the resolution, and each is a property worth hearing about:

    * exactly one object matches ``assets/index-*.js``. Two would mean the console emitted a
      second top-level entry under the same stem, and which of them a browser loads first is
      then a question nobody has answered;
    * that object is the LARGEST identity object in the tree. If it ever is not, the biggest
      thing this origin holds is something nobody reasoned about, and the ceiling's one
      refusal — asserted below over the socket — is about a different file than the entry.

    They are ``AssertionError`` at import time on purpose. A resolver that fell back to a
    literal when it could not find its subject would be the softening this file's own
    docstring forbids: the failure has to read as *the package changed shape*, loudly, in the
    place that can say what changed.

    With no package at all this returns the dated provenance record and ``resolved=False``.
    That is not a fallback that hides anything — every fixture that needs the tree skips with
    a sentence naming the builder to run — it exists so the cases that need no tree
    (``translate_response``'s two unit statements) still collect and run on a clean checkout.
    """
    if not ARTEFACT.is_file():
        return _Artefact(
            entry_path=_PROVENANCE_ENTRY_PATH,
            entry_identity_bytes=_PROVENANCE_ENTRY_IDENTITY_BYTES,
            entry_gzip_bytes=_PROVENANCE_ENTRY_GZIP_BYTES,
            index_identity_bytes=_PROVENANCE_INDEX_IDENTITY_BYTES,
            index_gzip_bytes=_PROVENANCE_INDEX_GZIP_BYTES,
            sibling_count=_PROVENANCE_SIBLING_COUNT,
            sibling_total_bytes=_PROVENANCE_SIBLING_TOTAL_BYTES,
            resolved=False,
        )

    with zipfile.ZipFile(ARTEFACT) as archive:
        web = {
            info.filename[len("web/") :]: info.file_size
            for info in archive.infolist()
            if info.filename.startswith("web/") and not info.is_dir()
        }
    identity = {name: size for name, size in web.items() if not name.lower().endswith(_GZ)}
    siblings = {name: size for name, size in web.items() if name.lower().endswith(_GZ)}

    matches = sorted(
        name
        for name in identity
        if name.startswith(_ENTRY_CHUNK_PREFIX) and name.endswith(_ENTRY_CHUNK_SUFFIX)
    )
    assert len(matches) == 1, (
        f"{len(matches)} objects in {ARTEFACT} match "
        f"{_ENTRY_CHUNK_PREFIX}*{_ENTRY_CHUNK_SUFFIX}: {matches}. The console emits exactly "
        "one entry chunk under that stem; a second one means a second top-level entry "
        "landed and nobody has decided which of them this file is about."
    )
    entry = matches[0]
    largest = max(identity.items(), key=lambda item: item[1])[0]
    assert entry == largest, (
        f"the entry chunk in {ARTEFACT} is {entry} but the largest identity object is "
        f"{largest} at {identity[largest]} B. The one object this origin refuses on the "
        "identity path is supposed to BE the console's entry chunk; if something else is "
        "now the biggest thing in the tree, that object is what would be 413'd and nobody "
        "decided to stop serving it."
    )
    assert entry + _GZ in siblings, f"{entry} ships without a .gz sibling"

    return _Artefact(
        entry_path="/" + entry,
        entry_identity_bytes=identity[entry],
        entry_gzip_bytes=siblings[entry + _GZ],
        index_identity_bytes=identity["index.html"],
        index_gzip_bytes=siblings["index.html" + _GZ],
        sibling_count=len(siblings),
        sibling_total_bytes=sum(siblings.values()),
        resolved=True,
    )


_TREE: Final = _resolve_artefact()

#: The entry bundle: the object that dominates this origin's egress and the one the whole
#: cost argument turns on. **Resolved from the archive, not typed** — see the file docstring
#: for the three red suites that produced that decision.
#:
#: The bound in this file is the **straddle** — ``ENTRY_GZIP_BYTES <= ceiling <
#: ENTRY_IDENTITY_BYTES`` — and it is unchanged in form across every build this repository
#: has packed. What these two numbers carry is a COST: they are what this origin puts on the
#: wire, so a rebuild that moves them is a cost change and is read as one, which is why the
#: staged tree is re-checked against them before a single request is sent.
#:
#: **WHICH OF THE TWO MOVES ON A RE-RELEASE.** ``vite.config.ts`` inlines
#: ``__MAINLINE_BUILD_ID__``, so a build-id-only re-release moves ``ENTRY_PATH`` and nudges
#: ``ENTRY_GZIP_BYTES`` by a handful of bytes while leaving ``ENTRY_IDENTITY_BYTES`` exactly
#: where it was. Neither of those now fails anything here. What still fails is a change of
#: SHAPE: two entry chunks, an entry chunk that is not the largest object, a missing sibling,
#: a second object over the ceiling, or a margin under 1,024 B.
#:
#: At build ``5302005``: ``/assets/index-HZTFrKeL.js``, **490,373** B identity / **137,939** B
#: gzipped, sitting **1,325 B — 0.95 %** under the ceiling. Read
#: ``test_an_identity_get_of_the_entry_bundle_is_refused_because_the_ceiling_binds`` for what
#: happens when it crosses; the short version is that this origin starts answering 413 for
#: the console's own JavaScript and a judge gets a blank page.
ENTRY_PATH: Final = _TREE.entry_path
ENTRY_IDENTITY_BYTES: Final = _TREE.entry_identity_bytes
ENTRY_GZIP_BYTES: Final = _TREE.entry_gzip_bytes

#: What the same gzipped bytes cost *inside the envelope*. ``base64`` packs 3 bytes into 4
#: characters and pads the remainder, so this is ``4·ceil(n/3)`` and nothing else — **written
#: as that arithmetic rather than as a number**, which is the change of 2026-08-16 and is
#: what makes ``len(envelope) == ENTRY_ENVELOPE_CHARS`` in
#: ``test_the_envelope_is_a_third_larger_than_the_wire_and_the_wire_is_what_arrives`` a
#: statement about the HANDLER's output rather than a statement about this line.
#:
#: **THE PADDING CLASS IS A PROPERTY OF ``n mod 3`` AND OF NOTHING THIS REPOSITORY CHOOSES.**
#: At ``n = 129,400`` the remainder was 1 and the envelope carried two ``=``; at
#: ``n = 138,177`` it was 0 and there were none; at ``n = 137,939`` it is 2 and there is one.
#: The rounded inflation ratio therefore reads 1.3334, then 1.3333, then 1.3333 — a reader
#: who expected a constant of nature was reading a property of one remainder. The claim
#: asserted below is the exact integer pair ``3·chars >= 4·n`` and ``3·chars <= 4·n + 8``,
#: whose two ends are attained at remainder 0 and remainder 1 respectively.
#:
#: **This is the number that must never reach a meter, a ceiling or a bill**, and the whole
#: point of the socket is that it is not the number that reaches the client. At build
#: ``5302005``: 183,920 characters for 137,939 bytes, 45,981 of them overhead AWS strips.
ENTRY_ENVELOPE_CHARS: Final = 4 * ((ENTRY_GZIP_BYTES + 2) // 3)
ENTRY_ENVELOPE_PADDING: Final = ENTRY_ENVELOPE_CHARS - ENTRY_GZIP_BYTES

#: ``index.html`` is the second object every judge fetches and, unlike the entry bundle,
#: **both** of its representations are under the ceiling. That makes it the only place a
#: refusal of compression can be proved as a 200-with-identity-bytes rather than inferred
#: from a 413, which is why the ``q=0`` and token-matching cases below use it.
#:
#: **IT WAS THIS FILE'S ONE FIXED POINT AND IT STOPPED BEING ONE AT BUILD `5302005`.** The
#: identity size held 4,655 B across three consecutive packages — ``index.html`` names the
#: chunks it preloads, a Vite content hash is a fixed-width field, and every new screen was
#: lazily routed, so the file's BYTES changed while its LENGTH did not. At `5302005` the
#: shell also names a second HTML entry and it is 4,749 B. Its sibling went 2,122 → 2,120 →
#: 2,152: whatever DEFLATE emitted for those bytes, which was never anybody's bound.
#: Resolved from the artefact now, so neither is a literal anybody has to notice again.
INDEX_PATH: Final = "/index.html"
INDEX_IDENTITY_BYTES: Final = _TREE.index_identity_bytes
INDEX_GZIP_BYTES: Final = _TREE.index_gzip_bytes

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
#: statement about the whole set rather than about the two objects this file names. The two
#: named ones were chosen because they are the extremes — the object the ceiling refuses in
#: identity, and the object every judge fetches first — and proving negotiation for the
#: extremes is not proving it for the set.
#:
#: **Resolved from the artefact's central directory** (2026-08-16), where they were typed in
#: before. 57 → 69 → **77** objects and 295,724 → 347,013 → **427,352 B**: the count moving
#: is the louder of the two, because it means the SHAPE of the site changed and not merely
#: its size. What the sweep below asserts is not these totals but the four properties they
#: summarise — one sibling per object, no orphan, no gap, and every one of them reaching the
#: wire — and each of those is checked against 231 real exchanges rather than against a sum.
#:
#: **COUNT THEM IN THE ARCHIVE.** The zip manifest describes the tree BEFORE the source-map
#: strip and BEFORE a `.gz` was written beside every compressible object. Only the tree these
#: constants are read from is one a request can reach.
SIBLING_COUNT: Final = _TREE.sibling_count
SIBLING_TOTAL_BYTES: Final = _TREE.sibling_total_bytes


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
    """**The proof this file exists for.** The sibling's bytes off a socket, not the envelope's.

    Four claims in one exchange, and the last is the one no dict test can make:

    1. the sibling is what answers — ``content-encoding: gzip`` and 200, from a URL with no
       ``.gz`` in it;
    2. ``vary: accept-encoding`` is present, without which a shared cache replays the
       compressed answer to the next client that asked for identity — the classic gzip
       cache-poisoning bug, which breaks the page for exactly the clients least able to
       say so;
    3. the body is **exactly** the wire bytes the archive records for the sibling, so the
       base64 envelope was decoded and its 33 % never reached the socket; and
    4. those bytes inflate to the byte-for-byte identity original, so what was saved was
       transport and not content.

    At build ``5302005``: 137,939 bytes off the socket rather than 183,920 characters, and
    they inflate to 490,373. **Both figures are RESOLVED from the archive rather than typed**
    — they moved 129,400 → 138,177 → 137,939 and 457,123 → 490,950 → 490,373 across three
    releases, and typing them in was three red suites. They are what the compiler emitted and
    the compressor produced, not thresholds: the claim being proved is the *equality of the
    socket and the sibling*, which is a property of the serving path and is indifferent to
    how large either number is. Two independent readings meet here — one off a TCP socket
    through the real handler, one out of a zip's central directory — so the equality is a
    measurement against a measurement and not a lookup against itself.
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
    compared: the dict carries ``4·ceil(n/3)`` base64 characters, the socket carries ``n``
    bytes, and the ratio is 4/3 to the character. That ratio is the entire hazard interface
    **I2** names — a meter, a ceiling or an invoice computed on the left-hand number
    over-states this origin's egress by a third — and this is the assertion that says which
    of the two numbers is the one AWS bills. At build ``5302005``: 183,920 characters against
    137,939 bytes, 45,981 of them overhead nobody is billed for.

    **THE ROUNDED RATIO IS A PROPERTY OF ``n mod 3`` AND OF NOTHING THIS REPOSITORY DOES.**
    It has now read 1.3334, 1.3334, 1.3333 and 1.3333 across four packages, and a reader
    could be forgiven for having filed it as a constant of nature at any point in that
    sequence. base64 packs three bytes into four characters and pads the remainder, so the
    encoded length is ``4·ceil(n/3)`` and the ratio is a function of the remainder alone:

        n = 124,177   n mod 3 = 1 → 2 pads → 165,572/124,177 = 1.33335481 → 1.3334
        n = 129,400   n mod 3 = 1 → 2 pads → 172,536/129,400 = 1.33335394 → 1.3334
        n = 138,177   n mod 3 = 0 → 0 pads → 184,236/138,177 = 1.33333333 → 1.3333
        n = 137,939   n mod 3 = 2 → 1 pad  → 183,920/137,939 = 1.33334879 → 1.3333

    All four sit in ``[4/3, 4/3 + 8/(3n)]``, which is what "a third larger" means exactly.
    The UPPER end is attained when the remainder is 1; the LOWER end exactly when it is 0.

    **THE DECIMAL STOPPED BEING PINNED ON 2026-08-16, AND WHAT REPLACED IT IS STRONGER.**
    ``round(inflation, 4) == 1.3333`` is a statement about one build's remainder wearing the
    clothes of a law — it would have had to be re-recorded the next time the remainder came
    out 1, which is a one-in-three coin flip per release. What is asserted instead is the
    EXACT identity ``len(envelope) == 4·ceil(len(wire)/3)`` over the two measured lengths:
    the same claim without the rounding, true for every ``n``, and tighter than the pair of
    inequalities it sits beside.

    **THE INTEGER FORM OF THOSE INEQUALITIES WAS AN EDIT MADE ON 2026-08-15 AND IS WORTH
    KEEPING.** The bound was once evaluated in binary floating point. Because an end of the
    interval is *attained* whenever ``n mod 3`` is 1 or 0, the comparison reduced to whether
    two unrepresentable thirds round to the same double — at n = 129,400 they did not, and
    the assertion failed by one unit in the last place against an envelope that is exactly
    ``4·ceil(n/3)`` characters. The inequalities are multiplied out and asserted over exact
    integers (``3·chars >= 4·n`` and ``3·chars <= 4·n + 8``): the identical mathematical
    statement with the approximation removed.
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
    # n = 129,400 the RIGHT-hand bound was ATTAINED EXACTLY — n mod 3 == 1, so
    # 3 x 172,536 == 4 x 129,400 + 8 — and the comparison then came down to which way two
    # unrepresentable thirds happened to round. It failed by one unit in the last place
    # against a build that satisfies the claim perfectly. Packages have since attained BOTH
    # ends of this interval — n mod 3 == 1 at 129,400 and n mod 3 == 0 at 138,177 — which is
    # as clear a demonstration as this file will ever get that the integer form is
    # load-bearing rather than fastidious. Multiplying the denominators out asserts the
    # IDENTICAL mathematical statement over exact integers, so nothing that used to be
    # refused is now accepted. The float form is what drifted; the bound is not.
    assert 3 * len(envelope) >= 4 * len(wire), (
        f"the envelope is shorter than 4·ceil(n/3) for n = {len(wire)}: {len(envelope)} "
        "characters, so it is not a base64 encoding of those bytes at all"
    )
    assert 3 * len(envelope) <= 4 * len(wire) + 8, (
        f"the envelope is longer than 4·ceil(n/3) for n = {len(wire)}: {len(envelope)} "
        "characters. Anything above this is padding nobody asked for, or a second encoding."
    )
    # THE EXACT IDENTITY, which since 2026-08-16 replaces the pinned decimal. It is tighter
    # than the two inequalities above — it picks out one value where they admit an interval —
    # and unlike `round(inflation, 4) == 1.3333` it is true for every n rather than for the
    # two remainders out of three that happen to round that way. Both sides are MEASURED:
    # the left off the handler's dict, the right off the socket.
    assert len(envelope) == 4 * ((len(wire) + 2) // 3), (
        f"the envelope is {len(envelope)} characters where base64 of {len(wire)} bytes is "
        f"exactly {4 * ((len(wire) + 2) // 3)}. Something other than base64 produced it."
    )
    assert 4 / 3 <= inflation <= 4 / 3 + 8 / (3 * len(wire)), (
        f"the envelope overhead left [4/3, 4/3 + 8/3n]: {inflation}"
    )
    # The padding, which is what interface I2 exists to keep off a meter. Both sides measured
    # again: the difference of the handler's envelope and the socket's body, against the same
    # difference predicted from the archive's sibling size.
    overhead = len(envelope) - len(wire)
    assert overhead == ENTRY_ENVELOPE_PADDING == ENTRY_ENVELOPE_CHARS - len(wire), (
        f"{overhead} characters of base64 padding that AWS strips and nobody is billed for, "
        f"against {ENTRY_ENVELOPE_PADDING} predicted from the archive. A ceiling or a metric "
        "applied to the envelope would count them."
    )

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
    entry bundle is several times that. Every browser that will ever load this console sends
    ``Accept-Encoding: gzip`` and is served; a client that refuses compression while asking
    for a 490 KB bundle is exactly the caller a *wire* ceiling exists for, and ``curl``
    without ``--compressed`` is the one that will meet it.

    **THE MULTIPLE MOVES BECAUSE THE NUMERATOR DOES.** It was 3.1133 (``433,564 / 139,264``),
    then 3.2824 (``457,123 / 139,264``), then 3.5253 (``490,950 / 139,264``), and at build
    ``5302005`` it is 3.5211 (``490,373 / 139,264``). **The denominator is unchanged and is
    not a measurement**: ruling **R10** (`docs/leads/reconcile-constants-plan.md` §1) keeps
    ``static_site.DEFAULT_MAX_RESPONSE_BYTES`` at 139,264 and demotes the derivation that
    first chose it to provenance, leaving interface **I3** and the straddle as the live law.
    Both still hold: ``137,939 <= 139,264 < 490,373``, and 139,264 < 1.20 x 137,939.

    **BUT READ THE FIRST OF THOSE TWO AGAIN.** ``137,939 <= 139,264`` clears by **1,325
    bytes — 0.95 %**. It cleared by 1,087 on the package before this one and by 9,864 on the
    one before that; it improved this time only because different bytes compressed
    differently, which is not room anybody won and can reverse on the next commit. This test
    is the socket-level statement of what the console loses when that reaches zero: the
    object at ``ENTRY_PATH`` starts answering 413 to *every* client rather than only to the
    ones refusing compression, ``GET /`` keeps returning its 200 and its shell, and the page
    a judge opens is blank. Nothing in the origin's own logs distinguishes that from a
    healthy day. The fix is a smaller entry chunk; raising 139,264 to make the inequality
    comfortable again is the move R10 exists to refuse.

    The straddle is asserted before the status, so this stays a **ratchet**: if somebody
    raises the ceiling above the identity size the first assertion fails naming the flood
    multiplier that came back, instead of the second one quietly starting to expect a 200.
    Both endpoints are resolved from the archive, so the inequality is about a bound and two
    representations rather than about a filename.
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
    """``<the entry chunk>.gz`` is a 404 **even though the file is right there**.

    That is the whole content of interface **I1**'s naming rule, and it is why this asserts
    the file exists first: a 404 from a path that happens to be missing would prove nothing.
    Two names for one object is two cache entries, two ``content-type`` answers, and a URL
    that hands a browser gzip bytes it was never told to inflate.

    The property is *"a ``.gz`` sibling has no URL of its own"*; the object it is proved
    against is whichever chunk this build emitted, and **no version of that name appears in
    this test or in this sentence.** It used to: the docstring named
    ``assets/index-LoN3Sn_L.js``, then ``assets/index-BH5dfAvF.js`` before that, and each
    rename was a line somebody had to notice and edit. ``ENTRY_PATH`` is resolved from the
    archive by :func:`_resolve_artefact`, so the property survives a rebuild without an edit
    and a *changed shape* — two entry chunks, or an entry chunk that is not the largest
    object — still fails, at import, naming what changed.
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
    so on the negotiated path it is the **sibling's** length and not the identity object's,
    and the body is empty. At build ``5302005`` that gap is 137,939 against 490,373. The
    header sets are compared as sets rather than one by one so a header that appears on only
    one of the two methods fails here rather than in a browser's cache six months later.

    **Both figures are resolved from the archive**, having moved 129,400 → 138,177 → 137,939
    and 457,123 → 490,950 → 490,373 across three releases. They are measurements of what a
    build emits, not limits: the claim under test is that ``HEAD`` and ``GET`` agree, and it
    would be the same claim at any pair of sizes. The gap matters at all because a ``HEAD``
    that announced the *identity* length on a negotiated response would be off by exactly
    it, and having both numbers to hand is what makes that failure legible.
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


# ── (f) EVERY sibling, and not just the two this file addresses ─────────────────────


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


def test_the_shipped_set_pairs_one_sibling_to_every_object_with_no_orphan_and_no_gap(
    web_root: Path,
) -> None:
    """The published inventory, measured against the artefact that deploys.

    **THIS TEST'S NAME STOPPED CARRYING A MEASUREMENT ON 2026-08-16, AND THAT IS THE POINT
    OF THE EDIT.** It has read ``…_of_289_312_…``, ``…_of_289_437_…``,
    ``…_is_57_siblings_of_295_724_bytes_…`` and ``…_is_69_siblings_of_347_013_bytes_…`` —
    four renames in a fortnight, each one a hand-edit forced by a console release. The
    reasoning behind those renames was sound as far as it went: *a name left standing after
    the measurement moved is a lie that ``-q`` output repeats on every run*. The conclusion
    was the wrong one. **A test name should not carry a measurement at all**; it should name
    the property, and then it never rots. The measurements live in the file docstring, dated
    and attributed to a build. Nothing outside this file references any of the five names —
    checked by grep across the repository, where the only hits are historical ``qa/*.xml``
    run artefacts.

    The sibling inventory is published in three places outside this file:
    ``docs/deploy/lambda-bundle.md`` §4, ``static_site``'s module docstring, and the L3 row
    of ``docs/deploy/COST-BOUND.md``. Until this control existed those were three copies of
    one unverified sentence.

    At build ``5302005``: **77 objects and 427,352 B of siblings**, up from 69 / 347,013 and
    before that 57 / 295,724. **They are measurements and not floors**: they are the sum of
    what the compressor produced, and no request is permitted or refused by them — the one
    refusal in this package is made by the ceiling, which did NOT move (ruling R10). Both are
    now RESOLVED from the archive rather than typed, so a release moves them without moving
    this file. As of this measurement ``docs/deploy/lambda-bundle.md:209,215`` still carries
    ``57 | 289 312``, a console several rebuilds back; that page is not this worker's file and
    is reported to the lead rather than edited here. **What this test enforces is the
    artefact's shape, not any document's numbers.** Four properties, each of which breaks a
    different published claim if it moves:

    1. **the inventory is the sibling set**, so the count in the docs is the count in the
       zip — and this one moved 57 → 69 → 77, which is what it looks like when a console
       gains screens rather than bytes; a count that moves the other way would mean an
       object stopped shipping or stopped being compressed;
    2. **every one of them has a ``.gz`` beside it** — one identity object without a
       sibling is one object served uncompressed to every browser, and the L3 saving is
       over-claimed by its identity size;
    3. **no orphan ``.gz``** — a sibling whose identity object was dropped is 100 % dead
       weight, since interface I1 gives it no URL of its own and nothing can ever reach it;
    4. **the staged tree and the archive agree** on both the count and the total. Those are
       two readings — one by walking an unpacked directory, one out of a central directory —
       so their equality is a check and not a restatement.

    A rebuild that legitimately changes the console moves these numbers. That is a cost
    change and has to be read as one: the file docstring records what they were, and the
    sentence in ``docs/deploy/lambda-bundle.md`` still has to be moved with it.
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


def test_every_sibling_reaches_the_wire_and_none_of_them_has_a_url(
    emulator: _Emulator, web_root: Path
) -> None:
    """**The control that discharges the claim.** All of them, over the socket, both ways.

    (The name carried ``57`` for two releases after the set had grown to 69 and then 77. A
    test name that embeds a measurement is a claim that rots; this one now names the
    property. The counts live in the file docstring, dated.)

    The rest of this file proves negotiation for two objects. The sentence the cost model
    and the bundle page publish is about the whole set — *the siblings are what every real
    browser receives* — and a set proved at its two extremes is a set with seventy-five
    untested members. Three exchanges per object, 231 at build ``5302005``:

    * ``Accept-Encoding: gzip`` on the **identity** URL answers 200 with
      ``content-encoding: gzip``, ``vary: accept-encoding`` and the sibling's bytes exactly;
      the body is a real gzip member that inflates to the identity object byte for byte, so
      what was saved is transport and not content;
    * the **media type is the identity object's**, asserted against the identity response
      for the same path rather than against this module's own table — a ``.js.gz`` served
      as ``application/gzip`` is a module a browser refuses to run;
    * ``<path>.gz`` is a **404** for every one of them, so a sibling never acquires a second
      name, a second cache entry or a way to hand a browser gzip it was never told to
      inflate.

    The ceiling is consulted rather than assumed: an object whose identity representation
    is over it answers 413 to the identity request, which is a bound and not a defect, and
    the media-type comparison is made against the gzip answer alone in that case. **Exactly
    one object may be in that state and it must be the entry chunk** — a rebuild that pushes
    a second object over the ceiling fails here rather than passing quietly with one fewer
    comparison, and the expected name is resolved from the archive rather than typed.

    The limiter is refilled between exchanges via its documented harness seam, and it still
    runs on every one of them: the per-IP bucket is 50 tokens and this file's own
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

        # And the sibling still has no name of its own — for every one of them.
        ratelimit.reset()
        gz_status, gz_headers, gz_body = emulator.request(
            "GET", f"{url}.gz", accept_encoding="gzip"
        )
        assert gz_status == 404, f"{url}.gz answered {gz_status}; the sibling acquired a URL"
        assert gz_headers["content-type"] == "application/json; charset=utf-8"
        assert gz_body[:2] != b"\x1f\x8b", f"{url}.gz handed out the compressed bytes"

    assert len(served) == SIBLING_COUNT
    assert refused_identity == [ENTRY_PATH.lstrip("/")], (
        f"{len(refused_identity)} objects are over the {ceiling} B ceiling in identity "
        f"({refused_identity}); exactly one is expected and it is the entry bundle, "
        f"{ENTRY_PATH.lstrip('/')}. Every gzip representation is under the ceiling, which is "
        "what makes every sibling reachable — if a sibling ever goes over, that object stops "
        "being servable at all and the L3 row of the cost model is no longer a bound anybody "
        "can rely on."
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
