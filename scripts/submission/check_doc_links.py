#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Prove that every path a judge can click, or is invited to open, actually exists.

    python scripts/submission/check_doc_links.py              # the full check
    python scripts/submission/check_doc_links.py --self-test  # prove it can go red
    python scripts/submission/check_doc_links.py --list-targets
    python scripts/submission/check_doc_links.py --check FILE...
    python scripts/submission/check_doc_links.py --links-only
    python scripts/submission/check_doc_links.py --cites-only

WHAT THIS IS FOR, IN ONE PARAGRAPH. Six documents in this repository are the ones a contest
judge actually opens. Every one of them is full of two kinds of pointer: a Markdown link the
judge clicks, and a bare file path quoted in the prose as the evidence behind a number. Both
kinds break silently. Renaming a file, moving a directory, or fixing a typo in a filename
leaves the pointer reading exactly as convincing as it did before, and the first person to
find out is a judge who clicks it. Nothing in this repository checked them until this file
existed. This program checks them, names every one it could not resolve, and exits non-zero.

TWO PASSES, BECAUSE THERE ARE TWO KINDS OF POINTER.

* **The link pass** reads Markdown link syntax -- the inline form and the reference form -- and
  resolves each relative target against the directory of the file that wrote it. Links inside
  fenced code blocks AND inside inline code spans are skipped, for the same reason in both
  cases: Markdown does not render a link inside code, it prints the characters, so those are
  illustrations of syntax rather than pointers anybody can click. Treating them as live would
  make this program cry wolf about a page that is documenting link syntax correctly.
* **The citation pass** reads bare `evidence/...` and `qa/...` paths anywhere in the file,
  fences included, because that is exactly where they live -- inside `[src: ...]` notes and
  inside the commands a judge is told to run. A path a document offers as its evidence is a
  promise about the disk, whether or not anybody made it clickable.

WHAT IS DELIBERATELY NOT CHECKED, AND IS REPORTED RATHER THAN DROPPED.

* **External addresses** (`https://`, `mailto:`) are not fetched. Reaching the network would
  make a documentation check depend on somebody else's uptime, and this program is meant to
  give the same answer on a plane. They are counted and the count is printed.
* **Fragments** -- the `#section` half of a link -- are stripped before the file is looked up.
  This program answers "does the file exist", not "does the heading exist".
* **Templates and globs.** `evidence/gate-refusal/proof-<UTC>.json` is a filename pattern a
  judge is told to expect, and `evidence/deploy/` is a directory. Neither is a claim that one
  particular file exists. They are skipped BY NAME, counted, and listed under `--verbose`.

THE ONE SUPPRESSION IN THIS FILE IS TWO-WAY, WHICH IS WHY IT IS NOT A MUTE BUTTON.
`DECLARED_ABSENT` below holds paths that a judge-facing document names precisely BECAUSE they
do not exist -- an artefact this repository says it still owes. Suppressing the finding is
correct; suppressing it forever is not. Each entry is an assertion in both directions: while
the path is absent the finding is suppressed, and the moment the path appears the entry
becomes a lie about the tree and this program says `STALE` and exits non-zero. An allow-list
that can only ever silence things is how a green gets bought. This one can bite back.

IT IS IN NO CI WORKFLOW, ON PURPOSE. Ruling R-H of `docs/submission/extra-credit-plan.md`:
the test baseline is 1070 collected / 1069 passed / 0 failed / 0 errors, and adding a lane the
day before a deadline is the cheapest way to break it. This is a standalone tool. Run it by
hand; `docs/submission/MECHANICAL-SWEEP.md` records the run.

