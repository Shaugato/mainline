#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim.
# I: CI-CLUSTER-3 — the cluster lane's diagnosis is READABLE. This program decides
#    NOTHING: it exits 0 on every input, and it emits no `::error`. The verdict belongs
#    to scripts/ci/cluster_lane_report.py and to pytest's own exit status.
"""Digest one cluster-lane run into the few lines a reader actually needs.

WHY A SECOND PROGRAM, WHEN `cluster_lane_report.py` ALREADY READS THE SAME XML.

Measured over the full 1,023-line log of GitHub Actions run `31735341117`
(`cluster-tests`, HEAD `eefae1c`), recorded in `docs/ci/cluster-lane-diagnosis.md`:

    the assertion that failed          line 830          one line
    the FAILURES block and verdict     lines 760-919     the actual diagnosis
    `docker logs … tail -60`           lines 943-1003    60 lines of event_log.go:90
    GitHub echoing `run:` bodies       186 lines total   mostly step comments

A reader who opens a failed run lands at the BOTTOM and sees CockroachDB's session log.
The one failing assertion is ~180 lines above it. That is why the last orchestrator to
read this lane had to `grep` for its own failure. **The container log is not the defect
and is not removed** — see `docs/ci/cluster-lane-diagnosis.md` §4 for why deleting it
would silence exactly the case it exists for. The defect is that nothing prints the
short version.

WHY IT EXITS 0 ALWAYS, WHICH IS THE ONLY PROPERTY OF THIS FILE THAT MATTERS.

A repository whose lane can go red in two places has two places a verdict can hide, and
the second one is always the one nobody reads. `cluster_lane_report.py` owns the verdict:
`--pytest-rc` is final there, the floor and the ceiling are enforced there, and its
refusal of a run whose JUnit records failures while the caller claims `rc 0` is a
load-bearing control. **This program is diagnosis.** It exits 0 on a green run, on a red
run, on a missing JUnit, on unparseable XML and on a body it could not understand — and
it emits no GitHub `::error`/`::warning` annotation, because the annotation channel is
where a reader looks for the verdict and there must be exactly one of those.

So every failure mode here degrades into a printed sentence. A diagnosis tool that dies
while trying to show you the failure fails precisely when it was needed.

WHAT IT PRINTS, IN THIS ORDER — fixed by `docs/leads/lane-honest-plan.md` §3.

  1. the one-line totals, read from the `<testsuite>` attributes;
  2. for each failing node id, the id and the assertion text extracted from the
     `<failure>`/`<error>` body, truncated with an EXPLICIT marker rather than silently;
  3. the skip census, grouped by message, with counts.

THE ONE THING THAT IS EASY TO GET WRONG HERE, AND IS THE REASON THIS FILE IS CAREFUL.

pytest's `<failure>` body is the whole longrepr, and the assertion is at its **END**. The
real body this program was calibrated against — `test_reads.py::test_the_disposition_
carries_the_lattice_and_the_projected_requirements` — is 53 lines and 3,554 characters, of
which the first ~40 are the test's docstring. A digest that truncated from the top would
print the docstring and hide the assertion: the same defect as the 1,023-line log,
reproduced inside the tool built to end it. `assertion_text()` therefore selects the
`>` failing statement, the `E` exception block and the trailing `file:line: Type` line —
and where a body carries no `E` block at all (a fixture that raised during setup, which is
how 13 of the calibration run's cases arrived) it takes the **tail**, and says so.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any

#: Per-failure display caps. These bound the DISPLAY only: nothing is filtered, the full
#: text is in the JUnit XML the digest names in its own truncation marker, and every
#: failing node id is printed whatever these are set to. They are not a ratchet and there
#: is no green to be had by moving them.
MAX_BODY_LINES = 24
MAX_BODY_CHARS = 2000

#: The headline is one line by contract. pytest's `message` attribute is not: this
#: repository's exception messages are paragraphs on purpose, and the calibration run
#: carries a 900-character one. A headline that wraps to twelve terminal lines is the wall
#: this program exists to replace, so it is capped — and the cap says so, because the same
#: text is in the detail immediately below it and in the XML.
MAX_HEADLINE_CHARS = 220

#: Skip messages are one-liners by construction; a long one is a bug in the skip, not here.
MAX_SKIP_MESSAGE_CHARS = 240

#: Node ids named per skip group before the rest are counted rather than listed.
SKIP_IDS_SHOWN = 3

_MARKED = re.compile(r"^\s*>")
_EXCEPTION = re.compile(r"^\s*E(\s|$)")
_OUTCOME = re.compile(r"^(FAILED|ERROR)\s+(\S+)")


# ── printing that cannot itself fail ───────────────────────────────────────────────


def emit(lines: list[str]) -> None:
    """Write to stdout without ever raising on an un-encodable character.

    The calibration body carries `⚠`, and a Windows console defaults to cp1252. A
    diagnosis program that raised `UnicodeEncodeError` while printing the assertion it
    exists to show would fail exactly when the assertion was interesting, so the
    characters it cannot render are replaced and the line is still printed.
    """
    text = "\n".join(lines)
    stream = sys.stdout
    try:
        stream.write(text + "\n")
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        stream.write(text.encode(encoding, "replace").decode(encoding, "replace") + "\n")
    stream.flush()


# ── reading the two accounts of the run ────────────────────────────────────────────


def find_suite(junit: pathlib.Path) -> tuple[Any, list[str]]:
    """Return the `<testsuite>` element, or `None` plus the reason there is not one.

    The root element is either `<testsuite>` or `<testsuites>` containing one — pytest
    writes the second under `--junitxml` in the versions this repository pins. The shape
    of this resolution is deliberately identical to `cluster_lane_report.py`'s, so the two
    programs cannot end up reading different halves of the same document.
    """
    try:
        root = ET.parse(junit).getroot()  # noqa: S314 - pytest's own output, not hostile input
    except FileNotFoundError:
        return None, [
            f"no JUnit report at {junit}.",
            "  The run did not reach the point of writing one. That is itself the finding:",
            "  look at the raw stdout below and at the container log in the collapsed group.",
        ]
    except ET.ParseError as exc:
        return None, [
            f"{junit} is not parseable XML: {exc}.",
            "  A half-written report usually means the runner died mid-suite.",
        ]

    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return None, [f"{junit} carries no <testsuite> element; nothing was collected."]
    return suite, []


def read_stdout(path: pathlib.Path) -> dict[str, Any]:
    """Mine pytest's captured stdout for the two things the XML does not carry.

    The XML records `classname` + `name`; the `short test summary info` block records the
    real, COPY-PASTEABLE node id. This program has no `--suite-root` and must never
    refuse, so rather than reconstruct an id it looks the printed one up — and where it
    cannot, it says the id is the JUnit form rather than inventing a path.

    The final counts line is read as a SECOND, INDEPENDENT account of the same run. When
    it disagrees with the `<testsuite>` attributes, that disagreement is printed: it is
    the signature of a run whose XML was written before the suite finished.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ids": {}, "counts": None, "note": f"could not read {path}: {exc}"}

    ids: dict[tuple[str, str], str] = {}
    counts: str | None = None
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        match = _OUTCOME.match(stripped)
        if match:
            nodeid = match.group(2)
            head, _, trailing = nodeid.partition("::")
            module = head.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".py")
            if trailing:
                ids.setdefault((module, trailing), nodeid)
        if re.match(r"^=*\s*\d+ (passed|failed|error)", stripped) or re.search(
            r"\b\d+ (failed|passed|error|errors|skipped)\b.*\bin \d", stripped
        ):
            counts = stripped.strip("= ")
    return {"ids": ids, "counts": counts, "note": ""}


