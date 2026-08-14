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


# ─────────────────────────────────────────────────────────────────────────────────────────
# 2. THE RATCHETS. Every one of these reads the artefact, then reads the prose.
# ─────────────────────────────────────────────────────────────────────────────────────────


def _sweep(checker) -> list[str]:
    found: list[str] = []
    for relative in LIVE_DOCS:
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
    }
    assert required <= set(LIVE_DOCS), (
        f"LIVE_DOCS no longer covers {sorted(required - set(LIVE_DOCS))}. These are the "
        "documents this wave's measurements falsified; removing one from the sweep is "
        "lowering the aperture to obtain a green, which is the same move as lowering a "
        "floor."
    )
    assert any(relative.startswith("docs/submission/") for relative in LIVE_DOCS), (
        "LIVE_DOCS covers no submission document. The stale plan count in "
        "docs/submission/RULES-MATRIX.md was invisible to this ratchet for exactly that "
        "reason."
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
        source_map_urls_presented_as_servable,
        path_citations_that_do_not_resolve,
    ):
        assert checker("clean.md", clean) == [], (
            f"{checker.__name__} reports an offence on text that carries none, so its "
            "reds on the real documents cannot be trusted either"
        )


@pytest.mark.parametrize("relative", sorted(LIVE_DOCS))
def test_every_live_document_is_readable_utf8(relative):
    """Cheap, but it is the precondition every sweep above depends on."""
    path = REPO_ROOT / relative
    assert path.exists(), f"{relative} is in LIVE_DOCS and not in the tree"
    path.read_text(encoding="utf-8")