WHY `--self-test` CHECKS THE REASON AND NOT ONLY THE EXIT CODE. A self-test that plants a
defect and asserts "the program exited non-zero" passes when the program fails to start, when
it crashes on an import, and when it rejects its own arguments. Every one of those is a
checker that is not checking anything, wearing a green. So `--self-test` runs two phases and
both must hold: a CONTROL phase over a clean fixture, which must exit ZERO -- if the checker
refuses everything, a red on the planted defect proves nothing -- and a PLANTED phase, which
must exit non-zero AND print the planted target's own literal name. That pairing is the rule
`docs/ci/anti-vacuity.md` states for the whole repository, applied to this program itself.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

#: The judge-facing set, repo-relative. These are the documents a contest judge lands on:
#: the repository front page, the reproduction page it points at, the three submission pages,
#: and the deploy pack that carries the credentials and the live URLs. Named literally rather
#: than globbed, because a glob would silently start or stop covering a file when the tree
#: moves, and the point of this program is that nothing about it moves silently.
JUDGE_FACING: tuple[str, ...] = (
    "README.md",
    "VERIFY.md",
    "docs/submission/JUDGE-START.md",
    "docs/submission/FIRST-FIVE-MINUTES.md",
    "docs/submission/DEVPOST.md",
    "docs/deploy/JUDGE-PACK.md",
)

#: Paths a judge-facing document names on purpose because they are NOT on disk -- an artefact
#: this repository says it still owes. Key is the repo-relative path; value is the reason,
#: which is printed on every run so the suppression is never invisible.
#:
#: READ THE MODULE DOCSTRING BEFORE ADDING ONE. An entry whose path EXISTS is reported as
#: `STALE` and fails the run: the document's sentence has become false, and the fix is to
#: rewrite the sentence and delete the entry, not to leave a silent pass behind.
DECLARED_ABSENT: dict[str, str] = {
    "evidence/deploy/cloud-gate-run.json": (
        "docs/submission/DEVPOST.md names this as OWED and says so in the same sentence: "
        "'The four-beat run through the HTTP handler has NOT been recorded against Cloud ... "
        "evidence/ holds none.' The citation is a declaration of absence, not a broken "
        "pointer. If this file is ever produced, that paragraph must be rewritten."
    ),
}

#: Link schemes this program does not resolve. Counted and printed, never silently dropped.
_EXTERNAL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

#: `[text](target)` and `[text](target "title")`, plus the angle form `](<target>)`.
_INLINE_LINK = re.compile(r"\]\(\s*<?([^)<>\s]+)>?(?:\s+[\"'(][^)]*)?\s*\)")

#: A reference definition at the head of a line: `[label]: target`. The `^(?!\^)` keeps
#: footnote definitions (`[^note]: prose`) out, since their body is prose and not a path.
_REF_DEF = re.compile(r"^\s{0,3}\[(?!\^)[^\]]+\]:\s*<?([^\s<>]+)>?", re.MULTILINE)

#: A bare evidence/ or qa/ path quoted in prose or in a command.
_CITATION = re.compile(r"(?<![\w./\-])((?:evidence|qa)/[A-Za-z0-9_./<>*+\-]*)")

#: Characters that mark a path as a pattern rather than a claim about one file.
_TEMPLATE_MARKS = ("<", ">", "*", "?", "{", "…")

_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

#: An inline code span: `like this`, or ``like `this` ``. Markdown does not render a link inside
#: one -- it prints the characters -- so a `[text](target)` in backticks is an illustration of
#: syntax and not a pointer anybody can click. The link pass blanks these for the same reason it
#: blanks fenced blocks. The CITATION pass does not: `evidence/foo.json` in backticks is this
#: repository's house style for quoting evidence, and those are exactly the claims worth checking.
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)


@dataclass(frozen=True)
class Finding:
    """One pointer that did not resolve. `kind` is `link`, `cite` or `stale`."""

    kind: str
    source: str
    line: int
    target: str
    detail: str

    def render(self) -> str:
        where = f"{self.source}:{self.line}" if self.line else self.source
        return f"MISSING {self.kind:<5} {where}  {self.target}\n        {self.detail}"