def nodeid_for(classname: str, name: str, printed: dict[tuple[str, str], str]) -> tuple[str, bool]:
    """Resolve JUnit's `classname` + `name` to the id pytest itself printed.

    Returns `(id, resolved)`. When nothing matches, the JUnit form is returned unchanged
    and flagged — a guessed path that does not exist would be worse than an honest
    `tests.test_reads::test_x`, because a reader would paste it and get "file not found"
    rather than "this tool could not resolve it".
    """
    parts = [part for part in classname.split(".") if part]
    for index in range(len(parts)):
        trailing = "::".join([*parts[index + 1 :], name])
        found = printed.get((parts[index], trailing))
        if found:
            return found, True
    return f"{classname}::{name}" if classname else name, False


# ── the part that has to be right: what counts as "the assertion text" ─────────────


def assertion_text(element: Any) -> tuple[str, list[str], int, str]:
    """Extract the diagnosis from one `<failure>`/`<error>` body.

    Returns `(headline, detail, body_line_count, strategy)`.

    THE BODY'S DIAGNOSIS IS AT ITS END, NOT ITS START. pytest writes the whole longrepr:
    the fixture reprs, then the test source including its docstring, then the `>` line
    that failed, then the `E` block, then `file:line: ExceptionType`. Taking the head
    would show a docstring. Two strategies, and the caller is told which one ran:

    * `assert`  — there is an `E` block. Detail is the `>` statement through the last `E`
      line, plus the trailing location line. This is the assertion, verbatim.
    * `tail`    — there is no `E` block, which is what a fixture raising during setup
      looks like. Detail is the END of the body, and the marker says so, because a tail
      is a weaker claim than an extracted assertion and the reader must be able to tell.
    """
    raw = (element.text or "").replace("\r\n", "\n")
    lines = [line.rstrip() for line in raw.split("\n")]
    body_lines = len([line for line in lines if line.strip()])

    exception_at = [index for index, line in enumerate(lines) if _EXCEPTION.match(line)]
    marked_at = [index for index, line in enumerate(lines) if _MARKED.match(line)]
    tail_non_empty = [index for index, line in enumerate(lines) if line.strip()]
    location = lines[tail_non_empty[-1]] if tail_non_empty else ""

    if exception_at:
        start = marked_at[-1] if marked_at and marked_at[-1] < exception_at[0] else exception_at[0]
        detail = [line for line in lines[start : exception_at[-1] + 1] if line.strip()]
        if location and location not in detail:
            detail.append(location)
        strategy = "assert"
    else:
        detail = [line for line in lines if line.strip()][-MAX_BODY_LINES:]
        strategy = "tail"

    # The `message` attribute is pytest's own one-line summary. It is ELLIPSISED — the
    # calibration case reads `assert set() == {'MECHANISM_P...LUDES_HAZARD'}`, which drops
    # the set contents — so it is used as the headline only, never as the detail.
    message = " ".join((element.get("message") or "").split())
    headline = message or (detail[0].strip() if detail else "(the body carried no text)")
    if len(headline) > MAX_HEADLINE_CHARS:
        headline = (
            headline[:MAX_HEADLINE_CHARS]
            + f" […{len(headline) - MAX_HEADLINE_CHARS} more character(s); "
            "the rest is in the detail below and in the JUnit XML]"
        )
    return headline, detail, body_lines, strategy


