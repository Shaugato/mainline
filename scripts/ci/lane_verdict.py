#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim.
# I: CI-CLUSTER-4 — a failing lane ENDS with a block a stranger can read. This program
#    decides NOTHING: it exits 0 on every input and emits no GitHub annotation. The
#    verdict is pytest's exit status, carried to `scripts/ci/cluster_lane_report.py`
#    through `--pytest-rc`, and it stays there.
"""The last thing a failing cluster-tests run prints, and the only thing it must print.

WHY A THIRD PROGRAM READS THE SAME XML — measured, ruling R8 of `docs/leads/ci-green-final.md`.

`cluster_lane_report.py` owns the verdict and `lane_log_digest.py` owns the assertion
text. Neither is the last thing in the log, and neither answers the question a reader
opening a red run actually has, which is *what is broken, who owns it, and what would
make it green*. Three measurements, all at HEAD `7535670`:

  1. The lane's `::error title=N NEW cluster failure(s)` annotation prints the first FIVE
     node ids and then `; …`. Run 31770005759 had EIGHT. Three of the eight appear
     nowhere in the annotation channel, so the count and the list disagree and the reader
     has to go find the difference. This program prints ALL of them, always, with no cap
     and no ellipsis. It does not touch that annotation: `cluster_lane_report.py` is
     owned elsewhere, its ellipsis is a bound on an annotation and not on a verdict, and
     an ellipsis in a pointer is fine once the thing it points at is complete.
  2. `docker logs … | tail -60` is the LAST step of a failed run — 60 lines of
     CockroachDB's own `event_log.go` session chatter, landing exactly where a reader's
     eye does. The failing assertion sits ~180 lines above it. The engine log is not the
     defect and is not removed; it is folded into a `::group::`, written to its own file
     and uploaded, and then THIS BLOCK is printed after it so that the bottom of the log
     is the diagnosis rather than the noise.
  3. Four NO-GO verdicts have already been traced to CI never running the product's
     tests. A lane whose diagnosis needs `grep` will not be read, and a lane that is not
     read is a lane that asserts nothing.

WHY IT EXITS 0 ALWAYS, WHICH IS THE ONLY PROPERTY OF THIS FILE THAT MATTERS.

A lane that can go red in two places has two places a verdict can hide, and the second is
always the one nobody reads. This is the same contract `lane_log_digest.py` states and for
the same reason: every failure mode here — a missing JUnit, unparseable XML, an inventory
this program does not recognise — degrades into a printed sentence. A diagnosis tool that
dies while showing you the failure fails precisely when it was needed. Deleting this step
cannot turn a red run green, and neither can breaking it.

NO ANSI, ANYWHERE, BY CONSTRUCTION. Every string that reaches stdout goes through
`plain()`, which strips CSI sequences and folds newlines. Two of the three lanes in this
wave set `FORCE_COLOR: "1"`, the lead could not read `db-schema`'s failure without
stripping escapes by hand, and a verdict block that inherits colour codes from the text it
quotes reproduces the defect it was written to end.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import textwrap
import xml.etree.ElementTree as ET
from typing import Any

#: CSI sequences, which is what `FORCE_COLOR` and pytest's own reporter emit. The class is
#: deliberately the full final-byte range rather than `m` alone: a truncated log can carry
#: a cursor-movement sequence, and half a stripped escape is worse than none.
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

RULE = "=" * 86
THIN = "-" * 86

#: DISPLAY bounds, and they bound prose only. Every failing node id is printed in full
#: whatever these are set to — that is the whole point of the file — and nothing here is a
#: ratchet or a threshold. There is no green to be had by moving them.
MAX_PROSE_CHARS = 420
WRAP_WIDTH = 86

DEFAULT_LANE = "cluster-tests / the demo-api suite against a real CockroachDB"
#: The same default `cluster_lane_report.py` carries, so an id spelled by one program is
#: the id the other looks up. The workflow passes `${SUITE}` explicitly all the same.
DEFAULT_SUITE_ROOT = pathlib.Path("verticals/mainline/apps/demo-api/tests")
UNATTRIBUTED = "NOT ATTRIBUTED"


def plain(text: object, *, limit: int = MAX_PROSE_CHARS) -> str:
    """One ANSI-free line, bounded with an explicit marker rather than silently."""
    flat = " ".join(ANSI.sub("", str(text)).split())
    if len(flat) <= limit:
        return flat
    return f"{flat[:limit].rstrip()} […{len(flat) - limit} more characters]"


def emit(line: str) -> None:
    """THE one place this program writes to stdout, and the only place that may.

    GitHub reads a workflow command off any line whose text — after leading whitespace is
    trimmed — begins `::`. This block quotes prose it did not write: a `cause` string in
    `qa/cluster-known-red.json`, an owner, an exception message. Any of those may contain
    `::error`, and a wrap can land it at the start of a line, at which point a DIAGNOSIS
    step has emitted an ANNOTATION and this file's central claim — that it decides
    nothing and owns no annotation channel — becomes false by accident.

    So a line that would open a workflow command is printed behind a `| ` gutter. Nothing
    is dropped and nothing is truncated; the two characters say "this is quoted text".
    """
    text = line.rstrip()
    print(f"| {text.lstrip()}" if text.lstrip().startswith("::") else text)


def say(line: str = "") -> None:
    """One line, ANSI-stripped, with its INDENTATION INTACT.

    Deliberately not `plain()`: that folds runs of whitespace, which is right for prose
    lifted out of a JSON `cause` and wrong for the node-id list, whose leading spaces are
    the only thing separating an id from its heading.
    """
    for part in ANSI.sub("", line).replace("\t", "    ").splitlines() or [""]:
        emit(part)


def block(label: str, text: str, *, indent: int = 18, margin: int = 2) -> None:
    """A `label : prose` row, wrapped so no line runs off the reader's terminal."""
    head = f"{' ' * margin}{label.ljust(indent - margin)}: "
    _wrapped(head, text, len(head))


