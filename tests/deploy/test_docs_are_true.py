# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The doc-truth ratchet: a document that is false about its own repository is a RED BUILD.

WHY THIS FILE EXISTS
====================

`github.com/Shaugato/mainline` is public. Every claim in `docs/` is a claim a judge can
settle by opening a second tab. MAINLINE's entire pitch is that it tells you what it has
not proven, so **a document that is false about its own repository is the exact failure
this product sells against.**

Until this file existed, that class of defect was caught by a lead reading 15,012 lines of
documentation. That is not a control; it is a person having a good day. One ratchet already
worked -- `test_cost_model.py::test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence`
went red against a real, unnoticed stale count -- and this file widens that mechanism to
the other defect classes this wave found, one test per class.

THE AUTHORITY, NAMED ONCE FOR THE WHOLE FILE
--------------------------------------------

`docs/leads/docs-and-cloud-plan.md` RULING 4: *"For resource counts and function-shape
attributes, the committed plan artefact is authoritative and prose is derived."* RULING 2:
*"A figure that does not name its tree is wrong, whichever tree it came from."* And
`docs/deploy/terraform-plan.md` §0.1 states it in the document's own words: *"The committed
plan artefact is **authoritative** and this prose is **derived**."*

So every check here reads the ARTEFACT and the TREE, and compares the prose to them. None
of them reads a number out of a document and calls it an expectation. When one goes red the
answer is ALWAYS to correct the document -- never to edit `evidence/`, never to widen the
check, and never to delete the claim, because *a claim deleted is not a claim corrected*
(`docs/deploy/COST-BOUND.md`'s own preservation rule). Each assertion message says which
side is authoritative, in the idiom of the message this file inherits: *"Do NOT edit the
evidence file to match the documents."*

WHY THE CHECKS ARE FUNCTIONS AND NOT LOOPS
------------------------------------------

Every checker below is a pure function over `(relative_path, text)` returning a list of
offences. That is not tidiness: it is what makes the NEGATIVE CONTROLS at the end of this
file possible. Each control synthesises a document fragment carrying the defect and asserts
the checker catches it. **A checker that has never been shown going red for the right
reason is indistinguishable from one that always returns green**, which is the exact
failure this repository sells against. Three are required; five are here.

THE EXEMPTION IDIOM, AND WHY IT CANNOT LAUNDER A STALE CLAIM
-------------------------------------------------------------

Several checks below exempt a line that carries its own correction. That is not a hole: it
is required by the preservation rule, which forbids deleting a false sentence and requires
striking or annotating it in place. The exemptions are all keyed to text a STALE claim
cannot carry -- a claim nobody has noticed is precisely one that has not been struck
through, does not state the value in force, and sits in no paragraph that says it is false.
The same reasoning is already written out in
`test_cost_model.py::test_no_live_document_still_claims_the_two_mebibyte_ceiling`, and the
exemptions here are modelled on it deliberately rather than invented.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.deploy import cost_model as cm
from tests.deploy.test_cost_model import LIVE_DOCS, markdown_paragraphs, markdown_sections

REPO_ROOT = cm.REPO_ROOT

#: The environment root whose `module "guard"` block the docs make claims about.
DEMO_MAIN_TF = REPO_ROOT / "infra/envs/demo/main.tf"

#: The plan artefact RULING 4 makes authoritative for function shape.
PLAN_FURL = REPO_ROOT / "evidence/deploy/terraform-plan-furl.txt"

#: The demo-api's route table -- the file that either carries the demo POST or does not.
#: Added 2026-08-14 for the same class of defect as `DEMO_MAIN_TF`: several live documents
#: asserted that `POST /v1/demo/gate-run` was unrouted and answered 404 long after the route
#: landed, and the deployed console shipped the same sentence in its own chrome.
DEMO_API_APP = REPO_ROOT / "verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py"

#: THE WIRE, WRITTEN DOWN. `scripts/deploy/judge_walk.py` takes a base URL and nothing else,
#: opens a socket for every reading, and stamps the document `"source": "live"`. Added
#: 2026-08-15 as the authoritative side for two claim classes no other artefact in this file
#: can settle: WHICH console asset the deployed origin actually serves, and WHICH transport
#: the served bytes select. Both were wrong in live documents on 2026-08-14 -- three different
#: content-hashed entry chunks were in circulation under one byte count, and the console on
#: the URL was playing a recording while the pages described it as the kernel it sits on.
JUDGE_WALK = REPO_ROOT / "evidence/deploy/judge-walk.json"

#: The judge-walk step whose `detail` names the assets `GET /` referenced.
_SHELL_STEP = "shell"

#: ...and the one that fetched them and read the compiled `VITE_MAINLINE_*` literals out.
_TRANSPORT_STEP = "transport"

#: THE APERTURE, WIDENED 2026-08-15 AND NEVER NARROWED.
#:
#: `LIVE_DOCS` lives in `test_cost_model.py` and is that file's to grow. Two pages a judge
#: reads as current truth are not in it and were policed by no sweep at all:
#:
#:   * `evidence/deploy/APPLIED.md` -- the record of the apply, written by the orchestrator.
#:     It is the first thing a reader opens to find out what is actually deployed, and it is
#:     the one document in the repository whose entire subject is a running deployment.
#:   * `docs/ci/cluster-lane-package.md` -- the page that recorded a console build under a
#:     name (`index-BKZMI9SJ.js`) that no commit produces, and whose figures three other
#:     documents were derived from before anybody re-measured it.
#:
#: They are swept HERE rather than added to `LIVE_DOCS` because that tuple belongs to another
#: file, and a worker who edits a file they do not own is the failure mode this repository
#: spends its whole budget on. `test_the_live_document_list_covers_the_documents_a_judge_reads`
#: asserts `set(LIVE_DOCS) <= set(SWEPT_DOCS)` and names these two, so this widening is a
#: RATCHET: dropping either one fails a test by name rather than turning a sweep green.
#:
#: THE ANTI-DELETION TESTS DELIBERATELY DO NOT USE THIS SET. They assert that a value is
#: stated SOMEWHERE live, so a bigger corpus is a WEAKER assertion; they stay on `LIVE_DOCS`.
SWEPT_DOCS: tuple[str, ...] = (
    *LIVE_DOCS,
    "evidence/deploy/APPLIED.md",
    "docs/ci/cluster-lane-package.md",
)

#: The two entries above, named once so the ratchet below and the comment cannot drift apart.
APERTURE_WIDENED_2026_08_15 = frozenset(
    {"evidence/deploy/APPLIED.md", "docs/ci/cluster-lane-package.md"}
)


# ─────────────────────────────────────────────────────────────────────────────────────────
# 0. READING THE AUTHORITATIVE SIDE. Nothing below is a literal copied from a document.
# ─────────────────────────────────────────────────────────────────────────────────────────


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _strip_markup(line: str) -> str:
    """Flatten markdown emphasis so `**input** tree` reads as `input tree`.

    Every marker match below runs on the flattened form. Without this, a document could
    satisfy a checker or evade one purely by where it put a `*`.

    UNDERSCORE IS NOT STRIPPED, and that is not an oversight. An earlier draft of this
    function stripped `_` as an emphasis marker and silently turned `memory_size` into
    `memorysize`, which made three checkers below match nothing at all -- including the
    negative controls, which is how it was caught. Every subject this file checks is a
    Terraform identifier carrying underscores; the emphasis this repository actually writes
    is `**` and `*`.
    """
    return re.sub(r"[*`~]+", "", line)


def _struck_text(line: str) -> str:
    """Everything inside a GitHub-flavoured `~~strikethrough~~` on this line, flattened.

    Index-free on purpose: matching a flattened offset back onto the raw line is exactly
    the kind of off-by-one this file exists to catch in documents.
    """
    return _strip_markup(" ".join(m.group(0) for m in re.finditer(r"~~.+?~~", line)))


def struck_line_numbers(paragraph: list[tuple[int, str]]) -> set[int]:
    """Line numbers inside a `~~strikethrough~~` span, WHICH MAY WRAP ACROSS LINES.

    A per-line reading of `~~` is wrong and this file had it wrong first. `OBSERVABILITY.md`
    strikes a two-line sentence -- the `~~` opens on one line and closes on the next -- and a
    line-at-a-time regex sees one lone `~~` on each and concludes nothing is struck. It then
    reported, as a live claim, a sentence the document had already retracted. Strikethrough
    is this repository's declared preservation idiom, so failing to see it turns the ratchet
    against the very authors who are obeying the rule.
    """
    if not paragraph:
        return set()
    blob = "\n".join(line for _, line in paragraph)
    starts = [0]
    for _, line in paragraph[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    struck: set[int] = set()
    for span in re.finditer(r"~~.+?~~", blob, re.DOTALL):
        for offset, (number, line) in zip(starts, paragraph, strict=True):
            if offset < span.end() and span.start() < offset + len(line):
                struck.add(number)
    return struck


def plan_resource_blocks(text: str) -> dict[str, list[tuple[int, str]]]:
    """Split a `terraform plan` transcript into its `# <address> will be created` blocks.

    THIS SPLIT IS LOAD-BEARING AND ITS ABSENCE WOULD BE A REAL BUG. The committed plan
    declares TWO Lambda functions: `module.api[0].aws_lambda_function.this` at
    `memory_size = 256` / `timeout = 14`, and `module.guard[0].aws_lambda_function.responder`
    at `memory_size = 128` / `timeout = 15`. A checker that grepped the whole file for
    `timeout` would accept `15` -- the exact stale value RULING 4 says the docs must stop
    printing -- because a different resource really does declare it.
    """
    blocks: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        header = re.match(r"\s*#\s+(\S+)\s+will be (created|destroyed|updated)", line)
        if header:
            current = header.group(1)
            blocks[current] = []
            continue
        if current is not None:
            blocks[current].append((number, line))
    return blocks


#: Which plan resource is authoritative for which attribute. Read as a table, not guessed.
FUNCTION_SHAPE_SUBJECTS = {
    "memory_size": "module.api[0].aws_lambda_function.this",
    "timeout": "module.api[0].aws_lambda_function.this",
    "reserved_concurrent_executions": "module.api[0].aws_lambda_function.this",
    "authorization_type": "module.api[0].aws_lambda_function_url.this",
}


def declared_function_shape() -> dict[str, tuple[str, int]]:
    """`{attribute: (value, line number in the plan artefact)}` for the demo-api function."""
    blocks = plan_resource_blocks(_text(PLAN_FURL))
    shape: dict[str, tuple[str, int]] = {}
    for attribute, address in FUNCTION_SHAPE_SUBJECTS.items():
        assert address in blocks, (
            f"{PLAN_FURL.relative_to(REPO_ROOT)} declares no block for {address}. The plan "
            "artefact is the authoritative side: if the address moved, re-read the "
            "regenerated artefact and correct THIS TABLE. Do NOT edit the artefact."
        )
        for number, line in blocks[address]:
            found = re.match(rf"\s*\+\s+{re.escape(attribute)}\s+=\s+(.+?)\s*$", line)
            if found:
                shape[attribute] = (found.group(1).strip('"'), number)
                break
    missing = set(FUNCTION_SHAPE_SUBJECTS) - set(shape)
    assert not missing, (
        f"{sorted(missing)} are not declared in {PLAN_FURL.relative_to(REPO_ROOT)}. The "
        "artefact is authoritative; re-read it rather than relaxing this check."
    )
    return shape


def guard_block_line() -> int | None:
    """The line `module \"guard\" {` opens on in the demo environment root, or None."""
    for number, line in enumerate(_text(DEMO_MAIN_TF).splitlines(), start=1):
        if re.match(r'\s*module\s+"guard"\s*\{', line):
            return number
    return None


def demo_gate_run_route_line() -> int | None:
    """The line `Route("POST", "/v1/demo/gate-run", …)` opens on in `app.py`, or None.

    The same shape as `guard_block_line()` and for the same reason: the TREE is the
    authoritative side, so the premise of the ratchet below is re-read on every run rather
    than typed here. If the route is ever removed this returns None, the checker returns
    nothing, and the caller asserts on the missing premise by name instead of quietly
    certifying documents against a fact that has stopped being true.
    """
    for number, line in enumerate(_text(DEMO_API_APP).splitlines(), start=1):
        if re.search(r'Route\(\s*"POST"\s*,\s*"/v1/demo/gate-run"', line):
            return number
    return None


def judge_walk() -> dict:
    """The judge's walk document, or `{}` when it has not been produced.

    Every caller asserts on the premise it needs BY NAME before trusting a checker built on
    it -- the shape `demo_gate_run_route_line()` already uses. A missing artefact must make
    this file say so, never make a sweep quietly certify documents against nothing.
    """
    if not JUDGE_WALK.is_file():
        return {}
    return json.loads(JUDGE_WALK.read_text(encoding="utf-8"))


def _walk_step(document: dict, identifier: str) -> dict:
    for step in document.get("steps", []):
        if step.get("id") == identifier:
            return step
    return {}


def served_console_assets(document: dict | None = None) -> set[str]:
    """Every `assets/index-*` name the DEPLOYED origin referenced or served, off the wire.

    Two independent readings in the same document, unioned rather than one trusted: the
    shell step records what `GET /` referenced, and the transport step records what it then
    fetched. A name in neither is a name this origin did not hand anybody.
    """
    document = judge_walk() if document is None else document
    names: set[str] = set()
    for asset in _walk_step(document, _SHELL_STEP).get("detail", {}).get("assets", []):
        names.add(str(asset))
    for scanned in _walk_step(document, _TRANSPORT_STEP).get("detail", {}).get("scanned", []):
        name = scanned.get("asset")
        if name:
            names.add(str(name))
    return names


def deployed_transport_mode(document: dict | None = None) -> str | None:
    """`REPLAY` or `LIVE` -- which source the SERVED bytes select, per the walk."""
    document = judge_walk() if document is None else document
    mode = document.get("context", {}).get("transport_mode")
    return str(mode) if mode else None


def package_shape() -> dict:
    return json.loads(cm.PACKAGE_SHAPE.read_text(encoding="utf-8"))


def arm64_shape() -> dict:
    return next(a for a in package_shape()["architectures"] if a["architecture"] == "arm64")


def input_tree_byte_figures() -> dict[int, str]:
    """The packer's INPUT-tree figures, read from `package-shape.json`, never typed here.

    RULING 1: *"The numbers 1,554,168 / 3,571,990 / 2,586,960 do not move. The label and the
    sourcing move."* They are load-bearing inputs to the §2.2 reproduction, so this file
    reads them out of the evidence and checks how the prose LABELS them.
    """
    before = arm64_shape()["before"]["web"]
    return {
        before["largest_identity_object"]["bytes"]: "the input tree's largest object",
        before["bytes"]: "the input tree's whole web/ tree",
        before["source_maps"]["bytes"]: "the input tree's source maps",
    }


def deployed_tree_figures() -> dict[int, str]:
    """The DEPLOYED package's figures, likewise read rather than typed.

    Used as an exemption: a line carrying an input figure AND the deployed figure it became
    -- `1,554,168 → 433,396 B`, or a `| | then | now |` row -- has named both trees by
    construction. Requiring it to say "input tree" as well would be requiring the label
    twice, and a checker that demands redundancy gets disabled rather than obeyed.
    """
    after = arm64_shape()["after"]["web"]
    return {
        after["largest_identity_object"]["bytes"]: "the deployed tree's largest object",
        after["largest_gz_object"]["bytes"]: "the deployed tree's largest gzip sibling",
        after["bytes"]: "the deployed tree's whole web/ tree",
    }


def deployed_source_map_entries() -> int:
    return arm64_shape()["after"]["web"]["source_maps"]["entries"]


def _quotes(flat_line: str, values) -> list[int]:
    """Which of `values` this flattened line quotes, comma-grouped or bare."""
    return [
        value
        for value in values
        if re.search(rf"(?<![\d,.]){value:,}(?![\d,.])", flat_line)
        or re.search(rf"(?<![\d,.]){value}(?![\d,.])", flat_line)
    ]


# ─────────────────────────────────────────────────────────────────────────────────────────
# 1. THE CHECKERS. Pure functions, so the negative controls at the end can drive them.
# ─────────────────────────────────────────────────────────────────────────────────────────

#: Words by which a line claims a figure describes the tree that is actually deployed.
_DEPLOYED_TREE_CLAIM = re.compile(
    r"out/lambda/mainline-demo-api|the origin can emit|largest response the origin"
    r"|largest (?:servable|emittable) (?:response|object)|in the (?:deployed|shipping) "
    r"(?:package|tree|origin)|the deployed package|servable by the origin",
    re.IGNORECASE,
)

#: Words by which a line names the packer's INPUT tree. Generous about PHRASING -- the point
#: is to require that the tree be named, not to dictate how -- and strict about SUBSTANCE.
#:
#: A bare `INPUT` alternative was here first and was removed: with `IGNORECASE` it matched
#: the word "input" anywhere on a line, so `"the input to the model is 1,554,168 B"` would
#: have exempted itself without naming any tree at all. Every alternative below names a tree
#: or a JSON path into `package-shape.json`.
_INPUT_TREE_MARKER = re.compile(
    r"input tree|input-tree|packer's input|pre-strip|prestrip|pre strip|before the strip"
    r"|architectures\[\]\.before|\.before\.web|before\.web",
    re.IGNORECASE,
)


def input_tree_figures_sourced_to_the_deployed_package(relative: str, text: str) -> list[str]:
    """RULING 1's defect: an INPUT-tree figure presented as a property of the DEPLOYED tree.

    This is the sharpest form of the two-trees defect and the one the ruling quotes
    verbatim: rows I4/I6/I7 said *"Largest response the origin **can emit**: 1,554,168 B"*,
    sourced to *"`zipfile` over `out/lambda/mainline-demo-api-arm64.zip`"* -- an artefact
    anyone can open in thirty seconds and be told the opposite.

    A line is an offence when it quotes an input-tree figure AND attributes it to the
    deployed artefact AND names neither the input tree nor the deployed figure that
    replaced it, on the same line. A markdown table row IS one line, so "same line" and
    "same table row" are the same rule here.

    THE BEFORE-AND-AFTER EXEMPTION, and why it is not a hole. `COST-BOUND.md` §0's table is
    headed `| | then | now |` and its row reads
    `| largest servable response | 1,554,168 B | 124,127 B on the wire |`. That row names
    both trees by construction: the second figure is the deployed one, read here out of
    `package-shape.json` rather than trusted from the prose. The same goes for a delta
    written `1,554,168 → 433,396 B`. A STALE claim is precisely one that gives the input
    figure and stops -- it has no "after" to show, because whoever wrote it did not know
    there was one.
    """
    figures = input_tree_byte_figures()
    deployed = deployed_tree_figures()
    offences: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        flat = _strip_markup(line)
        if not _DEPLOYED_TREE_CLAIM.search(flat):
            continue
        quoted = _quotes(flat, figures)
        if not quoted:
            continue
        if _INPUT_TREE_MARKER.search(flat) or _quotes(flat, deployed):
            continue
        offences.append(
            f"{relative}:{number} sources {', '.join(f'{v:,} B' for v in quoted)} to the "
            f"DEPLOYED artefact and shows no deployed figure beside it: {line.strip()[:110]}"
        )
    return offences


def input_tree_figures_labelled_as_such(text: str) -> list[int]:
    """The anti-deletion half of RULING 2: which input figures this document LABELS.

    Returns the figures this document quotes at least once WITH the input tree named on the
    same line. The caller uses it to assert the label still exists somewhere live, so the
    cheapest way past the check above -- deleting the labelled row and keeping the bare
    arithmetic -- is closed.

    Why this direction and not a blanket per-line rule: RULING 1 prescribes its own remedy
    at section granularity (*"add §1 to the header's enumerated list of annotated
    sections"*), and §2.2's worked arithmetic legitimately carries `1,554,168 B` as a
    load-bearing INPUT to the reproduction that `test_cost_model.py` gates. Demanding that
    every line of a calculation restate its provenance is churn, not truth. What must not
    happen is that NO line states it.
    """
    figures = input_tree_byte_figures()
    labelled: set[int] = set()
    for line in text.splitlines():
        flat = _strip_markup(line)
        if _INPUT_TREE_MARKER.search(flat):
            labelled.update(_quotes(flat, figures))
    return sorted(labelled)


#: An HCL-shaped assignment: `attr = 256`, `authorization_type = "NONE"`, with markdown
#: emphasis already flattened out of the line.
#:
#: THE UNIT SUFFIX IS EXCLUDED ON PURPOSE. `LATENCY.md` §0 records the founder's request as
#: `timeout = 3 s` and explains at length why it was refused. `3 s` is not valid HCL --
#: Terraform's `timeout` is a bare count of seconds -- so a value carrying a unit is prose
#: ABOUT the attribute, not a quotation OF the plan, and reading it as one would report a
#: recorded refusal as a stale claim.
_HCL_ASSIGNMENT = re.compile(
    r"\b(memory_size|timeout|reserved_concurrent_executions|authorization_type)\s*=\s*"
    r'"?(-?\d+|NONE|AWS_IAM)"?(?![\w.])'
    r"(?!\s*(?:s\b|ms\b|sec|min|hour|MB\b|GB\b|MiB\b|KiB\b))"
)

#: A line claims to REPORT the plan when it cites the plan artefact, or when it names the
#: shipping function whose shape the plan declares.
_REPORTS_THE_PLAN = re.compile(r"terraform-plan-furl|furl\.txt|mainline-demo-api", re.IGNORECASE)


def function_shape_claims_that_contradict_the_plan(relative: str, text: str) -> list[str]:
    """RULING 4: the committed plan artefact is authoritative; this prose is derived.

    SCOPE, AND WHY IT IS NOT THE WHOLE FILE. A line is checked when it claims to report the
    plan -- it cites `terraform-plan-furl.txt` or names `mainline-demo-api`. A line that
    does neither may be proposing a lever (`COST-BOUND.md` §3's L8 row prices
    `authorization_type = AWS_IAM`) or quoting a request that was refused
    (`LATENCY.md` §0's `timeout = 3 s`, recorded because it was rejected). Flagging those
    would flag correct prose, and a checker that goes red against correct prose gets
    disabled, which is worse than not having it.

    The anti-deletion counterpart is the test below: the plan's values must still be stated
    somewhere live, so the cheap way past this check -- removing the sentence -- is closed.
    """
    shape = declared_function_shape()
    offences: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        flat = _strip_markup(line)
        if not _REPORTS_THE_PLAN.search(flat):
            continue
        for found in _HCL_ASSIGNMENT.finditer(flat):
            attribute, value = found.group(1), found.group(2)
            declared, declared_line = shape[attribute]
            if value == declared:
                continue
            # A struck value is a corrected value: the preservation rule requires the old
            # one to stay visible. `memory_size = ~~512~~ **256**` is the correct idiom.
            if re.search(rf"(?<![\w.]){re.escape(value)}(?![\w.])", _struck_text(line)):
                continue
            # ... and the same line stating the value in force is the same exemption in the
            # form a table row can carry. A stale claim carries neither.
            if re.search(rf"(?<![\w.]){re.escape(declared)}(?![\w.])", flat):
                continue
            offences.append(
                f"{relative}:{number} says `{attribute} = {value}` while "
                f"{PLAN_FURL.relative_to(REPO_ROOT).as_posix()}:{declared_line} declares "
                f"`{attribute} = {declared}` for {FUNCTION_SHAPE_SUBJECTS[attribute]}"
            )
    return offences


#: Phrases by which a line asserts that the environment root has no `module "guard"`.
_GUARD_ABSENCE = re.compile(
    r"(?:no|not|never|lacks|without|absent|missing)[^.]{0,70}?module\s+\"?guard"
    r'|module\s+"?guard"?[^.]{0,70}?(?:is not|was not|is never|never instantiated'
    r"|does not exist|is absent|is missing)",
    re.IGNORECASE,
)

#: A paragraph carries its own correction when it says so. A claim nobody has noticed is
#: stale carries none of these, because nobody has written the correction yet.
_CORRECTION_MARKER = re.compile(
    r"\bCORRECTED\b|\bANNOTATED\b|\bSUPERSEDED\b|is false|are false|was false|were false"
    r"|no longer (?:true|the case)|is instantiated|now instantiat|predates|struck through",
    re.IGNORECASE,
)


def guard_absence_claims_while_the_block_is_in_the_tree(relative: str, text: str) -> list[str]:
    """No live document may assert the absence of a block that is in the tree.

    RULING 4 calls the original of this *"the worst document in the repository right now:
    it asserts the absence of a block that is in the tree, and it does so in a paragraph
    that correctly explains that the count is checked by a test -- a document explaining
    its own ratchet while failing it."*

    THE TREE IS AUTHORITATIVE. The exemption is derived from it too: a line may quote the
    superseded claim if it is struck through, or if its paragraph cites the block's ACTUAL
    location in the tree, or if its paragraph says the claim is false. The citation form is
    computed from `infra/envs/demo/main.tf` at read time, so when the block moves the
    exemption stops matching and every document that leans on it is re-read -- the
    exemption cannot rot into a permanent hole.
    """
    line_number = guard_block_line()
    if line_number is None:
        return []  # the premise is gone; the caller asserts on that separately
    citation = f"main.tf:{line_number}"
    offences: list[str] = []
    for paragraph in markdown_paragraphs(text):
        blob = _strip_markup(" ".join(line for _, line in paragraph))
        excused = citation in blob or _CORRECTION_MARKER.search(blob)
        struck = struck_line_numbers(paragraph)
        for number, line in paragraph:
            if not _GUARD_ABSENCE.search(_strip_markup(line)):
                continue
            if excused or number in struck:
                continue
            offences.append(
                f'{relative}:{number} asserts `module "guard"` is absent while it opens '
                f"at infra/envs/demo/main.tf:{line_number}: {line.strip()[:110]}"
            )
    return offences


#: Phrases by which a line asserts that `POST /v1/demo/gate-run` cannot be reached.
#:
#: THE SUBJECT AND THE CLAIM MUST BE IN ONE SENTENCE, in either order, in the first two
#: alternatives. A bare `404` alternative was drafted first and removed: `RUNBOOK.md` says
#: a package missing `web/index.html` *"404s the URL a judge opens"* and heads a
#: troubleshooting section *"The URL 404s but `/v1/health` is green"*, both of which are
#: correct prose about a DIFFERENT path, and a checker that is red against correct prose
#: gets disabled rather than obeyed. The third and fourth alternatives stand alone because
#: they cannot be about anything else: this repository has exactly one demo route, and
#: "the endpoint 404s" is the trailing clause of the one sentence this check exists to
#: retire -- shipped verbatim in `docs/deploy/gate-run-contract.md` §9 and in the deployed
#: console's own `DECLARATION_GAP` chrome.
_DEMO_ROUTE_ABSENCE = re.compile(
    r"(?:/v1/demo/gate-run|demo_gate_run)[^.]{0,90}?"
    r"(?:not (?:yet )?routed|unrouted|has no route|is not reachable|404s\b|answers? "
    r"(?:a |an )?404|returns? (?:a |an )?404|would 404)"
    r"|(?:not (?:yet )?routed|unrouted|no route (?:table entry )?for|answers? (?:a |an )?404"
    r"|returns? (?:a |an )?404)[^.]{0,90}?(?:/v1/demo/gate-run|demo_gate_run)"
    r"|no demo route"
    r"|(?:the |so the )?endpoint 404s",
    re.IGNORECASE,
)

#: A paragraph carries its own correction when it records the closure. `_CORRECTION_MARKER`
#: supplies the shared vocabulary; these are the words this particular gap closed with, and
#: they are separate so that widening them cannot loosen the `module "guard"` check.
_DEMO_ROUTE_CLOSURE = re.compile(
    r"\bCLOSED\b|now routed|is routed|routed since|carries the route|the route exists"
    r"|503 .?dsn_unset|dsn_unset",
    re.IGNORECASE,
)


def demo_route_absence_claims_while_the_route_is_in_the_table(
    relative: str, text: str
) -> list[str]:
    """No live document may say the demo route is unrouted while `app.py` declares it.

    THE DEFECT, MEASURED 2026-08-14. `docs/deploy/gate-run-contract.md` §9 read
    *"**`POST /v1/demo/gate-run` is not yet routed.** `app.py`'s route table … declares the
    four kernel POSTs and no demo route, so the endpoint 404s"*. `app.py` carries
    `Route("POST", "/v1/demo/gate-run", "demo_gate_run")` as its seventeenth route, and the
    deployed Function URL answers **503 `dsn_unset`** to that path -- not 404. The sentence
    was false in the tree and false on the wire, and the same sentence had been copied into
    the console's own chrome, where the founder read it off a screen.

    That is why this check is not decoration. Every other sweep in this file settles a
    NUMBER against an artefact; this one settles a claim about REACHABILITY against the
    route table, which is the only file that decides it.

    THE TREE IS AUTHORITATIVE, and the exemptions are derived from it. A line may carry the
    superseded claim when it is struck through, when its paragraph cites the route's ACTUAL
    line in `app.py`, or when its paragraph records the closure. The citation form is
    computed from `app.py` at read time, so if the route moves the exemption stops matching
    and every document leaning on it is re-read -- the exemption cannot rot into a hole.

    WHY THE WIRE IS NOT READ HERE. A test that curled the deployment would be a test that
    fails on an aeroplane, and a document check that needs the internet is a document check
    that gets marked flaky and skipped. The route table is the thing a stranger can settle
    in one grep, which is the standard the rest of this file holds itself to.
    """
    line_number = demo_gate_run_route_line()
    if line_number is None:
        return []  # the premise is gone; the caller asserts on that separately
    citation = f"app.py:{line_number}"
    offences: list[str] = []
    for paragraph in markdown_paragraphs(text):
        blob = _strip_markup(" ".join(line for _, line in paragraph))
        excused = (
            citation in blob
            or _CORRECTION_MARKER.search(blob) is not None
            or _DEMO_ROUTE_CLOSURE.search(blob) is not None
        )
        struck = struck_line_numbers(paragraph)
        for number, line in paragraph:
            if not _DEMO_ROUTE_ABSENCE.search(_strip_markup(line)):
                continue
            if excused or number in struck:
                continue
            offences.append(
                f"{relative}:{number} says `POST /v1/demo/gate-run` is unrouted or 404s "
                f"while app.py declares it at line {line_number}: {line.strip()[:110]}"
            )
    return offences


#: A `.map` presented as something a request retrieves: a method, a scheme, or a URL path.
_MAP_URL = re.compile(r"(?:GET\s+|https?://|(?<![\w])/)[\w./*-]*\.map\b")

#: The line claims that object comes back.
_SERVABLE_CLAIM = re.compile(
    r"\bserv(?:ed|able|es|ing)\b|\bemittable\b|\bcan emit\b|\bemits\b|\breachable\b"
    r"|\bretriev|\b200\b|largest response",
    re.IGNORECASE,
)

#: ...and the line or paragraph refutes it, which is the annotated form RULING 3 requires.
_MAP_REFUTATION = re.compile(
    r"\b404\b|asset_not_found|not found|zero source maps|0 source maps|no source maps"
    r"|\bANNOTATED\b|\bCORRECTED\b|input tree|pre-strip|pre strip|packer's input",
    re.IGNORECASE,
)


def source_map_urls_presented_as_servable(relative: str, text: str) -> list[str]:
    """RULING 3: the `asset_map` beat stays, ANNOTATED -- what is false is the implicature.

    *"The row reads as a beat of the shipping origin, and the shipping origin answers 404
    to `GET /assets/index-BjAGxrVJ.js.map` because the package holds zero maps."*

    The authoritative side is `evidence/deploy/cost/package-shape.json`, whose
    `architectures[].after.web.source_maps.entries` is the number of maps the DEPLOYED
    package holds. The caller asserts that it is zero before trusting this check, so if a
    map ever ships again the premise is re-read rather than this assertion adjusted.

    THE ANNOTATION IS SCOPED TO THE SECTION, not the paragraph, because that is where
    documents actually put it: `LATENCY.md` carries the `asset_map` row in a table and the
    *"against the shipping origin is a 404"* note in the blockquote beneath it, two
    paragraphs down. A paragraph-scoped rule would flag the annotated form and push an
    author to delete the beat -- which RULING 3 forbids, because `COST-BOUND.md` §0.1 row
    L1 is built on that measurement and deleting it orphans the honest "before".
    """
    offences: list[str] = []
    for paragraph in markdown_sections(text):
        blob = _strip_markup(" ".join(line for _, line in paragraph))
        if _MAP_REFUTATION.search(blob):
            continue
        for number, line in paragraph:
            flat = _strip_markup(line)
            if not (_MAP_URL.search(flat) and _SERVABLE_CLAIM.search(flat)):
                continue
            offences.append(
                f"{relative}:{number} presents a .map URL as servable by the deployed "
                f"origin, which answers 404 to it: {line.strip()[:110]}"
            )
    return offences


#: `evidence/…:N` or `infra/…:N` -- a citation a reviewer can follow in one click.
_PATH_CITATION = re.compile(
    r"\b((?:evidence|infra)/[A-Za-z0-9_./-]+?\.(?:txt|json|tf|sh|py|md|yml|yaml|hcl)):(\d+)"
)

#: Subjects whose citation this file can verify, each PINNED TO THE ONE FILE THAT IS
#: AUTHORITATIVE FOR IT. The pinning is the point and an earlier draft did without it: a
#: subject looked up "anywhere in the cited file" produced eight offences that were all
#: false, because `infra/envs/demo/main.tf` quotes a plan count in a COMMENT and
#: `infra/modules/demo-api/main.tf` assigns `authorization_type` from a variable. A check
#: that is red against correct prose gets deleted, and then nothing is checked at all.
#:
#: `terraform-plan-furl.txt` is authoritative for function shape (RULING 4);
#: `infra/envs/demo/main.tf` is the tree that either has the `module "guard"` block or does
#: not (RULING 5, which found this exact citation off by one at 632 against a real 631).
_CITED_SUBJECTS: tuple[tuple[str, str, re.Pattern[str], re.Pattern[str]], ...] = (
    *(
        (
            attribute,
            "evidence/deploy/terraform-plan-furl.txt",
            re.compile(rf"\b{attribute}\b"),
            re.compile(rf"^\s*\+?\s*{attribute}\s+=\s"),
        )
        for attribute in FUNCTION_SHAPE_SUBJECTS
    ),
    (
        'module "guard"',
        "infra/envs/demo/main.tf",
        re.compile(r'module\s+"guard"'),
        re.compile(r'^\s*module\s+"guard"\s*\{'),
    ),
)


def _flatten(text: str) -> str:
    return " ".join(text.split())


def path_citations_that_do_not_resolve(relative: str, text: str) -> list[str]:
    """`path:N` into `evidence/` or `infra/` must point at a line that supports the claim.

    This extends `test_cost_model.py::test_line_references_into_the_plan_evidence_point_at
    _the_plan_line`, which does exactly this for one citation shape and was added because
    that reference *"had drifted to 339 against a real line of 336 -- the kind of rot that
    is invisible until a reviewer follows the citation, finds an unrelated line, and stops
    trusting the rest of the document."* Two more instances of the same rot were found in
    this wave: `authorization_type` cited at `furl.txt:329` (a `MAINLINE_RATE_GLOBAL_RPS`
    line; the attribute is at 351) and `module "guard"` cited at `main.tf:632` (the
    `source` line; the block opens at 631).

    Three failure modes, in ascending order of subtlety:

    1. the cited file does not exist -- checked for EVERY citation, no exemptions;
    2. the cited line is past the end of that file -- likewise;
    3. the line exists but is about something else -- checked only for the subjects in
       `_CITED_SUBJECTS`, each pinned to the single file that is authoritative for it.

    Two exemptions, both DERIVED FROM THE CITED FILE and therefore impossible to write
    without having read it:

    * the citing line QUOTES what the cited line says today, which makes it a correction
      record rather than a stale citation (`RULES-MATRIX.md` records `main.tf:333` *"was
      `authorization_type = …` and now reads `handler = …`"*);
    * the citing SECTION states the subject's real line, which is how `TOOL-USAGE.md`
      records the census anchors that drifted -- it cites the stale `:333` and then says
      *"the two subjects are now at `:432` and `:280`"* three lines later.
    """
    offences: list[str] = []
    section_of: dict[int, str] = {}
    for section in markdown_sections(text):
        blob = " ".join(line for _, line in section)
        for number, _ in section:
            section_of[number] = blob

    for number, line in enumerate(text.splitlines(), start=1):
        for match in _PATH_CITATION.finditer(line):
            target, cited = match.group(1), int(match.group(2))
            path = REPO_ROOT / target
            if not path.exists():
                offences.append(f"{relative}:{number} cites {target}:{cited}, which does not exist")
                continue
            lines = _text(path).splitlines()
            if not 1 <= cited <= len(lines):
                offences.append(
                    f"{relative}:{number} cites {target}:{cited}, but {target} has "
                    f"{len(lines)} lines"
                )
                continue
            cited_text = lines[cited - 1]
            quoted = _flatten(cited_text.strip().lstrip("+").strip())
            if len(quoted) > 12 and quoted[:60] in _flatten(line):
                continue  # a correction record, quoting what the cited line reads today
            for name, owner, in_citing, in_cited in _CITED_SUBJECTS:
                if target != owner or not in_citing.search(line):
                    continue
                if in_cited.search(cited_text):
                    continue
                real = [
                    n for n, candidate in enumerate(lines, start=1) if in_cited.search(candidate)
                ]
                if not real:
                    continue  # the authoritative file no longer declares it; not this line's fault
                if any(f":{n}" in section_of.get(number, "") for n in real):
                    continue  # the section states the real line: a recorded drift
                offences.append(
                    f"{relative}:{number} names {name} and cites {target}:{cited}, which "
                    f"reads {cited_text.strip()[:60]!r}; {name} is declared at "
                    f"{target}:{','.join(str(n) for n in real[:4])}"
                )
    return offences


#: A Vite content-hashed entry chunk as this repository writes them: `assets/index-<hash>.js`
#: or `.css`. Only `index-*` is matched, and that narrowness is deliberate -- the walk can
#: only tell us about the assets `GET /` referenced, and the lazy `surface-*` chunks are not
#: among them. A checker must not have an opinion about something its artefact cannot see.
_CONSOLE_ENTRY_ASSET = re.compile(r"\bassets/index-([A-Za-z0-9_-]{6,})\.(?:js|css)\b")

#: SHAPE NOTATION IS NOT A CLAIM. `RUNBOOK.md` §7 writes
#: `GET /assets/index-XXXXXXXX.js` to show a reader the *form* of a request, exactly as it
#: writes `https://<id>.lambda-url…` for the hostname. A run of one repeated character is
#: nobody's content hash, and a checker that reported it would be red against correct prose.
_PLACEHOLDER_HASH = re.compile(r"^(.)\1*$")

#: ...and a line that says the origin answers 404 to the object is REFUTING the claim, not
#: making it. `LATENCY.md` carries *"`GET /assets/index-BjAGxrVJ.js.map` against the shipping
#: origin is a 404"* -- the annotated form RULING 3 requires, and the sentence this checker
#: would otherwise punish its author for writing.
_ORIGIN_REFUTATION = re.compile(
    r"\b404\b|asset_not_found|not found|does not serve|no longer serve|has gone stale"
    r"|went stale|is stale|superseded|answers? nothing",
    re.IGNORECASE,
)

#: Words by which a line claims that the RUNNING deployment hands that object to a client.
#:
#: DELIBERATELY NARROWER THAN `_DEPLOYED_TREE_CLAIM`. That one is about the packaged tree,
#: which several documents legitimately describe under an older declaration while the
#: re-record is somebody else's open action. This one is about the origin a judge can curl,
#: and there is exactly one right answer to what it serves at any moment.
_ORIGIN_SERVES_CLAIM = re.compile(
    r"lambda-url\.[a-z0-9-]+\.on\.aws"
    r"|the (?:live|deployed|shipping) (?:url|origin)"
    r"|the (?:function )?url (?:serves|is serving|answers|hands)"
    r"|the origin (?:serves|is serving|emits|hands)"
    r"|deployed today"
    r"|what (?:the origin|the url) serves"
    r"|a judge(?:'s browser)? (?:opens|fetches|receives|downloads)",
    re.IGNORECASE,
)


def console_assets_claimed_as_served_that_the_origin_does_not_serve(
    relative: str, text: str
) -> list[str]:
    """A content-hashed asset name presented as what the LIVE origin hands a browser.

    THE DEFECT, MEASURED 2026-08-14/15. This repository had **three** entry-chunk names in
    circulation at one byte count -- `index-BjAGxrVJ.js` (a `console/dist` no commit
    produces), `index-BKZMI9SJ.js` (the committed source built over a worktree carrying CRLF
    line-ending drift) and `index-DzVoV1YM.js` (what the committed source emits and what the
    Function URL actually serves). A Vite asset name IS a content hash, so three names at one
    length is three different files, and a document that names the wrong one is telling a
    reader to fetch a URL that answers 404.

    THE WIRE IS AUTHORITATIVE, and it is read rather than typed: `served_console_assets()`
    unions the shell step's referenced assets and the transport step's fetched ones out of
    `evidence/deploy/judge-walk.json`, which a program produced by opening a socket. When the
    orchestrator redeploys, the served set moves, this checker re-reads it, and every document
    leaning on the old name is re-read with it -- the check cannot rot into a permanent pass.

    A line is an offence when it names an `assets/index-*` the origin does NOT serve AND
    claims the origin serves it. Five exemptions, none of them a free-text password:

    * the hash is SHAPE NOTATION (`index-XXXXXXXX.js`) -- a run of one repeated character is
      nobody's content hash;
    * the same line REFUTES the claim (`…is a 404`) -- which is the annotated form RULING 3
      requires, and punishing it would push an author to delete the beat;
    * the same line also names an asset the origin DOES serve -- a `then | now` row or an
      `X -> Y` delta has named both builds by construction;
    * the line is struck through;
    * its SECTION carries its own correction (`_CORRECTION_MARKER`). Section rather than
      paragraph for the reason `source_map_urls_presented_as_servable` gives at length:
      documents put the annotation in a blockquote beneath the table, two paragraphs down,
      and a paragraph-scoped rule flags the corrected form.

    WHY NOT EVERY MENTION. `docs/deploy/lambda-bundle.md` and `docs/deploy/LATENCY.md` quote
    the older name while describing the PACKAGED tree under a declaration whose re-record is
    an open action owned elsewhere, and `docs/ci/cluster-lane-package.md` quotes it as
    history. Flagging those would be flagging correct prose, and a check that is red against
    correct prose gets disabled -- after which nothing is checked at all.
    """
    served = served_console_assets()
    if not served:
        return []  # the premise is gone; the caller asserts on that separately
    offences: list[str] = []
    for section in markdown_sections(text):
        blob = _strip_markup(" ".join(line for _, line in section))
        excused = _CORRECTION_MARKER.search(blob) is not None
        struck = struck_line_numbers(section)
        for number, line in section:
            flat = _strip_markup(line)
            named = {
                match.group(0)
                for match in _CONSOLE_ENTRY_ASSET.finditer(flat)
                if not _PLACEHOLDER_HASH.match(match.group(1))
            }
            unserved = sorted(name for name in named if name not in served)
            if not unserved:
                continue
            if not _ORIGIN_SERVES_CLAIM.search(flat):
                continue
            if _ORIGIN_REFUTATION.search(flat):
                continue
            if any(name in flat for name in served):
                continue
            if excused or number in struck:
                continue
            offences.append(
                f"{relative}:{number} says the deployed origin serves "
                f"{', '.join(unserved)}, which it does not: it serves "
                f"{', '.join(sorted(served))}. {line.strip()[:110]}"
            )
    return offences


#: The two transports `src/app/source-select.ts` can select, as the chrome spells them.
_TRANSPORT_WORD = {"LIVE": re.compile(r"\bLIVE\b"), "REPLAY": re.compile(r"\bREPLAY\b")}

#: A line whose SUBJECT is the transport of the artefact that is deployed right now. The
#: subject and the claim must be in one sentence: this repository writes a great deal of
#: correct prose about what a LIVE build WOULD do, and none of it is a claim about today.
_DEPLOYED_TRANSPORT_SUBJECT = re.compile(
    r"(?:the )?(?:artefact|artifact|console|build|bundle) (?:that is |currently )?"
    r"(?:on|deployed|serving|live) (?:on |at |to )?(?:that |the |this )?"
    r"(?:origin|url|hostname|deployment|demo)?"
    r"|the deployed (?:artefact|artifact|console|build|bundle)"
    r"|the (?:artefact|artifact|console) (?:on|at) the (?:demo )?(?:url|origin)"
    r"|the console (?:a judge|judges?) (?:sees|opens|gets)"
    r"|transport badge (?:on|of) the deployment",
    re.IGNORECASE,
)


def deployed_transport_claims_that_contradict_the_wire(relative: str, text: str) -> list[str]:
    """No live document may name a transport for the deployed artefact that the wire denies.

    THE FOUNDER'S OWN FINDING, TURNED INTO A CHECK. He opened the demo URL and read
    `TRANSPORT REPLAY (staged)` off a console that was sitting on a live kernel. Every local
    test passed over it, and no document in this repository could go red about it, because
    nothing here reads the bytes the origin serves.

    `evidence/deploy/judge-walk.json` `context.transport_mode` now does, and it is derived
    the way the browser derives it: the compiled `VITE_MAINLINE_*` literals are extracted from
    the served entry chunk and `src/app/source-select.ts`'s own `trimmed()` rule is applied,
    so an empty string is UNSET exactly as it is at runtime.

    THE CHECK IS SYMMETRIC AND THE ARTEFACT DECIDES WHICH WAY IT POINTS. Today the wire says
    `REPLAY`, so a document asserting the deployed console is LIVE is false. The day the
    orchestrator redeploys a corrected artefact the wire says `LIVE`, this checker inverts
    without being edited, and every page still saying REPLAY is re-read. **That is the
    property that makes it a ratchet rather than a snapshot** -- and it is why the opposite
    word is computed here rather than typed.

    Struck text and a paragraph carrying its own correction are exempt, for the reason the
    rest of this file gives: the preservation rule REQUIRES a superseded claim to stay
    visible, and a checker that punishes the annotated form teaches authors to delete it.
    """
    mode = deployed_transport_mode()
    if mode not in _TRANSPORT_WORD:
        return []  # the premise is gone; the caller asserts on that separately
    contradiction = "LIVE" if mode == "REPLAY" else "REPLAY"
    pattern = _TRANSPORT_WORD[contradiction]
    offences: list[str] = []
    for paragraph in markdown_paragraphs(text):
        blob = _strip_markup(" ".join(line for _, line in paragraph))
        excused = _CORRECTION_MARKER.search(blob) is not None
        struck = struck_line_numbers(paragraph)
        for number, line in paragraph:
            flat = _strip_markup(line)
            if not _DEPLOYED_TRANSPORT_SUBJECT.search(flat):
                continue
            if not pattern.search(flat):
                continue
            if _TRANSPORT_WORD[mode].search(flat):
                continue  # the line names the transport in force beside the other one
            if excused or number in struck:
                continue
            offences.append(
                f"{relative}:{number} gives the deployed artefact the transport "
                f"{contradiction!r} while the served bytes select {mode!r} "
                f"(evidence/deploy/judge-walk.json, context.transport_mode): "
                f"{line.strip()[:110]}"
            )
    return offences


#: The walk, as a reader would have to type it. Both halves are required: a page that names
#: the file without `--base-url` has mentioned a script, not published a command.
_JUDGE_WALK_SCRIPT = re.compile(r"scripts/deploy/judge_walk\.py|scripts\\deploy\\judge_walk\.py")
_JUDGE_WALK_INPUT = re.compile(r"--base-url")


def documents_publishing_the_judge_walk(corpus: dict[str, str]) -> list[str]:
    """Which documents publish the walk as something a reader can RUN. Pure, so it falsifies.

    The anti-deletion half of R8, in the idiom of
    `test_the_function_shape_the_plan_declares_is_still_stated_somewhere_live`. R8 requires an
    executable *"a judge's walk can be re-run from"*; an executable nobody is told about is a
    file in a directory. A page that names the script but never its one required input has
    published a mention, so both halves are required on the same page.
    """
    return sorted(
        relative
        for relative, text in corpus.items()
        if _JUDGE_WALK_SCRIPT.search(text) and _JUDGE_WALK_INPUT.search(text)
    )


# ─────────────────────────────────────────────────────────────────────────────────────────
# 2. THE RATCHETS. Every one of these reads the artefact, then reads the prose.
# ─────────────────────────────────────────────────────────────────────────────────────────


def _sweep(checker) -> list[str]:
    """Run one checker over the whole aperture.

    `SWEPT_DOCS`, not `LIVE_DOCS`: the aperture only ever grows, and the two additions are
    asserted by name in `test_the_live_document_list_covers_the_documents_a_judge_reads`.
    """
    found: list[str] = []
    for relative in SWEPT_DOCS:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        found.extend(checker(relative, _text(path)))
    return found


_AUTHORITY = (
    "\nThe committed artefact and the tree are the AUTHORITATIVE side and the prose is "
    "DERIVED (docs/leads/docs-and-cloud-plan.md RULING 4, docs/deploy/terraform-plan.md "
    "§0.1). Correct the document. Do NOT edit the evidence file to match the documents, "
    "do NOT delete the claim -- a claim deleted is not a claim corrected -- and do NOT "
    "widen this check."
)


def test_no_input_tree_figure_is_sourced_to_the_deployed_package():
    """The two trees are both authoritative, for different questions. Say which.

    `docs/decisions/response-ceiling-authoritative-tree.md` §1 rules the DEPLOYED tree
    authoritative for what the origin can emit, and §8 names this exact defect: a figure
    from the packer's INPUT tree printed as *"Largest response the origin can emit"* and
    sourced to the deployed zip. The zip contains zero source maps and 1,554,168 B of
    nothing.
    """
    offences = _sweep(input_tree_figures_sourced_to_the_deployed_package)
    before = arm64_shape()["before"]["web"]
    after = arm64_shape()["after"]["web"]
    assert not offences, (
        f"The packer's INPUT tree holds {before['entries']} entries / {before['bytes']:,} B "
        f"with {before['source_maps']['entries']} source maps; the DEPLOYED package holds "
        f"{after['entries']} entries / {after['bytes']:,} B with "
        f"{after['source_maps']['entries']}. These live claims give an INPUT-tree figure and "
        "attribute it to the deployed artefact:\n  " + "\n  ".join(offences) + _AUTHORITY
    )


def test_every_input_tree_figure_is_labelled_as_such_somewhere_live():
    """RULING 2's anti-deletion half: the label must exist, not just the digits.

    *"A figure that does not name its tree is wrong, whichever tree it came from."* The
    check above catches a figure MISLABELLED as the deployed tree's. This one catches the
    other way past it: keeping the arithmetic and quietly dropping the row that says which
    tree it came from, after which every remaining `1,554,168` in the repository is
    unsourced and nothing is red.
    """
    figures = input_tree_byte_figures()
    labelled: set[int] = set()
    for relative in LIVE_DOCS:
        path = REPO_ROOT / relative
        if path.exists():
            labelled.update(input_tree_figures_labelled_as_such(_text(path)))
    unlabelled = {value: what for value, what in figures.items() if value not in labelled}
    assert not unlabelled, (
        "evidence/deploy/cost/package-shape.json carries these under "
        "`architectures[].before` -- the packer's INPUT tree -- and no live document quotes "
        "them on a line that names that tree:\n  "
        + "\n  ".join(f"{value:,} B ({what})" for value, what in sorted(unlabelled.items()))
        + "\nThe digits DO NOT MOVE (RULING 1): they are load-bearing inputs to §2.2's "
        "reproduction, which test_cost_model.py gates. Restore the label, do not retype "
        "the digits, and do not edit the evidence file."
    )


def test_the_function_shape_in_the_docs_matches_the_plan_evidence():
    """`memory_size` / `timeout` / `reserved_concurrent_executions` / `authorization_type`.

    Four live staleness findings settled by one artefact: `COST-BOUND.md` I9 said
    `512 / 15 / 20` where the plan says `256 / 14 / -1`. Every one of those is prose losing
    to the artefact, which is the whole of RULING 4.
    """
    offences = _sweep(function_shape_claims_that_contradict_the_plan)
    shape = declared_function_shape()
    assert not offences, (
        "The committed plan declares "
        + ", ".join(
            f"{name} = {value} (line {line})" for name, (value, line) in sorted(shape.items())
        )
        + " for the demo-api function.\nThese live claims disagree with it:\n  "
        + "\n  ".join(offences)
        + _AUTHORITY
    )


def test_the_function_shape_the_plan_declares_is_still_stated_somewhere_live():
    """The anti-deletion counterpart. Deleting the sentence must not be the cheap way out.

    Modelled on `test_the_shipping_plan_count_is_actually_stated_somewhere_live`, and here
    for the same reason: the check above only catches a WRONG value. Without this one, the
    cheapest way to pass it is to stop saying anything about the function's shape, which
    would leave a judge with no statement to check at all.
    """
    shape = declared_function_shape()
    blob = "\n".join(
        _strip_markup(_text(REPO_ROOT / relative))
        for relative in LIVE_DOCS
        if (REPO_ROOT / relative).exists()
    )
    unstated = [
        f"{name} = {value} ({PLAN_FURL.relative_to(REPO_ROOT).as_posix()}:{line})"
        for name, (value, line) in sorted(shape.items())
        if not re.search(rf"{name}\s*=\s*\"?{re.escape(value)}\"?(?![\w.])", blob)
    ]
    assert not unstated, (
        "The committed plan declares these and no live document states them:\n  "
        + "\n  ".join(unstated)
        + "\nA claim deleted is not a claim corrected. State the value the artefact "
        "declares; do not remove the sentence and do not shrink LIVE_DOCS."
    )


def test_no_live_document_asserts_the_guard_module_is_absent():
    """The block is in the tree. A document that says otherwise is checkably false."""
    line_number = guard_block_line()
    assert line_number is not None, (
        'infra/envs/demo/main.tf no longer contains a `module "guard"` block, so this '
        "test's premise is gone. Re-read the tree and the documents that describe it "
        "rather than adjusting this assertion."
    )
    offences = _sweep(guard_absence_claims_while_the_block_is_in_the_tree)
    assert not offences, (
        f'`module "guard" {{` opens at infra/envs/demo/main.tf:{line_number} and '
        f'`source = "../../modules/cost-guard"` follows it. These live claims assert its '
        "absence:\n  " + "\n  ".join(offences) + _AUTHORITY
    )


def test_no_live_document_asserts_the_demo_route_is_unrouted_or_404s():
    """The route is in the table and the wire agrees. A document that says otherwise is false.

    Modelled deliberately on `test_no_live_document_asserts_the_guard_module_is_absent`,
    because it is the same defect class with a different noun: a document asserting the
    absence of something that is in the tree, checkable by a stranger in one grep.

    THE WIRE, MEASURED 2026-08-14 against the deployed Function URL and recorded in
    `docs/leads/console-live-plan.md` §0.1: `POST /v1/demo/gate-run` answers **503**
    `kind="dsn_unset"`, naming the SSM parameter it could not read. A 503 that names its
    cause is a reachable endpoint refusing honestly. A 404 would mean no such path.
    """
    line_number = demo_gate_run_route_line()
    assert line_number is not None, (
        "verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py no longer declares "
        '`Route("POST", "/v1/demo/gate-run", …)`, so this test\'s premise is gone. Re-read '
        "the route table and the documents that describe it rather than adjusting this "
        "assertion."
    )
    offences = _sweep(demo_route_absence_claims_while_the_route_is_in_the_table)
    assert not offences, (
        f'`Route("POST", "/v1/demo/gate-run", "demo_gate_run")` is declared at '
        f"verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:{line_number}, and "
        "the deployed Function URL answers 503 `dsn_unset` to it rather than 404. These "
        "live claims say it is unrouted:\n  " + "\n  ".join(offences) + _AUTHORITY
    )


def test_no_live_document_presents_a_source_map_url_as_servable():
    """The deployed package holds zero source maps, so every `.map` URL is a 404."""
    entries = deployed_source_map_entries()
    assert entries == 0, (
        f"the deployed package holds {entries} source maps again, so this test's premise "
        "is gone. Re-read evidence/deploy/cost/package-shape.json and the documents rather "
        "than adjusting this assertion."
    )
    offences = _sweep(source_map_urls_presented_as_servable)
    assert not offences, (
        "evidence/deploy/cost/package-shape.json reports 0 source maps in the deployed "
        "package, so the shipping origin answers 404 to every `.map` URL. These live "
        "claims present one as servable:\n  "
        + "\n  ".join(offences)
        + "\nThe measurement is real and STAYS (RULING 3) -- annotate the row with the "
        "tree it was taken against. Do not delete the beat and do not edit the evidence."
    )


def test_no_live_document_names_a_console_asset_the_origin_does_not_serve():
    """Three entry-chunk names at one byte count, and only one of them is on the wire.

    `assets/index-BjAGxrVJ.js` came from a `console/dist` no commit produces;
    `assets/index-BKZMI9SJ.js` from the committed source built over a worktree carrying CRLF
    drift; `assets/index-DzVoV1YM.js` is what the committed source emits and what the
    Function URL serves. A Vite asset name is a content hash, so those are three files, not
    three spellings, and a document that sends a reader to the wrong one sends them to a 404.
    """
    document = judge_walk()
    assert document, (
        f"{JUDGE_WALK.relative_to(REPO_ROOT).as_posix()} has not been produced, so this "
        "test's premise is gone. Re-run `python scripts/deploy/judge_walk.py --base-url "
        "<the demo URL>` rather than relaxing this assertion -- a checker with no artefact "
        "behind it certifies nothing about the documents it sweeps."
    )
    assert document.get("source") == "live", (
        f"{JUDGE_WALK.relative_to(REPO_ROOT).as_posix()} is stamped "
        f"source={document.get('source')!r}. Only a walk that opened a socket is a reading "
        "of a deployment; a synthetic document may never be cited as one."
    )
    served = served_console_assets(document)
    assert served, (
        "the judge walk records no served console asset, so this test's premise is gone. "
        "Re-read the walk rather than adjusting this assertion."
    )
    offences = _sweep(console_assets_claimed_as_served_that_the_origin_does_not_serve)
    assert not offences, (
        f"the deployed origin serves {', '.join(sorted(served))} -- read off the wire by "
        "scripts/deploy/judge_walk.py, not typed here. These live claims name a different "
        "content-hashed asset and say the origin hands it over:\n  "
        + "\n  ".join(offences)
        + "\nThe WIRE is the authoritative side. Correct the document, or annotate the row "
        "with the build it was measured against -- do not delete the measurement and do not "
        "edit the evidence file."
    )


def test_no_live_document_gives_the_deployment_a_transport_the_wire_denies():
    """The founder's finding as a ratchet, and it inverts the day the artefact is corrected.

    He opened the URL and read `TRANSPORT REPLAY (staged)` off a console sitting on a live
    kernel. Every local test passed over it. Nothing in this repository read the bytes the
    origin serves, so no document here could go red about it.

    `context.transport_mode` in the walk is derived the way the browser derives it -- the
    compiled `VITE_MAINLINE_*` literals out of the served entry chunk, then
    `source-select.ts`'s own `trimmed()` rule, so `""` is UNSET exactly as at runtime. The
    contradiction word is COMPUTED from that value rather than typed, so when the corrected
    artefact is deployed this test starts policing the opposite claim without being edited.
    """
    document = judge_walk()
    assert document, (
        f"{JUDGE_WALK.relative_to(REPO_ROOT).as_posix()} has not been produced, so this "
        "test's premise is gone. Re-run the walk rather than relaxing the assertion."
    )
    assert document.get("allow_replay_declared") is not True, (
        "the walk on disk was produced with `--allow-replay`, which stamps the document so "
        "it can never be cited as a reading of a LIVE artefact. Re-run it without the flag."
    )
    mode = deployed_transport_mode(document)
    assert mode in _TRANSPORT_WORD, (
        f"the judge walk records transport_mode={mode!r}, which is neither LIVE nor REPLAY, "
        "so this test's premise is gone. Re-read the walk and the documents that describe "
        "the deployment rather than adjusting this assertion."
    )
    offences = _sweep(deployed_transport_claims_that_contradict_the_wire)
    assert not offences, (
        f"the transport the served bytes resolve to is {mode!r} "
        "(evidence/deploy/judge-walk.json, context.transport_mode, read from a socket). "
        "These live claims give the deployed artefact the other one:\n  "
        + "\n  ".join(offences)
        + "\nThe WIRE is authoritative. If the artefact has been rebuilt and redeployed, "
        "re-run the walk FIRST and let this test tell you which documents to correct -- "
        "never correct the documents to a deployment nobody has measured."
    )


def test_the_judge_walk_is_published_as_a_runnable_command_somewhere_live():
    """R8's anti-deletion half: an executable nobody is told about is a file in a directory.

    R8 requires *"an executable that a judge's walk can be re-run from"*, running *"from a
    bare checkout with nothing but a URL"*. The program existing is half of that; a reader
    being told the command is the other half, and it is the half that rots first, because
    nothing goes red when a page stops mentioning a script.

    Both halves are required ON THE SAME PAGE -- the path and `--base-url` -- because a page
    that names the file without its one required input has published a mention rather than a
    command.
    """
    program = REPO_ROOT / "scripts/deploy/judge_walk.py"
    assert program.is_file(), (
        "scripts/deploy/judge_walk.py is not in the tree, so this test's premise is gone. "
        "Restore the program; do not delete the assertion that it is documented."
    )
    corpus = {
        relative: _text(REPO_ROOT / relative)
        for relative in SWEPT_DOCS
        if (REPO_ROOT / relative).exists()
    }
    publishing = documents_publishing_the_judge_walk(corpus)
    assert publishing, (
        "scripts/deploy/judge_walk.py is in the tree and NO live document publishes it as a "
        "command a reader can run: no page names both the script and `--base-url`. The walk "
        "is how a judge re-derives the deployment claims in docs/deploy/RUNBOOK.md and "
        "docs/deploy/JUDGE-PACK.md without a credential of ours; a claim that can only be "
        "re-derived by somebody who already knows the program exists is a claim on trust. "
        "Publish the command -- do not weaken this assertion."
    )
    required = {"docs/deploy/RUNBOOK.md", "docs/deploy/JUDGE-PACK.md"}
    missing = sorted(required - set(publishing))
    assert not missing, (
        f"these pages do not publish the judge walk as a runnable command: {missing}. The "
        "runbook is where an operator re-checks what the URL serves and the judge pack is "
        "where a judge does; both were named in the wave that added the program, and "
        "dropping either is dropping the only re-runnable evidence a reader has."
    )


def test_every_line_citation_into_evidence_and_infra_resolves_and_supports_its_claim():
    """A citation a reviewer follows and finds unrelated costs more than no citation."""
    offences = _sweep(path_citations_that_do_not_resolve)
    assert not offences, (
        "These live citations do not point at what they claim to:\n  "
        + "\n  ".join(offences)
        + "\nThe cited file is the AUTHORITATIVE side. Re-read it and correct the line "
        "number in the document. Do NOT edit the cited file to match the citation."
    )


def test_the_live_document_list_covers_the_documents_a_judge_reads():
    """LIVE_DOCS is the ratchet's aperture, and an aperture that shrinks is a hole.

    Every check in this file and the plan-count ratchet in `test_cost_model.py` sweep
    exactly `LIVE_DOCS`. Quietly dropping a path from it would turn every one of them green
    without correcting anything -- the same shape as lowering a floor. So the list is
    asserted here: every deploy and submission document a judge reads as current truth is
    in it, and each entry must exist on disk.
    """
    missing = [relative for relative in LIVE_DOCS if not (REPO_ROOT / relative).exists()]
    assert not missing, (
        f"LIVE_DOCS names paths that are not in the tree: {missing}. If a document was "
        "renamed, follow it; do not drop it from the list."
    )
    required = {
        "docs/deploy/COST-BOUND.md",
        "docs/deploy/LATENCY.md",
        "docs/deploy/OBSERVABILITY.md",
        "docs/deploy/terraform-plan.md",
        "docs/submission/DEVPOST.md",
        "docs/submission/RULES-MATRIX.md",
        # PINNED 2026-08-14. These three were policed by no ratchet at all, and the worst
        # of them was the verdict page: `docs/state-of-the-build.html` headlined `NO-GO`
        # about a build whose sole named blocker -- three unseeded `defeater_option` rows
        # -- had been fixed two commits earlier, and nothing in this tree could see it.
        # They are listed here, and not only in LIVE_DOCS, so that the widening is a
        # RATCHET rather than a preference: dropping one from LIVE_DOCS now fails this
        # test by name instead of silently turning every sweep green.
        "docs/CI-STATE.md",
        "docs/submission/VIDEO-KIT.md",
        "docs/state-of-the-build.html",
    }
    assert required <= set(LIVE_DOCS), (
        f"LIVE_DOCS no longer covers {sorted(required - set(LIVE_DOCS))}. These are the "
        "documents this repository's measurements falsified; removing one from the sweep "
        "is lowering the aperture to obtain a green, which is the same move as lowering a "
        "floor."
    )
    # The verdict page ships in two syntaxes and both are swept. A judge opens whichever
    # one renders in front of them, so a claim corrected in only one of them is still a
    # false claim shipped to somebody.
    assert {"docs/STATE-OF-THE-BUILD.md", "docs/state-of-the-build.html"} <= set(LIVE_DOCS), (
        "the verdict page is swept in only one of its two syntaxes. The Markdown and the "
        "HTML must agree sentence by sentence, and a ratchet that reads one of them "
        "certifies the other by assumption."
    )
    assert any(relative.startswith("docs/submission/") for relative in LIVE_DOCS), (
        "LIVE_DOCS covers no submission document. The stale plan count in "
        "docs/submission/RULES-MATRIX.md was invisible to this ratchet for exactly that "
        "reason."
    )
    # THE APERTURE ONLY EVER GROWS. Every sweep in this file runs over `SWEPT_DOCS`, so a
    # path dropped from EITHER tuple turns checks green without correcting anything -- the
    # same move as lowering a floor. `LIVE_DOCS` must remain a subset, and the two pages
    # this file added on 2026-08-15 are named individually so removing one fails here rather
    # than silently.
    assert set(LIVE_DOCS) <= set(SWEPT_DOCS), (
        f"SWEPT_DOCS no longer covers {sorted(set(LIVE_DOCS) - set(SWEPT_DOCS))}. The "
        "aperture of this file's sweeps must be a SUPERSET of LIVE_DOCS: every document the "
        "plan-count ratchet reads must also be read here, or the two files disagree about "
        "which pages are live."
    )
    dropped = sorted(APERTURE_WIDENED_2026_08_15 - set(SWEPT_DOCS))
    assert not dropped, (
        f"SWEPT_DOCS no longer covers "
        f"{dropped}. evidence/deploy/APPLIED.md "
        "is the record of what is actually deployed and docs/ci/cluster-lane-package.md "
        "recorded a console build under a name no commit produces; both were policed by no "
        "sweep at all until this file widened to them. An aperture that shrinks is a hole."
    )
    missing_swept = [relative for relative in SWEPT_DOCS if not (REPO_ROOT / relative).exists()]
    assert not missing_swept, (
        f"SWEPT_DOCS names paths that are not in the tree: {missing_swept}. If a document "
        "was renamed, follow it; do not drop it from the aperture."
    )


# ─────────────────────────────────────────────────────────────────────────────────────────
# 2b. THE TWIN CHECK. The defect class that every other sweep in this repository was blind to.
#
# On 2026-08-14 `docs/state-of-the-build.html` headlined `NO-GO` while
# `docs/STATE-OF-THE-BUILD.md` had been re-scored, and the HTML's masthead still named tree
# `073dfea` -- a tree three verifications stale. Widening `LIVE_DOCS` to include the HTML was
# necessary and NOT sufficient: every existing sweep checks plan counts, function shape, the
# guard module, source-map URLs and line citations, and not one of them can see a headline
# verdict that contradicts its own twin. This section is the checker for that class.
#
# It is deliberately structural rather than prose-keyed. It reads the ONE place each syntax
# declares its verdict and the ONE place each declares its tree, and requires them to agree.
# Nothing here can be satisfied by adding a sentence; it moves only when the headline moves.
# ─────────────────────────────────────────────────────────────────────────────────────────

VERDICT_PAGE_MD = "docs/STATE-OF-THE-BUILD.md"
VERDICT_PAGE_HTML = "docs/state-of-the-build.html"

#: The verdict vocabulary this page has ever headlined. `CONDITIONAL GO` is listed before
#: `GO` so the alternation prefers the longer, more qualified reading -- a page that says
#: `CONDITIONAL GO` must never be read as having said `GO`.
_VERDICT_TOKEN = re.compile(r"(CONDITIONAL GO|NO-GO|GO)")

#: Struck-through Markdown. The preservation rule REQUIRES superseded verdicts to stay on the
#: page, so the extractor must skip them or an honestly annotated history would read as a
#: live contradiction and this ratchet would punish the correct behaviour.
_MD_STRUCK = re.compile(r"~~.*?~~", re.DOTALL)

_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_STYLE = re.compile(r"<(style|script)\b.*?</\1>", re.DOTALL | re.IGNORECASE)

#: The HTML's headline slab and its footer restatement -- the two places the twin declares a
#: verdict to a reader who never scrolls.
_HTML_BIG = re.compile(r'<div class="big">\s*(.*?)\s*</div>', re.DOTALL)
_HTML_FOOTER_VERDICT = re.compile(r"Verdict:\s*([A-Z -]+?)\s*<", re.DOTALL)

#: An abbreviated git object name as this repository writes them.
_SHORT_SHA = re.compile(r"\b([0-9a-f]{7})\b")


def html_to_text(html: str) -> str:
    """Visible text of an HTML page, with style and script bodies removed."""
    return _HTML_TAG.sub(" ", _HTML_STYLE.sub(" ", html))


def headline_verdict_markdown(text: str) -> str | None:
    """The verdict the Markdown page declares NOW, ignoring struck-through history.

    Read from the `Verdict` section rather than from the first token in the file, because
    the page opens by quoting the verdict it is retracting -- which is exactly what the
    preservation rule asks it to do.
    """
    live = _MD_STRUCK.sub(" ", text)
    for section in reversed(markdown_sections(live)):
        heading = section[0][1]
        if not heading.lstrip("#").strip().endswith("Verdict"):
            continue
        body = " ".join(line for _, line in section[1:])
        found = _VERDICT_TOKEN.search(body)
        if found:
            return found.group(1)
    return None


def headline_verdicts_html(html: str) -> list[str]:
    """Every verdict the HTML twin declares in a headline position."""
    declared: list[str] = []
    for raw in _HTML_BIG.findall(html) + _HTML_FOOTER_VERDICT.findall(html):
        found = _VERDICT_TOKEN.search(_HTML_TAG.sub("", raw).strip())
        if found:
            declared.append(found.group(1))
    return declared


def twin_verdict_disagreements(md_text: str, html_text: str) -> list[str]:
    """Every way the two syntaxes of the verdict page contradict each other.

    A pure function over the two texts so the negative controls below can drive it with
    SYNTHETIC pages. A checker only ever observed returning `[]` is indistinguishable from
    `return []`.
    """
    problems: list[str] = []

    md_verdict = headline_verdict_markdown(md_text)
    if md_verdict is None:
        problems.append(
            "the Markdown verdict page declares no verdict in its `Verdict` section. "
            "Deleting the headline is the cheapest way to make a disagreement check pass, "
            "and a claim deleted is not a claim corrected."
        )
        return problems

    html_verdicts = headline_verdicts_html(html_text)
    if not html_verdicts:
        problems.append(
            "the HTML twin declares no verdict in either its headline slab or its footer, "
            "so a reader of the rendered page is told nothing while the Markdown says "
            f"{md_verdict!r}."
        )
    for declared in html_verdicts:
        if declared != md_verdict:
            problems.append(
                f"the HTML twin headlines {declared!r} while the Markdown declares "
                f"{md_verdict!r}. A judge opens whichever one renders in front of them, so "
                "a verdict corrected in only one syntax is still a false verdict shipped to "
                "somebody."
            )
    return problems


def twin_tree_disagreements(md_text: str, html_text: str) -> list[str]:
    """The twins must name the same tree.

    The HTML's masthead named `073dfea` while the Markdown named `d098721`. A page that
    misnames its own tree cannot be checked by anyone, and a stale SHA is the first thing
    about a verdict page to rot -- it went stale here three verifications running.
    """
    md_shas = set(_SHORT_SHA.findall(md_text))
    html_shas = set(_SHORT_SHA.findall(html_to_text(html_text)))
    orphaned = sorted(html_shas - md_shas)
    if orphaned:
        return [
            (
                f"the HTML twin names tree object(s) {orphaned} that appear nowhere in the "
                "Markdown. The Markdown is the authoritative side; re-read it and correct "
                "the HTML, never the reverse."
            )
        ]
    return []


def test_the_verdict_page_says_the_same_thing_in_both_of_its_syntaxes():
    """THE CHECK THAT WOULD HAVE CAUGHT THE WORST DOCUMENT DEFECT THIS REPOSITORY SHIPPED.

    `docs/state-of-the-build.html` printed `NO-GO` in a 44-pixel headline, and again in its
    footer, about a build whose sole named blocker had been fixed two commits earlier. The
    Markdown had been re-scored; the HTML had not; and because the two are maintained by
    hand with no generator between them, nothing in this tree could tell.
    """
    md_text = (REPO_ROOT / VERDICT_PAGE_MD).read_text(encoding="utf-8", errors="replace")
    html_text = (REPO_ROOT / VERDICT_PAGE_HTML).read_text(encoding="utf-8", errors="replace")

    problems = twin_verdict_disagreements(md_text, html_text) + twin_tree_disagreements(
        md_text, html_text
    )
    assert not problems, (
        "The verdict page contradicts itself across its two syntaxes:\n  "
        + "\n  ".join(problems)
        + f"\n{VERDICT_PAGE_MD} is authoritative. Correct the HTML to match it; do not "
        "resolve a disagreement by weakening the Markdown."
    )


def test_falsification__a_twin_that_headlines_a_retracted_verdict_is_caught():
    """The exact defect, synthesised. The control that makes the check above mean something."""
    markdown = (
        "# STATE OF THE BUILD\n\n## 11 · Verdict\n\n"
        "**CONDITIONAL GO — the conditions are named.**\n"
    )

    stale = '<div class="verdict"><div class="big">NO-GO</div></div>'
    assert twin_verdict_disagreements(markdown, stale), (
        "an HTML twin headlining NO-GO against a Markdown declaring CONDITIONAL GO was not "
        "caught, so the single worst document defect this repository has shipped would ship "
        "again unnoticed."
    )

    footer_only = "<footer><span>Verdict: NO-GO</span></footer>"
    assert twin_verdict_disagreements(markdown, footer_only), (
        "a stale verdict in the FOOTER was not caught. The footer is the last thing a "
        "reader sees and it restated NO-GO on the real page."
    )

    agreeing = (
        '<div class="big">CONDITIONAL GO</div><footer><span>Verdict: CONDITIONAL GO</span></footer>'
    )
    assert not twin_verdict_disagreements(markdown, agreeing), (
        "twins that agree were flagged, so the checker is banning the sentence rather than "
        "comparing the verdicts."
    )


def test_falsification__struck_history_is_not_read_as_a_live_contradiction():
    """The preservation rule and this ratchet must not pull in opposite directions.

    The page is REQUIRED to keep its superseded `NO-GO` visible, struck through. A checker
    that read that as a live verdict would be pushing every author to DELETE the history to
    get a green -- the precise move this repository forbids.
    """
    markdown = (
        "# STATE OF THE BUILD\n\n"
        "## Preserved\n\n"
        "> ~~This is a NO-GO for the sixth time.~~\n\n"
        "## 11 · Verdict\n\n"
        "**CONDITIONAL GO — the conditions are named.**\n"
    )
    assert headline_verdict_markdown(markdown) == "CONDITIONAL GO"
    agreeing = '<div class="big">CONDITIONAL GO</div>'
    assert not twin_verdict_disagreements(markdown, agreeing), (
        "an honestly struck-through NO-GO was read as the live verdict, which would reward "
        "deleting the history the preservation rule exists to keep."
    )


def test_falsification__a_deleted_headline_does_not_buy_a_green():
    """Removing the verdict is the cheapest way to end a disagreement. It must not work."""
    silent = "# STATE OF THE BUILD\n\n## 11 · Verdict\n\nThe build is in a state.\n"
    assert twin_verdict_disagreements(silent, '<div class="big">CONDITIONAL GO</div>'), (
        "a Markdown page with no verdict at all passed the twin check, so an author could "
        "clear a contradiction by deleting the claim instead of correcting it."
    )


def test_falsification__a_stale_tree_sha_in_the_twin_is_caught():
    """The masthead SHA rotted three verifications running. It is checked, not trusted."""
    markdown = "Local `HEAD` is `d098721`, four commits ahead of `7535670`.\n"
    stale = "<span>Tree <b>073dfea</b> + 48 modified</span>"
    assert twin_tree_disagreements(markdown, stale), (
        "the HTML naming a tree the Markdown never mentions was not caught, which is how "
        "the twin came to advertise a tree three verifications out of date."
    )
    current = "<span>Tree <b>d098721</b>, 4 ahead of <b>7535670</b></span>"
    assert not twin_tree_disagreements(markdown, current), (
        "twins naming the same tree were flagged, so the checker is not comparing SHAs."
    )


# ─────────────────────────────────────────────────────────────────────────────────────────
# 3. NEGATIVE CONTROLS. Each synthesises the defect and requires the checker to catch it.
#
# In the idiom of `test_cost_model.py::test_falsification__moving_one_tariff_constant_turns
# _the_reproduction_red`: the mutation must be a real mutation, and the checker must go red
# for the right reason. A checker that has only ever been observed returning [] is
# indistinguishable from `return []`.
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_falsification__an_input_tree_figure_sourced_to_the_deployed_zip_is_caught():
    """The exact sentence RULING 1 exists to correct, synthesised."""
    largest = arm64_shape()["before"]["web"]["largest_identity_object"]["bytes"]
    defective = (
        f"| I4 | Largest response the origin can emit | **{largest:,} B** — "
        "`zipfile` over `out/lambda/mainline-demo-api-arm64.zip` |\n"
    )
    caught = input_tree_figures_sourced_to_the_deployed_package("synthetic.md", defective)
    assert caught, (
        "the checker did not catch an INPUT-tree figure sourced to the deployed zip, which "
        "is the verbatim defect RULING 1 corrects. A checker that cannot go red here "
        "certifies nothing about the documents it sweeps."
    )

    # And the corrected form -- same digits, tree named -- must NOT be caught, or the
    # checker is just banning a number and the fix would be to delete the row.
    corrected = (
        f"| I4 | ~~Largest response the origin can emit~~ **Largest object in the packer's "
        f"INPUT tree** | **{largest:,} B** — `architectures[].before` |\n"
    )
    assert not input_tree_figures_sourced_to_the_deployed_package("synthetic.md", corrected), (
        "the checker flags the CORRECTED row too, so it is banning the digits rather than "
        "the mislabelling. RULING 1: the numbers do not move, the label and sourcing do."
    )

    # The marker must NAME A TREE. An earlier draft accepted the bare word "input", which
    # this fragment would have used to exempt itself while sourcing the figure to the zip.
    weasel = (
        f"| I4 | Largest response the origin can emit | **{largest:,} B** — the input to "
        "the model, per `zipfile` over `out/lambda/mainline-demo-api-arm64.zip` |\n"
    )
    assert input_tree_figures_sourced_to_the_deployed_package("synthetic.md", weasel), (
        "the bare word 'input' exempted a figure that names no tree at all, so the marker "
        "is a password rather than a statement of provenance."
    )


def test_falsification__a_stale_function_shape_attribute_is_caught():
    """`memory_size = 512` beside a citation of the artefact that says 256."""
    shape = declared_function_shape()
    for attribute, (declared, _) in shape.items():
        stale = "512" if declared not in ("512",) and declared.lstrip("-").isdigit() else "AWS_IAM"
        if stale == declared:
            stale = "9999"
        defective = (
            f"| I9 | Function shape | `mainline-demo-api`, `{attribute} = {stale}` "
            "(`evidence/deploy/terraform-plan-furl.txt`) |\n"
        )
        caught = function_shape_claims_that_contradict_the_plan("synthetic.md", defective)
        assert caught, (
            f"the checker did not catch `{attribute} = {stale}` on a line citing the plan "
            f"artefact, which declares `{attribute} = {declared}`. This is the defect "
            "RULING 4 settles, and a checker blind to it launders the stale value."
        )

    # The struck-and-corrected idiom the preservation rule REQUIRES must survive.
    memory, _ = shape["memory_size"]
    preserved = (
        f"| I9 | `mainline-demo-api` · `memory_size = `~~512~~ **{memory}** (`furl.txt:290`) |\n"
    )
    assert not function_shape_claims_that_contradict_the_plan("synthetic.md", preserved), (
        "the checker flags a value that is struck through and corrected in place. That is "
        "the idiom COST-BOUND.md's header mandates -- 'struck through or annotated in "
        "place, never removed' -- and flagging it would push authors to DELETE the "
        "history, which the preservation rule forbids."
    )

    # A value carrying a UNIT is prose about the attribute, not a quotation of the plan.
    # `LATENCY.md` records the founder's refused `timeout = 3 s` request and must be able
    # to keep doing so; the same figure written as bare HCL is a claim and is checked.
    refusal = "`mainline-demo-api`: the requested `timeout = 3 s` was refused as dishonest\n"
    assert not function_shape_claims_that_contradict_the_plan("synthetic.md", refusal), (
        "a recorded, refused REQUEST written with its unit was read as a quotation of the "
        "plan. That would make a document unable to record why a value was rejected."
    )
    as_hcl = "`mainline-demo-api` ships `timeout = 3` today\n"
    assert function_shape_claims_that_contradict_the_plan("synthetic.md", as_hcl), (
        "the same number written as bare HCL -- a claim about the shipping function -- was "
        "not caught, so the unit exclusion has swallowed the check rather than narrowing it"
    )


def test_falsification__an_assertion_that_the_guard_module_is_absent_is_caught():
    """The worst document in the repository, synthesised as a paragraph."""
    defective = (
        'The remaining gap is that `infra/envs/demo/main.tf` has **no `module "guard"` '
        "block**, so `var.alarm_actions` is still `[]` and every alarm on the demo "
        "function is actionless.\n"
    )
    caught = guard_absence_claims_while_the_block_is_in_the_tree("synthetic.md", defective)
    assert caught, (
        'the checker did not catch an assertion that `module "guard"` is absent while '
        "the block is in the tree at "
        f"infra/envs/demo/main.tf:{guard_block_line()}. That claim is checkable by a "
        "stranger in one grep, and a ratchet that misses it is decoration."
    )

    excused = defective.rstrip("\n") + (
        f" **CORRECTED 2026-08-14: the block is at "
        f"`infra/envs/demo/main.tf:{guard_block_line()}`.**\n"
    )
    assert not guard_absence_claims_while_the_block_is_in_the_tree("synthetic.md", excused), (
        "the checker flags a paragraph that cites the block's real location, so a document "
        "cannot record the superseded claim at all. The preservation rule requires it to."
    )

    # The exemption is derived from the TREE, so a citation of the wrong line does not
    # excuse anything. This is what stops the exemption rotting into a permanent hole.
    wrong = defective.rstrip("\n") + " (the block is at `infra/envs/demo/main.tf:1`.)\n"
    assert guard_absence_claims_while_the_block_is_in_the_tree("synthetic.md", wrong), (
        "a citation of the WRONG line excused the absence claim, so the exemption is a "
        "free-text password rather than a fact checked against the tree."
    )

    # A strikethrough that WRAPS ACROSS LINES is still a strikethrough. This control exists
    # because the checker got it wrong: it read `~~` a line at a time, saw one marker on
    # each of two lines, concluded nothing was struck, and reported OBSERVABILITY.md's
    # already-retracted sentence as a live claim.
    wrapped = (
        '~~The remaining gap is that `infra/envs/demo/main.tf` has **no `module "guard"`\n'
        "block**, so `var.alarm_actions` is still `[]`.~~\n"
    )
    assert not guard_absence_claims_while_the_block_is_in_the_tree("synthetic.md", wrapped), (
        "a strikethrough spanning two lines was not recognised, so the checker reports "
        "retracted sentences as live claims and punishes the authors who followed the "
        "preservation rule."
    )


def test_falsification__an_assertion_that_the_demo_route_is_unrouted_is_caught():
    """The PRE-FIX TEXT, verbatim. This is the control that makes the ratchet mean something.

    The fragment below is `docs/deploy/gate-run-contract.md` §9 as it stood before
    2026-08-14, copied character for character rather than paraphrased, because a control
    built from a paraphrase proves the checker catches the paraphrase.
    """
    pre_fix = (
        "* **`POST /v1/demo/gate-run` is not yet routed.** `app.py`'s route table\n"
        "  (`w3-api-core-reads`) declares the four kernel POSTs and no demo route, so the "
        "endpoint\n"
        '  404s until a `Route("POST", "/v1/demo/gate-run", "demo_gate_run")` and a\n'
        '  `SCHEMA_IDS["demo_gate_run"]` entry are added. The handler itself is complete and '
        "is\n"
        '  reachable today through `handle_transition("demo_gate_run", {}, {}, conn)`.\n'
    )
    caught = demo_route_absence_claims_while_the_route_is_in_the_table("synthetic.md", pre_fix)
    assert caught, (
        "the checker did not catch the verbatim pre-fix text of gate-run-contract.md §9, "
        "which asserts the demo route is unrouted while app.py declares it at line "
        f"{demo_gate_run_route_line()} and the deployed URL answers 503 dsn_unset to it. A "
        "ratchet that cannot go red against the sentence it was written for is decoration."
    )

    # The console shipped the same claim as one line of chrome. Same defect, no bullet.
    console_chrome = (
        "The route table declares the four kernel POSTs and no demo route, so the endpoint 404s.\n"
    )
    assert demo_route_absence_claims_while_the_route_is_in_the_table(
        "synthetic.md", console_chrome
    ), (
        "the clause the deployed console printed was not caught on its own. It reached a "
        "judge's screen without the word `gate-run` anywhere near it, which is exactly why "
        "the subject-and-claim proximity rule needs the standalone alternatives."
    )

    # The CORRECTED idiom the preservation rule REQUIRES must survive. A struck claim plus
    # the route's real line is the form this repository mandates, and flagging it would push
    # an author to DELETE the history instead of annotating it.
    preserved = (
        "* ~~**`POST /v1/demo/gate-run` is not yet routed** … so the endpoint 404s.~~\n"
        "  **CLOSED 2026-08-14: the route is declared at "
        f"`app.py:{demo_gate_run_route_line()}` and the deployed URL answers 503 "
        "`dsn_unset`.**\n"
    )
    assert not demo_route_absence_claims_while_the_route_is_in_the_table(
        "synthetic.md", preserved
    ), (
        "the checker flags a claim that is struck through and corrected in place with the "
        "route's real line. That is the idiom the preservation rule mandates, and flagging "
        "it would reward deleting the record that the gap was ever real."
    )

    # The exemption is derived from the TREE, so a citation of the WRONG line excuses
    # nothing. This is what stops it rotting into a permanent password.
    wrong = (
        "**`POST /v1/demo/gate-run` is not yet routed**, so the endpoint 404s. (The route is "
        "at `app.py:1`.)\n"
    )
    assert demo_route_absence_claims_while_the_route_is_in_the_table("synthetic.md", wrong), (
        "a citation of the WRONG line in app.py excused the absence claim, so the exemption "
        "is free text rather than a fact checked against the route table."
    )

    # ...and correct prose about a DIFFERENT path must not be caught, or the checker is
    # banning the digits `404` and RUNBOOK.md's troubleshooting section becomes unwritable.
    other_path = (
        "### The URL 404s but `/v1/health` is green\n\n"
        "The package's `web/` root is missing or empty, so `static_site.resolve()` 404s the "
        "URL a judge opens.\n"
    )
    assert not demo_route_absence_claims_while_the_route_is_in_the_table(
        "synthetic.md", other_path
    ), (
        "the checker flagged correct prose about a missing `web/` root. A check that is red "
        "against correct prose gets disabled, and then nothing is checked at all."
    )


def test_falsification__a_map_url_presented_as_servable_is_caught():
    """`GET …js.map` sold as a beat of an origin that answers 404 to it."""
    defective = (
        "| `asset_map` | `GET /assets/index-BjAGxrVJ.js.map` | largest **emittable** "
        "object, served by the shipping origin |\n"
    )
    caught = source_map_urls_presented_as_servable("synthetic.md", defective)
    assert caught, (
        "the checker did not catch a `.map` URL presented as servable while the deployed "
        "package holds "
        f"{deployed_source_map_entries()} source maps. `LATENCY.md` shipped exactly this "
        "row, and the origin answers 404 to it."
    )

    annotated = defective.rstrip("\n") + (
        "\n\n> **`GET /assets/index-BjAGxrVJ.js.map` against the shipping origin is a "
        "404.** The beat was measured against the packer's input tree.\n"
    )
    assert not source_map_urls_presented_as_servable("synthetic.md", annotated), (
        "the checker flags the ANNOTATED form too. RULING 3 keeps the measurement and "
        "annotates it, because COST-BOUND.md §0.1 row L1 is built on it -- flagging the "
        "annotation would push somebody to delete the row and orphan L1."
    )


def test_falsification__a_line_citation_pointing_at_the_wrong_line_is_caught():
    """The `furl.txt:329` rot, reconstructed from the artefact rather than remembered."""
    shape = declared_function_shape()
    _, real_line = shape["authorization_type"]
    wrong_line = real_line - 22 if real_line > 22 else real_line + 22
    defective = (
        f'the plan carries `authorization_type = "NONE"` '
        f"(`evidence/deploy/terraform-plan-furl.txt:{wrong_line}`)\n"
    )
    caught = path_citations_that_do_not_resolve("synthetic.md", defective)
    assert caught, (
        f"the checker did not catch a citation of furl.txt:{wrong_line} for "
        f"`authorization_type`, which the artefact declares at line {real_line}. This is "
        "the rot that is invisible until a reviewer follows the citation and stops "
        "trusting the page."
    )

    right = (
        f'the plan carries `authorization_type = "NONE"` '
        f"(`evidence/deploy/terraform-plan-furl.txt:{real_line}`)\n"
    )
    assert not path_citations_that_do_not_resolve("synthetic.md", right), (
        "the checker flags the CORRECT citation, so it is not reading the artefact and "
        "every citation it approves is approved by accident."
    )

    off_end = "see `evidence/deploy/terraform-plan-furl.txt:999999`\n"
    assert path_citations_that_do_not_resolve("synthetic.md", off_end), (
        "a citation past the end of the file was not caught"
    )
    absent = "see `evidence/deploy/there-is-no-such-artefact.txt:12`\n"
    assert path_citations_that_do_not_resolve("synthetic.md", absent), (
        "a citation into a file that does not exist was not caught"
    )


def test_falsification__an_asset_the_origin_does_not_serve_sold_as_served_is_caught():
    """The three-hashes defect, synthesised from the wire rather than remembered.

    The served name is READ from the walk and the stale one is CONSTRUCTED from it, so this
    control cannot pass by coincidence of literals and cannot rot when the artefact moves.
    """
    served = sorted(served_console_assets())
    assert served, "the walk records no served asset; the control below would be vacuous"
    real = next(name for name in served if name.endswith(".js"))
    stale = "assets/index-BjAGxrVJ.js"
    assert stale not in served, (
        "the origin now serves the very name this control uses as the stale one. Pick "
        "another and say why here; do not delete the control."
    )

    defective = (
        f"Check it yourself: `curl -s --compressed "
        f"https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/{stale}`\n"
    )
    assert console_assets_claimed_as_served_that_the_origin_does_not_serve(
        "synthetic.md", defective
    ), (
        f"a document telling a reader to fetch {stale} from the deployed origin was not "
        f"caught, while the origin serves {real}. A Vite asset name is a content hash: that "
        "URL is a 404, and the whole class of defect this checker exists for is a reader "
        "following a citation into nothing."
    )

    # The BEFORE-AND-AFTER form must survive, or the checker is banning a name rather than a
    # claim and the cheapest fix becomes deleting the record that the build ever moved.
    both = (
        f"| largest identity | `{stale}` (the stale record) | "
        f"**`{real}`** — what the deployed origin serves |\n"
    )
    assert not console_assets_claimed_as_served_that_the_origin_does_not_serve(
        "synthetic.md", both
    ), (
        "a row naming BOTH the superseded asset and the served one was flagged, so the "
        "checker cannot tell a correction from a stale claim and would push an author to "
        "delete the 'before'."
    )

    # ...and so must the annotated form the preservation rule mandates.
    annotated = defective.rstrip("\n") + (
        f"\n\n**CORRECTED 2026-08-15: the deployed origin serves `{real}`; the path above "
        "answers 404.**\n"
    )
    assert not console_assets_claimed_as_served_that_the_origin_does_not_serve(
        "synthetic.md", annotated
    ), "the annotated form was flagged, which rewards deleting the history over correcting it"

    # A line that names the stale asset WITHOUT claiming the origin hands it over is prose
    # about a package or about history, and several live documents legitimately carry it.
    history = f"The lane's declaration still pinned `{stale}` at 433,396 B.\n"
    assert not console_assets_claimed_as_served_that_the_origin_does_not_serve(
        "synthetic.md", history
    ), (
        "the checker flagged a line that names the old asset without claiming the origin "
        "serves it. A check that is red against correct prose gets disabled, and then "
        "nothing is checked at all."
    )

    # SHAPE NOTATION IS NOT A CLAIM. `RUNBOOK.md` §7 teaches a reader the FORM of the request
    # with `index-XXXXXXXX.js`, beside a `<id>` hostname. This was a real false positive
    # before the exemption existed, on a live page, which is how the exemption was found.
    shape = (
        "curl -sSI https://<id>.lambda-url.ap-southeast-1.on.aws/assets/index-XXXXXXXX.js "
        "| grep -i content-type\n"
    )
    assert not console_assets_claimed_as_served_that_the_origin_does_not_serve(
        "synthetic.md", shape
    ), (
        "shape notation was read as a content hash. A run of one repeated character is "
        "nobody's Vite hash, and a checker red against a worked example of the request form "
        "gets deleted rather than obeyed."
    )
    # ...and the exemption must not swallow a real hash, or it is a password.
    real_shape = shape.replace("index-XXXXXXXX.js", stale.removeprefix("assets/"))
    assert console_assets_claimed_as_served_that_the_origin_does_not_serve(
        "synthetic.md", real_shape
    ), (
        "the same worked example with a REAL stale hash in it was not caught, so the "
        "placeholder exemption has swallowed the check rather than narrowing it"
    )

    # A LINE THAT REFUTES ITSELF IS NOT A CLAIM. `LATENCY.md` carries exactly this sentence,
    # and it was the second false positive this checker produced against a live page.
    refuted = f"> **`GET /{stale}.map` against the shipping origin is a 404.**\n"
    assert not console_assets_claimed_as_served_that_the_origin_does_not_serve(
        "synthetic.md", refuted
    ), (
        "a line whose whole content is that the origin answers 404 to the object was "
        "reported as claiming the origin serves it. RULING 3 keeps that beat annotated; "
        "flagging the annotation is how a document loses its history."
    )


def test_falsification__a_transport_claim_the_wire_denies_is_caught():
    """The founder's screen, synthesised — and the inverse, so the check is not one-sided."""
    mode = deployed_transport_mode()
    assert mode in _TRANSPORT_WORD, "the walk records no transport; the control is vacuous"
    contradiction = "LIVE" if mode == "REPLAY" else "REPLAY"

    defective = (
        f"The artefact deployed on that origin is a **{contradiction}** build, so the console "
        "is talking to its own kernel.\n"
    )
    assert deployed_transport_claims_that_contradict_the_wire("synthetic.md", defective), (
        f"a document giving the deployed artefact the transport {contradiction!r} was not "
        f"caught, while the served bytes select {mode!r}. That sentence is the founder's "
        "complaint written down as a claim, and a ratchet blind to it is decoration."
    )

    truthful = (
        f"The artefact deployed on that origin is a **{mode}** build, and every byte on the "
        "screen is what that implies.\n"
    )
    assert not deployed_transport_claims_that_contradict_the_wire("synthetic.md", truthful), (
        "the checker flags the TRUE statement too, so it is banning a word rather than "
        "comparing a claim against the wire."
    )

    # Prose about what a CORRECT build would do is not a claim about today, and this
    # repository writes a great deal of it. Flagging it would make the argument unwritable.
    hypothetical = (
        f"With a correctly built {contradiction} console in front of that handler, a judge "
        "presses a control and the console issues the request to its own origin.\n"
    )
    assert not deployed_transport_claims_that_contradict_the_wire("synthetic.md", hypothetical), (
        "prose about what a corrected build WOULD do was read as a claim about the deployed "
        "artefact. The subject and the claim must be in one sentence."
    )

    # The struck-and-corrected idiom survives, as everywhere else in this file.
    preserved = (
        f"~~The artefact deployed on that origin is a {contradiction} build.~~ "
        f"**CORRECTED 2026-08-15: the served bytes select {mode}.**\n"
    )
    assert not deployed_transport_claims_that_contradict_the_wire("synthetic.md", preserved), (
        "the checker flags a claim struck through and corrected in place, which is the idiom "
        "the preservation rule mandates."
    )


def test_falsification__a_corpus_that_never_publishes_the_judge_walk_is_caught():
    """Removing the command is the cheapest way to stop having to keep it true. It must fail."""
    silent = {
        "docs/deploy/RUNBOOK.md": "### 5.10 What the URL serves today\n\nGET / -> 200.\n",
        "docs/deploy/JUDGE-PACK.md": "## 1 The demo URL\n\ncurl the URL yourself.\n",
    }
    assert not documents_publishing_the_judge_walk(silent), (
        "a corpus that mentions the walk nowhere was reported as publishing it, so the "
        "anti-deletion assertion above could never go red"
    )

    mention_only = dict(silent)
    mention_only["docs/deploy/RUNBOOK.md"] += (
        "\nThere is a program at `scripts/deploy/judge_walk.py` if you want it.\n"
    )
    assert not documents_publishing_the_judge_walk(mention_only), (
        "a page that names the script WITHOUT `--base-url` counted as publishing a command. "
        "A mention is not an instruction, and the walk takes exactly one required input."
    )

    published = dict(silent)
    published["docs/deploy/RUNBOOK.md"] += (
        "\n```bash\npython scripts/deploy/judge_walk.py --base-url https://example.invalid\n```\n"
    )
    assert documents_publishing_the_judge_walk(published) == ["docs/deploy/RUNBOOK.md"], (
        "a page carrying both the script path and `--base-url` was not recognised, so the "
        "assertion above cannot be satisfied by doing the right thing"
    )


def test_falsification__the_checkers_are_not_uniformly_blind_or_uniformly_red():
    """A last guard: every checker must return [] on clean text and non-[] on its defect.

    Written because the cheapest broken checker is not one that always returns [] -- the
    controls above catch that -- but one that returns [] because its regex never matched
    anything at all, in which case it would also stay green on the real documents for the
    wrong reason.
    """
    clean = (
        "# A clean page\n\nThe deployed package holds 114 entries and 1,274,342 B, and "
        "`evidence/deploy/terraform-plan-furl.txt:315` declares `timeout = 14` for "
        "`mainline-demo-api`.\n"
    )
    for checker in (
        input_tree_figures_sourced_to_the_deployed_package,
        function_shape_claims_that_contradict_the_plan,
        guard_absence_claims_while_the_block_is_in_the_tree,
        demo_route_absence_claims_while_the_route_is_in_the_table,
        source_map_urls_presented_as_servable,
        path_citations_that_do_not_resolve,
        console_assets_claimed_as_served_that_the_origin_does_not_serve,
        deployed_transport_claims_that_contradict_the_wire,
    ):
        assert checker("clean.md", clean) == [], (
            f"{checker.__name__} reports an offence on text that carries none, so its "
            "reds on the real documents cannot be trusted either"
        )


@pytest.mark.parametrize("relative", sorted(set(SWEPT_DOCS)))
def test_every_live_document_is_readable_utf8(relative):
    """Cheap, but it is the precondition every sweep above depends on.

    Parametrised over `SWEPT_DOCS` rather than `LIVE_DOCS` since 2026-08-15: the sweeps read
    the wider set, so the wider set is what must be readable. Every `LIVE_DOC` is still
    covered -- the subset relation is asserted above.
    """
    path = REPO_ROOT / relative
    assert path.exists(), f"{relative} is in SWEPT_DOCS and not in the tree"
    path.read_text(encoding="utf-8")