def truncate(detail: list[str], junit: pathlib.Path, strategy: str) -> tuple[list[str], str]:
    """Cap the detail, and return the marker that says exactly what was dropped.

    A marker that says `...` teaches the reader nothing and invites them to assume the
    rest was uninteresting. This one names the counts on both sides and the file that
    holds the whole text, so the reader can decide.
    """
    kept, chars = [], 0
    for line in detail:
        if len(kept) >= MAX_BODY_LINES or chars + len(line) > MAX_BODY_CHARS:
            break
        kept.append(line)
        chars += len(line) + 1

    notes = []
    if strategy == "tail":
        notes.append(
            "this body carries no `E` assertion block — it is a raise during setup or "
            "collection, so the LAST lines are shown rather than an extracted assertion"
        )
    if len(kept) < len(detail):
        notes.append(
            f"{len(kept)} of {len(detail)} extracted line(s) shown, "
            f"{chars} of {sum(len(line) + 1 for line in detail)} character(s); "
            f"the complete text is in {junit}"
        )
    return kept, ("[" + ". ".join(notes) + "]" if notes else "")


# ── the report ─────────────────────────────────────────────────────────────────────


def _int_attr(suite: Any, name: str) -> int:
    """Read a `<testsuite>` count. A missing or non-numeric attribute reads as 0.

    This program prints what it found; it never refuses a document. A JUnit whose counts
    are malformed is itself a finding, and the reader can see it in the printed line.
    """
    try:
        return int(suite.get(name, "0"))
    except (TypeError, ValueError):
        return 0


