#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The readability gate on `README.md`. Standard library only, no network.

    .venv/Scripts/python.exe scripts/submission/check_readme_readability.py
    .venv/Scripts/python.exe scripts/submission/check_readme_readability.py --self-test
    .venv/Scripts/python.exe scripts/submission/check_readme_readability.py --check FILE
    .venv/Scripts/python.exe scripts/submission/check_readme_readability.py --check-tracked
    .venv/Scripts/python.exe scripts/submission/check_readme_readability.py --list-families

WHAT THIS IS FOR. `scripts/demo/claim_hygiene.py` asks whether a sentence is TRUE.
`scripts/submission/check_submission_prose.py` asks whether a submission sentence overclaims.
Neither asks whether a stranger can READ the page. That is a third question, it is the one the
founder's sentence names -- *"even after going through your briefing, I'm finding a very hard
time to understand"* -- and this program is the only thing in the tree that asks it.

It does not ask whether the prose is good. It asks seven mechanical questions a person cannot
be trusted to ask about their own writing after four days inside a project.

SEVEN FAMILIES, and why each one exists:

  MKT   a banned marketing word. This product's entire claim is that it does not overstate.
        One `seamless` costs more credibility than a missing feature.
  JRG   a banned jargon term, or one of the two permitted-once terms used twice. These are
        words that mean something precise to five people and nothing to everybody else.
  GLS   a term from the glossary list used for the first time with no gloss near it.
  LEN   a sentence over 35 words, or a section A whose mean sentence runs over 22 words.
  L1    layer 1 -- the file's first sixty seconds -- over its line budget.
  BUD   the whole file over its line or byte ceiling.
  LNK   a relative link that resolves to nothing. With `--check-tracked`, also a link that
        resolves on this disk but is not in the tree a judge clones.

TWO DECISIONS IN THE IMPLEMENTATION THAT A READER SHOULD BE ABLE TO ARGUE WITH.

*One: "line" means the logical line, not the wrapped one.* `README.md` is hard-wrapped at
about 110 columns, so where a physical line ends is a fact about the author's editor and not
about the prose. Every family below therefore runs over BLOCKS -- a paragraph, a table row, a
list item, joined back into one string -- and the glossed-term family narrows further, to the
SENTENCE the term first appears in. Checking the physical line would let a gloss pass or fail
on where somebody pressed Enter.

*Two: the ban is on the word as prose, not on the word inside an identifier.* `defeater` is
banned; `resolve_defeater_vocabulary` is the name of a function a reader can grep for, and
renaming the world to satisfy a prose rule would be the tail wagging the dog. Word boundaries
in Python regex treat `_` as a word character, so the identifier does not match and the bare
word does. Same rule for `epoch` against `gate_epoch`.

A CHECK THAT HAS NEVER BEEN RED ASSERTS NOTHING. `--self-test` plants one violation per family
in a temporary tree and requires this program to fire on every one. It exits 0 only if all
seven went red. Run it whenever you change a pattern here.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── The budgets, from docs/submission/readme-plan.md §2 and R1 ────────────────────────────
MAX_LINES = 340
MAX_BYTES = 26_000
#: Layer 1 is the title through the end of section C -- everything before `## How it works`.
LAYER_1_ENDS_BEFORE = "## How it works"
MAX_LAYER_1_LINES = 109
MAX_SENTENCE_WORDS = 35
MAX_SECTION_A_MEAN_WORDS = 22.0
#: Section A is the opening story: the title through the heading that closes it.
SECTION_A_ENDS_BEFORE = "## What this is"

# ── MKT · banned outright, readme-plan.md §0 ─────────────────────────────────────────────
MARKETING = (
    "revolutionary",
    "seamless",
    "seamlessly",
    "unprecedented",
    "cutting-edge",
    "game-changing",
    "powerful",
    "robust",
    "effortlessly",
    "effortless",
    "blazing",
)