def bullet(text: str, *, indent: int = 4) -> None:
    """A `* prose` row. Its own function because `block('*', …)` prints `*   :`."""
    _wrapped(f"{' ' * indent}* ", text, indent + 2)


def _wrapped(head: str, text: str, hang: int) -> None:
    """Print `head` + wrapped body, with continuations aligned UNDER the body.

    `break_long_words=False` and `break_on_hyphens=False` are not cosmetic. Node ids and
    paths are the payload of this block, they are routinely longer than the wrap width,
    and a wrapper that splits them mid-token hands the reader an id that cannot be copied
    into `pytest` or searched for — which is the same "go and reassemble it yourself"
    the ellipsis in the annotation already costs. A long token overflows the margin
    instead; the reader's terminal soft-wraps it and the characters stay contiguous.
    """
    lines = textwrap.wrap(
        plain(text),
        width=WRAP_WIDTH,
        initial_indent=head,
        subsequent_indent=" " * hang,
        break_long_words=False,
        break_on_hyphens=False,
    )
    for line in lines or [head.rstrip()]:
        emit(line)


# ── the two files this program reads, both defensively ────────────────────────────────


def read_counts(junit: pathlib.Path, suite_root: pathlib.Path) -> tuple[dict[str, Any] | None, str]:
    """Totals and per-case outcomes, or `(None, why)`. Never raises — see the docstring."""
    try:
        root = ET.parse(junit).getroot()  # noqa: S314 - pytest's own output, not hostile input
    except FileNotFoundError:
        return None, f"UNAVAILABLE — pytest wrote no JUnit report at {junit}"
    except (ET.ParseError, OSError) as exc:
        return None, f"UNAVAILABLE — {junit} could not be read: {plain(exc, limit=200)}"
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return None, f"UNAVAILABLE — {junit} carries no <testsuite> element"

    bad: dict[str, str] = {}
    # PASSED, NOT "DID NOT FAIL", AND THE DIFFERENCE IS THE WHOLE POINT OF TRACKING IT.
    # The remedy section tells a reader to DELETE inventory entries that have stopped
    # failing. An id that was skipped, deselected or never collected also "did not fail",
    # and inviting its deletion on that basis would empty the inventory by looking away —
    # which is the motion this lane exists to reverse. Only an id with a `<testcase>` that
    # carries no failure, error or skipped child counts.
    passed: set[str] = set()
    for case in suite.iter("testcase"):
        nodeid = resolve_nodeid(case.get("classname", ""), case.get("name", ""), suite_root)
        for kind in ("failure", "error"):
            if case.find(kind) is not None:
                bad[nodeid] = kind
                break
        else:
            if case.find("skipped") is None:
                passed.add(nodeid)

    tests = int(suite.get("tests", "0"))
    skipped = int(suite.get("skipped", "0"))
    counts = {
        "collected": tests,
        "executed": tests - skipped,
        "skipped": skipped,
        "failed": int(suite.get("failures", "0")),
        "errored": int(suite.get("errors", "0")),
        "bad": bad,
        "passed": passed,
    }
    return counts, ""