def _totals(suite: Any, printed: dict[str, Any]) -> tuple[list[str], str]:
    """Section 1: the one-line totals, read from the `<testsuite>` attributes."""
    tests, skipped = _int_attr(suite, "tests"), _int_attr(suite, "skipped")
    line = (
        f"lane digest: {tests} collected, {tests - skipped} executed, {skipped} skipped, "
        f"{_int_attr(suite, 'failures')} failed, {_int_attr(suite, 'errors')} errored, "
        f"in {suite.get('time', '?')}s"
    )
    plain = [line]
    # pytest's own final line is a SECOND, independent account of the same run. Printing
    # both is how a reader sees an XML that was written before the suite finished.
    if printed["counts"]:
        plain.append(f"  pytest's own last line: {printed['counts']}")
    if printed["note"]:
        plain.append(f"  note: {printed['note']}")
    return plain, line


def _partition(
    suite: Any, printed: dict[str, Any]
) -> tuple[list[tuple[str, str, Any]], list[tuple[str, str]], bool]:
    """Split the cases into (failing, skipped, any-id-unresolved)."""
    bad: list[tuple[str, str, Any]] = []
    skips: list[tuple[str, str]] = []
    unresolved = False
    for case in suite.iter("testcase"):
        nodeid, resolved = nodeid_for(
            case.get("classname", ""), case.get("name", ""), printed["ids"]
        )
        # Only FAILED/ERROR lines carry a copy-pasteable id in `short test summary info`,
        # so a skipped case will normally not resolve. The suffix is terse and the reason
        # is stated ONCE at the end: an id marked here is JUnit's `classname::name`, which
        # is not a path. Inventing a path would be worse — a reader would paste it and be
        # told the file does not exist, rather than that this program could not resolve it.
        label = nodeid if resolved else f"{nodeid}  [junit id]"
        for kind in ("failure", "error"):
            found = case.find(kind)
            if found is not None:
                bad.append((label, kind, found))
                unresolved = unresolved or not resolved
                break
        else:
            skip = case.find("skipped")
            if skip is not None:
                skips.append((label, " ".join((skip.get("message") or "").split())))
                unresolved = unresolved or not resolved
            # A PASSING case is never printed, so whether its id resolved is not a fact
            # about this report. Counting it here would make the note below fire on every
            # healthy run, and a note that always fires is a note nobody reads.
    return bad, skips, unresolved