# ── JRG · banned outright, readme-plan.md R4 ─────────────────────────────────────────────
#: Each entry is (label, pattern). `MUS` is banned only as a bare capitalised acronym, which
#: is what a reader cannot decode; "minimal unsatisfiable subset" spelled out is allowed.
JARGON: tuple[tuple[str, str], ...] = (
    ("canonicalisation", r"\bcanonicalisation\b|\bcanonicalization\b"),
    ("defeater", r"\bdefeater\b|\bdefeaters\b"),
    ("archival bond", r"\barchival bond\b"),
    ("fixity", r"\bfixity\b"),
    ("MUS as a bare acronym", r"(?<![A-Za-z0-9_/-])MUS(?![A-Za-z0-9_-])"),
)

#: R4 lets these two appear once each, in layer 2, glossed inline. Twice is a tic.
PERMITTED_ONCE = ("diachronic", "synchronic")

#: R4 bans `C-SPANN` outside the platform table. A table row starts with a pipe; anywhere
#: else the acronym is unexplained to every reader who is not a CockroachDB engineer.
C_SPANN = re.compile(r"C-SPANN")

# ── GLS · readme-plan.md R4, the glossary discipline ─────────────────────────────────────
#: Each term must be glossed where it is first used. The pattern finds the term; the gloss is
#: looked for in the SENTENCE that first use falls in.
GLOSSED_TERMS: tuple[tuple[str, str], ...] = (
    ("CHECK constraint", r"`?CHECK`?\s+constraint"),
    ("projection", r"\bprojections?\b"),
    ("blame ancestry", r"\bblame ancestry\b"),
    ("obligation", r"\bobligations?\b"),
    ("disposition", r"\bdispositions?\b"),
    ("epoch", r"\bepochs?\b"),
    ("SQLSTATE", r"\bSQLSTATE\b"),
    ("changefeed", r"\bchangefeeds?\b"),
    ("vector index", r"\bvector index\b"),
)

#: What counts as a defining marker. Deliberately short: an em dash, a colon, a copula, the
#: word `means`, the phrase `we call`, or a comma sitting immediately after the term (the
#: appositive, as in "*blame ancestry*, the chain of past events that wrote the rule"). A
#: colon inside an evidence pointer -- `[src: ...]` -- or inside a URL is not a definition
#: and is stripped before this runs.
GLOSS_MARKERS: tuple[tuple[str, str], ...] = (
    ("em dash", r"—"),
    ("colon", r":"),
    ("copula", r"\b(?:is|are|was|were)\b"),
    ("means", r"\bmeans?\b"),
    ("we call", r"\bwe call\b"),
)
#: The appositive: the term, then a comma within one word of it.
APPOSITIVE = r",|\s\w+,"

#: NOT ADDED, ON PURPOSE, and recorded here so the next person does not spend the hour again.
#: `A vector index finds the most similar records without comparing every one.` is a real gloss
#: that this family misses -- no dash, no colon, no copula, no comma. The tempting fix is a
#: "definitional opener" marker: indefinite article, then the term, then a present-tense verb.
#: It does not survive its own counter-example. `A vector index appears beside every beat and
#: nobody ever says what one is` satisfies all three conditions and glosses nothing, so the
#: marker would turn a red into a green while the reader stayed lost. Narrowing it to a list of
#: *defining* verbs only moves the problem, because that list has no end.
#:
#: So the rule stands and the PROSE moved instead: the README now glosses with a copula. A gate
#: relaxed until the page passes measures the gate, not the page.

SRC_POINTER = re.compile(r"\[src:[^\]]*\]")
URL = re.compile(r"https?://\S+")
CODE_SPAN = re.compile(r"`[^`]*`")
MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
FOOTNOTE_DEF = re.compile(r"^\[\^[^\]]+\]:")
HEADING = re.compile(r"^#{1,6}\s")
TABLE_ROW = re.compile(r"^\s*\|")
FENCE = re.compile(r"^\s*```")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Finding:
    family: str
    line: int
    detail: str
    why: str