@dataclass
class Tally:
    """Everything the run looked at, including what it chose not to resolve."""

    links_checked: int = 0
    links_external: int = 0
    links_fragment: int = 0
    cites_checked: int = 0
    cites_template: int = 0
    files: int = 0


def _strip_fenced_code(text: str) -> str:
    """Blank out fenced code blocks, keeping line numbering intact.

    Line numbering is preserved by replacing each fenced line with an empty line rather than
    deleting it, so a finding's reported line number is the line a reader will open.
    """
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = _FENCE.match(line)
        if fence is None:
            if marker:
                fence = marker.group(1)[0]
                out.append("")
                continue
            out.append(line)
        else:
            out.append("")
            if marker and marker.group(1)[0] == fence:
                fence = None
    return "\n".join(out)


def _blank_inline_code(text: str) -> str:
    """Blank inline code spans, preserving both length and newlines so offsets still line up."""

    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return _INLINE_CODE.sub(blank, text)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _resolve(root: Path, source_rel: str, target: str) -> Path:
    """Resolve a link target the way a reader's browser would.

    A target beginning with `/` is taken as repo-root-relative, which is how GitHub renders it
    inside a repository. Anything else is relative to the directory holding the document.
    """
    if target.startswith("/"):
        return root / target.lstrip("/")
    return (root / source_rel).parent / target


def check_links(root: Path, rel: str, tally: Tally) -> list[Finding]:
    """Resolve every Markdown link in one file. Fenced code blocks are not links."""
    raw = (root / rel).read_text(encoding="utf-8")
    text = _blank_inline_code(_strip_fenced_code(raw))
    findings: list[Finding] = []

    for match in list(_INLINE_LINK.finditer(text)) + list(_REF_DEF.finditer(text)):
        target = match.group(1).strip()
        if not target:
            continue
        if target.startswith("#"):
            tally.links_fragment += 1
            continue
        if target.startswith("//") or _EXTERNAL_SCHEME.match(target):
            tally.links_external += 1
            continue

        bare = urllib.parse.unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not bare:
            tally.links_fragment += 1
            continue

        tally.links_checked += 1
        resolved = _resolve(root, rel, bare)
        if not resolved.exists():
            findings.append(
                Finding(
                    kind="link",
                    source=rel,
                    line=_line_of(text, match.start()),
                    target=target,
                    detail=f"resolved to {resolved} -- no such file or directory on disk",
                )
            )
    return findings


def check_citations(root: Path, rel: str, tally: Tally) -> tuple[list[Finding], set[str]]:
    """Resolve every bare `evidence/` or `qa/` path this file offers as its evidence.

    Returns the findings and the set of `DECLARED_ABSENT` keys this file actually cited, so
    the caller can report an entry that has stopped suppressing anything.
    """
    text = (root / rel).read_text(encoding="utf-8")
    findings: list[Finding] = []
    used: set[str] = set()

    for match in _CITATION.finditer(text):
        target = match.group(1).rstrip(".,;:)`'\"")
        if not target or target.endswith("/"):
            tally.cites_template += 1
            continue
        if any(mark in target for mark in _TEMPLATE_MARKS):
            tally.cites_template += 1
            continue

        tally.cites_checked += 1
        if (root / target).exists():
            continue
        if target in DECLARED_ABSENT:
            used.add(target)
            continue
        findings.append(
            Finding(
                kind="cite",
                source=rel,
                line=_line_of(text, match.start()),
                target=target,
                detail=(
                    "cited as evidence and not present on disk. Fix the citation or produce "
                    "the artefact -- do NOT create an empty file to satisfy the pointer."
                ),
            )
        )
    return findings, used