def resolve_nodeid(classname: str, name: str, suite_root: pathlib.Path) -> str:
    """Rebuild a real pytest node id from JUnit's `classname` + `name`.

    THE SUITE ROOT IS LOAD-BEARING AND WAS MISSING FROM THE FIRST DRAFT OF THIS FILE.
    Measured on a real `--crdb=reuse` report: pytest wrote `classname="tests.test_reads"`,
    not the full path, because the demo-api suite sets its own rootdir. Rebuilding that as
    `tests/test_reads.py::…` produced an id no entry in `qa/cluster-known-red.json` could
    ever match, so a known failure would have been printed as `NEW` and an inventoried id
    that PASSED would never have been reported as fixed. The prefix walk below is
    `cluster_lane_report.py`'s, so the block and the verdict spell ids the same way.

    IT FALLS BACK RATHER THAN RAISING, WHICH IS THE ONE DIFFERENCE FROM THAT COPY. There,
    an unresolvable classname is a refusal, and correctly so: a verdict computed from ids
    that match nothing is a verdict about nothing. Here the id is being PRINTED. An id
    this program cannot place under the suite root is still the only name the reader has
    for a failing test, and losing the list to protect the attribution would be the exact
    trade this file exists to refuse.
    """
    parts = [part for part in classname.split(".") if part]
    for index, part in enumerate(parts):
        if (suite_root / f"{part}.py").is_file():
            trailing = [*parts[index + 1 :], name]
            return "::".join([f"{suite_root.as_posix()}/{part}.py", *trailing])
    classes: list[str] = []
    while parts and parts[-1][:1].isupper():
        classes.insert(0, parts.pop())
    if not parts:
        return "::".join([*classes, name]) if classes else name
    return "::".join(["/".join(parts) + ".py", *classes, name])