# ─────────────────────────────────────────────────────────────────── text preparation ────


def strip_fences(lines: list[str]) -> list[tuple[int, str]]:
    """Drop fenced code blocks. Returns (1-based line number, text) for what survives."""
    kept: list[tuple[int, str]] = []
    inside = False
    for number, text in enumerate(lines, start=1):
        if FENCE.match(text):
            inside = not inside
            continue
        if not inside:
            kept.append((number, text))
    return kept


def blocks(lines: list[str]) -> list[tuple[int, str]]:
    """Logical lines: paragraphs joined, table rows and list items kept whole.

    A hard-wrapped paragraph is one thought, so it is one block. A table row is its own
    block because a row is read on its own. Headings, footnote definitions and list items
    each stand alone for the same reason.
    """
    out: list[tuple[int, str]] = []
    buffer: list[str] = []
    start = 0
    for number, text in strip_fences(lines):
        stripped = text.strip()
        standalone = (
            not stripped
            or TABLE_ROW.match(text)
            or HEADING.match(text)
            or FOOTNOTE_DEF.match(text)
            or stripped.startswith(("* ", "- ", "> "))
        )
        if standalone:
            if buffer:
                out.append((start, " ".join(buffer)))
                buffer = []
            if stripped:
                out.append((number, stripped))
            continue
        if not buffer:
            start = number
        buffer.append(stripped)
    if buffer:
        out.append((start, " ".join(buffer)))
    return out


EMPHASIS = re.compile(r"\*{1,2}|_{1,2}")


def prose_for_terms(text: str) -> str:
    """The sentence as a reader meets it: evidence machinery gone, words intact.

    Backticks come off rather than the word inside them, because ``a `CHECK` constraint`` is
    a reader meeting the term `CHECK constraint`, and the glossary family has to see it.
    """
    text = SRC_POINTER.sub(" ", text)
    text = URL.sub(" ", text)
    text = MD_LINK.sub(lambda m: m.group(1), text)
    text = text.replace("`", "")
    return EMPHASIS.sub("", text)


def prose_for_length(text: str) -> str:
    """The sentence as a word count: a link is one word, a code literal is one word.

    Both become a capitalised placeholder rather than a blank. Deleting them outright made
    the next sentence start with a lowercase word, the splitter refused to split there, and
    two ordinary sentences were reported as one 53-word monster. A placeholder is the fix.
    """
    text = SRC_POINTER.sub(" ", text)
    text = URL.sub(" Link ", text)
    text = MD_LINK.sub(" Doc ", text)
    text = CODE_SPAN.sub(" Code ", text)
    return EMPHASIS.sub("", text)


def sentences(text: str) -> list[str]:
    """Split on sentence-final punctuation followed by a space and a capital or a quote."""
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[\"'“(*_A-Z0-9])", text)
    return [part for part in parts if part.strip()]


def word_count(sentence: str) -> int:
    return len(re.findall(r"[A-Za-z0-9À-ɏ][A-Za-z0-9À-ɏ'’.-]*", sentence))


# ──────────────────────────────────────────────────────────────────────── the families ───


def check_marketing(units: list[tuple[int, str]]) -> list[Finding]:
    findings = []
    for number, text in units:
        for word in MARKETING:
            if re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE):
                findings.append(
                    Finding(
                        "MKT",
                        number,
                        f"{word!r} in: {text[:90]}",
                        "banned outright: this page's claim is that it does not overstate",
                    )
                )
    return findings