def _stale_suppressions(root: Path) -> list[Finding]:
    """The other direction of `DECLARED_ABSENT`: an entry whose path now exists is a lie.

    The document that named the path said, in the same sentence, that it does not exist. If it
    does, that sentence has silently become untrue and somebody has to rewrite it.
    """
    findings: list[Finding] = []
    for path, reason in DECLARED_ABSENT.items():
        if not (root / path).exists():
            continue
        findings.append(
            Finding(
                kind="stale",
                source="DECLARED_ABSENT",
                line=0,
                target=path,
                detail=(
                    "this path EXISTS now, so the entry is false. Rewrite the sentence that "
                    f"declared it absent, then delete the entry. Recorded reason was: {reason}"
                ),
            )
        )
    return findings


def _collect(
    root: Path, targets: tuple[str, ...], do_links: bool, do_cites: bool, tally: Tally
) -> tuple[list[Finding], set[str]]:
    findings: list[Finding] = []
    absent_used: set[str] = set()

    for rel in targets:
        if not (root / rel).is_file():
            # A named judge-facing document that is not on disk is the loudest possible
            # finding: the set this program guards has itself moved.
            findings.append(
                Finding(
                    kind="link",
                    source="(target set)",
                    line=0,
                    target=rel,
                    detail="named in JUDGE_FACING and not present -- the guarded set has moved",
                )
            )
            continue
        tally.files += 1
        if do_links:
            findings.extend(check_links(root, rel, tally))
        if do_cites:
            found, used = check_citations(root, rel, tally)
            findings.extend(found)
            absent_used |= used

    if do_cites:
        findings.extend(_stale_suppressions(root))
    return findings, absent_used


def _report(
    root: Path, tally: Tally, absent_used: set[str], do_links: bool, do_cites: bool, verbose: bool
) -> None:
    print(f"check_doc_links: {tally.files} judge-facing file(s) under {root}")
    if do_links:
        print(
            f"  links     {tally.links_checked} relative resolved-or-reported, "
            f"{tally.links_external} external not fetched, "
            f"{tally.links_fragment} same-page fragment(s) skipped"
        )
    if not do_cites:
        return
    print(
        f"  citations {tally.cites_checked} evidence/qa path(s) checked, "
        f"{tally.cites_template} template-or-directory skipped"
    )
    for path, reason in DECLARED_ABSENT.items():
        state = "cited" if path in absent_used else "not cited by this set"
        print(f"  DECLARED ABSENT ({state}): {path}")
        if verbose:
            print(f"      {reason}")


def run(root: Path, targets: tuple[str, ...], do_links: bool, do_cites: bool, verbose: bool) -> int:
    tally = Tally()
    findings, absent_used = _collect(root, targets, do_links, do_cites, tally)
    _report(root, tally, absent_used, do_links, do_cites, verbose)

    if findings:
        print("")
        for finding in sorted(findings, key=lambda f: (f.source, f.line)):
            print(finding.render())
        print(f"\nFAIL: {len(findings)} unresolved pointer(s).")
        return EXIT_FINDINGS

    print("OK: every relative link and every cited evidence path resolves.")
    return EXIT_OK


# --------------------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------------------

_FIXTURE_DOC = """<!-- SPDX-License-Identifier: Apache-2.0 -->
# fixture

A link that resolves: [the real one](../../real.md).
An external address nobody fetches: [devpost](https://example.invalid/rules).
A same-page jump: [below](#tail).
A citation that resolves: `evidence/real.json`, and a directory `evidence/`.
A template that is not a claim: `evidence/proof-<UTC>.json`.

```
[this link is inside a fence](nowhere/at/all.md)
```

## tail
"""

_PLANTED_LINK = "nope/PLANTED-MISSING-DOC.md"
_PLANTED_CITE = "evidence/nope/PLANTED-MISSING-EVIDENCE.json"


def _build_fixture(root: Path) -> Path:
    (root / "docs" / "x").mkdir(parents=True)
    (root / "evidence").mkdir()
    (root / "real.md").write_text("# real\n", encoding="utf-8")
    (root / "evidence" / "real.json").write_text("{}\n", encoding="utf-8")
    doc = root / "docs" / "x" / "FIXTURE.md"
    doc.write_text(_FIXTURE_DOC, encoding="utf-8")
    return doc