def _one_failure(
    index: int,
    entry: tuple[str, str, Any],
    junit: pathlib.Path,
    seen: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Render one failing node id: the id, its headline, and the assertion text."""
    nodeid, kind, element = entry
    headline, detail, body_lines, strategy = assertion_text(element)
    plain = [f"{index:>3}. [{kind}] {nodeid}", f"       {headline}"]
    markdown = [f"{index}. `{nodeid}` — **{kind}**", "", f"   {headline}"]

    fingerprint = "\n".join(detail)
    first = seen.get(fingerprint)
    if first is not None:
        # Folding an EXTRACTED ASSERTION that is byte-identical to one already printed
        # hides no id and no text: this id is named on the line above, its headline is
        # printed, and the identical text is at #first. The claim is deliberately about
        # the extracted assertion and not about the whole body, which may differ — so the
        # marker also says how long this case's own body is and where to read it. The
        # calibration run carried 13 cases sharing one 67-line setup traceback; printing
        # it 13 times would rebuild the wall this program exists to end.
        note = (
            f"[the extracted assertion is identical to #{first} above and is not "
            f"repeated; this case's own body is {body_lines} line(s), in {junit}]"
        )
        return [*plain, f"       {note}", ""], [*markdown, "", f"   _{note}_", ""]

    seen[fingerprint] = index
    kept, marker = truncate(detail, junit, strategy)
    plain.extend(f"       {line}" for line in kept)
    markdown.extend(["", "```text", *kept, "```"])
    if marker:
        plain.append(f"       {marker}")
        markdown.extend([f"_{marker}_", ""])
    plain.append("")
    return plain, markdown


def _failures(
    bad: list[tuple[str, str, Any]], junit: pathlib.Path, max_failures: int
) -> tuple[list[str], list[str]]:
    """Section 2: every failing node id, with the assertion text."""
    if not bad:
        return ["failures: none."], ["**Failures:** none."]

    shown = bad[:max_failures]
    header = f"failures: {len(bad)}"
    if len(bad) > len(shown):
        header += (
            f" — the first {len(shown)} are shown (--max-failures {max_failures}). "
            "This is a DISPLAY cap: every id is in the JUnit XML, and this program "
            "decides nothing either way."
        )
    plain = [header, ""]
    capped = f" (showing {len(shown)})" if len(bad) > len(shown) else ""
    markdown = [f"**Failures: {len(bad)}**{capped}", ""]

    seen: dict[str, int] = {}
    for index, entry in enumerate(shown, start=1):
        one_plain, one_markdown = _one_failure(index, entry, junit, seen)
        plain.extend(one_plain)
        markdown.extend(one_markdown)
    return plain, markdown


def _skip_census(skips: list[tuple[str, str]], junit: pathlib.Path) -> tuple[list[str], list[str]]:
    """Section 3: the skip census, grouped by message, with counts."""
    census: dict[str, list[str]] = {}
    for nodeid, message in skips:
        key = message or "(no message recorded on the <skipped> element)"
        census.setdefault(key, []).append(nodeid)

    line = (
        f"skips: {len(skips)} across {len(census)} distinct message(s)."
        if skips
        else "skips: none."
    )
    plain, markdown = [line], ["", f"**{line}**"]
    for message, ids in sorted(census.items(), key=lambda item: (-len(item[1]), item[0])):
        short = message
        if len(short) > MAX_SKIP_MESSAGE_CHARS:
            dropped = len(message) - MAX_SKIP_MESSAGE_CHARS
            short = (
                short[:MAX_SKIP_MESSAGE_CHARS]
                + f" […{dropped} more character(s), full text in {junit}]"
            )
        plain.append(f"  {len(ids):>4} x  {short}")
        markdown.append(f"- **{len(ids)}x** {short}")
        plain.extend(f"          {nodeid}" for nodeid in ids[:SKIP_IDS_SHOWN])
        if len(ids) > SKIP_IDS_SHOWN:
            plain.append(f"          … and {len(ids) - SKIP_IDS_SHOWN} more with this message")

    if skips:
        plain.append("")
        plain.append(
            "  A skip is indistinguishable from a green tick on a dashboard. This census "
            "does not judge it — qa/cluster-known-red.json's `floor.max_skipped` does, "
            "through scripts/ci/cluster_lane_report.py."
        )
    return plain, markdown


def build(
    junit: pathlib.Path, stdout: pathlib.Path, max_failures: int
) -> tuple[list[str], list[str]]:
    """Produce (plain lines, markdown lines). Never decides anything.

    The three sections are the contract, in this order: totals, failures with their
    assertion text, then the skip census. `docs/leads/lane-honest-plan.md` §3 fixes it.
    """
    markdown: list[str] = ["## cluster lane — what failed", ""]
    suite, why_not = find_suite(junit)
    printed = read_stdout(stdout)

    if suite is None:
        plain = ["lane digest: THE RUN PRODUCED NO READABLE JUNIT REPORT.", *why_not]
        markdown.append("**The run produced no readable JUnit report.**")
        markdown.extend(f"- {line.strip()}" for line in why_not)
        if printed["counts"]:
            plain.append(f"  pytest's own last line: {printed['counts']}")
            markdown.append(f"- pytest's own last line: `{printed['counts']}`")
        if printed["note"]:
            plain.append(f"  {printed['note']}")
        # Exit status is still 0. This program does not decide; cluster_lane_report.py
        # refuses a missing report on its own, with pytest's status.
        return plain, markdown

    totals_plain, totals_line = _totals(suite, printed)
    markdown.append(f"`{totals_line}`")
    markdown.append("")

    bad, skips, unresolved = _partition(suite, printed)
    fail_plain, fail_markdown = _failures(bad, junit, max_failures)
    skip_plain, skip_markdown = _skip_census(skips, junit)

    plain = [*totals_plain, "", *fail_plain, *skip_plain]
    markdown.extend([*fail_markdown, *skip_markdown])

    if unresolved:
        plain.append("")
        plain.append(
            "  note: an id marked [junit id] is JUnit's `classname::name`, because it did "
            f"not appear in {stdout}'s `short test summary info` — normal for a skip, which "
            "that block does not list by id. It is NOT a path; resolve it against the suite "
            "root before pasting it into pytest."
        )
    return plain, markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Digest a cluster-lane run into the lines a reader needs first.",
        epilog=(
            "EXITS 0 ALWAYS. This program is diagnosis and decides nothing: the verdict "
            "belongs to pytest's exit status and to scripts/ci/cluster_lane_report.py. A "
            "diagnosis tool that could fail a lane would be a second place a verdict can "
            "hide, and the second place is the one nobody reads."
        ),
    )
    parser.add_argument("--junit", type=pathlib.Path, required=True, help="pytest's JUnit XML")
    parser.add_argument(
        "--stdout",
        type=pathlib.Path,
        required=True,
        help=(
            "pytest's captured stdout. Read for the copy-pasteable node ids in `short test "
            "summary info` and for the final counts line, which is a second account of the "
            "same run."
        ),
    )
    parser.add_argument(
        "--summary",
        type=pathlib.Path,
        default=None,
        help="append the same content as Markdown here (GitHub's $GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=20,
        help=(
            "how many failing node ids to PRINT in full (default: %(default)s). A display "
            "cap only - the count above it is always printed, nothing is filtered, and no "
            "verdict anywhere reads this number."
        ),
    )
    args = parser.parse_args(argv)

    try:
        plain, markdown = build(args.junit, args.stdout, max(0, args.max_failures))
    except Exception as exc:  # noqa: BLE001 - see the module docstring: never raise.
        plain = [
            f"lane digest: this program could not read the run ({type(exc).__name__}: {exc}).",
            (
                "  That is a defect in scripts/ci/lane_log_digest.py and nothing else. The "
                "verdict is unaffected: it is pytest's exit status, applied by "
                "scripts/ci/cluster_lane_report.py."
            ),
        ]
        markdown = ["## cluster lane — what failed", "", plain[0]]

    emit(plain)

    if args.summary is not None:
        try:
            with args.summary.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(markdown) + "\n")
        except OSError as exc:
            emit([f"  (could not append the Markdown summary to {args.summary}: {exc})"])

    # 0, unconditionally. See the module docstring.
    return 0


if __name__ == "__main__":
    sys.exit(main())