def check_jargon(units: list[tuple[int, str]], raw: list[str]) -> list[Finding]:
    findings = []
    for number, text in units:
        for label, pattern in JARGON:
            if re.search(pattern, text):
                findings.append(
                    Finding(
                        "JRG",
                        number,
                        f"{label!r} in: {text[:90]}",
                        "banned by readme-plan.md R4: precise to five readers, opaque to the rest",
                    )
                )
    for word in PERMITTED_ONCE:
        # Occurrences, not blocks: two uses inside one paragraph is still two uses, and an
        # earlier version of this check counted blocks and therefore missed exactly that.
        hits = [
            (n, len(re.findall(rf"\b{word}\b", t, re.IGNORECASE)))
            for n, t in units
            if re.search(rf"\b{word}\b", t, re.IGNORECASE)
        ]
        total = sum(count for _, count in hits)
        if total > 1:
            findings.append(
                Finding(
                    "JRG",
                    hits[0][0],
                    f"{word!r} used {total} times, on lines {[n for n, _ in hits]}",
                    "R4 permits it once, glossed inline; a second use is a tic, not a term",
                )
            )
    for number, text in units:
        if C_SPANN.search(text) and not TABLE_ROW.match(text):
            findings.append(
                Finding(
                    "JRG",
                    number,
                    f"'C-SPANN' outside a table row: {text[:90]}",
                    "R4 allows the acronym only inside the platform table",
                )
            )
    return findings


def check_glosses(units: list[tuple[int, str]]) -> list[Finding]:
    """Every glossary term must carry a defining marker where it is first used."""
    findings = []
    for label, pattern in GLOSSED_TERMS:
        compiled = re.compile(pattern, re.IGNORECASE if label != "SQLSTATE" else 0)
        first: tuple[int, str, re.Match[str]] | None = None
        for number, text in units:
            clean = prose_for_terms(text)
            match = compiled.search(clean)
            if match:
                first = (number, clean, match)
                break
        if first is None:
            continue
        number, clean, _match = first
        window = next((s for s in sentences(clean) if compiled.search(s)), clean)
        marked = [name for name, marker in GLOSS_MARKERS if re.search(marker, window)]
        inside = compiled.search(window)
        if inside and re.match(APPOSITIVE, window[inside.end() :]):
            marked.append("appositive comma")
        if not marked:
            findings.append(
                Finding(
                    "GLS",
                    number,
                    f"{label!r} first used with no gloss: {window[:120]}",
                    "R4: glossed in twelve words or fewer at first use, or it does not appear",
                )
            )
    return findings


def check_lengths(units: list[tuple[int, str]], section_a: list[tuple[int, str]]) -> list[Finding]:
    findings = []
    for number, text in units:
        if TABLE_ROW.match(text) or HEADING.match(text) or FOOTNOTE_DEF.match(text):
            continue
        for sentence in sentences(prose_for_length(text)):
            count = word_count(sentence)
            if count > MAX_SENTENCE_WORDS:
                findings.append(
                    Finding(
                        "LEN",
                        number,
                        f"{count} words: {sentence[:110]}",
                        f"R12: no sentence over {MAX_SENTENCE_WORDS} words in layers 1 and 2",
                    )
                )
    counts = [
        word_count(s)
        for _, text in section_a
        if not (TABLE_ROW.match(text) or HEADING.match(text))
        for s in sentences(prose_for_length(text))
    ]
    if counts:
        mean = sum(counts) / len(counts)
        if mean > MAX_SECTION_A_MEAN_WORDS:
            findings.append(
                Finding(
                    "LEN",
                    1,
                    f"section A mean sentence is {mean:.1f} words over {len(counts)} sentences",
                    f"R12: the opening's mean stays at or under {MAX_SECTION_A_MEAN_WORDS:.0f}",
                )
            )
    return findings


def check_budgets(text: str, lines: list[str]) -> list[Finding]:
    findings = []
    total_lines = len(lines)
    total_bytes = len(text.encode("utf-8"))
    if total_lines > MAX_LINES:
        findings.append(
            Finding("BUD", total_lines, f"{total_lines} lines", f"R1 ceiling is {MAX_LINES}")
        )
    if total_bytes > MAX_BYTES:
        findings.append(
            Finding(
                "BUD",
                total_lines,
                f"{total_bytes} bytes, {total_bytes - MAX_BYTES} over",
                f"R1 ceiling is {MAX_BYTES} bytes",
            )
        )
    try:
        end = next(i for i, line in enumerate(lines) if line.startswith(LAYER_1_ENDS_BEFORE))
    except StopIteration:
        return findings
    if end > MAX_LAYER_1_LINES:
        findings.append(
            Finding(
                "L1",
                end,
                f"layer 1 runs {end} lines",
                f"R1: the first sixty seconds is at most {MAX_LAYER_1_LINES} lines",
            )
        )
    return findings