def _run_child(root: Path, rel: str) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(Path(__file__).resolve())]
    argv += ["--root", str(root), "--check", rel, "--verbose"]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )


def self_test() -> int:
    """Plant a broken link and a broken citation and prove this checker refuses BOTH.

    Four assertions, and the first one is the one people leave out. If the control phase does
    not go green, then the red in the planted phase says nothing about the planted defect --
    it could be a crash, a bad argument, a missing import. Checking only that the program
    exited non-zero would pass in every one of those cases.
    """
    print(
        "self-test: two phases -- a clean control that must PASS, a planted defect that must FAIL\n"
    )
    results: list[tuple[bool, str]] = []

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        doc = _build_fixture(root)
        rel = "docs/x/FIXTURE.md"

        control = _run_child(root, rel)
        print("--- phase 1: control, a fixture whose every pointer resolves")
        print(control.stdout.rstrip() or control.stderr.rstrip())
        results.append(
            (
                control.returncode == EXIT_OK,
                (
                    f"A1 control exits 0 (got {control.returncode}). A checker that "
                    "refuses a clean tree makes the planted red meaningless."
                ),
            )
        )

        doc.write_text(
            doc.read_text(encoding="utf-8")
            + f"\nA planted link: [broken]({_PLANTED_LINK}).\n"
            + f"A planted citation: `{_PLANTED_CITE}`.\n",
            encoding="utf-8",
        )

        planted = _run_child(root, rel)
        print("\n--- phase 2: planted, one broken link and one broken citation added")
        print(planted.stdout.rstrip() or planted.stderr.rstrip())
        results.append(
            (
                planted.returncode != EXIT_OK,
                f"A2 planted exits non-zero (got {planted.returncode})",
            )
        )
        results.append(
            (
                _PLANTED_LINK in planted.stdout,
                f"A3 output names the planted LINK target literally: {_PLANTED_LINK}",
            )
        )
        results.append(
            (
                _PLANTED_CITE in planted.stdout,
                f"A4 output names the planted CITATION target literally: {_PLANTED_CITE}",
            )
        )

    print("\n--- verdict")
    for ok, label in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if all(ok for ok, _ in results):
        print(
            "\nself-test OK: the checker goes green on a clean tree "
            "and red on a planted defect, naming it."
        )
        return EXIT_OK
    print("\nself-test FAILED: this checker cannot be trusted to report a real break.")
    return EXIT_FINDINGS


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_doc_links.py",
        description=(
            "Resolve every relative link and every cited evidence path on the judge-facing pages."
        ),
    )
    add = parser.add_argument
    add("--root", default=None, help="repository root (default: inferred from this file)")
    add("--check", nargs="+", metavar="FILE", help="check these repo-relative files instead")
    add("--links-only", action="store_true", help="run the Markdown link pass only")
    add("--cites-only", action="store_true", help="run the evidence-citation pass only")
    add("--list-targets", action="store_true", help="print the judge-facing set and exit")
    add("--self-test", action="store_true", help="plant a defect and prove this checker refuses")
    add("--verbose", action="store_true", help="print the reason behind each suppression")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.list_targets:
        for rel in JUDGE_FACING:
            print(rel)
        return EXIT_OK

    if args.links_only and args.cites_only:
        parser.error(
            "--links-only and --cites-only are contradictory; omit both to run both passes"
        )

    root = Path(args.root).resolve() if args.root else _default_root()
    if not root.is_dir():
        print(f"usage error: --root {root} is not a directory", file=sys.stderr)
        return EXIT_USAGE

    targets = tuple(args.check) if args.check else JUDGE_FACING
    return run(
        root=root,
        targets=targets,
        do_links=not args.cites_only,
        do_cites=not args.links_only,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    raise SystemExit(main())