def read_inventory(path: pathlib.Path) -> dict[str, Any]:
    """The known-red inventory, reduced to what this block needs — never raising.

    W3 owns `qa/cluster-known-red.json` and is pruning it. Every read below is `.get()`
    with a default: a shape this program does not recognise must cost the reader the
    attribution, not the node-id list.
    """
    empty: dict[str, Any] = {"known": {}, "unstable": {}, "floor": {}, "note": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        empty["note"] = f"{path} is absent, so no failure below can be attributed from it."
        return empty
    except (json.JSONDecodeError, OSError) as exc:
        empty["note"] = (
            f"{path} could not be read ({plain(exc, limit=160)}); attribution is omitted."
        )
        return empty
    if not isinstance(data, dict):
        empty["note"] = f"{path} is not an object; attribution is omitted."
        return empty

    known: dict[str, dict[str, str]] = {}
    for group in data.get("groups", []) or []:
        if not isinstance(group, dict):
            continue
        entry = {
            "slug": str(group.get("slug", "(no slug)")),
            "owner": str(group.get("owner", UNATTRIBUTED)),
            "cause": str(group.get("cause", "")),
        }
        for nodeid in group.get("nodeids", []) or []:
            known[str(nodeid)] = entry

    unstable: dict[str, dict[str, Any]] = {}
    for item in data.get("unstable", []) or []:
        if isinstance(item, dict) and item.get("nodeid"):
            unstable[str(item["nodeid"])] = item

    floor = data.get("floor", {})
    return {
        "known": known,
        "unstable": unstable,
        "floor": floor if isinstance(floor, dict) else {},
        "note": "",
    }


# ── the block ─────────────────────────────────────────────────────────────────────────


def header(
    args: argparse.Namespace, counts: dict[str, Any] | None, why: str, inv: dict[str, Any]
) -> None:
    say(RULE)
    say("CLUSTER-TESTS — VERDICT. Everything a reader needs is between these two rules.")
    say(RULE)
    block("lane", args.lane)
    block(
        "pytest exit",
        f"{args.pytest_rc}  (0 = every test passed; 1 = tests failed; 2, 3 and 4 mean the "
        "run itself broke and the colours are not the suite's)",
    )
    if counts is None:
        block("counts", why)
    else:
        block(
            "counts",
            f"collected {counts['collected']} | executed {counts['executed']} | skipped "
            f"{counts['skipped']} | failed {counts['failed']} | errored {counts['errored']}",
        )
    floor = inv["floor"]
    if counts is not None and floor:
        report_floor(counts, floor, args.known)
    if inv["note"]:
        block("inventory", inv["note"])
    block(
        "engine output",
        "CockroachDB's own event log is in the collapsed `docker logs` group above and in "
        "the uploaded artefact. Nothing below this line is engine output.",
    )


def report_floor(counts: dict[str, Any], floor: dict[str, Any], known_path: pathlib.Path) -> None:
    """Say whether the floor and the ceiling were met, reading both rather than restating."""
    minimum, ceiling = floor.get("min_executed"), floor.get("max_skipped")
    parts: list[str] = []
    if isinstance(minimum, int):
        verdict = "MET" if counts["executed"] >= minimum else "BREACHED"
        parts.append(f"min_executed {minimum} -> {counts['executed']} executed ({verdict})")
    if isinstance(ceiling, int):
        verdict = "MET" if counts["skipped"] <= ceiling else "BREACHED"
        parts.append(f"max_skipped {ceiling} -> {counts['skipped']} skipped ({verdict})")
    if parts:
        block("floor/ceiling", f"{' | '.join(parts)}  [read from {known_path.as_posix()}]")


#: The heading a failure gets when nothing in the inventory names it. Read by
#: `print_failures` to decide which ids the remedy section is about, so the two cannot
#: drift apart the way a second literal would.
NEW_HEADING = "NEW — named by no entry in the inventory"


def classify(nodeid: str, inv: dict[str, Any]) -> tuple[str, str, str]:
    """One failing node id -> (heading, owner, cause). No id is left unbucketed."""
    recorded = inv["known"].get(nodeid)
    if recorded:
        return (f"known [{recorded['slug']}]", recorded["owner"], recorded["cause"])
    seen = inv["unstable"].get(nodeid)
    if seen is not None:
        heading = (
            f"declared unstable ({seen.get('runs_failed', '?')}/"
            f"{seen.get('runs_observed', '?')} runs observed)"
        )
        owner = (
            "the `unstable` list of qa/cluster-known-red.json — a category no ceiling "
            "polices. Ruling R3 orders it emptied; W3 owns that file."
        )
        return (heading, owner, str(seen.get("reason", "")))
    return (NEW_HEADING, UNATTRIBUTED, "")


def group_failures(
    bad: dict[str, str], inv: dict[str, Any]
) -> list[tuple[str, str, str, list[str]]]:
    """Every failing node id, in exactly one bucket, with the owner the inventory records."""
    buckets: dict[tuple[str, str, str], list[str]] = {}
    for nodeid in sorted(bad):
        buckets.setdefault(classify(nodeid, inv), []).append(nodeid)
    return [(heading, owner, cause, ids) for (heading, owner, cause), ids in buckets.items()]


def print_failures(counts: dict[str, Any], inv: dict[str, Any], lane_owner: str) -> list[str]:
    """The complete list, and the NEW ids the caller needs for the green/not-green section."""
    bad = counts["bad"]
    say(THIN)
    say(f"FAILING NODE IDS — all {len(bad)}, in full. No ellipsis and no cap.")
    say(THIN)
    if not bad:
        say("  none. The JUnit report records no failing or errored test case.")
        return []
    new: list[str] = []
    for heading, owner, cause, ids in group_failures(bad, inv):
        say(f"  {heading} — {len(ids)} id(s)")
        block("owner", owner, indent=14, margin=4)
        if cause:
            block("cause", cause, indent=14, margin=4)
        for nodeid in ids:
            say(f"      {bad[nodeid]:<8}{nodeid}")
        if heading == NEW_HEADING:
            new.extend(ids)
        say()
    if new:
        block(
            "attribute via",
            f"{lane_owner} — a NEW id is either a defect the inventory has never seen or a "
            "known one whose node id moved. Both are answered by naming the cause, never by "
            "filing the id.",
            indent=18,
        )
        say()
    return new


def print_remedy(counts: dict[str, Any] | None, inv: dict[str, Any], new: list[str]) -> None:
    """What turns this lane green, and what only appears to."""
    green: list[str] = []
    never: list[str] = [
        (
            "adding a failing id to qa/cluster-known-red.json to stop hearing about it — "
            "the inventory is a ceiling that must reach empty, not a suppression list"
        ),
        (
            "`-k`, `--deselect`, `xfail`, `continue-on-error` or `|| true` — each converts "
            "a visible defect back into an invisible one, which is the motion this lane "
            "exists to reverse"
        ),
        (
            "raising `floor.max_skipped` or lowering `floor.min_executed` — a skip is "
            "indistinguishable from a green tick on a dashboard, and the ceiling is the "
            "measurement this lane was built to keep honest, not a dial"
        ),
        (
            "deleting the verdict block, the digest, the artefact upload or the engine "
            "log — none of them decides anything, and removing a diagnosis leaves the red "
            "exactly where it was with nobody able to read it"
        ),
    ]
    if new:
        green.append(
            f"{len(new)} NEW failure(s): fix what each assertion names. The assertion text "
            "is in the `What failed, in the few lines a reader needs first` step above and "
            "in the uploaded `pytest-cluster.txt`."
        )
    if counts is not None:
        floor = inv["floor"]
        ceiling, minimum = floor.get("max_skipped"), floor.get("min_executed")
        if isinstance(ceiling, int) and counts["skipped"] > ceiling:
            green.append(
                f"{counts['skipped']} skipped against a ceiling of {ceiling}: give the "
                "skipped tests what they are missing — the deployed package is built by "
                "`./.github/actions/build-demo-package` in this job for exactly that reason."
            )
        if isinstance(minimum, int) and counts["executed"] < minimum:
            green.append(
                f"only {counts['executed']} executed against a floor of {minimum}: the "
                "suite did not reach the cluster this job started. Fix the reach."
            )
        fixed = sorted(set(inv["known"]) & counts["passed"])
        if fixed:
            green.append(
                f"{len(fixed)} inventoried id(s) PASSED this run — {', '.join(fixed)}. "
                "Delete them from qa/cluster-known-red.json in the commit that fixed "
                "them; that list is a ceiling which must reach empty, and a ceiling "
                "nobody is made to lower is a ceiling that never falls."
            )
    if not green:
        green.append(
            "nothing in this block: the run failed for a reason that is not a test outcome. "
            "Read the step that exited non-zero."
        )

    say(THIN)
    say("WHAT TURNS THIS LANE GREEN")
    for line in green:
        bullet(line)
    say()
    say("WHAT DOES NOT")
    for line in never:
        bullet(line)
    say(RULE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print one bounded, ANSI-free verdict block at the end of a failing lane."
    )
    parser.add_argument("--junit", type=pathlib.Path, required=True)
    parser.add_argument("--known", type=pathlib.Path, required=True)
    parser.add_argument("--suite-root", type=pathlib.Path, default=DEFAULT_SUITE_ROOT)
    parser.add_argument("--pytest-rc", type=int, default=0)
    parser.add_argument("--lane", default=DEFAULT_LANE)
    parser.add_argument(
        "--lane-owner",
        default="the CI-BOARD lead, docs/leads/ci-green-final.md",
        help="who attributes a failure the inventory does not name",
    )
    args = parser.parse_args(argv)
    # The block is UTF-8 by construction — it quotes node ids, causes and owners written
    # in this repository's prose. A runner whose stdout defaults to a legacy code page
    # must render a replacement character, not raise `UnicodeEncodeError` and take the
    # whole diagnosis with it.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    inv = read_inventory(args.known)
    say()
    counts, why = read_counts(args.junit, args.suite_root)
    header(args, counts, why, inv)
    new = print_failures(counts, inv, args.lane_owner) if counts is not None else []
    if counts is None:
        say(THIN)
        say("FAILING NODE IDS — cannot be listed: there is no report to list them from.")
        say(THIN)
        block(
            "what this means",
            "the run failed BEFORE pytest wrote its JUnit report, so the defect is in a "
            "step above the suite. Read the first step that exited non-zero; it carries "
            "its own error annotation and its own diagnosis.",
        )
        say()
    print_remedy(counts, inv, new)
    # ALWAYS 0. See the module docstring: the verdict is pytest's exit status and it is
    # carried by `--pytest-rc` into `cluster_lane_report.py`. This program is diagnosis.
    return 0


if __name__ == "__main__":
    sys.exit(main())