def relative_targets(text: str) -> list[tuple[int, str, str]]:
    """(line number, label, path) for every link that is not http, mailto or an anchor."""
    out = []
    for number, line in enumerate(text.split("\n"), start=1):
        for label, target in MD_LINK.findall(line):
            if re.match(r"^(?:https?:|mailto:|#)", target.strip()):
                continue
            path = target.split("#", 1)[0].split("?", 1)[0].strip()
            if path:
                out.append((number, label, path))
    return out


def check_links(text: str, source: Path, root: Path) -> list[Finding]:
    """Every relative link must resolve to a path that exists. R8 invariant 6."""
    findings = []
    for number, label, path in relative_targets(text):
        if not (source.parent / path).resolve().exists() and not (root / path).exists():
            findings.append(
                Finding(
                    "LNK",
                    number,
                    f"[{label[:40]}]({path}) resolves to nothing",
                    "R8 invariant 6: every relative link resolves to a path that exists",
                )
            )
    return findings


def check_tracked(text: str, root: Path) -> list[Finding]:
    """Every relative link must resolve in the tree a JUDGE CLONES, not on the author's disk.

    Not part of the brief and switched on with `--check-tracked`, because it shells out to
    `git` and a checker that needs a repository is a narrower tool than one that does not.
    It earns its place anyway: it is what caught `qa/live2.json`, section C's only artefact
    for the second use case, sitting untracked where a judge would find a dead link.
    """
    import subprocess  # noqa: PLC0415 -- only needed on this path, and only with a repo

    try:
        listing = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return [Finding("LNK", 1, "git ls-files did not run", "cannot check what a clone gets")]

    tracked = {line.strip() for line in listing.split("\n") if line.strip()}
    findings = []
    for number, label, path in relative_targets(text):
        stem = path.rstrip("/")
        if stem in tracked or any(f.startswith(stem + "/") for f in tracked):
            continue
        findings.append(
            Finding(
                "LNK",
                number,
                f"[{label[:40]}]({path}) is not tracked by git",
                "it resolves on this disk and not in the tree a judge clones",
            )
        )
    return findings


# ───────────────────────────────────────────────────────────────────────────── driver ────


def check_file(path: Path, root: Path, *, tracked: bool = False) -> list[Finding]:
    raw = path.read_text(encoding="utf-8")
    # Blank the comments OUT rather than delete them, so a reported line number is the line
    # number in the file on disk. The budgets are measured on `raw` for the same reason:
    # a ceiling is about the file a judge downloads, not about a filtered view of it.
    text = HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), raw)
    lines = text.rstrip("\n").split("\n")
    units = blocks(lines)
    try:
        cut = next(i for i, line in enumerate(lines) if line.startswith(SECTION_A_ENDS_BEFORE))
    except StopIteration:
        cut = len(lines)
    section_a = [(n, t) for n, t in units if n <= cut]

    findings: list[Finding] = []
    findings += check_marketing(units)
    findings += check_jargon(units, lines)
    findings += check_glosses(units)
    findings += check_lengths(units, section_a)
    findings += check_budgets(raw, raw.rstrip("\n").split("\n"))
    findings += check_links(raw, path, root)
    if tracked:
        findings += check_tracked(raw, root)
    return findings


FAMILIES = ("MKT", "JRG", "GLS", "LEN", "L1", "BUD", "LNK")


def report(path: Path, findings: list[Finding]) -> None:
    print(f"== readability gate over {path.as_posix()}")
    if not findings:
        print(f"  {len(FAMILIES)} families, 0 findings")
        return
    for finding in sorted(findings, key=lambda f: (f.family, f.line)):
        print(f"  [{finding.family}] {path.name}:{finding.line}: {finding.detail}")
        print(f"      {finding.why}")
    print(f"  {len(findings)} finding(s) across {len({f.family for f in findings})} family(ies)")


# ─── the self-test: one planted violation per family, and it must fire on every one ───────

PLANTED = """<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PLANTED

One planted MKT violation, a seamless and robust answer to the problem.

One planted JRG violation, the defeater resolved by canonicalisation of the archival bond
beside a bare MUS and its fixity. C-SPANN appears here too, outside any table row.

Planted twice, this gate runs diachronic and the diachronic reading wins, while a synchronic
gate and a synchronic check remain different things.

A vector index appeared beside every beat and nobody ever explained anything about it.

One planted LEN violation, a deliberately overlong sentence that exists so the length family
has something to fire on, and it therefore keeps going well past the thirty-five word ceiling
by adding one more clause and then another clause and then a final trailing clause.

Planted LNK, see [a file that is not there](docs/this-path-does-not-exist.md) for details.

## What this is

Filler.

## How it works

Filler, so that layer 1 has an end.
"""


def self_test() -> int:
    """Plant one violation per family and require every family to go red."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "PLANTED.md"
        # L1 and BUD need bulk, not a sentence: pad past both ceilings before layer 1 ends.
        filler = "\n".join(f"Padding line {n}, which is prose and nothing else." for n in range(400))
        body = PLANTED.replace("## How it works", filler + "\n\n## How it works")
        target.write_text(body, encoding="utf-8")
        findings = check_file(target, root)

    fired = {finding.family for finding in findings}
    print("== self-test: one planted violation per family")
    for family in FAMILIES:
        status = "RED  " if family in fired else "GREEN"
        example = next((f for f in findings if f.family == family), None)
        print(f"  {status} {family}  {example.detail[:88] if example else 'DID NOT FIRE'}")
    print(f"  {len(findings)} finding(s) in the planted tree, in full:")
    for finding in sorted(findings, key=lambda f: (f.family, f.line)):
        print(f"    [{finding.family}] line {finding.line}: {finding.detail[:96]}")
    missing = [family for family in FAMILIES if family not in fired]
    if missing:
        print(f"  FAILED: {', '.join(missing)} never fired. A check that cannot go red asserts nothing.")
        return EXIT_FINDINGS
    print(f"  all {len(FAMILIES)} families fired")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_readme_readability",
        description="Seven mechanical readability questions about README.md.",
    )
    parser.add_argument("--check", type=Path, nargs="*", default=None, help="files to check")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    parser.add_argument(
        "--check-tracked",
        action="store_true",
        help="also require every relative link to be tracked by git",
    )
    parser.add_argument("--self-test", action="store_true", help="prove every family can go red")
    parser.add_argument("--list-families", action="store_true", help="print the families and exit")
    args = parser.parse_args(argv)

    if args.list_families:
        for family, why in zip(
            FAMILIES,
            (
                "banned marketing word",
                "banned jargon, or a permitted-once word used twice",
                "a glossary term used first with no gloss beside it",
                "a sentence over 35 words, or section A's mean over 22",
                "layer 1 over its line budget",
                "the file over its line or byte ceiling",
                "a relative link that resolves to nothing",
            ),
            strict=True,
        ):
            print(f"  {family}  {why}")
        return EXIT_OK

    if args.self_test:
        return self_test()

    targets = args.check or [args.root / "README.md"]
    total = 0
    for path in targets:
        if not path.exists():
            print(f"== readability gate over {path.as_posix()}")
            print("  ABSENT -- not scanned, and therefore not passed")
            total += 1
            continue
        findings = check_file(path, args.root, tracked=args.check_tracked)
        report(path, findings)
        total += len(findings)
    return EXIT_OK if total == 0 else EXIT_FINDINGS


if __name__ == "__main__":
    sys.exit(main())
